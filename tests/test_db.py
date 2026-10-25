# app/db.py's connection pool, against the real test database: connections
# are reused, a failed request rolls back, a connection the server dropped
# is replaced instead of being handed to the next request, and a request
# waits for a free connection instead of failing at once.

import threading
import time
from contextlib import closing

import psycopg2
import pytest

from app import db as app_db


@pytest.fixture()
def pool_on_test_db(test_db_url, monkeypatch):
    monkeypatch.setattr(app_db, "DB_URL", test_db_url)
    monkeypatch.setattr(app_db, "_pool", None)
    monkeypatch.setattr(app_db, "_returned_at", {})
    yield
    if app_db._pool is not None:
        app_db._pool.closeall()


# A pool with room for a single request, so one held cursor fills it.
@pytest.fixture()
def one_slot(monkeypatch):
    monkeypatch.setattr(app_db, "_slots", threading.BoundedSemaphore(1))


def test_connection_is_reused_across_requests(pool_on_test_db):
    with app_db.get_cursor() as cur:
        first = cur.connection
    with app_db.get_cursor() as cur:
        assert cur.connection is first


def test_error_rolls_back_the_request(pool_on_test_db):
    with pytest.raises(RuntimeError), app_db.get_cursor() as cur:
        cur.execute(
            "INSERT INTO exchange_rates (currency_code, usd_per_unit, as_of_date) VALUES ('XXX', 1, CURRENT_DATE)"
        )
        raise RuntimeError("request failed")

    with app_db.get_cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM exchange_rates WHERE currency_code = 'XXX'")
        assert cur.fetchone()["n"] == 0


def test_dropped_connection_is_replaced(pool_on_test_db):
    # The original error must surface, not a "connection already closed"
    # from trying to roll back a dead connection.
    with pytest.raises(psycopg2.OperationalError), app_db.get_cursor() as cur:
        dropped = cur.connection
        cur.execute("SELECT pg_terminate_backend(pg_backend_pid())")

    with app_db.get_cursor() as cur:
        assert cur.connection is not dropped
        cur.execute("SELECT 1 AS one")
        assert cur.fetchone()["one"] == 1


# Neon closes its connections when it suspends, and a warm Lambda keeps the
# dead one in its pool: the next request got a 500 (ROADMAP 4.3). A connection
# that sat idle is checked before a request gets it.
def test_idle_connection_closed_by_the_server_is_replaced(pool_on_test_db, monkeypatch):
    with app_db.get_cursor() as cur:
        cur.execute("SELECT pg_backend_pid() AS pid")
        idle, pid = cur.connection, cur.fetchone()["pid"]
    with closing(psycopg2.connect(app_db.DB_URL)) as other, other.cursor() as cur:
        cur.execute("SELECT pg_terminate_backend(%s)", (pid,))
    monkeypatch.setattr(app_db, "CHECK_AFTER_IDLE_SECONDS", 0)

    with app_db.get_cursor() as cur:
        assert cur.connection is not idle
        cur.execute("SELECT 1 AS one")
        assert cur.fetchone()["one"] == 1


# A check that wrongly failed would open a new connection (a TLS handshake to
# Neon) for every request after a pause, and no other test would notice.
def test_healthy_idle_connection_passes_the_check_and_is_reused(pool_on_test_db, monkeypatch):
    with app_db.get_cursor() as cur:
        idle = cur.connection
    monkeypatch.setattr(app_db, "CHECK_AFTER_IDLE_SECONDS", 0)

    with app_db.get_cursor() as cur:
        assert cur.connection is idle
        cur.execute("SELECT 1 AS one")
        assert cur.fetchone()["one"] == 1


def test_request_waits_for_a_free_connection(pool_on_test_db, one_slot):
    holding = threading.Event()

    def hold_briefly():
        with app_db.get_cursor():
            holding.set()
            time.sleep(0.3)

    holder = threading.Thread(target=hold_briefly)
    holder.start()
    holding.wait()

    started = time.monotonic()
    with app_db.get_cursor() as cur:
        waited = time.monotonic() - started
        cur.execute("SELECT 1 AS one")
        assert cur.fetchone()["one"] == 1
    holder.join()

    assert waited >= 0.2


def test_gives_up_when_no_connection_frees_up(pool_on_test_db, one_slot, monkeypatch):
    monkeypatch.setattr(app_db, "POOL_WAIT_SECONDS", 0.1)

    with app_db.get_cursor(), pytest.raises(app_db.PoolExhausted), app_db.get_cursor():
        pass


def test_failed_connect_gives_its_slot_back(one_slot, monkeypatch):
    monkeypatch.setattr(app_db, "DB_URL", "postgresql://nobody@127.0.0.1:1/nothing")
    monkeypatch.setattr(app_db, "_pool", None)
    monkeypatch.setattr(app_db, "POOL_WAIT_SECONDS", 0.1)

    # With the only slot leaked, the second attempt would be PoolExhausted.
    for _ in range(2):
        with pytest.raises(psycopg2.OperationalError), app_db.get_cursor():
            pass
