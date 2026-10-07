# One-time load of sql/seed/countries_seed.csv and sql/seed/airports_seed.csv.
#
# Run with: uv run python -m etl.loaders.load_airports

import csv
import pathlib

from etl.common.db import get_conn

SEED_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "sql" / "seed"


def load_countries(cur):
    with open(SEED_DIR / "countries_seed.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        cur.execute(
            """
            INSERT INTO countries (country_code, country_name)
            VALUES (%s, %s)
            ON CONFLICT (country_code) DO UPDATE SET country_name = EXCLUDED.country_name
            """,
            (row["country_code"], row["country_name"]),
        )
    return len(rows)


def load_airports(cur):
    with open(SEED_DIR / "airports_seed.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    for row in rows:
        cur.execute(
            """
            INSERT INTO airports (iata_code, airport_name, city_name, country_code, latitude, longitude)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (iata_code) DO UPDATE SET
                airport_name = EXCLUDED.airport_name,
                city_name = EXCLUDED.city_name,
                country_code = EXCLUDED.country_code,
                latitude = EXCLUDED.latitude,
                longitude = EXCLUDED.longitude
            """,
            (
                row["iata_code"],
                row["airport_name"],
                row["city_name"],
                row["country_code"],
                row["latitude"] or None,
                row["longitude"] or None,
            ),
        )
    return len(rows)


def main():
    with get_conn() as conn:
        with conn.cursor() as cur:
            n_countries = load_countries(cur)
            n_airports = load_airports(cur)
    print(f"loaded {n_countries} countries, {n_airports} airports")


if __name__ == "__main__":
    main()
