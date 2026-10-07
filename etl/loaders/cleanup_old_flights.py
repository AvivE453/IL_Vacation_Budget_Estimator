# Deletes flight_price_observations rows whose return_date is more than
# RETENTION_MONTHS in the past -this keeps the table from growing unbounded.
#
# Run with: uv run python -m etl.loaders.cleanup_old_flights

from etl.common.db import get_conn

RETENTION_MONTHS = 3


def cleanup_old_flights(cur):
    cur.execute(
        "DELETE FROM flight_price_observations WHERE return_date < CURRENT_DATE - (interval '1 month' * %s)",
        (RETENTION_MONTHS,),
    )
    return cur.rowcount


def main():
    with get_conn() as conn:
        with conn.cursor() as cur:
            n = cleanup_old_flights(cur)
    print(f"deleted {n} flight_price_observations with return_date more than {RETENTION_MONTHS} months in the past")


if __name__ == "__main__":
    main()
