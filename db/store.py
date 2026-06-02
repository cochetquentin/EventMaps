import hashlib
import json
import os
import sqlite3
from datetime import date as _date
from datetime import datetime, timedelta, timezone

_JST = timezone(timedelta(hours=9))


def _today_jst() -> str:
    """Return today's date in JST (UTC+9) as YYYY-MM-DD."""
    return datetime.now(_JST).date().isoformat()

from models.event import Event


def _make_id(parts: list[str]) -> str:
    key = "|".join(parts)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id          TEXT PRIMARY KEY,
    source      TEXT NOT NULL,
    title       TEXT NOT NULL,
    url         TEXT NOT NULL,
    start_date  TEXT,
    end_date    TEXT,
    times       TEXT,
    venue       TEXT,
    latitude    REAL,
    longitude   REAL,
    price       TEXT,
    attributes  TEXT,
    created_at  TEXT NOT NULL
)
"""

_SCRAPE_JOBS_DDL = """
CREATE TABLE IF NOT EXISTS scrape_jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT,
    status         TEXT,
    started_at     TEXT,
    finished_at    TEXT,
    events_scraped INTEGER,
    error          TEXT
)
"""

_EVENTS_HEADERS = [
    "id", "source", "title", "url", "start_date", "end_date",
    "times", "venue", "latitude", "longitude", "price", "attributes", "created_at",
]


def _safe_iso_date(raw: str | None) -> str | None:
    """Normalize YYYY/MM/DD or YYYY-MM-DD to YYYY-MM-DD; return None if unparseable."""
    if not raw:
        return None
    normalized = raw.replace("/", "-")
    try:
        _date.fromisoformat(normalized)
        return normalized
    except ValueError:
        return None


def _migrate(conn: sqlite3.Connection) -> None:
    """Migrate tokyo_cheapo + hanabi tables → events table if they still exist."""
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ).fetchall()}

    if "tokyo_cheapo" in tables:
        rows = conn.execute("SELECT * FROM tokyo_cheapo").fetchall()
        for row in rows:
            # id(0) title(1) start_date(2) end_date(3) start_time(4) end_time(5)
            # price(6) categories(7) tags(8) official_link(9) url(10)
            # location_name(11) lat(12) lng(13) scraped_at(14)
            r_id = row[0]
            title = row[1] or ""
            start_date = row[2]
            end_date = row[3]
            start_time = row[4]
            end_time = row[5]
            price = row[6] or None
            categories = row[7]
            tags = row[8]
            official_link = row[9] or None
            url = row[10]
            location_name = row[11] or None
            lat = row[12]
            lng = row[13]
            scraped_at = row[14]

            norm_start = _safe_iso_date(start_date)
            norm_end = _safe_iso_date(end_date)

            times = None
            if start_time and end_time:
                times = f"{start_time}-{end_time}"
            elif start_time:
                times = start_time

            attributes = json.dumps({
                "categories": json.loads(categories or "[]"),
                "tags": json.loads(tags or "[]"),
                "official_link": official_link,
                "location_name": location_name,
            })

            conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, title, url, start_date, end_date, times,
                    venue, latitude, longitude, price, attributes, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r_id, "tc", title, url, norm_start, norm_end, times,
                 None, lat, lng, price, attributes, scraped_at),
            )
        conn.execute("DROP TABLE tokyo_cheapo")

    if "hanabi" in tables:
        rows = conn.execute("SELECT * FROM hanabi").fetchall()
        for row in rows:
            # id(0) title(1) fireworks_count(2) fireworks_duration(3)
            # expected_crowd(4) start_time(5) end_time(6) rain_policy(7)
            # paid_seating(8) paid_seating_details(9) food_stalls(10)
            # notes(11) venue(12) access(13) parking(14) official_site(15)
            # official_x(16) url(17) lat(18) lng(19) date(20)
            # contact(21) contact2(22) scraped_at(23)
            r_id = row[0]
            title = row[1] or ""
            fireworks_count = row[2] or None
            fireworks_duration = row[3] or None
            expected_crowd = row[4] or None
            start_time = row[5]
            end_time = row[6]
            rain_policy = row[7] or None
            paid_seating = row[8] or None
            paid_seating_details = row[9] or None
            food_stalls = row[10] or None
            notes = row[11] or None
            venue = row[12] or None
            access = row[13] or None
            parking = row[14] or None
            official_site = row[15] or None
            official_x = row[16] or None
            url = row[17]
            lat = row[18]
            lng = row[19]
            date_val = row[20]
            contact = row[21] or None
            contact2 = row[22] or None
            scraped_at = row[23]

            norm_start = _safe_iso_date(date_val)

            times = None
            if start_time and end_time:
                times = f"{start_time}-{end_time}"
            elif start_time:
                times = start_time

            attributes = json.dumps({
                "fireworks_count": fireworks_count,
                "fireworks_duration": fireworks_duration,
                "expected_crowd": expected_crowd,
                "rain_policy": rain_policy,
                "paid_seating": paid_seating,
                "paid_seating_details": paid_seating_details,
                "food_stalls": food_stalls,
                "notes": notes,
                "access": access,
                "parking": parking,
                "official_site": official_site,
                "official_x": official_x,
                "contact": contact,
                "contact2": contact2,
            })

            conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, title, url, start_date, end_date, times,
                    venue, latitude, longitude, price, attributes, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (r_id, "hanabi", title, url, norm_start, None, times,
                 venue, lat, lng, None, attributes, scraped_at),
            )
        conn.execute("DROP TABLE hanabi")

    conn.commit()


class EventStore:
    def __init__(self, db_path: str = "data/events.db"):
        if parent := os.path.dirname(db_path):
            os.makedirs(parent, exist_ok=True)
        self._conn = sqlite3.connect(db_path)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute(_EVENTS_DDL)
        self._conn.execute(_SCRAPE_JOBS_DDL)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(start_date)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_events_coords ON events(latitude, longitude)")
        self._conn.commit()
        _migrate(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._conn.close()

    # --- Upsert ---

    def upsert_events(self, events: list[Event]) -> None:
        rows = [self._event_row(e) for e in events]
        self._conn.executemany(
            """INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   title=excluded.title, start_date=excluded.start_date,
                   end_date=excluded.end_date, times=excluded.times,
                   venue=excluded.venue, latitude=excluded.latitude,
                   longitude=excluded.longitude, price=excluded.price,
                   attributes=excluded.attributes, created_at=excluded.created_at
            """,
            rows,
        )
        self._conn.commit()

    # --- Query ---

    def get_events(
        self,
        source: str | None = None,
        date: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        upcoming: bool = True,
        start_from: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Event]:
        clauses: list[str] = []
        params: list = []
        if source:
            clauses.append("source = ?")
            params.append(source)
        if date:
            # Explicit overlap filter — overrides everything
            clauses.append("start_date <= ? AND COALESCE(end_date, start_date) >= ?")
            params.extend([date, date])
        elif start_from is not None:
            # Client-supplied lower bound (e.g. date picker set to a past date)
            clauses.append("COALESCE(end_date, start_date) >= ?")
            params.append(start_from)
        elif upcoming:
            # Default: events that are not yet over as of today JST
            clauses.append("COALESCE(end_date, start_date) >= ?")
            params.append(_today_jst())
        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            clauses.append(
                "latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?"
            )
            params.extend([min_lat, max_lat, min_lon, max_lon])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM events {where} ORDER BY start_date LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [self._event_from_row(r) for r in rows]

    def get_event(self, event_id: str) -> Event | None:
        row = self._conn.execute(
            "SELECT * FROM events WHERE id = ?", (event_id,)
        ).fetchone()
        return self._event_from_row(row) if row else None

    # --- Scrape jobs ---

    def start_job(self, source: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO scrape_jobs (source, status, started_at) VALUES (?, 'running', ?)",
            (source, datetime.now(timezone.utc).isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid

    def finish_job(self, job_id: int, count: int) -> None:
        self._conn.execute(
            """UPDATE scrape_jobs SET status='done', finished_at=?, events_scraped=?
               WHERE id=?""",
            (datetime.now(timezone.utc).isoformat(), count, job_id),
        )
        self._conn.commit()

    def fail_job(self, job_id: int, error: str) -> None:
        self._conn.execute(
            """UPDATE scrape_jobs SET status='failed', finished_at=?, error=?
               WHERE id=?""",
            (datetime.now(timezone.utc).isoformat(), error, job_id),
        )
        self._conn.commit()

    def get_last_job(self, source: str | None = None) -> dict | None:
        if source:
            row = self._conn.execute(
                "SELECT * FROM scrape_jobs WHERE source=? ORDER BY id DESC LIMIT 1",
                (source,),
            ).fetchone()
        else:
            row = self._conn.execute(
                "SELECT * FROM scrape_jobs ORDER BY id DESC LIMIT 1"
            ).fetchone()
        if row is None:
            return None
        keys = ["id", "source", "status", "started_at", "finished_at", "events_scraped", "error"]
        return dict(zip(keys, row))

    # --- Internal helpers ---

    @staticmethod
    def _event_row(e: Event) -> tuple:
        return (
            e.id,
            e.source,
            e.title,
            e.url,
            e.start_date.isoformat() if e.start_date else None,
            e.end_date.isoformat() if e.end_date else None,
            e.times,
            e.venue,
            e.latitude,
            e.longitude,
            e.price,
            json.dumps(e.attributes),
            e.created_at.isoformat(),
        )

    @staticmethod
    def _event_from_row(row: tuple) -> Event:
        col = {name: i for i, name in enumerate(_EVENTS_HEADERS)}
        raw_start = row[col["start_date"]]
        raw_end = row[col["end_date"]]
        return Event(
            id=row[col["id"]],
            source=row[col["source"]],
            title=row[col["title"]],
            url=row[col["url"]],
            start_date=_date.fromisoformat(raw_start) if raw_start else None,
            end_date=_date.fromisoformat(raw_end) if raw_end else None,
            times=row[col["times"]],
            venue=row[col["venue"]],
            latitude=row[col["latitude"]],
            longitude=row[col["longitude"]],
            price=row[col["price"]],
            attributes=json.loads(row[col["attributes"]] or "{}"),
            created_at=datetime.fromisoformat(row[col["created_at"]]),
        )
