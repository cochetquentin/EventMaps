import html as _html
import json
import logging
import re
import requests
from bs4 import BeautifulSoup
import calendar
from datetime import date as _date, datetime, timezone

from tenacity import retry, stop_after_attempt, wait_exponential, before_log

from models.identity import make_event_id as _make_id
from models.event import Event
from scrapers.base import BaseScraper, ScrapeReport

logger = logging.getLogger(__name__)

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

_EXCLUDE_LINKS = {
    "/events/", "/events/this-week/", "/events/weekend/",
    "/events/this-month/", "/events/next-month/",
    "/events/this-week", "/events/this-month",
    *[f"/events/{m}" for m in _MONTHS],
}

BASE_URL = "https://tokyocheapo.com"

_MONTH_ABBREVS = {
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5, 'jun': 6,
    'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(min=2, max=10),
    before=before_log(logger, logging.WARNING),
)
def _fetch(url: str, session: requests.Session) -> requests.Response:
    response = session.get(url, timeout=10)
    response.raise_for_status()
    return response


def _parse_iso_date(s: str) -> _date | None:
    if not s:
        return None
    try:
        return _date.fromisoformat(s.replace("/", "-"))
    except (ValueError, AttributeError):
        return None


def _clean_whitespace(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip()


def _is_price_text(text: str) -> bool:
    t = text.strip()
    return bool(re.match(r'^(Free|¥|\$|€)', t, re.IGNORECASE)) \
        or bool(re.search(r'advance sales|at the door', t, re.IGNORECASE))


def _parse_12h_time(token: str) -> str:
    """'7:30pm' → '19:30'. Retourne le token original si non parseable."""
    m = re.match(r'^(\d{1,2}):(\d{2})\s*(am|pm)$', token.strip(), re.IGNORECASE)
    if not m:
        return token.strip()
    h, mn, period = int(m.group(1)), int(m.group(2)), m.group(3).lower()
    if period == 'pm' and h != 12:
        h += 12
    elif period == 'am' and h == 12:
        h = 0
    return f"{h:02d}:{mn:02d}"


def _split_time(time_str: str) -> tuple[str, str]:
    """'7:30pm – 10:00pm' → ('19:30', '22:00'). Retourne ('', '') si vide."""
    parts = re.split(r'\s*[–—\-]\s*', time_str.strip(), maxsplit=1)
    if len(parts) == 2:
        return _parse_12h_time(parts[0]), _parse_12h_time(parts[1])
    if parts[0]:
        return _parse_12h_time(parts[0]), ''
    return '', ''


def _parse_date_part(text: str, year: int) -> _date | None:
    """Parse 'May 15', 'Fri, May 15', 'Mar 27' → date object."""
    text = re.sub(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),?\s*', '', text, flags=re.IGNORECASE).strip()
    m = re.match(r'^([A-Za-z]{3,})\s+(\d{1,2})$', text)
    if m:
        month = _MONTH_ABBREVS.get(m.group(1)[:3].lower())
        if month:
            return _date(year, month, int(m.group(2)))
    return None


_FUZZY_PERIODS = {"early": (1, 10), "mid": (11, 20), "late": (21, None)}

_FUZZY_SINGLE_RE = re.compile(r'^(early|mid|late)\s+([a-z]+)$', re.IGNORECASE)
_FUZZY_SAME_MONTH_RE = re.compile(r'^(early|mid|late)\s*~\s*(early|mid|late)\s+([a-z]+)$', re.IGNORECASE)
_FUZZY_CROSS_MONTH_RE = re.compile(r'^(early|mid|late)\s+([a-z]+)\s*~\s*(early|mid|late)\s+([a-z]+)$', re.IGNORECASE)


def _fuzzy_start(period: str, month: int, year: int) -> _date:
    return _date(year, month, _FUZZY_PERIODS[period.lower()][0])


def _fuzzy_end(period: str, month: int, year: int) -> _date:
    day = _FUZZY_PERIODS[period.lower()][1] or calendar.monthrange(year, month)[1]
    return _date(year, month, day)


def _parse_fuzzy_date_range(date_str: str, year: int) -> tuple[str, str] | None:
    m = _FUZZY_SINGLE_RE.match(date_str)
    if m:
        period, mon = m.group(1), m.group(2)
        month = _MONTH_ABBREVS.get(mon[:3].lower())
        if month:
            return (
                _fuzzy_start(period, month, year).strftime('%Y/%m/%d'),
                _fuzzy_end(period, month, year).strftime('%Y/%m/%d'),
            )

    m = _FUZZY_SAME_MONTH_RE.match(date_str)
    if m:
        p1, p2, mon = m.group(1), m.group(2), m.group(3)
        month = _MONTH_ABBREVS.get(mon[:3].lower())
        if month:
            return (
                _fuzzy_start(p1, month, year).strftime('%Y/%m/%d'),
                _fuzzy_end(p2, month, year).strftime('%Y/%m/%d'),
            )

    m = _FUZZY_CROSS_MONTH_RE.match(date_str)
    if m:
        p1, mon1, p2, mon2 = m.group(1), m.group(2), m.group(3), m.group(4)
        month1 = _MONTH_ABBREVS.get(mon1[:3].lower())
        month2 = _MONTH_ABBREVS.get(mon2[:3].lower())
        if month1 and month2:
            return (
                _fuzzy_start(p1, month1, year).strftime('%Y/%m/%d'),
                _fuzzy_end(p2, month2, year).strftime('%Y/%m/%d'),
            )

    return None


def _parse_date_range(date_str: str, year: int | None = None) -> tuple[str, str]:
    """
    Retourne (start_date, end_date) en format YYYY/MM/DD.
    - Date unique → (date, "")
    - Plage → (start, end) normalisés
    - Dates fuzzy ('Mid May') → (date_str, "")
    """
    if year is None:
        year = _date.today().year

    range_m = re.match(r'^(.+?)\s+-\s+(.+)$', date_str.strip())
    if range_m:
        start = _parse_date_part(range_m.group(1).strip(), year)
        end = _parse_date_part(range_m.group(2).strip(), year)
        if start and end:
            return start.strftime('%Y/%m/%d'), end.strftime('%Y/%m/%d')
        return date_str, ""

    single = _parse_date_part(date_str.strip(), year)
    if single:
        d = single.strftime('%Y/%m/%d')
        return d, d

    fuzzy = _parse_fuzzy_date_range(date_str.strip(), year)
    if fuzzy:
        return fuzzy
    return date_str, ""


class TokyoCheapo(BaseScraper):
    def __init__(self):
        from config import settings
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)
        self.session.headers["User-Agent"] = settings.scrape_user_agent

    def get_event_links(self, max_pages: int = 10) -> list[str]:
        """Retourne les URLs de tous les événements de la semaine."""
        links = []
        for i in range(1, max_pages + 1):
            url = f"{BASE_URL}/events/this-week/page/{i}/"
            try:
                response = _fetch(url, self.session)
            except requests.HTTPError as e:
                if e.response is not None and e.response.status_code == 404:
                    break
                raise

            soup = BeautifulSoup(response.content, "html.parser")
            page_links = {
                href for a in soup.find_all("a")
                if (href := a.get("href"))
                and href.startswith("/events/")
                and href not in _EXCLUDE_LINKS
                and href != f"/events/this-week/page/{i}/"
            }

            if page_links:
                links += [BASE_URL + href for href in page_links]
            else:
                break

        return links

    def get_event_page(self, url: str) -> BeautifulSoup:
        """Télécharge et parse une page événement."""
        response = _fetch(url, self.session)
        return BeautifulSoup(response.content, "html.parser")

    def parse_title(self, soup: BeautifulSoup) -> str:
        header = soup.find_all("header")[-1]
        return header.find("h1").text

    def parse_date(self, soup: BeautifulSoup) -> str:
        header = soup.find_all("header")[-1]
        dates = header.find_all("div", class_="date")
        if len(dates) > 1:
            return " - ".join(d.get_text(" ", strip=True) for d in dates)
        day_divs = header.find_all("div", class_="day")
        if not day_divs:
            return dates[0].get_text(" ", strip=True) if dates else ""
        return f"{day_divs[0].text} {dates[0].text}"

    def parse_time_and_price(self, soup: BeautifulSoup) -> tuple[str, str | None]:
        header = soup.find_all("header")[-1]
        attrs = header.find_all("div", class_="event__attribute")
        if not attrs:
            return "", None
        first = _clean_whitespace(attrs[0].text)
        second = _clean_whitespace(attrs[1].text) if len(attrs) > 1 else None
        if _is_price_text(first) and second is None:
            return "", first
        return first, second

    def parse_description(self, soup: BeautifulSoup) -> str:
        div = soup.find("div", class_="entry-content__text")
        return div.text.strip() if div else ""

    def parse_categories(self, soup: BeautifulSoup) -> list[str]:
        article = soup.find("article")
        if not article:
            return []
        return [
            re.sub(r"-\d+$", "", c.removeprefix("event-category-"))
            for c in article.get("class", [])
            if c.startswith("event-category-")
        ]

    def parse_tags(self, soup: BeautifulSoup) -> list[str]:
        article = soup.find("article")
        if not article:
            return []
        return [
            re.sub(r"-\d+$", "", c.removeprefix("event-tag-"))
            for c in article.get("class", [])
            if c.startswith("event-tag-")
        ]

    def parse_official_link(self, soup: BeautifulSoup) -> str | None:
        infos = soup.find("div", class_="section--info-box--event__content")
        if not infos:
            return None
        all_divs = infos.find_all("div")
        for i, div in enumerate(all_divs):
            if div.get_text(strip=True).startswith("External link"):
                a = div.find("a") or (all_divs[i + 1].find("a") if i + 1 < len(all_divs) else None)
                return a["href"] if a else None
        return None

    def parse_locations(self, soup: BeautifulSoup) -> list[dict]:
        """Retourne la liste des lieux avec lat/lng depuis le JSON Apple Maps."""
        map_div = soup.find("div", {"async-component": "1", "component-name": "apple-maps"})
        if not map_div:
            return []

        json_script = map_div.find("script", {"type": "application/json"})
        if not json_script:
            return []

        data = json.loads(json_script.string)

        locations = data.get("locations", [])
        if locations:
            return [
                {
                    "name": _html.unescape(loc[0]),
                    "lat": float(loc[1]),
                    "lng": float(loc[2]),
                    "address": loc[3] if len(loc) > 3 else "",
                }
                for loc in locations
            ]

        return [
            {
                "name": _html.unescape(data.get("title", "")),
                "lat": float(data["lat"]),
                "lng": float(data["lng"]),
                "address": data.get("addr") or data.get("dispaddr", ""),
            }
        ]

    def scrape_event(self, url: str) -> dict:
        """Scrape toutes les infos d'un événement depuis son URL."""
        soup = self.get_event_page(url)
        time_raw, price = self.parse_time_and_price(soup)
        start_time, end_time = _split_time(time_raw) if time_raw else ('', '')
        date_raw = self.parse_date(soup)
        start_date, end_date = _parse_date_range(date_raw)
        return {
            "url": url,
            "title": self.parse_title(soup),
            "start_date": start_date,
            "end_date": end_date,
            "start_time": start_time,
            "end_time": end_time,
            "price": price,
            "description": self.parse_description(soup),
            "categories": self.parse_categories(soup),
            "tags": self.parse_tags(soup),
            "official_link": self.parse_official_link(soup),
            "locations": self.parse_locations(soup),
        }

    def scrape_all(self, max_pages: int = 10) -> tuple[list[dict], dict]:
        """Scrape tous les événements de la semaine. Ignore les erreurs par événement.

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

    def scrape(self, max_pages: int = 10) -> tuple[list[Event], ScrapeReport]:
        """Retourne les événements sous forme de modèles canoniques Event avec un rapport."""
        now = datetime.now(timezone.utc)
        raw_events, counts = self.scrape_all(max_pages=max_pages)
        report = ScrapeReport(
            source="tc",
            links_seen=counts["links_seen"],
            events_ok=counts["events_ok"],
            errors=counts["errors"],
        )
        events: list[Event] = []
        for e in raw_events:
            locations = e.get("locations") or [{"name": "", "lat": None, "lng": None}]
            for loc in locations:
                start_time = e.get("start_time") or ""
                end_time = e.get("end_time") or ""
                times = None
                if start_time and end_time:
                    times = f"{start_time}-{end_time}"
                elif start_time:
                    times = start_time
                location_name = loc.get("name") or ""
                events.append(Event(
                    id=_make_id([e["url"], location_name]),
                    source="tc",
                    title=e.get("title", ""),
                    url=e["url"],
                    start_date=_parse_iso_date(e.get("start_date", "")),
                    end_date=_parse_iso_date(e.get("end_date", "")),
                    times=times,
                    venue=None,
                    latitude=loc.get("lat"),
                    longitude=loc.get("lng"),
                    price=e.get("price") or None,
                    attributes={
                        "categories": e.get("categories") or [],
                        "tags": e.get("tags") or [],
                        "official_link": e.get("official_link") or None,
                        "location_name": location_name or None,
                    },
                    created_at=now,
                ))
        if not events:
            logger.critical(
                "Scraper %s returned 0 events — likely a parser failure (HTML structure changed?)",
                self.__class__.__name__,
            )
        return events, report
