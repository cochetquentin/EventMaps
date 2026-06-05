import json
import sqlite3
from datetime import date as _date
from datetime import datetime

from db.migrations import _today_jst
from db.schema import _EVENTS_HEADERS
from models.event import Event


class EventsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

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

    def get_events(
        self,
        source: str | None = None,
        date: str | None = None,
        bbox: tuple[float, float, float, float] | None = None,
        upcoming: bool = True,
        start_from: str | None = None,
        start_to: str | None = None,
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
        elif start_from is not None or start_to is not None:
            # Client-supplied range — disable upcoming default
            if start_from is not None:
                clauses.append("COALESCE(end_date, start_date) >= ?")
                params.append(start_from)
            if start_to is not None:
                clauses.append("start_date <= ?")
                params.append(start_to)
        elif upcoming:
            # Default: events that are not yet over as of today JST
            clauses.append("COALESCE(end_date, start_date) >= ?")
            params.append(_today_jst())
        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            clauses.append("latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?")
            params.extend([min_lat, max_lat, min_lon, max_lon])
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._conn.execute(
            f"SELECT * FROM events {where} ORDER BY start_date LIMIT ? OFFSET ?",
            params + [limit, offset],
        ).fetchall()
        return [self._event_from_row(r) for r in rows]

    def get_event(self, event_id: str) -> Event | None:
        row = self._conn.execute("SELECT * FROM events WHERE id = ?", (event_id,)).fetchone()
        return self._event_from_row(row) if row else None

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
            json.dumps(e.attributes.model_dump()),
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
