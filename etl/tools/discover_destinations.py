# Lists the destination cities that real searches from TLV actually reach,
# to pick new rows for sql/seed/destinations_seed.csv. Read-only: prints a
# report, writes nothing.
#
# One prices_for_dates call per month with no destination returns a sample
# of the cached round trips to every city (not all of them - a targeted call
# per destination returns far more), which is enough to rank demand. The
# cache leans towards Russian-speaking users, so judge each city as an
# Israeli vacation destination before adding it, don't add the list blindly.
#
# Run with: uv run python -m etl.tools.discover_destinations

import csv
import datetime
from collections import defaultdict

from etl.collectors.flights_collector import ORIGIN_IATA, fetch_round_trips
from etl.loaders.load_destinations_seed import SEED_PATH

MONTHS_AHEAD = 12


def months_ahead(today, n):
    months = []
    for offset in range(n):
        index = today.month - 1 + offset
        months.append(f"{today.year + index // 12:04d}-{index % 12 + 1:02d}")
    return months


def main():
    seeded = {row["iata_code"] for row in csv.DictReader(open(SEED_PATH, newline="", encoding="utf-8"))}
    trips = defaultdict(int)
    months_seen = defaultdict(set)
    cheapest = {}

    for month in months_ahead(datetime.date.today(), MONTHS_AHEAD):
        payload = fetch_round_trips(ORIGIN_IATA, None, month)
        for trip in payload.get("data", []):
            airport = trip["destination_airport"]
            trips[airport] += 1
            months_seen[airport].add(month)
            cheapest[airport] = min(cheapest.get(airport, trip["price"]), trip["price"])

    ranked = sorted(trips, key=lambda a: (-len(months_seen[a]), -trips[a]))
    print(f"{'airport':<8}{'seeded':<8}{'months':>7}{'trips':>7}{'min $':>8}")
    for airport in ranked:
        seeded_mark = "yes" if airport in seeded else ""
        print(f"{airport:<8}{seeded_mark:<8}{len(months_seen[airport]):>7}{trips[airport]:>7}{cheapest[airport]:>8}")


if __name__ == "__main__":
    main()
