import threading
from contextlib import contextmanager

import psycopg2.extras
import psycopg2.pool

from etl.common.config import DB_URL

# One pool per API process.
# MIN_CONNECTIONS is also how many idle connections psycopg2 keeps: one
# returned while that many are already idle is closed, not pooled.
MIN_CONNECTIONS = 1
MAX_CONNECTIONS = 10

# psycopg2's getconn() raises PoolError the moment all MAX_CONNECTIONS are
# checked out. One slot per connection makes a request wait up to this long
# for a free one instead, and getconn() then always has one to give.
POOL_WAIT_SECONDS = 5
_slots = threading.BoundedSemaphore(MAX_CONNECTIONS)

_pool = None
_pool_lock = threading.Lock()


# The server is busy, not broken - the apps answer it with 503, not 500.
class PoolExhausted(Exception):
    pass


# Created on first use, not at import: importing the app (tests, CI lint)
# must not need a reachable database. The lock stops two first requests
# arriving together from each building a pool.
def _get_pool():
    global _pool
    with _pool_lock:
        if _pool is None:
            _pool = psycopg2.pool.ThreadedConnectionPool(MIN_CONNECTIONS, MAX_CONNECTIONS, DB_URL)
        return _pool


# Only a dict cursor is exposed here (unlike etl/common/db.py, which also
# has a raw get_conn()) - every route wants the same thing: one ready
# cursor with dict-style row access.
@contextmanager
def get_cursor():
    if not _slots.acquire(timeout=POOL_WAIT_SECONDS):
        raise PoolExhausted(f"no free database connection within {POOL_WAIT_SECONDS}s")
    # The slot goes back even when no connection was ever handed out (e.g. the
    # database is down) - otherwise each failure would shrink the pool for good.
    try:
        pool = _get_pool()
        conn = pool.getconn()
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                yield cur
            conn.commit()
        except Exception:
            # Rolling back a connection the server already dropped would raise
            # its own error and hide the original one.
            if not conn.closed:
                conn.rollback()
            raise
        finally:
            pool.putconn(conn)
    finally:
        _slots.release()
