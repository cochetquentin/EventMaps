import logging

from fastapi import APIRouter, BackgroundTasks, Query

from db.store import EventStore
from scrapers.hanabi_walker import HanabiWalker
from scrapers.tokyo_cheapo import TokyoCheapo

logger = logging.getLogger(__name__)

router = APIRouter()

DB_PATH = "data/events.db"


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


@router.post("")
def trigger_scrape(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="tc | hanabi | all"),
    region: str = Query("ar0300"),
):
    with EventStore(DB_PATH) as store:
        last = store.get_last_job(source)
    if last and last["status"] == "running":
        return {"status": "already_running"}
    background_tasks.add_task(_do_scrape, source, region)
    return {"status": "started"}


@router.get("/status")
def scrape_status(source: str | None = Query(None)):
    with EventStore(DB_PATH) as store:
        last = store.get_last_job(source)
    if last is None:
        return {"status": "never_run"}
    return last
