# The API for the Playwright end-to-end tests (frontend/e2e/): rebuilds
# vacation_budget_e2e - a separate database on the same server, like the
# pytest one - with fixed flights, hotels and an exchange rate, then serves
# the API on it with live flight search switched off, so every run sees
# exactly the same data.
#
# Run with: uv run python -m tests.e2e_server [port]   (Playwright starts it)

import os
import sys

import psycopg2
import psycopg2.extras
from psycopg2.extensions import make_dsn

from etl.common.config import DB_URL
from etl.loaders.load_airports import load_airports, load_countries
from etl.loaders.load_destinations_seed import load_destinations
from etl.loaders.run_migrations import migrate
from tests.e2e_data import add_e2e_data

E2E_DB = "vacation_budget_e2e"


def rebuild_database():
    admin = psycopg2.connect(DB_URL)
    admin.autocommit = True  # CREATE/DROP DATABASE can't run inside a transaction
    with admin.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {E2E_DB} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {E2E_DB}")
    admin.close()

    url = make_dsn(DB_URL, dbname=E2E_DB)
    conn = psycopg2.connect(url)
    try:
        migrate(conn)
        with conn, conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            load_countries(cur)
            load_airports(cur)
            load_destinations(cur)
            add_e2e_data(cur)
    finally:
        conn.close()
    return url


if __name__ == "__main__":
    port = sys.argv[1] if len(sys.argv) > 1 else "8001"
    url = rebuild_database()
    # A fresh process, not uvicorn.run() here: etl.common.config has already
    # read DB_URL (the dev database) into a constant, so only a new process
    # with the new environment points the app at vacation_budget_e2e.
    env = {**os.environ, "DB_URL": url, "LIVE_FLIGHT_SEARCH": "off"}
    os.execvpe(sys.executable, [sys.executable, "-m", "uvicorn", "api.main:app", "--port", port], env)
