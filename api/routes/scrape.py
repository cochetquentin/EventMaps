import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request

from api.limiter import limiter
from config import settings
from db.store import EventStore
from scrapers.hanabi_walker import HanabiWalker
from scrapers.tokyo_cheapo import TokyoCheapo

logger = logging.getLogger(__name__)

router = APIRouter()


def verify_scrape_token(request: Request) -> None:
    """Raise 403 if a scrape token is configured and the request doesn't provide it."""
    token = settings.scrape_token
    if token is None:
        return
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer ") or auth[7:] != token:
        raise HTTPException(status_code=403, detail="Invalid or missing scrape token")


def _is_stale(job: dict) -> bool:
    """Return True if a 'running' job was started more than scrape_timeout_hours ago."""
    try:
        started = datetime.fromisoformat(job["started_at"])
        age = datetime.now(timezone.utc) - started
        return age.total_seconds() > settings.scrape_timeout_hours * 3600
    except (ValueError, TypeError, KeyError):
        return True


def _do_scrape(source: str, region: str) -> None:
    with EventStore(settings.db_path) as store:
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


@router.get("/config")
def scrape_config():
    """Return whether the scrape endpoint is publicly accessible (no token required)."""
    return {"public": settings.scrape_token is None}


@router.post("")
@limiter.limit("2/hour")
async def trigger_scrape(
    request: Request,
    background_tasks: BackgroundTasks,
    source: Literal["tc", "hanabi", "all"] = Query("all"),
    region: str = Query("ar0300"),
    _auth: None = Depends(verify_scrape_token),
):
    with EventStore(settings.db_path) as store:
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
    with EventStore(settings.db_path) as store:
        last = store.get_last_job(source)
    if last is None:
        return {"status": "never_run"}
    return last
