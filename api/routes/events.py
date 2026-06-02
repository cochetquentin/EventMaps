from datetime import date as DateType, timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from config import settings
from db.store import EventStore
from models.event import Event

try:
    from icalendar import Calendar, Event as ICSEvent
    _ICAL_AVAILABLE = True
except ImportError:
    _ICAL_AVAILABLE = False

router = APIRouter()


def _parse_bbox(s: str) -> tuple[float, float, float, float]:
    parts = s.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=422, detail="bbox: 4 floats attendus (min_lon,min_lat,max_lon,max_lat)")
    try:
        min_lon, min_lat, max_lon, max_lat = map(float, parts)
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox: valeurs float invalides")
    if not (-180 <= min_lon <= max_lon <= 180):
        raise HTTPException(status_code=422, detail="bbox: plage de longitude invalide")
    if not (-90 <= min_lat <= max_lat <= 90):
        raise HTTPException(status_code=422, detail="bbox: plage de latitude invalide")
    return min_lon, min_lat, max_lon, max_lat


@router.get("", response_model=list[Event])
def list_events(
    source: Literal["tc", "hanabi"] | None = Query(None),
    date: DateType | None = Query(None, description="YYYY-MM-DD"),
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
):
    date_str = date.isoformat() if date else None
    upcoming = date_str is None
    parsed_bbox = _parse_bbox(bbox) if bbox else None
    with EventStore(settings.db_path) as store:
        return store.get_events(
            source=source,
            date=date_str,
            bbox=parsed_bbox,
            upcoming=upcoming,
            limit=limit,
            offset=offset,
        )


@router.get("/{event_id}.ics")
def export_event_ical(event_id: str):
    if not _ICAL_AVAILABLE:
        raise HTTPException(status_code=501, detail="icalendar non installé")
    with EventStore(settings.db_path) as store:
        event = store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")

    cal = Calendar()
    cal.add("prodid", "-//EventMaps//Tokyo Events//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")

    ics_event = ICSEvent()
    ics_event.add("summary", event.title)
    ics_event.add("uid", f"{event.id}@eventmaps")
    if event.start_date:
        ics_event.add("dtstart", event.start_date)
    end = event.end_date or event.start_date
    if end:
        ics_event.add("dtend", end + timedelta(days=1))
    ics_event.add("url", event.url)
    location = event.venue or event.attributes.get("location_name")
    if location:
        ics_event.add("location", location)
    if event.price:
        ics_event.add("description", event.price)
    cal.add_component(ics_event)

    return Response(
        content=cal.to_ical(),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{event_id}.ics"'},
    )


@router.get("/{event_id}", response_model=Event)
def get_event(event_id: str):
    with EventStore(settings.db_path) as store:
        event = store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    return event
