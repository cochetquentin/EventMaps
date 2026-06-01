import argparse
import csv
import logging
import sys
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

from scrapers.tokyo_cheapo import TokyoCheapo
from scrapers.hanabi_walker import HanabiWalker
from db.store import EventStore, _make_id
from models.event import HanabiEvent, TokyoCheapoEvent


def _explode_locations(events: list[dict]) -> list[dict]:
    flat = []
    for e in events:
        locations = e["locations"] or [{"name": "", "lat": None, "lng": None}]
        for loc in locations:
            flat.append({**e, "location_name": loc["name"], "lat": loc.get("lat"), "lng": loc.get("lng")})
    return flat


def _to_tc_events(flat_events: list[dict]) -> list[TokyoCheapoEvent]:
    now = datetime.now(timezone.utc)
    return [
        TokyoCheapoEvent(
            id=_make_id([e["url"], e.get("location_name") or ""]),
            scraped_at=now,
            title=e.get("title", ""),
            url=e["url"],
            start_date=e.get("start_date", ""),
            end_date=e.get("end_date") or None,
            start_time=e.get("start_time") or None,
            end_time=e.get("end_time") or None,
            price=e.get("price") or None,
            categories=e.get("categories") or [],
            tags=e.get("tags") or [],
            official_link=e.get("official_link") or None,
            location_name=e.get("location_name") or None,
            lat=e.get("lat"),
            lng=e.get("lng"),
        )
        for e in flat_events
    ]


def _to_hanabi_events(events: list[dict]) -> list[HanabiEvent]:
    now = datetime.now(timezone.utc)
    return [
        HanabiEvent(
            id=_make_id([e["url"], e.get("date") or ""]),
            scraped_at=now,
            title=e.get("title", ""),
            url=e["url"],
            start_date=e.get("date", ""),
            start_time=e.get("start_time") or None,
            end_time=e.get("end_time") or None,
            lat=e.get("lat"),
            lng=e.get("lng"),
            fireworks_count=e.get("fireworks_count") or None,
            fireworks_duration=e.get("fireworks_duration") or None,
            expected_crowd=e.get("expected_crowd") or None,
            rain_policy=e.get("rain_policy") or None,
            paid_seating=e.get("paid_seating") or None,
            paid_seating_details=e.get("paid_seating_details") or None,
            food_stalls=e.get("food_stalls") or None,
            notes=e.get("notes") or None,
            venue=e.get("venue") or None,
            access=e.get("access") or None,
            parking=e.get("parking") or None,
            official_site=e.get("official_site") or None,
            official_x=e.get("official_x") or None,
            contact=e.get("contact") or None,
            contact2=e.get("contact2") or None,
        )
        for e in events
    ]


def _write_tc_csv(events: list[TokyoCheapoEvent]) -> None:
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    writer = csv.writer(sys.stdout)
    writer.writerow(["title", "start_date", "end_date", "start_time", "end_time", "price",
                     "categories", "tags", "official_link", "url", "location_name", "lat", "lng"])
    for e in events:
        writer.writerow([
            e.title, e.start_date, e.end_date, e.start_time, e.end_time,
            e.price or "",
            ", ".join(e.categories),
            ", ".join(e.tags),
            e.official_link or "",
            e.url, e.location_name, e.lat, e.lng,
        ])


_HANABI_FIELDS = [
    "title", "fireworks_count", "fireworks_duration", "expected_crowd",
    "start_time", "end_time", "rain_policy", "paid_seating", "paid_seating_details",
    "food_stalls", "notes", "venue", "access", "parking", "official_site", "official_x",
    "url", "lat", "lng", "date", "contact", "contact2",
]


def _write_hanabi_csv(events: list[HanabiEvent]) -> None:
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    writer = csv.writer(sys.stdout)
    writer.writerow(_HANABI_FIELDS)
    for e in events:
        writer.writerow([getattr(e, f, "") or "" for f in _HANABI_FIELDS])


def cmd_tc(args):
    raw = _explode_locations(TokyoCheapo().scrape_all())
    events = _to_tc_events(raw)
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_tokyo_cheapo(events)
        logger.info("Tokyo Cheapo: %d rows → %s", len(events), args.db)
    else:
        _write_tc_csv(events)


def cmd_hanabi(args):
    raw = HanabiWalker(region=args.region).scrape_all()
    events = _to_hanabi_events(raw)
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_hanabi(events)
        logger.info("Hanabi Walker: %d rows → %s", len(events), args.db)
    else:
        _write_hanabi_csv(events)


def cmd_all(args):
    tc_raw = _explode_locations(TokyoCheapo().scrape_all())
    hanabi_raw = HanabiWalker(region=args.region).scrape_all()
    tc_events = _to_tc_events(tc_raw)
    hanabi_events = _to_hanabi_events(hanabi_raw)
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_tokyo_cheapo(tc_events)
            store.upsert_hanabi(hanabi_events)
        logger.info("Tokyo Cheapo: %d rows", len(tc_events))
        logger.info("Hanabi Walker: %d rows", len(hanabi_events))
        logger.info("Stored in %s", args.db)
    else:
        _write_tc_csv(tc_events)
        _write_hanabi_csv(hanabi_events)


def main():
    parser = argparse.ArgumentParser(description="EventMaps scraper")
    parser.add_argument("--output", choices=["csv", "db"], default="db")
    parser.add_argument("--db", default="data/events.db", metavar="PATH")

    sub = parser.add_subparsers(dest="source", required=True)

    sub.add_parser("tc", help="Scrape Tokyo Cheapo")

    p_hanabi = sub.add_parser("hanabi", help="Scrape Hanabi Walker")
    p_hanabi.add_argument("--region", default="ar0300", metavar="CODE")

    p_all = sub.add_parser("all", help="Scrape all sources")
    p_all.add_argument("--region", default="ar0300", metavar="CODE")

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s")
    args = parser.parse_args()

    if args.source == "tc":
        cmd_tc(args)
    elif args.source == "hanabi":
        cmd_hanabi(args)
    elif args.source == "all":
        cmd_all(args)


if __name__ == "__main__":
    main()
