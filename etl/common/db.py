from contextlib import contextmanager

import psycopg2

from etl.common.config import DB_URL


# One connection per script run, committed when the block ends and rolled back
# if it raises. Scripts open their own cursor on it, and can commit partway
# through (the collectors commit after each destination).
@contextmanager
def get_conn():
    conn = psycopg2.connect(DB_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
