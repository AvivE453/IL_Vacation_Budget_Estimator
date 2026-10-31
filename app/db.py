import threading
import time
from contextlib import contextmanager

import psycopg2
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

# A pooled connection idle this long is checked with SELECT 1 before a request
# gets it, and replaced if the server has closed it. Neon closes its connections
# when it suspends (after 5 idle minutes on the free plan), and a warm Lambda
# would hand the dead one to the next request: a 500 (seen on AWS). One minute,
# not just under five: that setting is Neon's, and other hops on the way may
# drop quiet connections sooner. A check costs one round trip.
CHECK_AFTER_IDLE_SECONDS = 60
_returned_at = {}

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


# No rollback after the SELECT: the request's own queries continue the
# transaction it opened, so the check stays one round trip.
def _is_alive(conn):
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except psycopg2.Error:
        return False


# A connection opened for this request, or returned less than
# CHECK_AFTER_IDLE_SECONDS ago, is used as is. Each dead one is closed, so the
# loop ends at the latest when the pool opens a new connection.
def _get_live_connection(pool):
    while True:
        conn = pool.getconn()
        returned_at = _returned_at.pop(conn, None)
        if returned_at is None or time.monotonic() - returned_at < CHECK_AFTER_IDLE_SECONDS or _is_alive(conn):
            return conn
        pool.putconn(conn, close=True)


# Only a cursor is handed out here, with dict-style row access - every route
# wants just that. etl/common/db.py's get_conn() hands out the connection
# instead, because the collectors commit partway through a run.
@contextmanager
def get_cursor():
    if not _slots.acquire(timeout=POOL_WAIT_SECONDS):
        raise PoolExhausted(f"no free database connection within {POOL_WAIT_SECONDS}s")
    # The slot goes back even when no connection was ever handed out (e.g. the
    # database is down) - otherwise each failure would shrink the pool for good.
    try:
        pool = _get_pool()
        conn = _get_live_connection(pool)
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
            # putconn closes a connection that's already dead or not kept idle.
            if not conn.closed:
                _returned_at[conn] = time.monotonic()
    finally:
        _slots.release()
