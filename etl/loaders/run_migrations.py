# Applies each .sql file in sql/migrations/ that hasn't run yet, in filename
# order, and records it in schema_migrations. Safe to rerun anytime.

# Run with: uv run python -m etl.loaders.run_migrations

# Never edit a migration that has already been applied anywhere - only the
# filename is tracked, so the change would silently never run. Add a new
# numbered file instead.

import pathlib

from etl.common.db import get_conn

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent.parent.parent / "sql" / "migrations"

# These ran before schema_migrations existed, all in one transaction (so a
# database has either all of them or none). Their plain CREATE TABLEs fail if
# run twice, so an existing schema gets them recorded instead of re-run.
PRE_TRACKING_MIGRATIONS = [
    "001_reference_tables.sql",
    "002_destinations.sql",
    "003_hotel_prices.sql",
    "004_flight_observations.sql",
    "005_app_tables.sql",
]
# Created by the last pre-tracking migration, so its presence means all of them ran.
PRE_TRACKING_MARKER_TABLE = "public.search_queries"


def ensure_tracking_table(conn):
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename   TEXT PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
            )
            """
        )


def record_pre_tracking_migrations(conn):
    with conn, conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM schema_migrations)")
        if cur.fetchone()[0]:
            return []
        cur.execute("SELECT to_regclass(%s) IS NOT NULL", (PRE_TRACKING_MARKER_TABLE,))
        if not cur.fetchone()[0]:
            return []
        for filename in PRE_TRACKING_MIGRATIONS:
            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (filename,))
    return PRE_TRACKING_MIGRATIONS


def apply_pending_migrations(conn, migrations_dir):
    with conn, conn.cursor() as cur:
        cur.execute("SELECT filename FROM schema_migrations")
        already_applied = {row[0] for row in cur.fetchall()}

    newly_applied = []
    for path in sorted(migrations_dir.glob("*.sql")):
        if path.name in already_applied:
            continue
        print(f"applying {path.name}")
        # One transaction per file: the file's changes and its tracking row
        # commit together, and a failure rolls back only this file.
        with conn, conn.cursor() as cur:
            cur.execute(path.read_text())
            cur.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
        newly_applied.append(path.name)
    return newly_applied


def migrate(conn, migrations_dir=MIGRATIONS_DIR):
    if not any(migrations_dir.glob("*.sql")):
        raise SystemExit(f"no migration files found in {migrations_dir}")
    ensure_tracking_table(conn)
    recorded = record_pre_tracking_migrations(conn)
    applied = apply_pending_migrations(conn, migrations_dir)
    return recorded, applied


def main():
    with get_conn() as conn:
        recorded, applied = migrate(conn)
    if recorded:
        print(f"existing schema found; recorded as already applied: {', '.join(recorded)}")
    print(f"applied {len(applied)} new migration(s)")


if __name__ == "__main__":
    main()
