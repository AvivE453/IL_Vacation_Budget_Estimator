# Tests run against vacation_budget_test, a separate database on the same
# server as the dev DB, rebuilt from scratch at the start of every run:
# migrations + the reference-data seed CSVs (countries, airports,
# destinations), nothing else. Each test inserts the flights/hotels it needs
# (tests/factories.py) through the `cur` fixture, whose transaction is rolled
# back afterwards - so tests never see each other's rows or any dev data.
#
# The database is left in place after the run so it can be inspected; the
# next run drops it first.

import psycopg2
import psycopg2.extras
import pytest
from psycopg2.extensions import make_dsn

from etl.common.config import DB_URL
from etl.loaders.load_airports import load_airports, load_countries
from etl.loaders.load_destinations_seed import load_destinations
from etl.loaders.run_migrations import migrate

TEST_DB = "vacation_budget_test"


def _recreate_test_db():
    try:
        admin = psycopg2.connect(DB_URL)
    except psycopg2.OperationalError as e:
        pytest.skip(f"database server not reachable at {DB_URL}: {e}")
    admin.autocommit = True  # CREATE/DROP DATABASE can't run inside a transaction
    try:
        with admin.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            cur.execute(f"CREATE DATABASE {TEST_DB}")
    finally:
        admin.close()


@pytest.fixture(scope="session")
def test_db_url():
    _recreate_test_db()
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


@pytest.fixture()
def cur(test_db_url):
    conn = psycopg2.connect(test_db_url)
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            yield c
    finally:
        conn.rollback()
        conn.close()
