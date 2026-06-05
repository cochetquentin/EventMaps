import logging
import time
from datetime import UTC, datetime
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
        age = datetime.now(UTC) - started
        return age.total_seconds() > settings.scrape_timeout_hours * 3600
    except (ValueError, TypeError, KeyError):
        return True


def _do_scrape(source: str, region: str) -> None:
    from scrapers.base import ScrapeReport

    with EventStore(settings.db_path) as store:
        job_id = store.start_job(source)
        try:
            events = []
            reports: list[ScrapeReport] = []
            job_start = time.monotonic()

            if source in ("tc", "all"):
                t0 = time.monotonic()
                tc_events, tc_report = TokyoCheapo().scrape()
                tc_report.duration_s = time.monotonic() - t0
                events.extend(tc_events)
                reports.append(tc_report)
                logger.info(
                    "scraper source=tc job_id=%d events=%d links=%d errors=%d duration=%.2fs",
                    job_id,
                    tc_report.events_ok,
                    tc_report.links_seen,
                    len(tc_report.errors),
                    tc_report.duration_s,
                )
            if source in ("hanabi", "all"):
                t0 = time.monotonic()
                h_events, h_report = HanabiWalker(region=region).scrape()
                h_report.duration_s = time.monotonic() - t0
                events.extend(h_events)
                reports.append(h_report)
                logger.info(
                    "scraper source=hanabi job_id=%d events=%d links=%d errors=%d duration=%.2fs",
                    job_id,
                    h_report.events_ok,
                    h_report.links_seen,
                    len(h_report.errors),
                    h_report.duration_s,
                )

            job_duration = time.monotonic() - job_start
            links_seen = sum(r.links_seen for r in reports)
            events_ok = sum(r.events_ok for r in reports)
            events_skipped = sum(r.events_skipped for r in reports)
            error_count = sum(len(r.errors) for r in reports)
            combined_error_rate = (
                (events_skipped + error_count) / links_seen if links_seen > 0 else 0.0
            )
            # Also check per-source so a healthy source can't mask a broken one
            failing_source = next(
                (
                    r
                    for r in reports
                    if r.links_seen > 0 and r.error_rate > settings.scrape_error_threshold
                ),
                None,
            )

            store.upsert_events(events)

            if failing_source is not None or (
                links_seen > 0 and combined_error_rate > settings.scrape_error_threshold
            ):
                if failing_source is not None:
                    msg = (
                        f"Source '{failing_source.source}' error rate {failing_source.error_rate:.0%} "
                        f"exceeded threshold {settings.scrape_error_threshold:.0%} "
                        f"({len(failing_source.errors)} errors / {failing_source.links_seen} links)"
                    )
                else:
                    msg = (
                        f"Combined error rate {combined_error_rate:.0%} exceeded threshold "
                        f"{settings.scrape_error_threshold:.0%} "
                        f"({error_count} errors / {links_seen} links)"
                    )
                store.fail_job(
                    job_id,
                    msg,
                    links_seen=links_seen,
                    events_ok=events_ok,
                    events_skipped=events_skipped,
                    error_count=error_count,
                )
                logger.error(
                    "scrape_fail source=%s job_id=%d %s",
                    source,
                    job_id,
                    msg,
                )
            else:
                store.finish_job(
                    job_id,
                    len(events),
                    links_seen=links_seen,
                    events_ok=events_ok,
                    events_skipped=events_skipped,
                    error_count=error_count,
                )
                logger.info(
                    "scrape_done source=%s job_id=%d events=%d links=%d errors=%d duration=%.2fs",
                    source,
                    job_id,
                    len(events),
                    links_seen,
                    error_count,
                    job_duration,
                )
        except Exception as e:
            store.fail_job(job_id, str(e))
            logger.error("scrape_error source=%s job_id=%d error=%r", source, job_id, str(e))
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
