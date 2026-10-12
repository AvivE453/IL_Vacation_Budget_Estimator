# The OpenAPI schema is the contract the React app's TypeScript types are
# generated from. No database needed - the schema comes from the code alone.

from api.export_openapi import OPENAPI_PATH, render_openapi
from api.main import app


def test_saved_schema_matches_the_code():
    assert OPENAPI_PATH.read_text() == render_openapi(), (
        "api/openapi.json is stale - run: uv run python -m api.export_openapi"
    )


def test_operation_ids_are_the_route_function_names():
    operation_ids = {
        operation["operationId"] for path in app.openapi()["paths"].values() for operation in path.values()
    }

    assert operation_ids == {
        "health",
        "origins",
        "data_quality",
        "create_estimate",
        "list_searches",
        "get_saved_search",
        "destinations",
        "destination_trip",
        "destination_date_grid",
    }


def test_errors_the_routes_raise_are_documented():
    paths = app.openapi()["paths"]

    for path in paths.values():
        for operation in path.values():
            assert "503" in operation["responses"]
    assert "404" in paths["/api/v1/searches/{search_id}"]["get"]["responses"]
    assert "404" in paths["/api/v1/destinations/{destination_id}/trip"]["get"]["responses"]
    assert "404" in paths["/api/v1/destinations/{destination_id}/date-grid"]["get"]["responses"]
