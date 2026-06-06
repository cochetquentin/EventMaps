"""Scraper for Time Out Tokyo (https://www.timeout.com/tokyo).

Strategy:
- Listing pages are server-side rendered (SSR) with an initial batch of event links.
- Detail pages expose structured JSON-LD metadata (Event/TheaterEvent/MusicEvent/…).
- GPS coordinates are extracted from the ``data-zone-location-info`` JSON attribute
  found on ``div[data-component="maps"]`` elements when present.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup
from tenacity import (
    Retrying,
    before_log,
    retry_if_exception,
    stop_after_attempt,
    wait_exponential,
)

from models.attributes import TimeoutTokyoAttributes
from models.event import Event
from models.identity import make_event_id as _make_id
from scrapers.base import BaseScraper, ScrapeReport

logger = logging.getLogger(__name__)

BASE_URL = "https://www.timeout.com"
SOURCE = "tot"

_JST = timezone(timedelta(hours=9))

_MONTHS_EN = [
    "january",
    "february",
    "march",
    "april",
    "may",
    "june",
    "july",
    "august",
    "september",
    "october",
    "november",
    "december",
]

# JSON-LD @type values that represent events (schema.org Event subtypes)
_EVENT_LD_TYPES = frozenset(
    {
        "Event",
        "TheaterEvent",
        "MusicEvent",
        "ExhibitionEvent",
        "Festival",
        "SportsEvent",
        "ScreeningEvent",
        "DanceEvent",
        "FoodEvent",
        "SaleEvent",
        "ComedyEvent",
        "LiteraryEvent",
        "ChildrensEvent",
        "VisualArtsEvent",
        "BusinessEvent",
        "EducationEvent",
        "PublicationEvent",
    }
)

# Href prefixes to exclude from listing page link extraction
_EXCLUDE_HREF_PREFIXES = (
    "/tokyo/news/",
    "/tokyo/things-to-do/things-to-do-",
    "/tokyo/things-to-do/best-",
    "/tokyo/things-to-do/free-",
    "/tokyo/travel/",
)


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


_STATIC_LISTING_PATHS = [
    "/tokyo/things-to-do/things-to-do-this-week-in-tokyo",
    "/tokyo/things-to-do/things-to-do-in-tokyo-this-weekend",
]


def _listing_paths(max_pages: int = 4) -> list[str]:
    """Return up to *max_pages* listing page paths.

    The two static pages (this-week, this-weekend) are always included first,
    followed by dynamic monthly pages until the total reaches *max_pages*.
    ``max_pages=0`` returns an empty list; ``max_pages=1`` returns only the
    first static page.
    """
    paths = _STATIC_LISTING_PATHS[:max_pages]
    remaining = max_pages - len(paths)
    now = datetime.now(_JST)
    for i in range(remaining):
        month_idx = (now.month - 1 + i) % 12
        paths.append(f"/tokyo/things-to-do/{_MONTHS_EN[month_idx]}-events-in-tokyo")
    return paths


def _is_event_href(href: str) -> bool:
    """Return True if an href looks like a Time Out Tokyo event detail page."""
    if not href.startswith("/tokyo/"):
        return False
    # Must have at least 3 path segments: /tokyo/category/slug
    parts = href.strip("/").split("/")
    if len(parts) < 3:
        return False
    for prefix in _EXCLUDE_HREF_PREFIXES:
        if href.startswith(prefix):
            return False
    return True


def _format_price(price: float, currency: str = "JPY") -> str:
    """Format a numeric price into a human-readable string."""
    if price == 0:
        return "Free"
    if currency == "JPY":
        return f"¥{int(price):,}"
    return f"{price} {currency}"


def _parse_ld_json_blocks(soup: BeautifulSoup) -> list[dict]:
    """Parse all JSON-LD script blocks in the page and return them as dicts.

    Also exposes ``itemReviewed`` nested objects so that Time Out Tokyo's
    ``Review``-wrapped event data is surfaced alongside top-level entries.
    The expansion is applied to every collected dict (top-level, graph, and
    array members) so that Review entries inside @graph or JSON-LD arrays are
    also unwrapped.
    """
    raw: list = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
        if isinstance(data, list):
            raw.extend(data)
        elif isinstance(data, dict):
            raw.append(data)
            raw.extend(data.get("@graph", []))

    # Second pass: expand itemReviewed from every collected dict
    items: list = []
    for entry in raw:
        items.append(entry)
        if isinstance(entry, dict):
            item_reviewed = entry.get("itemReviewed")
            if isinstance(item_reviewed, dict):
                items.append(item_reviewed)
    return items


class TimeoutTokyo(BaseScraper):
    def __init__(self):
        from config import settings

        self._timeout = settings.scrape_request_timeout_seconds
        self._max_pages = settings.scrape_max_listing_pages_tot
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
                "Accept-Language": "en-US,en;q=0.9",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            }
        )

    def get_event_page(self, url: str) -> BeautifulSoup:
        """Download and parse a page."""
        response = self._retrying(_fetch, url, self.session, self._timeout)
        return BeautifulSoup(response.content, "html.parser")

    def _parse_zone_location(self, soup: BeautifulSoup) -> tuple[float | None, float | None]:
        """Extract GPS coordinates from the data-zone-location-info attribute.

        Returns (latitude, longitude) or (None, None) if not found.
        """
        div = soup.find("div", attrs={"data-component": "maps", "data-zone-location-info": True})
        if not div:
            return None, None
        try:
            data = json.loads(div["data-zone-location-info"])
            zones = data.get("zones") or []
            if zones:
                lat = float(zones[0]["latitude"])
                lng = float(zones[0]["longitude"])
                return lat, lng
        except (KeyError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return None, None

    def _parse_json_ld(self, soup: BeautifulSoup) -> dict | None:
        """Return the first Event-type JSON-LD object found in the page, or None."""
        for item in _parse_ld_json_blocks(soup):
            if not isinstance(item, dict):
                continue
            ld_type = item.get("@type")
            types = ld_type if isinstance(ld_type, list) else [ld_type]
            if any(t in _EVENT_LD_TYPES for t in types):
                return item
        return None

    def _is_news_article(self, soup: BeautifulSoup) -> bool:
        """Return True if the page has only article JSON-LD and no Event JSON-LD.

        A page with both Event and Article metadata is treated as an event page.
        """
        if self._parse_json_ld(soup) is not None:
            return False
        _ARTICLE_TYPES = {"NewsArticle", "Article", "BlogPosting"}
        for item in _parse_ld_json_blocks(soup):
            if isinstance(item, dict) and item.get("@type") in _ARTICLE_TYPES:
                return True
        return False

    def get_event_links(self, max_pages: int | None = None) -> list[str]:
        """Return de-duplicated event URLs extracted from listing pages."""
        if max_pages is None:
            max_pages = self._max_pages

        paths = _listing_paths(max_pages)
        seen: dict[str, str] = {}  # href → full URL, preserves insertion order

        for path in paths:
            url = BASE_URL + path
            try:
                response = self._retrying(_fetch, url, self.session, self._timeout)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    logger.debug("Listing page not found: %s", url)
                    continue
                raise

            soup = BeautifulSoup(response.content, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                # Strip query strings and fragments
                href = re.split(r"[?#]", href)[0]
                if _is_event_href(href) and href not in seen:
                    seen[href] = BASE_URL + href

        return list(seen.values())

    def scrape_event(self, url: str) -> dict:
        """Scrape all info from an event detail page."""
        soup = self.get_event_page(url)

        # Skip news articles and non-event pages
        if self._is_news_article(soup):
            raise ValueError(f"Page is a news article, not an event: {url}")

        ld = self._parse_json_ld(soup)
        latitude, longitude = self._parse_zone_location(soup)

        if ld is None:
            # HTML fallback: require a title, GPS coordinates, AND a parseable date.
            # Without all three the event cannot surface via the API (date filter)
            # or on the map (coords), and accepting any h1+coords would incorrectly
            # treat venue/restaurant pages as events.
            h1 = soup.find("h1")
            if not h1:
                raise ValueError(f"No JSON-LD event data and no <h1> found at: {url}")
            if latitude is None:
                raise ValueError(
                    f"No Event JSON-LD and no coordinates — page would be unreachable: {url}"
                )
            # Require at least one parseable date from <time datetime="…">
            fallback_date: str | None = None
            for time_el in soup.find_all("time", attrs={"datetime": True}):
                try:
                    dt = datetime.fromisoformat(time_el["datetime"])
                    if dt.tzinfo is not None:
                        dt = dt.astimezone(_JST)
                    fallback_date = dt.date().isoformat()
                    break
                except (ValueError, TypeError):
                    continue
            if fallback_date is None:
                raise ValueError(
                    f"No Event JSON-LD and no extractable date — likely a venue page: {url}"
                )
            return {
                "url": url,
                "title": h1.get_text(strip=True),
                "start_date": fallback_date,
                "end_date": None,
                "times": None,
                "price": None,
                "venue_name": None,
                "venue_address": None,
                "categories": [],
                "description": None,
                "image_url": None,
                "latitude": latitude,
                "longitude": longitude,
            }

        # ── Title ──────────────────────────────────────────────────────────────
        # Time Out Tokyo names follow the pattern "Event Name | Venue | Category in Tokyo"
        # Keep only the first segment (the actual event name).
        raw_name = ld.get("name", "").strip()
        title = raw_name.split("|")[0].strip() if raw_name else ""
        if not title:
            raise ValueError(f"No title in JSON-LD at: {url}")

        # ── Dates & time ───────────────────────────────────────────────────────
        start_date: str | None = None
        end_date: str | None = None
        times: str | None = None
        try:
            raw_start = ld.get("startDate")
            if raw_start:
                dt_start = datetime.fromisoformat(raw_start)
                # Normalise to JST so stored dates/times match the rest of the app
                if dt_start.tzinfo is not None:
                    dt_start = dt_start.astimezone(_JST)
                start_date = dt_start.date().isoformat()
                # Include time only if it's not midnight
                if dt_start.hour != 0 or dt_start.minute != 0:
                    times = dt_start.strftime("%H:%M")
        except (ValueError, TypeError):
            pass
        try:
            raw_end = ld.get("endDate")
            if raw_end:
                dt_end = datetime.fromisoformat(raw_end)
                if dt_end.tzinfo is not None:
                    dt_end = dt_end.astimezone(_JST)
                end_date = dt_end.date().isoformat()
                # Don't store same-day end as end_date (single-day event),
                # but append the end time to times so "19:30-22:00" is preserved.
                if end_date == start_date:
                    end_date = None
                    if times and (dt_end.hour != 0 or dt_end.minute != 0):
                        times = f"{times}-{dt_end.strftime('%H:%M')}"
        except (ValueError, TypeError):
            pass

        # ── Price ──────────────────────────────────────────────────────────────
        price: str | None = None
        try:
            offers = ld.get("offers", {})
            if isinstance(offers, list):
                offers = offers[0] if offers else {}
            price_val = offers.get("price") if isinstance(offers, dict) else None
            if price_val is None:
                price_val = ld.get("price")
            currency = (
                offers.get("priceCurrency") if isinstance(offers, dict) else None
            ) or ld.get("priceCurrency", "JPY")
            if price_val is not None:
                if isinstance(price_val, str) and price_val.strip().lower() == "free":
                    price = "Free"
                else:
                    price = _format_price(float(price_val), str(currency))
        except (ValueError, TypeError, AttributeError):
            pass

        # ── Location ───────────────────────────────────────────────────────────
        venue_name: str | None = None
        venue_address: str | None = None
        try:
            loc = ld.get("location", {})
            if isinstance(loc, dict):
                venue_name = loc.get("name") or None
                addr = loc.get("address", {})
                if isinstance(addr, dict):
                    parts = [
                        addr.get("streetAddress"),
                        addr.get("addressLocality"),
                        addr.get("addressRegion"),
                    ]
                    joined = ", ".join(p for p in parts if p)
                    venue_address = joined or None
                elif isinstance(addr, str) and addr:
                    venue_address = addr
        except (AttributeError, TypeError):
            pass

        # ── Categories ─────────────────────────────────────────────────────────
        categories: list[str] = []
        keywords = ld.get("keywords", "")
        if isinstance(keywords, str) and keywords:
            categories = [k.strip().lower() for k in keywords.split(",") if k.strip()]
        elif isinstance(keywords, list):
            categories = [str(k).strip().lower() for k in keywords if k]

        # ── Image ──────────────────────────────────────────────────────────────
        image_url: str | None = None
        img = ld.get("image")
        if isinstance(img, str):
            image_url = img
        elif isinstance(img, dict):
            image_url = img.get("url") or img.get("contentUrl") or None
        elif isinstance(img, list) and img:
            first = img[0]
            image_url = (
                first
                if isinstance(first, str)
                else (
                    first.get("url") or first.get("contentUrl") if isinstance(first, dict) else None
                )
            )

        # ── Description ────────────────────────────────────────────────────────
        description: str | None = ld.get("description") or None
        if not description:
            og = soup.find("meta", attrs={"property": "og:description"})
            if og and og.get("content"):
                description = og["content"].strip() or None

        return {
            "url": url,
            "title": title,
            "start_date": start_date,
            "end_date": end_date,
            "times": times,
            "price": price,
            "venue_name": venue_name,
            "venue_address": venue_address,
            "categories": categories,
            "description": description,
            "image_url": image_url,
            "latitude": latitude,
            "longitude": longitude,
        }

    def scrape_all(self, max_pages: int | None = None) -> tuple[list[dict], dict]:
        """Scrape all events. Ignores per-event errors (continues on exception).

        Returns:
            (raw_events, counts) where counts = {"links_seen": int, "events_ok": int, "errors": list}
        """
        urls = self.get_event_links(max_pages=max_pages)
        events = []
        errors = []
        for url in urls:
            try:
                events.append(self.scrape_event(url))
            except Exception as e:
                logger.warning("SKIP %s — %s", url, e)
                errors.append({"url": url, "reason": str(e)})
        counts = {"links_seen": len(urls), "events_ok": len(events), "errors": errors}
        return events, counts

    def scrape(self, max_pages: int | None = None) -> tuple[list[Event], ScrapeReport]:
        """Return canonical Event models with a scrape report.

        Note: Time Out Tokyo does not expose GPS coordinates in its HTML.
        All returned events have latitude=None and longitude=None.
        They appear in the list view but not on the map.
        """
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
            start_date = None
            end_date = None
            try:
                if e.get("start_date"):
                    start_date = datetime.strptime(e["start_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass
            try:
                if e.get("end_date"):
                    end_date = datetime.strptime(e["end_date"], "%Y-%m-%d").date()
            except (ValueError, TypeError):
                pass

            events.append(
                Event(
                    id=_make_id([e["url"]]),
                    source=SOURCE,
                    title=e.get("title", ""),
                    url=e["url"],
                    start_date=start_date,
                    end_date=end_date,
                    times=e.get("times") or None,
                    venue=e.get("venue_name") or None,
                    latitude=e.get("latitude"),
                    longitude=e.get("longitude"),
                    price=e.get("price") or None,
                    attributes=TimeoutTokyoAttributes(
                        categories=e.get("categories") or [],
                        venue_name=e.get("venue_name") or None,
                        venue_address=e.get("venue_address") or None,
                        image_url=e.get("image_url") or None,
                        description=e.get("description") or None,
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
