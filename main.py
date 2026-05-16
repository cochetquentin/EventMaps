import csv
import sys

from scrapers.tokyo_cheapo import TokyoCheapo


def main():
    sys.stdout.reconfigure(encoding="utf-8", newline="")
    tc = TokyoCheapo()
    events = tc.scrape_all()

    writer = csv.writer(sys.stdout)
    writer.writerow(["title", "start_date", "end_date", "start_time", "end_time", "price",
                     "categories", "tags", "official_link", "url", "location_name", "lat", "lng"])

    for e in events:
        base = [
            e["title"],
            e["start_date"],
            e["end_date"],
            e["start_time"],
            e["end_time"],
            e["price"] or "",
            ", ".join(e["categories"]),
            ", ".join(e["tags"]),
            e["official_link"] or "",
            e["url"],
        ]
        locations = e["locations"] or [{"name": "", "lat": "", "lng": ""}]
        for loc in locations:
            writer.writerow(base + [loc["name"], loc.get("lat", ""), loc.get("lng", "")])


if __name__ == "__main__":
    main()
