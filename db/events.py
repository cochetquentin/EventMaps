import json
import sqlite3
from datetime import date as _date
from datetime import datetime

from db.migrations import today_jst
from db.schema import EVENTS_HEADERS
from models.event import Event


class EventsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def upsert_events(self, events: list[Event]) -> None:
        rows = [self._event_row(e) for e in events]
        self._conn.executemany(
            """INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(id) DO UPDATE SET
                   title=excluded.title, start_date=excluded.start_date,
                   end_date=excluded.end_date, times=excluded.times,
                   venue=excluded.venue, latitude=excluded.latitude,
                   longitude=excluded.longitude, price=excluded.price,
                   attributes=excluded.attributes, created_at=excluded.created_at,
                   canonical_id=excluded.canonical_id
            """,
            rows,
        )
        self._conn.commit()

    def set_canonical_ids(self, mapping: dict[str, str]) -> None:
        """Mettre à jour ``canonical_id`` de lignes existantes (id → canonical_id)."""
        if not mapping:
            return
        self._conn.executemany(
            "UPDATE events SET canonical_id = ? WHERE id = ?",
            [(canonical, event_id) for event_id, canonical in mapping.items()],
        )
        self._conn.commit()

    def recompute_canonical(self, upcoming_only: bool = True) -> dict[str, str]:
        """Recalculer les ``canonical_id`` sur les événements déjà en base (backfill).

        Ne touche à aucun autre champ, ne supprime rien. Par défaut ne traite que
        les événements à venir (les seuls affichés sur la carte)."""
        from dedup import assign_canonical_ids

        events = self.get_events(upcoming=upcoming_only, limit=1000000)
        mapping = assign_canonical_ids(events)
        self.set_canonical_ids(mapping)
        return mapping

    def upsert_with_dedup(self, events: list[Event]) -> dict[str, str]:
        """Insérer des événements en leur assignant un ``canonical_id`` cross-source.

        Les nouveaux événements sont clusterisés AVEC les événements à venir déjà
        en base : un doublon peut provenir d'un scrape antérieur d'une autre
        source. On met à jour le ``canonical_id`` des nouveaux (avant upsert) et
        des lignes existantes dont le représentant a changé. Rien n'est supprimé.

        Renvoie le mapping complet id → canonical_id (utile pour les tests/logs).
        """
        from dedup import assign_canonical_ids

        existing = self.get_events(upcoming=True, limit=100000)
        # Union par id : les nouveaux événements priment sur la version en base.
        new_ids = {e.id for e in events}
        union = [e for e in existing if e.id not in new_ids] + list(events)

        mapping = assign_canonical_ids(union)

        # Assigne le canonical aux nouveaux événements avant insertion.
        for event in events:
            event.canonical_id = mapping.get(event.id, event.id)
        self.upsert_events(events)

        # Met à jour uniquement les lignes existantes dont le canonical a changé.
        changed = {
            e.id: mapping[e.id]
            for e in existing
            if e.id not in new_ids and mapping.get(e.id, e.id) != e.canonical_id
        }
        self.set_canonical_ids(changed)
        return mapping

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
        q: str | None = None,
        category: str | None = None,
        collapse: bool = False,
    ) -> list[Event]:
        clauses: list[str] = []
        params: list = []
        if collapse:
            # Ne garder qu'un représentant par cluster de doublons. Les lignes
            # non encore dédupliquées (canonical_id NULL) sont leur propre
            # représentant.
            clauses.append("(canonical_id IS NULL OR canonical_id = id)")
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
            params.append(today_jst())
        if bbox:
            min_lon, min_lat, max_lon, max_lat = bbox
            # Time Out Tokyo events without coordinates are always included so
            # they appear in the list view regardless of the map viewport.
            # All other sources must fall inside the bbox.
            clauses.append(
                "((source = 'tot' AND latitude IS NULL)"
                " OR (latitude BETWEEN ? AND ? AND longitude BETWEEN ? AND ?))"
            )
            params.extend([min_lat, max_lat, min_lon, max_lon])
        if q:
            # Recherche sur titre, venue, location_name et access.
            # json_extract évite de matcher les noms de champs (ex: "food_stalls").
            # % et _ non échappés — élargit le match légèrement (acceptable MVP).
            clauses.append(
                "(title LIKE ? OR venue LIKE ?"
                " OR json_extract(attributes, '$.location_name') LIKE ?"
                " OR json_extract(attributes, '$.access') LIKE ?)"
            )
            params.extend([f"%{q}%", f"%{q}%", f"%{q}%", f"%{q}%"])
        if category:
            # Filtre exact sur le tableau $.categories via json_each pour éviter
            # les faux positifs sur les autres champs du JSON attributes.
            clauses.append(
                "EXISTS ("
                "SELECT 1 FROM json_each(json_extract(attributes, '$.categories')) "
                "WHERE value = ?"
                ")"
            )
            params.append(category)
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
            e.canonical_id,
        )

    @staticmethod
    def _event_from_row(row: tuple) -> Event:
        col = {name: i for i, name in enumerate(EVENTS_HEADERS)}
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
            canonical_id=row[col["canonical_id"]],
        )
