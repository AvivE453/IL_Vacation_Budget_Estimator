# JSON API, served alongside the Flask app (app/main.py) until React replaces
# the Jinja pages. Both use the same SQL (app/queries.py) and connection pool
# (app/db.py).
#
# Run with: uv run uvicorn api.main:app --reload --port 8000
# Interactive docs at http://127.0.0.1:8000/docs, schema at /openapi.json.

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.routes.health import router as health_router
from app.db import PoolExhausted

API_PREFIX = "/api/v1"

app = FastAPI(title="IL Vacation Budget Estimator API", version="1")
app.include_router(health_router, prefix=API_PREFIX)


@app.exception_handler(PoolExhausted)
def server_busy(request: Request, exc: PoolExhausted) -> JSONResponse:
    return JSONResponse(
        status_code=503, content={"detail": "Server busy, try again shortly"}, headers={"Retry-After": "1"}
    )
