from datetime import timedelta, timezone

_JST = timezone(timedelta(hours=9))

_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS events (
    id           TEXT PRIMARY KEY,
    source       TEXT NOT NULL,
    title        TEXT NOT NULL,
    url          TEXT NOT NULL,
    start_date   TEXT,
    end_date     TEXT,
    times        TEXT,
    venue        TEXT,
    latitude     REAL,
    longitude    REAL,
    price        TEXT,
    attributes   TEXT,
    created_at   TEXT NOT NULL,
    canonical_id TEXT
)
"""

# Migrations idempotentes pour les DB events existantes (ALTER si la colonne manque).
_EVENTS_MIGRATIONS = [
    "ALTER TABLE events ADD COLUMN canonical_id TEXT",
]

_SCRAPE_JOBS_DDL = """
CREATE TABLE IF NOT EXISTS scrape_jobs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    source         TEXT,
    status         TEXT,
    started_at     TEXT,
    finished_at    TEXT,
    events_scraped INTEGER,
    error          TEXT,
    links_seen     INTEGER,
    events_ok      INTEGER,
    events_skipped INTEGER,
    error_count    INTEGER
)
"""

_SCRAPE_JOBS_MIGRATIONS = [
    "ALTER TABLE scrape_jobs ADD COLUMN links_seen INTEGER",
    "ALTER TABLE scrape_jobs ADD COLUMN events_ok INTEGER",
    "ALTER TABLE scrape_jobs ADD COLUMN events_skipped INTEGER",
    "ALTER TABLE scrape_jobs ADD COLUMN error_count INTEGER",
]

EVENTS_HEADERS = [
    "id",
    "source",
    "title",
    "url",
    "start_date",
    "end_date",
    "times",
    "venue",
    "latitude",
    "longitude",
    "price",
    "attributes",
    "created_at",
    "canonical_id",
]
