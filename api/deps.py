import datetime
import uuid
from typing import Annotated

from fastapi import Depends, Request, Response
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


SESSION_COOKIE = "session_id"
SESSION_MAX_AGE = datetime.timedelta(days=30)


# Anonymous per-browser id scoping /history - no login, just a cookie. It
# holds only a random UUID - nothing to tamper with, and another browser's id
# can't be guessed - so it isn't signed. Re-set on every response, so the 30 days count from the last visit.
def session_id(request: Request, response: Response) -> str:
    value = request.cookies.get(SESSION_COOKIE) or str(uuid.uuid4())
    response.set_cookie(
        SESSION_COOKIE, value, max_age=int(SESSION_MAX_AGE.total_seconds()), httponly=True, samesite="lax"
    )
    return value


SessionId = Annotated[str, Depends(session_id)]
