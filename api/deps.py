from typing import Annotated

from fastapi import Depends
from psycopg2.extras import RealDictCursor

from app.db import get_cursor


# One cursor (and one transaction) per request. Tests swap this function out
# through app.dependency_overrides instead of monkeypatching modules.
def db_cursor():
    with get_cursor() as cur:
        yield cur


# scope="function" commits before the response is sent, so a failed commit
# becomes an error response instead of a 200 for data that was never saved.
Cursor = Annotated[RealDictCursor, Depends(db_cursor, scope="function")]
