# FastAPI routes, driven through its TestClient. The db_cursor dependency is
# overridden with the test's own cursor, so everything a route reads and
# writes stays inside the test's rolled-back transaction.

import pytest
from fastapi.testclient import TestClient

from api.deps import db_cursor
from api.main import app
from app.db import PoolExhausted


@pytest.fixture()
def client(cur):
    app.dependency_overrides[db_cursor] = lambda: cur
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_health_reports_ok(client):
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_busy_database_is_503_not_500(client):
    def no_free_connection():
        raise PoolExhausted("no free database connection")

    app.dependency_overrides[db_cursor] = no_free_connection
    response = client.get("/api/v1/health")

    assert response.status_code == 503
    assert response.headers["Retry-After"] == "1"
