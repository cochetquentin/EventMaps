from fastapi import APIRouter, BackgroundTasks, Query

from db.store import EventStore
from main import _explode_locations, _to_hanabi_events, _to_tc_events
from scrapers.hanabi_walker import HanabiWalker
from scrapers.tokyo_cheapo import TokyoCheapo

router = APIRouter()

DB_PATH = "data/events.db"
_scraping = False


def _do_scrape(source: str, region: str) -> None:
    global _scraping
    _scraping = True
    try:
        with EventStore(DB_PATH) as store:
            if source in ("tc", "all"):
                raw = _explode_locations(TokyoCheapo().scrape_all())
                store.upsert_tokyo_cheapo(_to_tc_events(raw))
            if source in ("hanabi", "all"):
                raw = HanabiWalker(region=region).scrape_all()
                store.upsert_hanabi(_to_hanabi_events(raw))
    finally:
        _scraping = False


@router.post("")
def trigger_scrape(
    background_tasks: BackgroundTasks,
    source: str = Query("all", description="tc | hanabi | all"),
    region: str = Query("ar0300"),
):
    if _scraping:
        return {"status": "already_running"}
    background_tasks.add_task(_do_scrape, source, region)
    return {"status": "started"}


@router.get("/status")
def scrape_status():
    return {"running": _scraping}
