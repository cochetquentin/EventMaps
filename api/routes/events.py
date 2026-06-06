from datetime import date as DateType
from datetime import timedelta
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from config import settings
from db.store import EventStore
from models.event import Event

try:
    from icalendar import Calendar
    from icalendar import Event as ICSEvent

    _ICAL_AVAILABLE = True
except ImportError:
    _ICAL_AVAILABLE = False

router = APIRouter()


def _parse_bbox(s: str) -> tuple[float, float, float, float]:
    parts = s.split(",")
    if len(parts) != 4:
        raise HTTPException(
            status_code=422, detail="bbox: 4 floats attendus (min_lon,min_lat,max_lon,max_lat)"
        )
    try:
        min_lon, min_lat, max_lon, max_lat = map(float, parts)
    except ValueError:
        raise HTTPException(status_code=422, detail="bbox: valeurs float invalides")
    if not (-180 <= min_lon <= max_lon <= 180):
        raise HTTPException(status_code=422, detail="bbox: plage de longitude invalide")
    if not (-90 <= min_lat <= max_lat <= 90):
        raise HTTPException(status_code=422, detail="bbox: plage de latitude invalide")
    return min_lon, min_lat, max_lon, max_lat


def _build_ics_event(event: Event) -> "ICSEvent":
    ics_event = ICSEvent()
    ics_event.add("summary", event.title)
    ics_event.add("uid", f"{event.id}@eventmaps")
    if event.start_date:
        ics_event.add("dtstart", event.start_date)
    end = event.end_date or event.start_date
    if end:
        ics_event.add("dtend", end + timedelta(days=1))
    ics_event.add("url", event.url)
    location = event.venue or getattr(event.attributes, "location_name", None)
    if location:
        ics_event.add("location", location)
    if event.price:
        ics_event.add("description", event.price)
    return ics_event


def _build_calendar(events: list[Event]) -> "Calendar":
    cal = Calendar()
    cal.add("prodid", "-//EventMaps//Tokyo Events//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")
    for event in events:
        cal.add_component(_build_ics_event(event))
    return cal


@router.get("", response_model=list[Event])
def list_events(
    source: Literal["tc", "hanabi"] | None = Query(None),
    date: DateType | None = Query(None, description="YYYY-MM-DD overlap filter"),
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    start_from: DateType | None = Query(
        None, description="Lower bound on event end/start date (overrides upcoming default)"
    ),
    start_to: DateType | None = Query(
        None, description="Upper bound on event start date (overrides upcoming default)"
    ),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="Recherche texte sur le titre (LIKE)"),
    category: str | None = Query(None, description="Filtre par catégorie (événements TC)"),
):
    date_str = date.isoformat() if date else None
    start_from_str = start_from.isoformat() if start_from else None
    start_to_str = start_to.isoformat() if start_to else None
    upcoming = date_str is None and start_from_str is None and start_to_str is None
    parsed_bbox = _parse_bbox(bbox) if bbox else None
    with EventStore(settings.db_path) as store:
        return store.get_events(
            source=source,
            date=date_str,
            bbox=parsed_bbox,
            upcoming=upcoming,
            start_from=start_from_str,
            start_to=start_to_str,
            limit=limit,
            offset=offset,
            q=q or None,
            category=category or None,
        )


_ICS_PAGE = 500
_ICS_MAX = 5000


@router.get(".ics")
def export_events_ical(
    source: Literal["tc", "hanabi"] | None = Query(None),
    date: DateType | None = Query(None, description="YYYY-MM-DD overlap filter"),
    bbox: str | None = Query(None, description="min_lon,min_lat,max_lon,max_lat"),
    start_from: DateType | None = Query(None),
    start_to: DateType | None = Query(None),
    q: str | None = Query(None),
    category: str | None = Query(None),
):
    if not _ICAL_AVAILABLE:
        raise HTTPException(status_code=501, detail="icalendar non installé")
    date_str = date.isoformat() if date else None
    start_from_str = start_from.isoformat() if start_from else None
    start_to_str = start_to.isoformat() if start_to else None
    upcoming = date_str is None and start_from_str is None and start_to_str is None
    parsed_bbox = _parse_bbox(bbox) if bbox else None
    all_events: list[Event] = []
    offset = 0
    with EventStore(settings.db_path) as store:
        while len(all_events) < _ICS_MAX:
            page = store.get_events(
                source=source,
                date=date_str,
                bbox=parsed_bbox,
                upcoming=upcoming,
                start_from=start_from_str,
                start_to=start_to_str,
                limit=_ICS_PAGE,
                offset=offset,
                q=q or None,
                category=category or None,
            )
            all_events.extend(page)
            if len(page) < _ICS_PAGE:
                break
            offset += _ICS_PAGE
    cal = _build_calendar(all_events)
    return Response(
        content=cal.to_ical(),
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="events.ics"'},
    )


@router.get("/{event_id}.ics")
def export_event_ical(event_id: str):
    if not _ICAL_AVAILABLE:
        raise HTTPException(status_code=501, detail="icalendar non installé")
    with EventStore(settings.db_path) as store:
        event = store.get_event(event_id)
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    cal = _build_calendar([event])
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
