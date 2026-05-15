import csv
import sys

from scrapers.tokyo_cheapo import TokyoCheapo


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    tc = TokyoCheapo()
    events = tc.scrape_all()

    writer = csv.writer(sys.stdout)
    writer.writerow(["title", "date", "time", "price", "categories", "tags", "official_link", "location_name", "lat", "lng"])

    for e in events:
        base = [
            e["title"],
            e["date"],
            e["time"],
            e["price"],
            ", ".join(e["categories"]),
            ", ".join(e["tags"]),
            e["official_link"] or "",
        ]
        if e["locations"]:
            for loc in e["locations"]:
                writer.writerow(base + [loc["name"], loc["lat"], loc["lng"]])
        else:
            writer.writerow(base + ["", "", ""])


if __name__ == "__main__":
    main()
