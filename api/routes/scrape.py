import logging
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Query

from db.store import EventStore
from scrapers.hanabi_walker import HanabiWalker
from scrapers.tokyo_cheapo import TokyoCheapo

logger = logging.getLogger(__name__)

router = APIRouter()

DB_PATH = "data/events.db"
_SCRAPE_TIMEOUT_HOURS = 2


def _is_stale(job: dict) -> bool:
    """Return True if a 'running' job was started more than _SCRAPE_TIMEOUT_HOURS ago."""
    try:
        started = datetime.fromisoformat(job["started_at"])
        age = datetime.now(timezone.utc) - started
        return age.total_seconds() > _SCRAPE_TIMEOUT_HOURS * 3600
    except (ValueError, TypeError, KeyError):
        return True


def _do_scrape(source: str, region: str) -> None:
    with EventStore(DB_PATH) as store:
        job_id = store.start_job(source)
        try:
            events = []
            if source in ("tc", "all"):
                events.extend(TokyoCheapo().scrape())
            if source in ("hanabi", "all"):
                events.extend(HanabiWalker(region=region).scrape())
            store.upsert_events(events)
            store.finish_job(job_id, len(events))
            logger.info("Scrape done (%s): %d events", source, len(events))
        except Exception as e:
            store.fail_job(job_id, str(e))
            logger.error("Scrape failed (%s): %s", source, e)
            raise


def _conflicting_sources(source: str) -> list[str]:
    """Return all source names that would overlap with the requested source."""
    if source == "all":
        return ["tc", "hanabi", "all"]
    return [source, "all"]


@router.post("")
def trigger_scrape(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="tc | hanabi | all"),
    region: str = Query("ar0300"),
):
    with EventStore(DB_PATH) as store:
        running = []
        for s in _conflicting_sources(source):
            j = store.get_last_job(s)
            if j and j["status"] == "running":
                if _is_stale(j):
                    store.fail_job(j["id"], "stale: process killed or server restarted")
                    logger.warning("Cleared stale scrape job %s (source=%s)", j["id"], s)
                else:
                    running.append(s)
    if running:
        return {"status": "already_running", "running_sources": running}
    background_tasks.add_task(_do_scrape, source, region)
    return {"status": "started"}


@router.get("/status")
def scrape_status(source: str | None = Query(None)):
    with EventStore(DB_PATH) as store:
        last = store.get_last_job(source)
    if last is None:
        return {"status": "never_run"}
    return last
