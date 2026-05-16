import csv
import hashlib
import json
import sqlite3
import sys
from datetime import datetime

from models.event import HanabiEvent, TokyoCheapoEvent


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
    def __init__(self, db_path: str = "data/events.db"):
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

    # --- Upsert ---

    def upsert_tokyo_cheapo(self, events: list[TokyoCheapoEvent]) -> None:
        rows = [self._tc_row(e) for e in events]
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

    def upsert_hanabi(self, events: list[HanabiEvent]) -> None:
        rows = [self._hanabi_row(e) for e in events]
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

    # --- Query ---

    def get_events(
        self,
        source: str | None = None,
        date: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[TokyoCheapoEvent | HanabiEvent]:
        results = []
        if source in (None, "tc"):
            results.extend(self._query_tc(date=date, limit=limit, offset=offset))
        if source in (None, "hanabi"):
            results.extend(self._query_hanabi(date=date, limit=limit, offset=offset))
        return results

    def get_event(self, event_id: str) -> TokyoCheapoEvent | HanabiEvent | None:
        row = self._conn.execute(
            "SELECT * FROM tokyo_cheapo WHERE id = ?", (event_id,)
        ).fetchone()
        if row:
            return self._tc_from_row(row)

        row = self._conn.execute(
            "SELECT * FROM hanabi WHERE id = ?", (event_id,)
        ).fetchone()
        if row:
            return self._hanabi_from_row(row)

        return None

    # --- CSV export ---

    def export_tokyo_cheapo_csv(self, path: str) -> None:
        rows = self._conn.execute(
            "SELECT * FROM tokyo_cheapo ORDER BY scraped_at DESC"
        ).fetchall()
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

    # --- Internal helpers ---

    def _query_tc(self, date: str | None, limit: int, offset: int) -> list[TokyoCheapoEvent]:
        if date:
            rows = self._conn.execute(
                "SELECT * FROM tokyo_cheapo WHERE start_date = ? OR end_date = ? LIMIT ? OFFSET ?",
                (date, date, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM tokyo_cheapo ORDER BY start_date LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._tc_from_row(r) for r in rows]

    def _query_hanabi(self, date: str | None, limit: int, offset: int) -> list[HanabiEvent]:
        if date:
            rows = self._conn.execute(
                "SELECT * FROM hanabi WHERE date = ? LIMIT ? OFFSET ?",
                (date, limit, offset),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT * FROM hanabi ORDER BY date LIMIT ? OFFSET ?",
                (limit, offset),
            ).fetchall()
        return [self._hanabi_from_row(r) for r in rows]

    @staticmethod
    def _tc_from_row(row: tuple) -> TokyoCheapoEvent:
        col = {name: i for i, name in enumerate(_TC_HEADERS)}
        return TokyoCheapoEvent(
            id=row[col["id"]],
            title=row[col["title"]] or "",
            start_date=row[col["start_date"]] or "",
            end_date=row[col["end_date"]] or None,
            start_time=row[col["start_time"]] or None,
            end_time=row[col["end_time"]] or None,
            price=row[col["price"]] or None,
            categories=json.loads(row[col["categories"]] or "[]"),
            tags=json.loads(row[col["tags"]] or "[]"),
            official_link=row[col["official_link"]] or None,
            url=row[col["url"]],
            location_name=row[col["location_name"]] or None,
            lat=row[col["lat"]],
            lng=row[col["lng"]],
            scraped_at=datetime.fromisoformat(row[col["scraped_at"]]),
        )

    @staticmethod
    def _hanabi_from_row(row: tuple) -> HanabiEvent:
        col = {name: i for i, name in enumerate(_HANABI_HEADERS)}
        return HanabiEvent(
            id=row[col["id"]],
            title=row[col["title"]] or "",
            url=row[col["url"]],
            start_date=row[col["date"]] or "",
            start_time=row[col["start_time"]] or None,
            end_time=row[col["end_time"]] or None,
            lat=row[col["lat"]],
            lng=row[col["lng"]],
            scraped_at=datetime.fromisoformat(row[col["scraped_at"]]),
            fireworks_count=row[col["fireworks_count"]] or None,
            fireworks_duration=row[col["fireworks_duration"]] or None,
            expected_crowd=row[col["expected_crowd"]] or None,
            rain_policy=row[col["rain_policy"]] or None,
            paid_seating=row[col["paid_seating"]] or None,
            paid_seating_details=row[col["paid_seating_details"]] or None,
            food_stalls=row[col["food_stalls"]] or None,
            notes=row[col["notes"]] or None,
            venue=row[col["venue"]] or None,
            access=row[col["access"]] or None,
            parking=row[col["parking"]] or None,
            official_site=row[col["official_site"]] or None,
            official_x=row[col["official_x"]] or None,
            contact=row[col["contact"]] or None,
            contact2=row[col["contact2"]] or None,
        )

    @staticmethod
    def _tc_row(e: TokyoCheapoEvent) -> tuple:
        return (
            e.id,
            e.title,
            e.start_date,
            e.end_date or "",
            e.start_time or "",
            e.end_time or "",
            e.price or "",
            json.dumps(e.categories),
            json.dumps(e.tags),
            e.official_link or "",
            e.url,
            e.location_name or "",
            e.lat,
            e.lng,
            e.scraped_at.isoformat(),
        )

    @staticmethod
    def _hanabi_row(e: HanabiEvent) -> tuple:
        return (
            e.id,
            e.title,
            e.fireworks_count or "",
            e.fireworks_duration or "",
            e.expected_crowd or "",
            e.start_time or "",
            e.end_time or "",
            e.rain_policy or "",
            e.paid_seating or "",
            e.paid_seating_details or "",
            e.food_stalls or "",
            e.notes or "",
            e.venue or "",
            e.access or "",
            e.parking or "",
            e.official_site or "",
            e.official_x or "",
            e.url,
            e.lat,
            e.lng,
            e.start_date,  # stored as `date` column
            e.contact or "",
            e.contact2 or "",
            e.scraped_at.isoformat(),
        )

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
