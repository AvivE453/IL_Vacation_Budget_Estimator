import datetime
from typing import Literal

from fastapi import APIRouter
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, model_validator

from api.deps import Cursor, SessionId
from app.queries import list_origin_airports
from app.search import run_search

router = APIRouter()

# The currencies etl/loaders/refresh_exchange_rates.py keeps rates for.
Currency = Literal["ILS", "USD", "EUR"]
HotelTier = Literal["budget", "average", "luxury"]


class EstimateRequest(BaseModel):
    origin_iata: str
    depart_date: datetime.date
    return_date: datetime.date
    # search_queries.budget_amount is NUMERIC(10,2), so 10^8 and up can't be stored.
    budget_amount: float = Field(gt=0, lt=100_000_000)
    budget_currency: Currency = "ILS"
    hotel_tier: HotelTier = Field(
        default="average", description="The tier saved to history; the response always has all three"
    )

    @model_validator(mode="after")
    def return_after_depart(self):
        if self.return_date <= self.depart_date:
            raise ValueError("return_date must be after depart_date")
        return self


class DestinationEstimate(BaseModel):
    destination_id: int
    city_name: str
    city_name_he: str | None = Field(description="Hebrew name; null when the seed has none (show city_name)")
    airline_code: str | None
    airline_name: str | None = Field(description="null when the airline code isn't in our reference table")
    flight_out_date: datetime.date
    flight_return_date: datetime.date
    matched_nights: int = Field(
        description="Nights of the matched flight, which the hotel is priced for - may differ from the request"
    )
    flight_total_amount: float
    hotel_total_amount: float
    total_estimate_amount: float
    flight_seen_on: datetime.date = Field(
        description="The day a real search last saw this flight price - or, for prices collected before"
        " that was recorded, the day we collected it"
    )
    hotel_price_age_days: int = Field(description="Days since the city's hotel prices were collected")


class TierEstimate(BaseModel):
    exact_dates_only: bool = Field(
        description="true: every destination matched the requested dates exactly; false: all are the nearest dates"
    )
    has_missing_data: bool = Field(
        description="true only when no destination has both a flight and a hotel price for these dates"
        " - as opposed to the budget excluding them all"
    )
    destinations: list[DestinationEstimate]


class TierEstimates(BaseModel):
    budget: TierEstimate
    average: TierEstimate
    luxury: TierEstimate


class EstimateResponse(BaseModel):
    search_id: int
    currency: str = Field(description="Every amount is in this currency: the budget's, or USD if it has no rate")
    budget_amount: float | None = Field(
        description="null when the budget currency has no exchange rate - results are then not filtered by budget"
    )
    tiers: TierEstimates


# Ranks every destination by total cost for all three hotel tiers, and saves
# the search (with the requested tier's results) to this browser's history.
@router.post("/estimates")
def create_estimate(body: EstimateRequest, cur: Cursor, session_id: SessionId) -> EstimateResponse:
    require_known_origin(cur, body.origin_iata, location="body")
    search = run_search(
        cur, session_id, body.origin_iata, body.depart_date, body.return_date,
        body.budget_amount, body.budget_currency, body.hotel_tier,
    )
    return EstimateResponse(
        search_id=search.search_query_id,
        currency=search.display_currency,
        budget_amount=search.budget_amount_display,
        tiers=TierEstimates(
            **{
                tier: TierEstimate(
                    exact_dates_only=result.exact_dates_only,
                    has_missing_data=result.has_missing_data,
                    destinations=[DestinationEstimate.model_validate(e) for e in result.estimates],
                )
                for tier, result in search.tiers.items()
            }
        ),
    )


# Origins live in the database, so this can't be a Literal on the model. Raised
# as a validation error so it reaches the client in the same 422 shape as the
# model's own checks - and before saving the search would hit the foreign key.
# location is where the field came from: "body" or "query".
def require_known_origin(cur, origin_iata, location):
    if origin_iata not in {o["iata_code"] for o in list_origin_airports(cur)}:
        error = {"type": "value_error", "loc": (location, "origin_iata"), "msg": "Unknown origin airport"}
        raise RequestValidationError([{**error, "input": origin_iata}])
