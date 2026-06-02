import argparse
import csv
import logging
import sys

logger = logging.getLogger(__name__)

from scrapers.tokyo_cheapo import TokyoCheapo
from scrapers.hanabi_walker import HanabiWalker
from db.store import EventStore
from models.event import Event


def _write_events_csv(events: list[Event]) -> None:
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    writer = csv.writer(sys.stdout)
    writer.writerow([
        "id", "source", "title", "url", "start_date", "end_date",
        "times", "venue", "latitude", "longitude", "price", "attributes", "created_at",
    ])
    for e in events:
        writer.writerow([
            e.id, e.source, e.title, e.url,
            e.start_date.isoformat() if e.start_date else "",
            e.end_date.isoformat() if e.end_date else "",
            e.times or "", e.venue or "",
            e.latitude, e.longitude, e.price or "",
            str(e.attributes), e.created_at.isoformat(),
        ])


def cmd_tc(args):
    events = TokyoCheapo().scrape()
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_events(events)
        logger.info("Tokyo Cheapo: %d rows → %s", len(events), args.db)
    else:
        _write_events_csv(events)


def cmd_hanabi(args):
    events = HanabiWalker(region=args.region).scrape()
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_events(events)
        logger.info("Hanabi Walker: %d rows → %s", len(events), args.db)
    else:
        _write_events_csv(events)


def cmd_all(args):
    tc_events = TokyoCheapo().scrape()
    hanabi_events = HanabiWalker(region=args.region).scrape()
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_events(tc_events)
            store.upsert_events(hanabi_events)
        logger.info("Tokyo Cheapo: %d rows", len(tc_events))
        logger.info("Hanabi Walker: %d rows", len(hanabi_events))
        logger.info("Stored in %s", args.db)
    else:
        _write_events_csv(tc_events + hanabi_events)


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
