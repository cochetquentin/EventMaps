from datetime import date as DateType
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from config import settings
from db.store import EventStore
from models.event import Event

router = APIRouter()


@router.get("", response_model=list[Event])
def list_events(
    source: Literal["tc", "hanabi"] | None = Query(None),
    date: DateType | None = Query(None, description="YYYY-MM-DD"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    date_str = date.isoformat() if date else None
    with EventStore(settings.db_path) as store:
        return store.get_events(source=source, date=date_str, limit=limit, offset=offset)


@router.get("/{event_id}", response_model=Event)
def get_event(event_id: str):
    with EventStore(settings.db_path) as store:
        event = store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
