# Runs the migration runner against a throwaway database created on the same
# server as the dev DB (never the dev DB itself), one fresh database per test.
# Server access (and skip-vs-fail when it's down) comes from conftest.py's
# admin_conn fixture.

import shutil

import psycopg2
import pytest
from psycopg2.extensions import make_dsn

from etl.common.config import DB_URL
from etl.loaders.run_migrations import MIGRATIONS_DIR, PRE_TRACKING_MIGRATIONS, migrate

SCRATCH_DB = "vacation_budget_migrations_test"
ALL_MIGRATIONS = sorted(path.name for path in MIGRATIONS_DIR.glob("*.sql"))
TRACKED_MIGRATIONS = [name for name in ALL_MIGRATIONS if name not in PRE_TRACKING_MIGRATIONS]


@pytest.fixture()
def empty_db(admin_conn):
    with admin_conn.cursor() as cur:
        cur.execute(f"DROP DATABASE IF EXISTS {SCRATCH_DB}")
        cur.execute(f"CREATE DATABASE {SCRATCH_DB}")
    conn = psycopg2.connect(make_dsn(DB_URL, dbname=SCRATCH_DB))
    try:
        yield conn
    finally:
        conn.close()
        with admin_conn.cursor() as cur:
            cur.execute(f"DROP DATABASE {SCRATCH_DB}")


@pytest.fixture()
def migrations_copy(tmp_path):
    for path in MIGRATIONS_DIR.glob("*.sql"):
        shutil.copy(path, tmp_path)
    return tmp_path


def _tracked(conn):
    with conn, conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations ORDER BY filename")
        return [row[0] for row in cur.fetchall()]


def _table_exists(conn, name):
    with conn, conn.cursor() as cur:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (name,))
        return cur.fetchone()[0]


def test_empty_database_applies_every_migration(empty_db):
    recorded, applied = migrate(empty_db)

    assert recorded == []
    assert applied == ALL_MIGRATIONS
    assert _tracked(empty_db) == ALL_MIGRATIONS
    assert _table_exists(empty_db, "search_results")


def test_second_run_applies_nothing(empty_db):
    migrate(empty_db)

    assert migrate(empty_db) == ([], [])


def test_existing_untracked_schema_is_recorded_not_rerun(empty_db):
    with empty_db, empty_db.cursor() as cur:
        for filename in PRE_TRACKING_MIGRATIONS:
            cur.execute((MIGRATIONS_DIR / filename).read_text())
        cur.execute("INSERT INTO countries (country_code, country_name) VALUES ('IL', 'Israel')")

    recorded, applied = migrate(empty_db)

    assert recorded == PRE_TRACKING_MIGRATIONS
    assert applied == TRACKED_MIGRATIONS
    with empty_db, empty_db.cursor() as cur:
        cur.execute("SELECT country_name FROM countries WHERE country_code = 'IL'")
        assert cur.fetchone() == ("Israel",)


def test_only_new_migration_runs(empty_db, migrations_copy):
    migrate(empty_db, migrations_copy)
    (migrations_copy / "006_new_table.sql").write_text("CREATE TABLE new_table (id INT);")

    recorded, applied = migrate(empty_db, migrations_copy)

    assert recorded == []
    assert applied == ["006_new_table.sql"]
    assert _table_exists(empty_db, "new_table")


def test_failed_migration_rolls_back_only_itself(empty_db, migrations_copy):
    migrate(empty_db, migrations_copy)
    (migrations_copy / "006_good.sql").write_text("CREATE TABLE good_table (id INT);")
    (migrations_copy / "007_bad.sql").write_text("CREATE TABLE bad_table (id INT); SELECT 1 / 0;")

    with pytest.raises(psycopg2.errors.DivisionByZero):
        migrate(empty_db, migrations_copy)

    assert _tracked(empty_db)[-1] == "006_good.sql"
    assert _table_exists(empty_db, "good_table")
    assert not _table_exists(empty_db, "bad_table")
