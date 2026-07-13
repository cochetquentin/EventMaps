import json
import os
import sqlite3
from datetime import date as _date
from datetime import datetime

from db.schema import (
    _EVENTS_DDL,
    _EVENTS_MIGRATIONS,
    _JST,
    _SCRAPE_JOBS_DDL,
    _SCRAPE_JOBS_MIGRATIONS,
)


def today_jst() -> str:
    """Return today's date in JST (UTC+9) as YYYY-MM-DD."""
    return datetime.now(_JST).date().isoformat()


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


def _migrate_scrape_jobs(conn: sqlite3.Connection) -> None:
    """Add new metric columns to scrape_jobs if they don't exist yet (existing DBs)."""
    for sql in _SCRAPE_JOBS_MIGRATIONS:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def _migrate_events(conn: sqlite3.Connection) -> None:
    """Add new columns to events if they don't exist yet (existing DBs)."""
    for sql in _EVENTS_MIGRATIONS:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError as exc:
            if "duplicate column name" not in str(exc).lower():
                raise


def _migrate(conn: sqlite3.Connection) -> None:
    """Migrate tokyo_cheapo + hanabi tables → events table if they still exist."""
    tables = {
        r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }

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

            attributes = json.dumps(
                {
                    "categories": json.loads(categories or "[]"),
                    "tags": json.loads(tags or "[]"),
                    "official_link": official_link,
                    "location_name": location_name,
                }
            )

            conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, title, url, start_date, end_date, times,
                    venue, latitude, longitude, price, attributes, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    r_id,
                    "tc",
                    title,
                    url,
                    norm_start,
                    norm_end,
                    times,
                    None,
                    lat,
                    lng,
                    price,
                    attributes,
                    scraped_at,
                ),
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

            attributes = json.dumps(
                {
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
                }
            )

            conn.execute(
                """INSERT OR IGNORE INTO events
                   (id, source, title, url, start_date, end_date, times,
                    venue, latitude, longitude, price, attributes, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    r_id,
                    "hanabi",
                    title,
                    url,
                    norm_start,
                    None,
                    times,
                    venue,
                    lat,
                    lng,
                    None,
                    attributes,
                    scraped_at,
                ),
            )
        conn.execute("DROP TABLE hanabi")

    conn.commit()


def init_schema(db_path: str) -> sqlite3.Connection:
    """Open DB, create tables, run all migrations. Returns the connection."""
    if parent := os.path.dirname(db_path):
        os.makedirs(parent, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute(_EVENTS_DDL)
    conn.execute(_SCRAPE_JOBS_DDL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_source ON events(source)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_start_date ON events(start_date)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_coords ON events(latitude, longitude)")
    conn.commit()
    _migrate_scrape_jobs(conn)
    _migrate_events(conn)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_events_canonical ON events(canonical_id)")
    conn.commit()
    _migrate(conn)
    return conn
