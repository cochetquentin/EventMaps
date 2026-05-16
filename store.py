import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime, timezone


def _make_id(parts: list[str]) -> str:
    key = "|".join(parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


_TC_HEADERS = [
    "id", "title", "start_date", "end_date", "start_time", "end_time",
    "price", "categories", "tags", "official_link", "url", "location_name",
    "lat", "lng", "scraped_at",
]

_HANABI_HEADERS = [
    "id", "title", "fireworks_count", "fireworks_duration", "expected_crowd",
    "start_time", "end_time", "rain_policy", "paid_seating", "paid_seating_details",
    "food_stalls", "notes", "venue", "access", "parking", "official_site", "official_x",
    "url", "lat", "lng", "date", "contact", "contact2", "scraped_at",
]

_TC_DDL = """
CREATE TABLE IF NOT EXISTS tokyo_cheapo (
    id             TEXT PRIMARY KEY,
    title          TEXT,
    start_date     TEXT,
    end_date       TEXT,
    start_time     TEXT,
    end_time       TEXT,
    price          TEXT,
    categories     TEXT,
    tags           TEXT,
    official_link  TEXT,
    url            TEXT NOT NULL,
    location_name  TEXT,
    lat            REAL,
    lng            REAL,
    scraped_at     TEXT NOT NULL
)
"""

_HANABI_DDL = """
CREATE TABLE IF NOT EXISTS hanabi (
    id                   TEXT PRIMARY KEY,
    title                TEXT,
    fireworks_count      TEXT,
    fireworks_duration   TEXT,
    expected_crowd       TEXT,
    start_time           TEXT,
    end_time             TEXT,
    rain_policy          TEXT,
    paid_seating         TEXT,
    paid_seating_details TEXT,
    food_stalls          TEXT,
    notes                TEXT,
    venue                TEXT,
    access               TEXT,
    parking              TEXT,
    official_site        TEXT,
    official_x           TEXT,
    url                  TEXT NOT NULL,
    lat                  REAL,
    lng                  REAL,
    date                 TEXT,
    contact              TEXT,
    contact2             TEXT,
    scraped_at           TEXT NOT NULL
)
"""


class EventStore:
    def __init__(self, db_path: str = "events.db"):
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute(_TC_DDL)
        self._conn.execute(_HANABI_DDL)
        self._conn.commit()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._conn.close()

    def upsert_tokyo_cheapo(self, events: list[dict]) -> None:
        scraped_at = datetime.now(timezone.utc).isoformat()
        rows = [self._tc_row(e, scraped_at) for e in events]
        self._conn.executemany(
            """
            INSERT INTO tokyo_cheapo VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, start_date=excluded.start_date,
                end_date=excluded.end_date, start_time=excluded.start_time,
                end_time=excluded.end_time, price=excluded.price,
                categories=excluded.categories, tags=excluded.tags,
                official_link=excluded.official_link, lat=excluded.lat,
                lng=excluded.lng, scraped_at=excluded.scraped_at
            """,
            rows,
        )
        self._conn.commit()

    def upsert_hanabi(self, events: list[dict]) -> None:
        scraped_at = datetime.now(timezone.utc).isoformat()
        rows = [self._hanabi_row(e, scraped_at) for e in events]
        self._conn.executemany(
            """
            INSERT INTO hanabi VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title, fireworks_count=excluded.fireworks_count,
                fireworks_duration=excluded.fireworks_duration,
                expected_crowd=excluded.expected_crowd,
                start_time=excluded.start_time, end_time=excluded.end_time,
                rain_policy=excluded.rain_policy, paid_seating=excluded.paid_seating,
                paid_seating_details=excluded.paid_seating_details,
                food_stalls=excluded.food_stalls, notes=excluded.notes,
                venue=excluded.venue, access=excluded.access, parking=excluded.parking,
                official_site=excluded.official_site, official_x=excluded.official_x,
                lat=excluded.lat, lng=excluded.lng, contact=excluded.contact,
                contact2=excluded.contact2, scraped_at=excluded.scraped_at
            """,
            rows,
        )
        self._conn.commit()

    def export_tokyo_cheapo_csv(self, path: str) -> None:
        rows = self._conn.execute(
            "SELECT * FROM tokyo_cheapo ORDER BY scraped_at DESC"
        ).fetchall()
        headers = [h for h in _TC_HEADERS if h != "id" and h != "scraped_at"]
        headers = ["title", "start_date", "end_date", "start_time", "end_time",
                   "price", "categories", "tags", "official_link", "url",
                   "location_name", "lat", "lng"]
        col = {name: i for i, name in enumerate(_TC_HEADERS)}

        def fmt_row(r):
            return [
                r[col["title"]], r[col["start_date"]], r[col["end_date"]],
                r[col["start_time"]], r[col["end_time"]], r[col["price"]],
                ", ".join(json.loads(r[col["categories"]] or "[]")),
                ", ".join(json.loads(r[col["tags"]] or "[]")),
                r[col["official_link"]], r[col["url"]], r[col["location_name"]],
                r[col["lat"]], r[col["lng"]],
            ]

        self._write_csv(path, headers, [fmt_row(r) for r in rows])

    def export_hanabi_csv(self, path: str) -> None:
        rows = self._conn.execute(
            "SELECT * FROM hanabi ORDER BY scraped_at DESC"
        ).fetchall()
        headers = ["title", "fireworks_count", "fireworks_duration", "expected_crowd",
                   "start_time", "end_time", "rain_policy", "paid_seating",
                   "paid_seating_details", "food_stalls", "notes", "venue", "access",
                   "parking", "official_site", "official_x", "url", "lat", "lng",
                   "date", "contact", "contact2"]
        col = {name: i for i, name in enumerate(_HANABI_HEADERS)}

        def fmt_row(r):
            return [r[col[h]] for h in headers]

        self._write_csv(path, headers, [fmt_row(r) for r in rows])

    @staticmethod
    def _write_csv(path: str, headers: list[str], rows: list[list]) -> None:
        if path == "-":
            sys.stdout.reconfigure(encoding="utf-8", newline="")
            w = csv.writer(sys.stdout)
            w.writerow(headers)
            w.writerows(rows)
        else:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                w = csv.writer(f)
                w.writerow(headers)
                w.writerows(rows)

    @staticmethod
    def _tc_row(e: dict, scraped_at: str) -> tuple:
        location_name = e.get("location_name") or ""
        return (
            _make_id([e["url"], location_name]),
            e.get("title", ""),
            e.get("start_date", ""),
            e.get("end_date", ""),
            e.get("start_time", ""),
            e.get("end_time", ""),
            e.get("price") or "",
            json.dumps(e.get("categories") or []),
            json.dumps(e.get("tags") or []),
            e.get("official_link") or "",
            e["url"],
            location_name,
            e.get("lat"),
            e.get("lng"),
            scraped_at,
        )

    @staticmethod
    def _hanabi_row(e: dict, scraped_at: str) -> tuple:
        return (
            _make_id([e["url"], e.get("date") or ""]),
            e.get("title", ""),
            e.get("fireworks_count", ""),
            e.get("fireworks_duration", ""),
            e.get("expected_crowd", ""),
            e.get("start_time") or "",
            e.get("end_time") or "",
            e.get("rain_policy", ""),
            e.get("paid_seating", ""),
            e.get("paid_seating_details") or "",
            e.get("food_stalls", ""),
            e.get("notes", ""),
            e.get("venue", ""),
            e.get("access", ""),
            e.get("parking", ""),
            e.get("official_site") or "",
            e.get("official_x") or "",
            e["url"],
            e.get("lat"),
            e.get("lng"),
            e.get("date", ""),
            e.get("contact", ""),
            e.get("contact2", ""),
            scraped_at,
        )
