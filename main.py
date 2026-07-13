import argparse
import csv
import logging
import sys

from db.store import EventStore
from models.event import Event
from scrapers.hanabi_walker import HanabiWalker
from scrapers.timeout_tokyo import TimeoutTokyo
from scrapers.tokyo_cheapo import TokyoCheapo

logger = logging.getLogger(__name__)


def _write_events_csv(events: list[Event]) -> None:
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    writer = csv.writer(sys.stdout)
    writer.writerow(
        [
            "id",
            "source",
            "title",
            "url",
            "start_date",
            "end_date",
            "times",
            "venue",
            "latitude",
            "longitude",
            "price",
            "attributes",
            "created_at",
        ]
    )
    for e in events:
        writer.writerow(
            [
                e.id,
                e.source,
                e.title,
                e.url,
                e.start_date.isoformat() if e.start_date else "",
                e.end_date.isoformat() if e.end_date else "",
                e.times or "",
                e.venue or "",
                e.latitude,
                e.longitude,
                e.price or "",
                str(e.attributes),
                e.created_at.isoformat(),
            ]
        )


def cmd_tc(args):
    events, report = TokyoCheapo().scrape()
    logger.info(
        "Tokyo Cheapo: %d ok, %d skipped, %d errors (of %d links)",
        report.events_ok,
        report.events_skipped,
        len(report.errors),
        report.links_seen,
    )
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_with_dedup(events)
        logger.info("Tokyo Cheapo: %d rows → %s", len(events), args.db)
    else:
        _write_events_csv(events)


def cmd_hanabi(args):
    events, report = HanabiWalker(region=args.region).scrape()
    logger.info(
        "Hanabi Walker: %d ok, %d skipped, %d errors (of %d links)",
        report.events_ok,
        report.events_skipped,
        len(report.errors),
        report.links_seen,
    )
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_with_dedup(events)
        logger.info("Hanabi Walker: %d rows → %s", len(events), args.db)
    else:
        _write_events_csv(events)


def cmd_tot(args):
    events, report = TimeoutTokyo().scrape()
    logger.info(
        "Time Out Tokyo: %d ok, %d skipped, %d errors (of %d links)",
        report.events_ok,
        report.events_skipped,
        len(report.errors),
        report.links_seen,
    )
    if args.output == "db":
        with EventStore(args.db) as store:
            store.upsert_with_dedup(events)
        logger.info("Time Out Tokyo: %d rows → %s", len(events), args.db)
    else:
        _write_events_csv(events)


def cmd_all(args):
    tc_events, tc_report = TokyoCheapo().scrape()
    hanabi_events, hanabi_report = HanabiWalker(region=args.region).scrape()
    tot_events, tot_report = TimeoutTokyo().scrape()
    logger.info(
        "Tokyo Cheapo: %d ok, %d skipped, %d errors (of %d links)",
        tc_report.events_ok,
        tc_report.events_skipped,
        len(tc_report.errors),
        tc_report.links_seen,
    )
    logger.info(
        "Hanabi Walker: %d ok, %d skipped, %d errors (of %d links)",
        hanabi_report.events_ok,
        hanabi_report.events_skipped,
        len(hanabi_report.errors),
        hanabi_report.links_seen,
    )
    logger.info(
        "Time Out Tokyo: %d ok, %d skipped, %d errors (of %d links)",
        tot_report.events_ok,
        tot_report.events_skipped,
        len(tot_report.errors),
        tot_report.links_seen,
    )
    if args.output == "db":
        with EventStore(args.db) as store:
            # Un seul passage de dédup sur l'ensemble agrégé des 3 sources.
            store.upsert_with_dedup(tc_events + hanabi_events + tot_events)
        logger.info(
            "Stored %d + %d + %d rows in %s",
            len(tc_events),
            len(hanabi_events),
            len(tot_events),
            args.db,
        )
    else:
        _write_events_csv(tc_events + hanabi_events + tot_events)


def main():
    parser = argparse.ArgumentParser(description="EventMaps scraper")
    parser.add_argument("--output", choices=["csv", "db"], default="db")
    parser.add_argument("--db", default="data/events.db", metavar="PATH")

    sub = parser.add_subparsers(dest="source", required=True)

    sub.add_parser("tc", help="Scrape Tokyo Cheapo")

    p_hanabi = sub.add_parser("hanabi", help="Scrape Hanabi Walker")
    p_hanabi.add_argument("--region", default="ar0300", metavar="CODE")

    sub.add_parser("tot", help="Scrape Time Out Tokyo")

    p_all = sub.add_parser("all", help="Scrape all sources")
    p_all.add_argument("--region", default="ar0300", metavar="CODE")

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s"
    )
    args = parser.parse_args()

    if args.source == "tc":
        cmd_tc(args)
    elif args.source == "hanabi":
        cmd_hanabi(args)
    elif args.source == "tot":
        cmd_tot(args)
    elif args.source == "all":
        cmd_all(args)


if __name__ == "__main__":
    main()
