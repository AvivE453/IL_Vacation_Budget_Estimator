# The nightly backup: every table's rows as a gzipped CSV in S3.
# Data only: the schema is in git as migrations, so restore.py rebuilds it
# with run_migrations and then loads these files.

import datetime
import gzip
import io

from etl.common.config import BACKUP_BUCKET
from etl.common.db import get_conn

# Every table but schema_migrations (run_migrations fills it on restore), in the
# order restore.py loads them: each after the tables its foreign keys point to.
TABLES = [
    "countries",
    "airlines",
    "exchange_rates",
    "airports",
    "destinations",
    "flight_price_observations",
    "hotel_prices",
    "search_queries",
    "search_results",
]


# table comes from our own list, never from a user, so it's safe in an f-string
# (a table name can't be a %s parameter).
def dump_table(cur, table):
    buffer = io.BytesIO()
    cur.copy_expert(f"COPY {table} TO STDOUT WITH (FORMAT csv, HEADER)", buffer)
    return gzip.compress(buffer.getvalue())


# s3 is a boto3 S3 client, or a fake one in the tests.
def backup_all(cur, s3, bucket, day):
    for table in TABLES:
        data = dump_table(cur, table)
        s3.put_object(Bucket=bucket, Key=f"backups/{day}/{table}.csv.gz", Body=data)


def main():
    # Lambda's runtime has boto3; this machine doesn't, and only Lambda runs main().
    import boto3

    if not BACKUP_BUCKET:
        raise SystemExit("BACKUP_BUCKET is not set - it's set on the jobs Lambda by Terraform")
    with get_conn() as conn:
        # One snapshot for all nine COPYs: under the default READ COMMITTED each
        # would see its own moment, and a search saved between the search_queries
        # and the search_results COPY would leave results pointing at a search
        # missing from the backup, which the restore's foreign keys reject.
        conn.set_session(isolation_level="REPEATABLE READ", readonly=True)
        with conn.cursor() as cur:
            backup_all(cur, boto3.client("s3"), BACKUP_BUCKET, datetime.date.today().isoformat())
    print(f"backed up {len(TABLES)} tables to s3://{BACKUP_BUCKET}/backups/")

