# JSON API for the React frontend (frontend/). The SQL lives in app/queries.py
# and the connection pool in app/db.py.
#
# Run with: uv run uvicorn api.main:app --reload --port 8000
# Interactive docs at http://127.0.0.1:8000/docs, schema at /openapi.json.

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute

from api.errors import SERVER_BUSY
from api.routes.data_quality import router as data_quality_router
from api.routes.destinations import router as destinations_router
from api.routes.estimates import router as estimates_router
from api.routes.health import router as health_router
from api.routes.origins import router as origins_router
from api.routes.searches import router as searches_router
from app.db import PoolExhausted

API_PREFIX = "/api/v1"


# The operationId is the route function's name (destination_trip), not
# FastAPI's default (destination_trip_api_v1_destinations__destination_id__trip_get) -
# it becomes the operation's name in the generated TypeScript.
def operation_id(route: APIRoute) -> str:
    return route.name


app = FastAPI(
    title="IL Vacation Budget Estimator API",
    version="1",
    generate_unique_id_function=operation_id,
    responses=SERVER_BUSY,
)
app.include_router(health_router, prefix=API_PREFIX)
app.include_router(origins_router, prefix=API_PREFIX)
app.include_router(data_quality_router, prefix=API_PREFIX)
app.include_router(estimates_router, prefix=API_PREFIX)
app.include_router(searches_router, prefix=API_PREFIX)
app.include_router(destinations_router, prefix=API_PREFIX)


@app.exception_handler(PoolExhausted)
def server_busy(request: Request, exc: PoolExhausted) -> JSONResponse:
    return JSONResponse(
        status_code=503, content={"detail": "Server busy, try again shortly"}, headers={"Retry-After": "1"}
    )
