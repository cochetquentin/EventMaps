import json
import re
import requests
from bs4 import BeautifulSoup

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


class TokyoCheapo:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(_HEADERS)

    def get_event_links(self, max_pages: int = 10) -> list[str]:
        """Retourne les URLs de tous les événements de la semaine."""
        links = []
        for i in range(1, max_pages + 1):
            url = f"{BASE_URL}/events/this-week/page/{i}/"
            response = self.session.get(url, timeout=10)
            if response.status_code == 404:
                break
            response.raise_for_status()

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
        response = self.session.get(url, timeout=10)
        response.raise_for_status()
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
            # Date non confirmée : "Early Apr", "Mid May ~ Early Jun", etc.
            return dates[0].get_text(" ", strip=True) if dates else ""
        return f"{day_divs[0].text} {dates[0].text}"

    def parse_time_and_price(self, soup: BeautifulSoup) -> tuple[str, str | None]:
        header = soup.find_all("header")[-1]
        attrs = header.find_all("div", class_="event__attribute")
        time = attrs[0].text.strip() if attrs else ""
        price = attrs[1].text.strip() if len(attrs) > 1 else None
        return time, price

    def parse_description(self, soup: BeautifulSoup) -> str:
        return soup.find("div", class_="entry-content__text").text.strip()

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
                # Le lien peut être dans ce div ou dans le suivant
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
                    "name": loc[0],
                    "lat": float(loc[1]),
                    "lng": float(loc[2]),
                    "address": loc[3] if len(loc) > 3 else "",
                }
                for loc in locations
            ]

        # Fallback: un seul lieu
        return [
            {
                "name": data.get("title", ""),
                "lat": float(data["lat"]),
                "lng": float(data["lng"]),
                "address": data.get("addr") or data.get("dispaddr", ""),
            }
        ]

    def scrape_event(self, url: str) -> dict:
        """Scrape toutes les infos d'un événement depuis son URL."""
        soup = self.get_event_page(url)
        time, price = self.parse_time_and_price(soup)
        return {
            "url": url,
            "title": self.parse_title(soup),
            "date": self.parse_date(soup),
            "time": time,
            "price": price,
            "description": self.parse_description(soup),
            "categories": self.parse_categories(soup),
            "tags": self.parse_tags(soup),
            "official_link": self.parse_official_link(soup),
            "locations": self.parse_locations(soup),
        }

    def scrape_all(self, max_pages: int = 10) -> list[dict]:
        """Scrape tous les événements de la semaine. Ignore les erreurs par événement."""
        urls = self.get_event_links(max_pages=max_pages)
        events = []
        for url in urls:
            try:
                events.append(self.scrape_event(url))
            except Exception as e:
                print(f"[SKIP] {url} — {e}")
        return events
