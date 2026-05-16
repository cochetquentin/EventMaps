import re
from datetime import date as Date, timedelta
import requests
from bs4 import BeautifulSoup

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Pour ces champs, on extrait le href de l'<a> plutôt que le texte
_LINK_FIELDS = {"official_site", "official_x"}

_FIELD_MAP = {
    "大会名": "title",
    "開催期間": "date",
    "開催時間": "time",
    "打ち上げ数": "fireworks_count",
    "打ち上げ時間": "fireworks_duration",
    "例年の人出": "expected_crowd",
    "荒天の場合": "rain_policy",
    "有料席": "paid_seating",
    "屋台など": "food_stalls",
    "その他・全体備考": "notes",
    "会場": "venue",
    "会場アクセス": "access",
    "駐車場": "parking",
    "問い合わせ": "contact",
    "問い合わせ２": "contact2",
    "公式サイト": "official_site",
    "公式X": "official_x",
}

BASE_URL = "https://hanabi.walkerplus.com"

_FULL_DATE_RE = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
_MONTH_DAY_RE = re.compile(r"(\d{1,2})月(\d{1,2})日")
_DAY_WEEKDAY_RE = re.compile(r"(?<!\d)(\d{1,2})日[（(][月火水木金土日祝][）)]")
_RANGE_RE = re.compile(r"(\d{1,2})日[（(][月火水木金土日祝][）)]～(\d{1,2})日")
_TIME_RANGE_RE = re.compile(r"\d{1,2}:\d{2}[～〜]\d{1,2}:\d{2}")
_TIME_START_RE = re.compile(r"\d{1,2}:\d{2}[～〜]")


def _extract_time(text: str) -> tuple[str | None, str | None]:
    """Retourne (start_time, end_time) extraits du texte, ou None si absent."""
    m = _TIME_RANGE_RE.search(text)
    if m:
        start, end = re.split(r"[～〜]", m.group(0))
        return start, end
    m = _TIME_START_RE.search(text)
    if m:
        start = m.group(0).rstrip("～〜")
        return start, None
    return None, None


def _extract_dates(raw: str) -> list[str]:
    """
    Retourne la liste de toutes les dates YYYY/MM/DD trouvées dans le texte.
    Gère les listes (・/、) et les plages (～). Fallback sur la première date
    pour les formats complexes avec /.
    """
    text = raw.replace("〜", "～")

    # Formats non-japonais trop complexes (ex: '2026/7/20・26～31')
    if re.search(r"年\d{1,2}/|\d{4}/\d{1,2}[・～]", text):
        m = _FULL_DATE_RE.search(text)
        return [f"{m.group(1)}/{int(m.group(2)):02d}/{int(m.group(3)):02d}"] if m else [raw]

    first = _FULL_DATE_RE.search(text)
    if not first:
        return [raw]

    year = int(first.group(1))
    collected: set[Date] = set()

    # 1. Plages explicites : DD日(X)～DD日
    for m in _RANGE_RE.finditer(text):
        prefix = text[: m.start()]
        months_found = re.findall(r"(\d{1,2})月", prefix)
        month = int(months_found[-1]) if months_found else int(first.group(2))
        d = Date(year, month, int(m.group(1)))
        end = Date(year, month, int(m.group(2)))
        while d <= end:
            collected.add(d)
            d += timedelta(days=1)

    # 2. Toutes les références MM月DD日
    for m in _MONTH_DAY_RE.finditer(text):
        collected.add(Date(year, int(m.group(1)), int(m.group(2))))

    # 3. DD日(weekday) standalone avec contexte du dernier mois vu
    ctx_month = int(first.group(2))
    for m in _DAY_WEEKDAY_RE.finditer(text):
        prefix = text[: m.start()]
        months_found = re.findall(r"(\d{1,2})月", prefix)
        month = int(months_found[-1]) if months_found else ctx_month
        collected.add(Date(year, month, int(m.group(1))))

    return sorted(d.strftime("%Y/%m/%d") for d in collected)


def _split_paid_seating(text: str) -> tuple[str, str | None]:
    """Sépare 'ありXXX' en ('あり', 'XXX') et 'なし' en ('なし', None)."""
    for flag in ("あり", "なし"):
        if text.startswith(flag):
            details = text[len(flag):].strip() or None
            return flag, details
    return text, None


class HanabiWalker:
    def __init__(self, region: str = "ar0300"):
        self.region = region
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)

    def get_event_links(self, max_pages: int = 20) -> list[str]:
        """Retourne les paths /detail/... de tous les événements paginés (sans doublons)."""
        links = []
        for i in range(1, max_pages + 1):
            url = f"{BASE_URL}/list/{self.region}/scheduled/{i}.html"
            response = self.session.get(url, timeout=10)
            if response.status_code == 404:
                break
            response.raise_for_status()

            soup = BeautifulSoup(response.content, "html.parser")
            page_links = [
                a.get("href") for a in soup.find_all("a")
                if a.get("href", "").startswith("/detail/")
            ]

            if len(page_links) > 1:
                links += page_links
            else:
                break

        return list(dict.fromkeys(links))

    def get_data_page(self, path: str) -> BeautifulSoup:
        response = self.session.get(f"{BASE_URL}{path}data.html", timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")

    def get_map_page(self, path: str) -> BeautifulSoup:
        response = self.session.get(f"{BASE_URL}{path}map.html", timeout=10)
        response.raise_for_status()
        return BeautifulSoup(response.content, "html.parser")

    def parse_event_table(self, soup: BeautifulSoup) -> dict:
        """Parse les tables s_table et mappe les clés japonaises en anglais."""
        result = {}
        for table in soup.find_all("table", class_="s_table"):
            for th, td in zip(table.find_all("th"), table.find_all("td")):
                key = th.text.strip()
                english_key = _FIELD_MAP.get(key)
                if not english_key:
                    continue
                if english_key in _LINK_FIELDS:
                    a = td.find("a")
                    result[english_key] = a.get("href") if a else None
                elif english_key == "access":
                    # Retire le lien "MAP" présent en fin de cellule
                    for a in td.find_all("a"):
                        a.decompose()
                    result[english_key] = td.get_text(" ", strip=True)
                elif english_key == "time":
                    result["start_time"], result["end_time"] = _extract_time(td.text.strip())
                elif english_key == "date":
                    result["dates"] = _extract_dates(td.text.strip())
                elif english_key == "paid_seating":
                    flag, details = _split_paid_seating(td.text.strip())
                    result["paid_seating"] = flag
                    result["paid_seating_details"] = details
                else:
                    result[english_key] = td.text.strip()
        return result

    def parse_coordinates(self, soup: BeautifulSoup) -> tuple[float, float] | tuple[None, None]:
        """Extrait lat/lng depuis l'iframe Google Maps dans map.html."""
        map_div = soup.find("div", class_="map_canvas")
        if not map_div:
            return None, None
        iframe = map_div.find("iframe")
        if not iframe:
            return None, None
        src = iframe.get("src", "")
        match = re.search(r"q=([-\d.]+),([-\d.]+)", src)
        if not match:
            return None, None
        return float(match.group(1)), float(match.group(2))

    def scrape_event(self, path: str) -> dict:
        """Scrape toutes les infos d'un événement depuis son path /detail/...."""
        data_soup = self.get_data_page(path)
        map_soup = self.get_map_page(path)

        event = self.parse_event_table(data_soup)
        lat, lng = self.parse_coordinates(map_soup)

        event["url"] = f"{BASE_URL}{path}"
        event["lat"] = lat
        event["lng"] = lng
        return event

    def scrape_all(self, max_pages: int = 20) -> list[dict]:
        """Scrape tous les événements. Explose les multi-jours en une ligne par jour."""
        paths = self.get_event_links(max_pages=max_pages)
        events = []
        for path in paths:
            try:
                event = self.scrape_event(path)
                dates = event.pop("dates")
                for date in dates:
                    events.append({**event, "date": date})
            except Exception as e:
                print(f"[SKIP] {path} — {e}")
        return events
