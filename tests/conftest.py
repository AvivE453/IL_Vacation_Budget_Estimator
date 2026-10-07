# Tests run against vacation_budget_test, a separate database on the same
# server as the dev DB, rebuilt from scratch at the start of every run:
# migrations + the reference-data seed CSVs (countries, airports,
# destinations), nothing else. Each test inserts the flights/hotels it needs
# (tests/factories.py) through the `cur` fixture, whose transaction is rolled
# back afterwards - so tests never see each other's rows or any dev data.
#
# The database is left in place after the run so it can be inspected; the
# next run drops it first.

import os

import psycopg2
import psycopg2.extras
import pytest
from psycopg2.extensions import make_dsn

from etl.common.config import DB_URL
from etl.loaders.load_airports import load_airports, load_countries
from etl.loaders.load_destinations_seed import load_destinations
from etl.loaders.run_migrations import migrate

TEST_DB = "vacation_budget_test"


# Connection to the server itself, for creating/dropping test databases.
# Locally, no server just skips the DB tests. In CI (GitHub Actions sets
# CI=true) a skip would turn into a green run that tested nothing, so it fails.
@pytest.fixture(scope="session")
def admin_conn():
    try:
        conn = psycopg2.connect(DB_URL)
    except psycopg2.OperationalError as e:
        message = f"database server not reachable at {DB_URL}: {e}"
        if os.environ.get("CI"):
            pytest.fail(message)
        pytest.skip(message)
    conn.autocommit = True  # CREATE/DROP DATABASE can't run inside a transaction
    yield conn
    conn.close()


@pytest.fixture(scope="session")
def test_db_url(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
        cur.execute(f"CREATE DATABASE {TEST_DB}")
    url = make_dsn(DB_URL, dbname=TEST_DB)
    conn = psycopg2.connect(url)
    try:
        migrate(conn)
        with conn, conn.cursor() as cur:
            load_countries(cur)
            load_airports(cur)
            load_destinations(cur)
    finally:
        conn.close()
    return url


# For code that opens its own connection through etl.common.db and commits for
# real (the collectors' main()): points it at the test database, and deletes
# what it wrote afterwards since there's no transaction to roll back.
@pytest.fixture()
def committing_db(test_db_url, monkeypatch):
    monkeypatch.setattr("etl.common.db.DB_URL", test_db_url)
    yield test_db_url
    conn = psycopg2.connect(test_db_url)
    with conn, conn.cursor() as c:
        c.execute("DELETE FROM flight_price_observations")
        c.execute("DELETE FROM hotel_prices")
    conn.close()


@pytest.fixture()
def cur(test_db_url):
    conn = psycopg2.connect(test_db_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            yield c
    finally:
        conn.rollback()
        conn.close()
