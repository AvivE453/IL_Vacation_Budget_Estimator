# etl/backup/: the test database backed up (to a fake S3) and restored into a
# fresh empty database comes back row for row, and the restored sequences
# give the next INSERT a new id. The fresh database lives on the same server
# as the test database and is dropped after the test.

import gzip
from collections import Counter

import psycopg2
import pytest
from psycopg2.extensions import make_dsn

from etl.backup.backup import TABLES, backup_all
from etl.backup.restore import restore, restore_table
from etl.common.config import DB_URL
from tests.factories import add_airline, add_exchange_rate, add_flight, add_hotel, add_saved_search

RESTORE_DB = "vacation_budget_restore_test"
DAY = "2030-01-01"


class FakeS3:
    def __init__(self):
        self.files = {}

    def put_object(self, Bucket, Key, Body):
        self.files[Key] = Body


@pytest.fixture()
def empty_db(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {RESTORE_DB} WITH (FORCE)")
        cur.execute(f"CREATE DATABASE {RESTORE_DB}")
    conn = psycopg2.connect(make_dsn(DB_URL, dbname=RESTORE_DB))
    try:
        yield conn
    finally:
        conn.close()
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE {RESTORE_DB} WITH (FORCE)")


# Every row as a tuple, counted: the same rows in any order compare equal. A
# plain cursor on the same connection, since the cur fixture returns dicts,
# which can't be counted.
def rows(cur, table):
    with cur.connection.cursor() as plain:
        plain.execute(f"SELECT * FROM {table}")
        return Counter(plain.fetchall())


# A row in every table the backup covers, beyond the seeded reference data.
def add_one_of_everything(cur):
    add_airline(cur, "ZZ", "Test Air")
    add_exchange_rate(cur, "ILS", 0.27)
    add_flight(cur, "BCN", "2030-06-01", "2030-06-08", price_usd=300)
    add_hotel(cur, "BCN", avg_usd=150)
    add_saved_search(cur, "browser-a", ["BCN"])


# The test database, with a row in every table, backed up to a fake S3 and
# downloaded into a folder, the way restore.py gets a night's files.
@pytest.fixture()
def backup_folder(cur, tmp_path):
    add_one_of_everything(cur)
    s3 = FakeS3()
    backup_all(cur, s3, "bucket", DAY)
    for key, body in s3.files.items():
        (tmp_path / key.rsplit("/", 1)[-1]).write_bytes(body)
    return tmp_path


def test_backup_covers_every_table(cur):
    cur.execute(
        "SELECT table_name FROM information_schema.tables"
        " WHERE table_schema = 'public' AND table_name <> 'schema_migrations'"
    )
    assert sorted(row["table_name"] for row in cur.fetchall()) == sorted(TABLES)


def test_backup_and_restore_round_trip_every_row(cur, empty_db, backup_folder):

    restore(empty_db, backup_folder)

    with empty_db.cursor() as restored:
        for table in TABLES:
            assert rows(restored, table) == rows(cur, table), table


def test_after_a_restore_the_next_insert_gets_a_new_id(empty_db, backup_folder):

    restore(empty_db, backup_folder)

    with empty_db.cursor() as restored:
        restored.execute("SELECT max(search_query_id) FROM search_queries")
        highest = restored.fetchone()[0]
        restored.execute("SELECT nextval(pg_get_serial_sequence('search_queries', 'search_query_id'))")
        assert restored.fetchone()[0] == highest + 1


# A database built over months can have its columns in another order than one
# built from today's migration files: the first restore drill (2026-10-26) put
# a price into depart_time. Columns are matched by the CSV header's names.
def test_restore_matches_columns_by_name_not_position(cur):
    cur.execute("CREATE TEMP TABLE pairs (a int, b text)")

    restore_table(cur, "pairs", gzip.compress(b"b,a\nx,1\n"))

    cur.execute("SELECT a, b FROM pairs")
    assert cur.fetchone() == {"a": 1, "b": "x"}


def test_restore_refuses_a_database_that_has_tables(empty_db, backup_folder):
    with empty_db.cursor() as other:
        other.execute("CREATE TABLE countries (country_code text)")

    with pytest.raises(SystemExit, match="isn't empty"):
        restore(empty_db, backup_folder)

    with empty_db.cursor() as other:
        other.execute("SELECT to_regclass('schema_migrations')")
        assert other.fetchone()[0] is None, "refused only after migrating"

