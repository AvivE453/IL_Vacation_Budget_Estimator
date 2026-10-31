# The API as Lambda runs it: an API Gateway HTTP API event (payload format 2.0)
# goes into api/lambda_handler.py's handler, and its answer is checked in the
# shape API Gateway turns back into an HTTP response.

import json

import pytest

from api.deps import db_cursor
from api.lambda_handler import handler
from api.main import app


@pytest.fixture(autouse=True)
def routes_use_the_test_cursor(cur):
    app.dependency_overrides[db_cursor] = lambda: cur
    yield
    app.dependency_overrides.clear()


def api_gateway_event(method, path, cookies=None):
    event = {
        "version": "2.0",
        "routeKey": "$default",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {"host": "abc123.execute-api.eu-north-1.amazonaws.com", "accept": "application/json"},
        "requestContext": {
            "http": {
                "method": method,
                "path": path,
                "protocol": "HTTP/1.1",
                "sourceIp": "203.0.113.7",
                "userAgent": "pytest",
            },
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }
    # HTTP API events carry the request's cookies in their own list, not in headers.
    if cookies:
        event["cookies"] = cookies
    return event


def test_health_through_the_lambda_handler():
    response = handler(api_gateway_event("GET", "/api/v1/health"), None)

    assert response["statusCode"] == 200
    assert json.loads(response["body"]) == {"status": "ok"}


# The session cookie has to survive the trip through API Gateway both ways,
# or "My searches" would start empty on every request.
def test_session_cookie_goes_out_and_comes_back():
    first = handler(api_gateway_event("GET", "/api/v1/searches"), None)
    [set_cookie] = first["cookies"]
    cookie = set_cookie.split(";")[0]
    assert cookie.startswith("session_id=")

    second = handler(api_gateway_event("GET", "/api/v1/searches", cookies=[cookie]), None)

    assert second["statusCode"] == 200
    assert second["cookies"][0].split(";")[0] == cookie
