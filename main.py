import argparse
import csv
import sys

from scrapers.tokyo_cheapo import TokyoCheapo
from scrapers.hanabi_walker import HanabiWalker
from db.store import EventStore


def _explode_locations(events: list[dict]) -> list[dict]:
    flat = []
    for e in events:
        locations = e["locations"] or [{"name": "", "lat": None, "lng": None}]
        for loc in locations:
            flat.append({**e, "location_name": loc["name"], "lat": loc.get("lat"), "lng": loc.get("lng")})
    return flat


def _write_tc_csv(events: list[dict]) -> None:
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    writer = csv.writer(sys.stdout)
    writer.writerow(["title", "start_date", "end_date", "start_time", "end_time", "price",
                     "categories", "tags", "official_link", "url", "location_name", "lat", "lng"])
    for e in events:
        writer.writerow([
            e["title"], e["start_date"], e["end_date"], e["start_time"], e["end_time"],
            e["price"] or "",
            ", ".join(e["categories"]),
            ", ".join(e["tags"]),
            e["official_link"] or "",
            e["url"], e["location_name"], e.get("lat", ""), e.get("lng", ""),
        ])


_HANABI_FIELDS = [
    "title", "fireworks_count", "fireworks_duration", "expected_crowd",
    "start_time", "end_time", "rain_policy", "paid_seating", "paid_seating_details",
    "food_stalls", "notes", "venue", "access", "parking", "official_site", "official_x",
    "url", "lat", "lng", "date", "contact", "contact2",
]


def _write_hanabi_csv(events: list[dict]) -> None:
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    writer = csv.writer(sys.stdout)
    writer.writerow(_HANABI_FIELDS)
    for e in events:
        writer.writerow([e.get(f, "") or "" for f in _HANABI_FIELDS])


def cmd_tc(args):
    events = _explode_locations(TokyoCheapo().scrape_all())
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_tokyo_cheapo(events)
        print(f"Tokyo Cheapo: {len(events)} rows → {args.db}", file=sys.stderr)
    else:
        _write_tc_csv(events)


def cmd_hanabi(args):
    events = HanabiWalker(region=args.region).scrape_all()
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_hanabi(events)
        print(f"Hanabi Walker: {len(events)} rows → {args.db}", file=sys.stderr)
    else:
        _write_hanabi_csv(events)


def cmd_all(args):
    tc_events = _explode_locations(TokyoCheapo().scrape_all())
    hanabi_events = HanabiWalker(region=args.region).scrape_all()
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_tokyo_cheapo(tc_events)
            store.upsert_hanabi(hanabi_events)
        print(f"Tokyo Cheapo: {len(tc_events)} rows", file=sys.stderr)
        print(f"Hanabi Walker: {len(hanabi_events)} rows", file=sys.stderr)
        print(f"Stored in {args.db}", file=sys.stderr)
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

    args = parser.parse_args()

    if args.source == "tc":
        cmd_tc(args)
    elif args.source == "hanabi":
        cmd_hanabi(args)
    elif args.source == "all":
        cmd_all(args)


if __name__ == "__main__":
    main()
