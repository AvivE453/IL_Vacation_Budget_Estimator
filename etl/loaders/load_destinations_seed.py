# One-time load of sql/seed/destinations_seed.csv into the destinations crosswalk table.
#
# Run with: uv run python -m etl.loaders.load_destinations_seed

import csv
import pathlib

from etl.common.db import get_conn

SEED_PATH = pathlib.Path(__file__).resolve().parent.parent.parent / "sql" / "seed" / "destinations_seed.csv"


def load_destinations(cur):
    with open(SEED_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        cur.execute(
            """
            INSERT INTO destinations
                (city_name, iata_code, city_name_he)
            VALUES (%s, %s, %s)
            ON CONFLICT (iata_code) DO UPDATE SET
                city_name = EXCLUDED.city_name,
                city_name_he = EXCLUDED.city_name_he
            """,
            (
                row["city_name"],
                row["iata_code"],
                # An empty cell is no Hebrew name (NULL, so the frontend shows the English one), not "".
                row["city_name_he"] or None,
            ),
        )
    # The CSV is the list of destinations: one removed from it stops being
    # collected, but its row stays, so its price history isn't lost.
    cur.execute(
        "UPDATE destinations SET is_active = (iata_code = ANY(%s))",
        ([row["iata_code"] for row in rows],),
    )
    return len(rows)


def main():
    with get_conn() as conn:
        with conn.cursor() as cur:
            n_destinations = load_destinations(cur)
    print(f"loaded {n_destinations} destinations")


if __name__ == "__main__":
    main()
