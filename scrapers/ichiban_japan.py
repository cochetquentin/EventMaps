"""Scraper for Ichiban Japan (https://ichiban-japan.com).

French WordPress/Gutenberg site listing Japanese events (festivals, exhibitions,
flea markets). Two levels, structurally different from the other sources:

- Category listing pages (``/category/japon/evenements-japon/page/N/``) only yield
  ARTICLE urls, taken from ``li.post-card`` cards.
- Each ARTICLE page aggregates MANY events, one per ``h2.wp-block-heading``. Events
  are grouped by heading and recognised by an info paragraph containing ``Lieu :``.
  The last ``<a>`` of that paragraph is the official site; the first is the venue,
  whose Google Maps link carries the coordinates.

GPS coordinates are parsed from the venue's Google Maps link (``!3d!4d`` or
``@lat,lng``); ``maps.app.goo.gl`` short links are resolved via a throttled redirect
follow. See docs/guide-scraping-ichiban-japan.md for the full structural analysis.
"""

from __future__ import annotations

import json
import logging
import re
import time
import unicodedata
from datetime import UTC, datetime, timedelta, timezone
from datetime import date as _date

import requests
from bs4 import BeautifulSoup, NavigableString, Tag
from tenacity import (
    Retrying,
    before_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from models.attributes import IchibanJapanAttributes
from models.event import Event
from models.identity import make_event_id
from scrapers.base import BaseScraper, ScrapeReport

logger = logging.getLogger(__name__)

BASE_URL = "https://ichiban-japan.com"
CATEGORY_PATH = "/category/japon/evenements-japon/"
SOURCE = "ij"
THROTTLE_S = 1.0  # politeness delay between network requests (guide §6.9)

_JST = timezone(timedelta(hours=9))

# French month names, accent-stripped (WordPress and our matching both drop accents).
_FR_MONTHS = {
    "janvier": 1,
    "fevrier": 2,
    "mars": 3,
    "avril": 4,
    "mai": 5,
    "juin": 6,
    "juillet": 7,
    "aout": 8,
    "septembre": 9,
    "octobre": 10,
    "novembre": 11,
    "decembre": 12,
}
_MONTHS_ALT = "|".join(_FR_MONTHS)
_DAY = r"(\d{1,2})(?:er)?"  # "1er", "5", "23"

_LIEU_RE = re.compile(r"Lieux?\s*:")
_COORD_3D4D_RE = re.compile(r"!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)")  # precise place (preferred)
_COORD_AT_RE = re.compile(r"@(-?\d+\.\d+),(-?\d+\.\d+)")  # map centre (fallback)
_YEAR_RE = re.compile(r"(20\d{2})")

# Date shapes, tried in this order (most specific first).
# Ranges tolerate an optional 4-digit year after each month ("du 30 decembre 2025
# au 2 janvier 2026"), otherwise the trailing "2025" leaks into the two-day pattern.
_YEAR_TOKEN = r"(?:\s+(20\d{2}))?"
_JUSQU_RE = re.compile(rf"jusqu.au\s+{_DAY}\s+({_MONTHS_ALT})")
_RANGE_RE = re.compile(
    rf"du\s+{_DAY}\s+(?:({_MONTHS_ALT}){_YEAR_TOKEN}\s+)?au\s+{_DAY}\s+({_MONTHS_ALT}){_YEAR_TOKEN}"
)
_TWO_DAY_RE = re.compile(rf"{_DAY}\s*(?:et|au|[-–—])\s*{_DAY}\s+({_MONTHS_ALT})")
_SINGLE_RE = re.compile(rf"{_DAY}\s+({_MONTHS_ALT})")


# ── Pure helpers (no I/O) ─────────────────────────────────────────────────────


def _strip_accents(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


def _clean(text: str | None) -> str:
    """Collapse whitespace (incl. non-breaking spaces) and strip."""
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("\xa0", " ")).strip()


def _has_lieu(text: str) -> bool:
    return bool(_LIEU_RE.search((text or "").replace("\xa0", " ")))


def _strip_parenthetical(text: str) -> str:
    """'Sanja Matsuri (15-17 mai 2026)' → 'Sanja Matsuri'."""
    return re.sub(r"\s*\([^)]*\)\s*$", "", text).strip()


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", _strip_accents(text).lower()).strip("-")
    return slug


def _strip_credit(caption: str) -> str:
    """Drop a trailing photo credit ('… © Author')."""
    return re.sub(r"\s*©.*$", "", caption).strip()


def _mk_date(day: int, month_name: str, year: int) -> _date | None:
    month = _FR_MONTHS.get(month_name)
    if month is None:
        return None
    try:
        return _date(year, month, day)
    except ValueError:
        return None


def _parse_fr_dates(text: str, fallback_year: int) -> tuple[_date | None, _date | None]:
    """Parse a French free-text date into ``(start, end)`` date objects.

    Handles the shapes seen on Ichiban:
      - single day .......... "1er mai 2026", "5 mai 2026"      → (d, None)
      - two days ............ "2-3 mai 2026", "2 et 3 mai 2026" → (d1, d2)
      - range same month .... "Du 3 au 5 mai 2026"             → (d1, d2)
      - range cross month ... "Du 25 mai au 14 juin 2026"      → (d1, d2)
      - end only ............ "jusqu'au 6 mai 2026"            → (None, d)

    ``end`` is None for a single day. Year is read from the text, else *fallback_year*.
    """
    if not text:
        return (None, None)
    t = _strip_accents(text.lower())
    ym = _YEAR_RE.search(t)
    year = int(ym.group(1)) if ym else fallback_year

    m = _JUSQU_RE.search(t)
    if m:
        return (None, _mk_date(int(m.group(1)), m.group(2), year))

    m = _RANGE_RE.search(t)
    if m:
        day_start, month1, year1, day_end, month2, year2 = m.groups()
        month_start = month1 or month2  # "du 3 au 5 mai" → start month omitted
        year_end = int(year2) if year2 else year
        year_start = int(year1) if year1 else year_end
        start = _mk_date(int(day_start), month_start, year_start)
        end = _mk_date(int(day_end), month2, year_end)
        # Cross-year when the start has no explicit year ("du 30 decembre au 2 janvier
        # 2026"): the start month rolled over from the previous year → bump it back.
        # Skipped when the start year was written explicitly.
        if start and end and end < start and not year1:
            start = start.replace(year=start.year - 1)
        return (start, end)

    m = _TWO_DAY_RE.search(t)
    if m:
        month = m.group(3)
        return (_mk_date(int(m.group(1)), month, year), _mk_date(int(m.group(2)), month, year))

    m = _SINGLE_RE.search(t)
    if m:
        return (_mk_date(int(m.group(1)), m.group(2), year), None)

    return (None, None)


def _coords_from_url_string(url: str) -> tuple[float, float] | None:
    """Extract (lat, lng) from a full Google Maps URL, or None."""
    m = _COORD_3D4D_RE.search(url) or _COORD_AT_RE.search(url)
    if m:
        return (float(m.group(1)), float(m.group(2)))
    return None


def _br_lines(paragraph: Tag) -> list[str]:
    """Return the paragraph's text split on ``<br>`` (including ``<br>`` nested in
    ``<strong>``), one cleaned line per entry, empties removed."""
    frag = BeautifulSoup(str(paragraph), "html.parser")
    for br in frag.find_all("br"):
        br.replace_with("\n")
    return [ln for ln in (_clean(part) for part in frag.get_text().split("\n")) if ln]


def _dates_from_lines(lines: list[str], name: str) -> str:
    """The date text sits between the name and the ``Lieu :`` line."""
    lieu_idx = next((i for i, ln in enumerate(lines) if _has_lieu(ln)), None)
    candidate = lines[:lieu_idx] if lieu_idx is not None else lines[1:]
    clean_name = _clean(name)
    out = [ln for ln in candidate if _clean(ln) != clean_name and not _has_lieu(ln)]
    return " ".join(out).strip()


def _is_retryable(exc: BaseException) -> bool:
    """Retry transient errors (5xx, 429) but not definitive client errors (4xx)."""
    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        status = exc.response.status_code
        return status == 429 or status >= 500
    return True


def _fetch(url: str, session: requests.Session, timeout: int = 10) -> requests.Response:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return response


# ── Scraper ───────────────────────────────────────────────────────────────────


class IchibanJapan(BaseScraper):
    def __init__(self):
        from config import settings

        self._timeout = settings.scrape_request_timeout_seconds
        self._max_pages = settings.scrape_max_pages_ij
        self._throttle_s = THROTTLE_S
        self._today = datetime.now(_JST).date()
        self._short_cache: dict[str, str | None] = {}
        self._retrying = Retrying(
            stop=stop_after_attempt(settings.scrape_retry_attempts),
            wait=wait_exponential(
                min=settings.scrape_retry_wait_min,
                max=settings.scrape_retry_wait_max,
            ),
            retry=retry_if_exception(_is_retryable),
            before=before_log(logger, logging.WARNING),
            reraise=True,
        )
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": settings.scrape_user_agent,
                "Accept-Language": "fr-FR,fr;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    # ── Network ────────────────────────────────────────────────────────────────

    def get_page(self, url: str) -> BeautifulSoup:
        response = self._retrying(_fetch, url, self.session, self._timeout)
        return BeautifulSoup(response.content, "html.parser")

    def _throttle(self) -> None:
        if self._throttle_s > 0:
            time.sleep(self._throttle_s)

    def _resolve_short(self, href: str) -> str | None:
        """Follow a maps.app.goo.gl short link to its final Google Maps URL.

        Cached per run; returns None on any network failure. Uses a streamed GET so
        only the redirect chain is read, not the (heavy) maps page body.
        """
        if href in self._short_cache:
            return self._short_cache[href]
        resolved: str | None = None
        try:
            self._throttle()
            response = self.session.get(
                href, timeout=self._timeout, allow_redirects=True, stream=True
            )
            resolved = response.url
            response.close()
        except requests.RequestException as exc:
            logger.debug("short-link resolve failed for %s — %s", href, exc)
        self._short_cache[href] = resolved
        return resolved

    def _coords_from_maps_url(self, href: str | None) -> tuple[float | None, float | None]:
        if not href:
            return (None, None)
        coords = _coords_from_url_string(href)
        if coords is None and ("maps.app.goo.gl" in href or "goo.gl/maps" in href):
            resolved = self._resolve_short(href)
            if resolved:
                coords = _coords_from_url_string(resolved)
        return coords if coords else (None, None)

    # ── Level 1: article discovery ──────────────────────────────────────────────

    def get_article_links(self, max_pages: int | None = None) -> list[str]:
        """Return de-duplicated article URLs from the paginated category listing."""
        if max_pages is None:
            max_pages = self._max_pages
        seen: dict[str, str] = {}
        for i in range(1, max_pages + 1):
            path = CATEGORY_PATH if i == 1 else f"{CATEGORY_PATH}page/{i}/"
            url = BASE_URL + path
            try:
                soup = self.get_page(url)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    break
                raise
            hrefs = [
                href
                for card in soup.find_all("li", class_="post-card")
                for a in card.find_all("a", class_="post-title-link")
                if (href := a.get("href"))
            ]
            if not hrefs:
                break
            for href in hrefs:
                full = href if href.startswith("http") else BASE_URL + href
                seen.setdefault(full, full)
            self._throttle()
        return list(seen.values())

    # ── Level 2: article → events ───────────────────────────────────────────────

    def _og(self, soup: BeautifulSoup, prop: str) -> str | None:
        tag = soup.find("meta", attrs={"property": prop})
        if tag and tag.get("content"):
            return tag["content"].strip() or None
        return None

    def _article_ld(self, soup: BeautifulSoup) -> dict:
        """Return the first JSON-LD ``Article`` object, or {}."""
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string or "")
            except (json.JSONDecodeError, TypeError):
                continue
            candidates = data if isinstance(data, list) else [data]
            for entry in list(candidates):
                if isinstance(entry, dict) and isinstance(entry.get("@graph"), list):
                    candidates = candidates + entry["@graph"]
            for entry in candidates:
                if not isinstance(entry, dict):
                    continue
                ld_type = entry.get("@type")
                types = ld_type if isinstance(ld_type, list) else [ld_type]
                if "Article" in types:
                    return entry
        return {}

    def _article_meta(self, soup: BeautifulSoup, url: str) -> dict:
        ld = self._article_ld(soup)
        image = ld.get("image")
        if isinstance(image, dict):
            image = image.get("url")
        elif not isinstance(image, str):
            image = None
        image = image or self._og(soup, "og:image")
        published = ld.get("datePublished")
        year = None
        if isinstance(published, str) and len(published) >= 4 and published[:4].isdigit():
            year = int(published[:4])
        author = ld.get("author")
        if isinstance(author, dict):
            author = author.get("name")
        elif not isinstance(author, str):
            author = None
        slug = _strip_accents(url.lower())
        zone = "Tohoku" if "tohoku" in slug else "Tokyo" if "tokyo" in slug else None
        return {
            "article_url": url,
            "article_title": ld.get("headline") or self._og(soup, "og:title") or "",
            "article_image": image,
            "published": published if isinstance(published, str) else None,
            "year": year,
            "author": author,
            "zone": zone,
        }

    def _iter_event_groups(self, content: Tag) -> list[dict]:
        """Group direct children of .entry-content by ``h2.wp-block-heading``.

        Each h2 opens a new group; following siblings are attached until the next h2.
        Content before the first h2 (breadcrumbs, header image, intro) is ignored.
        """
        groups: list[dict] = []
        current: dict | None = None
        for child in content.children:
            if not isinstance(child, Tag):
                continue
            if child.name == "h2" and "wp-block-heading" in child.get("class", []):
                current = {"h2": child, "els": []}
                groups.append(current)
            elif current is not None:
                current["els"].append(child)
        return groups

    def _parse_event_group(self, group: dict, meta: dict) -> dict | None:
        """Turn one h2-group into an event dict, or None if it is not an event
        (no ``Lieu :`` info paragraph → intro/conclusion/sidebar heading)."""
        h2: Tag = group["h2"]
        els: list[Tag] = group["els"]

        info_p = next(
            (el for el in els if el.name == "p" and _has_lieu(el.get_text())),
            None,
        )
        if info_p is None:
            return None

        h2_text = _clean(h2.get_text())
        strong = info_p.find("strong")
        strong_text = _clean(strong.get_text()) if strong else ""
        name = strong_text or _strip_parenthetical(h2_text)

        links = info_p.find_all("a")
        venue_a = links[0] if links else None
        venue_name = _clean(venue_a.get_text()) if venue_a else None
        venue_maps_url = venue_a.get("href") if venue_a else None

        neighbourhood = None
        if venue_a is not None:
            sib = venue_a.next_sibling
            while isinstance(sib, NavigableString) and not sib.strip():
                sib = sib.next_sibling
            if isinstance(sib, NavigableString):
                pm = re.search(r"\(([^)]+)\)", str(sib))
                if pm:
                    neighbourhood = _clean(pm.group(1))

        official_link = None
        if links and links[-1] is not venue_a:
            official_link = links[-1].get("href")

        dates_text = _dates_from_lines(_br_lines(info_p), name)
        if not dates_text:
            hm = re.search(r"\(([^)]*)\)\s*$", h2_text)
            dates_text = hm.group(1) if hm else ""
        start_date, end_date = _parse_fr_dates(dates_text, meta.get("year") or self._today.year)

        latitude, longitude = self._coords_from_maps_url(venue_maps_url)

        descriptions = [
            txt
            for el in els
            if el is not info_p
            and el.name == "p"
            and "wp-block-paragraph" in el.get("class", [])
            and (txt := _clean(el.get_text()))
            and not _has_lieu(txt)
        ]
        description = "\n\n".join(descriptions) or None

        image_url = image_caption = None
        figure = next(
            (el for el in els if el.name == "figure" and "wp-block-image" in el.get("class", [])),
            None,
        )
        if figure is not None:
            img = figure.find("img")
            if img is not None:
                image_url = img.get("src")
            caption = figure.find("figcaption")
            if caption is not None:
                image_caption = _strip_credit(_clean(caption.get_text())) or None

        anchor = _slugify(name)
        event_url = f"{meta['article_url']}#{anchor}" if anchor else meta["article_url"]

        return {
            "url": event_url,
            "name": name,
            "dates_text": dates_text,
            "start_date": start_date,
            "end_date": end_date,
            "venue_name": venue_name,
            "neighbourhood": neighbourhood,
            "official_link": official_link,
            "description": description,
            "image_url": image_url,
            "image_caption": image_caption,
            "latitude": latitude,
            "longitude": longitude,
            "zone": meta.get("zone"),
            "article_url": meta["article_url"],
            "article_title": meta.get("article_title"),
        }

    def scrape_article(self, url: str) -> list[dict]:
        """Scrape all events from a single article page."""
        soup = self.get_page(url)
        content = soup.find("div", class_="entry-content")
        if content is None:
            raise ValueError(f"No .entry-content found at {url}")
        meta = self._article_meta(soup, url)
        events = []
        for group in self._iter_event_groups(content):
            event = self._parse_event_group(group, meta)
            if event is not None:
                events.append(event)
        return events

    def scrape_all(self, max_pages: int | None = None) -> tuple[list[dict], dict]:
        """Scrape every article. Per-article errors are collected, not raised.

        Returns:
            (raw_events, counts) with counts = {"links_seen", "events_ok", "errors"};
            ``links_seen`` counts ARTICLES (each yields many events).
        """
        urls = self.get_article_links(max_pages=max_pages)
        events: list[dict] = []
        errors: list[dict] = []
        for url in urls:
            try:
                article_events = self.scrape_article(url)
            except Exception as exc:  # noqa: BLE001 — isolate one bad article
                logger.warning("SKIP %s — %s", url, exc)
                errors.append({"url": url, "reason": str(exc)})
            else:
                if article_events:
                    events.extend(article_events)
                else:
                    errors.append({"url": url, "reason": "no events parsed"})
            self._throttle()
        counts = {"links_seen": len(urls), "events_ok": len(events), "errors": errors}
        return events, counts

    def scrape(self, max_pages: int | None = None) -> tuple[list[Event], ScrapeReport]:
        """Return canonical Event models with a scrape report."""
        now = datetime.now(UTC)
        raw_events, counts = self.scrape_all(max_pages=max_pages)
        report = ScrapeReport(
            source=SOURCE,
            links_seen=counts["links_seen"],
            events_ok=counts["events_ok"],
            errors=counts["errors"],
        )

        events: list[Event] = []
        for e in raw_events:
            start_date = e["start_date"]
            end_date = e["end_date"]
            # "jusqu'au X" has no start → anchor it on the end date so it stays
            # dedupable and displayable.
            if start_date is None:
                start_date = end_date
            # Single-day events keep end_date=None (matches the other scrapers).
            if end_date is not None and end_date == start_date:
                end_date = None

            events.append(
                Event(
                    id=make_event_id([e["url"]]),
                    source=SOURCE,
                    title=e["name"] or "",
                    url=e["url"],
                    start_date=start_date,
                    end_date=end_date,
                    times=None,
                    venue=e.get("venue_name") or None,
                    latitude=e.get("latitude"),
                    longitude=e.get("longitude"),
                    price=None,
                    attributes=IchibanJapanAttributes(
                        description=e.get("description"),
                        official_link=e.get("official_link"),
                        neighbourhood=e.get("neighbourhood"),
                        venue_name=e.get("venue_name"),
                        zone=e.get("zone"),
                        image_url=e.get("image_url"),
                        image_caption=e.get("image_caption"),
                        dates_text=e.get("dates_text") or None,
                        article_url=e.get("article_url"),
                        article_title=e.get("article_title"),
                    ),
                    created_at=now,
                )
            )

        if not events:
            logger.critical(
                "Scraper %s returned 0 events — likely a parser failure (HTML structure changed?)",
                self.__class__.__name__,
            )
        return events, report
