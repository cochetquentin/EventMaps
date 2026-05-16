from fastapi import APIRouter, HTTPException, Query

from db.store import EventStore
from models.event import Event, HanabiEvent, TokyoCheapoEvent

router = APIRouter()

DB_PATH = "data/events.db"


@router.get("", response_model=list[Event])
def list_events(
    source: str | None = Query(None, description="tc | hanabi"),
    date: str | None = Query(None, description="YYYY/MM/DD"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
):
    with EventStore(DB_PATH) as store:
        return store.get_events(source=source, date=date, limit=limit, offset=offset)


@router.get("/{event_id}", response_model=Event)
def get_event(event_id: str):
    with EventStore(DB_PATH) as store:
        event = store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
