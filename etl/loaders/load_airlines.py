# One-time load of the airlines reference table from Travelpayouts' free,
# public airlines.json (no authentication needed) - same idea as load_airports.py, but
# pulled live from the API instead of a checked-in seed CSV, since this is
# Travelpayouts' own canonical IATA-code-to-name mapping and there's no reason
# to hand-curate it.
#
# Run with: uv run python -m etl.loaders.load_airlines

import requests

from etl.common.db import get_conn

AIRLINES_URL = "https://api.travelpayouts.com/data/en/airlines.json"


def load_airlines(cur):
    resp = requests.get(AIRLINES_URL, timeout=15)
    resp.raise_for_status()
    rows = [r for r in resp.json() if r.get("code") and r.get("name")]

    for row in rows:
        cur.execute(
            """
            INSERT INTO airlines (airline_code, airline_name, is_lowcost)
            VALUES (%s, %s, %s)
            ON CONFLICT (airline_code) DO UPDATE SET
                airline_name = EXCLUDED.airline_name,
                is_lowcost = EXCLUDED.is_lowcost
            """,
            (row["code"], row["name"], bool(row.get("is_lowcost"))),
        )
    return len(rows)


def main():
    with get_conn() as conn:
        with conn.cursor() as cur:
            n = load_airlines(cur)
    print(f"loaded {n} airlines")


if __name__ == "__main__":
    main()
