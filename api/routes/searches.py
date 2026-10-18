import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from api.deps import Cursor, SessionId
from api.errors import NOT_FOUND
from api.routes.estimates import HotelTier
from app.currency import from_usd
from app.queries import get_recent_searches, get_search, get_search_results
from app.search import display_currency_and_rate

router = APIRouter()


class SearchSummary(BaseModel):
    # Read from the search_queries column, sent as search_id - the same name
    # POST /estimates returns it under.
    search_id: int = Field(validation_alias="search_query_id")
    origin_iata: str
    depart_date: datetime.date
    return_date: datetime.date
    budget_amount: float
    budget_currency: str
    hotel_tier: HotelTier
    travelers: int
    rooms: int
    created_at: datetime.datetime


class SavedResult(BaseModel):
    cost_rank: int
    destination_id: int
    city_name: str
    city_name_he: str | None = Field(description="Hebrew name; null when the seed has none (show city_name)")
    airline_code: str | None
    airline_name: str | None
    estimated_total_amount: float


class SavedSearch(SearchSummary):
    exact_dates_only: bool | None = Field(description="null for searches saved before this was recorded")
    currency: str = Field(description="Amounts are in the search's budget currency, or USD if it has no rate")
    results: list[SavedResult] = Field(description="Empty when every destination was over budget")


# This browser's recent searches, newest first.
@router.get("/searches")
def list_searches(cur: Cursor, session_id: SessionId) -> list[SearchSummary]:
    return [SearchSummary.model_validate(row) for row in get_recent_searches(cur, session_id)]


# One past search with the ranking saved at the time. Another browser's
# search is a 404, the same as one that doesn't exist.
@router.get("/searches/{search_id}", responses=NOT_FOUND)
def get_saved_search(search_id: int, cur: Cursor, session_id: SessionId) -> SavedSearch:
    search = get_search(cur, search_id, session_id)
    if search is None:
        raise HTTPException(status_code=404, detail="Search not found")

    currency, usd_per_unit = display_currency_and_rate(cur, search["budget_currency"])
    results = [
        SavedResult.model_validate({**r, "estimated_total_amount": from_usd(r["estimated_total_usd"], usd_per_unit)})
        for r in get_search_results(cur, search_id, session_id)
    ]
    return SavedSearch.model_validate({**search, "currency": currency, "results": results})
