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
                (city_name, country_code, iata_code, hotel_data_city_key, city_name_he)
            VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (iata_code) DO UPDATE SET
                city_name = EXCLUDED.city_name,
                country_code = EXCLUDED.country_code,
                hotel_data_city_key = EXCLUDED.hotel_data_city_key,
                city_name_he = EXCLUDED.city_name_he
            """,
            (
                row["city_name"],
                row["country_code"],
                row["iata_code"],
                row["hotel_data_city_key"],
                # An empty cell is no Hebrew name (NULL, so the frontend shows the English one), not "".
                row["city_name_he"] or None,
            ),
        )
    return len(rows)


def main():
    with get_conn() as conn:
        with conn.cursor() as cur:
            n_destinations = load_destinations(cur)
    print(f"loaded {n_destinations} destinations")


if __name__ == "__main__":
    main()
