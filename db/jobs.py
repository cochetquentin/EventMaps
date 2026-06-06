import sqlite3
from datetime import UTC, datetime


class JobsRepository:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def start_job(self, source: str) -> int:
        cur = self._conn.execute(
            "INSERT INTO scrape_jobs (source, status, started_at) VALUES (?, 'running', ?)",
            (source, datetime.now(UTC).isoformat()),
        )
        self._conn.commit()
        return cur.lastrowid

    def finish_job(
        self,
        job_id: int,
        count: int,
        *,
        links_seen: int | None = None,
        events_ok: int | None = None,
        events_skipped: int | None = None,
        error_count: int | None = None,
    ) -> None:
        self._conn.execute(
            """UPDATE scrape_jobs
               SET status='done', finished_at=?, events_scraped=?,
                   links_seen=?, events_ok=?, events_skipped=?, error_count=?
               WHERE id=?""",
            (
                datetime.now(UTC).isoformat(),
                count,
                links_seen,
                events_ok,
                events_skipped,
                error_count,
                job_id,
            ),
        )
        self._conn.commit()

    def fail_job(
        self,
        job_id: int,
        error: str,
        *,
        links_seen: int | None = None,
        events_ok: int | None = None,
        events_skipped: int | None = None,
        error_count: int | None = None,
    ) -> None:
        self._conn.execute(
            """UPDATE scrape_jobs
               SET status='failed', finished_at=?, error=?,
                   links_seen=?, events_ok=?, events_skipped=?, error_count=?
               WHERE id=?""",
            (
                datetime.now(UTC).isoformat(),
                error,
                links_seen,
                events_ok,
                events_skipped,
                error_count,
                job_id,
            ),
        )
        self._conn.commit()

    def get_job_by_id(self, job_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM scrape_jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        keys = [
            "id",
            "source",
            "status",
            "started_at",
            "finished_at",
            "events_scraped",
            "error",
            "links_seen",
            "events_ok",
            "events_skipped",
            "error_count",
        ]
        return dict(zip(keys, row))

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
        keys = [
            "id",
            "source",
            "status",
            "started_at",
            "finished_at",
            "events_scraped",
            "error",
            "links_seen",
            "events_ok",
            "events_skipped",
            "error_count",
        ]
        return dict(zip(keys, row))
