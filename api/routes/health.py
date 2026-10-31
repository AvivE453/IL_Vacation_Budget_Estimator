from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import Cursor

router = APIRouter()


class Health(BaseModel):
    status: Literal["ok"]


# Runs a real query, so it fails when the database is unreachable - the
# signal a hosting health check needs.
@router.get("/health")
def health(cur: Cursor) -> Health:
    cur.execute("SELECT 1")
    return Health(status="ok")
