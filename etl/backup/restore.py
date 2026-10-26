# Restores a nightly backup (backup.py's files) into an empty database:
# the migrations rebuild the schema, then each table's rows are
# loaded back. Also how the local development database gets the cloud's data.
#
# Run with: uv run python -m etl.backup.restore <folder with the .csv.gz files>
# (download a night first: aws s3 cp --recursive s3://<bucket>/backups/<day>/ <folder>)
# The target must have no tables. To refresh the local database, empty it first
# (this drops all its data):
#   docker exec vacation_budget_db psql -U vacation -d vacation_budget \
#     -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

import gzip
import io
import sys
from pathlib import Path

from etl.backup.backup import TABLES
from etl.common.db import get_conn
from etl.loaders.run_migrations import migrate


# The reverse of backup.dump_table: data is that function's gzipped CSV.
# The columns are named from its header line, not taken by position: a
# database built over months (the local one, and Neon, copied from it) has
# some columns in another order than one built from today's migration files,
# and the first restore drill put a price into depart_time.
def restore_table(cur, table, data):
    csv_bytes = gzip.decompress(data)
    columns = csv_bytes.split(b"\n", 1)[0].decode()
    cur.copy_expert(f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER)", io.BytesIO(csv_bytes))


# COPY writes the ids as they were but doesn't move the SERIAL sequences, so
# each still stands at 1 and the next INSERT would reuse an existing id. Set
# each to its table's highest id + 1 (or 1 when the table is empty).
def reset_sequences(cur):
    cur.execute(
        "SELECT table_name, column_name FROM information_schema.columns"
        " WHERE table_schema = 'public' AND (column_default LIKE 'nextval(%' OR is_identity = 'YES')"
    )
    for table, column in cur.fetchall():
        cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', '{column}'),"
            f" COALESCE(MAX({column}), 0) + 1, false) FROM {table}"
        )


def restore(conn, folder):
    # Checked before migrating, so a wrong DB_URL (the dev database, or Neon)
    # is refused untouched: loading into tables that have rows would mix two
    # databases, and even pending migrations would be applied to the wrong one.
    with conn.cursor() as cur:
        cur.execute("SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public')")
        if cur.fetchone()[0]:
            raise SystemExit("the target database isn't empty (it has tables) - restore only into a new one")
    migrate(conn)
    with conn.cursor() as cur:
        for table in TABLES:
            restore_table(cur, table, (folder / f"{table}.csv.gz").read_bytes())
        reset_sequences(cur)


def main():
    folder = Path(sys.argv[1])
    # The data commits once at the end: every table loads, or none does. The
    # migrations commit before it, so after a failed load the empty schema
    # stays and a rerun is refused: drop it first (DROP SCHEMA public CASCADE).
    with get_conn() as conn:
        restore(conn, folder)
    print(f"restored {len(TABLES)} tables from {folder}")


if __name__ == "__main__":
    main()
