from db.events import EventsRepository
from db.jobs import JobsRepository
from db.migrations import init_schema
from models.event import Event


class EventStore:
    def __init__(self, db_path: str = "data/events.db"):
        self._conn = init_schema(db_path)
        self._events = EventsRepository(self._conn)
        self._jobs = JobsRepository(self._conn)

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self._conn.close()

    # --- Events ---

    def upsert_events(self, events: list[Event]) -> None:
        return self._events.upsert_events(events)

    def upsert_with_dedup(self, events: list[Event]) -> dict[str, str]:
        return self._events.upsert_with_dedup(events)

    def set_canonical_ids(self, mapping: dict[str, str]) -> None:
        return self._events.set_canonical_ids(mapping)

    def recompute_canonical(self, upcoming_only: bool = True) -> dict[str, str]:
        return self._events.recompute_canonical(upcoming_only=upcoming_only)

    def get_events(
        self,
        source=None,
        date=None,
        bbox=None,
        upcoming=True,
        start_from=None,
        start_to=None,
        limit=100,
        offset=0,
        q=None,
        category=None,
        collapse=False,
    ) -> list[Event]:
        return self._events.get_events(
            source=source,
            date=date,
            bbox=bbox,
            upcoming=upcoming,
            start_from=start_from,
            start_to=start_to,
            limit=limit,
            offset=offset,
            q=q,
            category=category,
            collapse=collapse,
        )

    def get_event(self, event_id: str) -> Event | None:
        return self._events.get_event(event_id)

    # --- Scrape jobs ---

    def start_job(self, source: str) -> int:
        return self._jobs.start_job(source)

    def finish_job(self, job_id: int, count: int, **kwargs) -> None:
        return self._jobs.finish_job(job_id, count, **kwargs)

    def fail_job(self, job_id: int, error: str, **kwargs) -> None:
        return self._jobs.fail_job(job_id, error, **kwargs)

    def get_job_by_id(self, job_id: int) -> dict | None:
        return self._jobs.get_job_by_id(job_id)

    def get_last_job(self, source: str | None = None) -> dict | None:
        return self._jobs.get_last_job(source)
