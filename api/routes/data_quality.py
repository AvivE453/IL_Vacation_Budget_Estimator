import datetime

from fastapi import APIRouter
from pydantic import BaseModel, Field

from api.deps import Cursor
from app.queries import get_collection_volume, get_data_quality_report

router = APIRouter()


class DestinationCoverage(BaseModel):
    city_name: str
    country_name: str
    flight_obs_count: int
    hotel_sample_size: int | None = Field(description="null when the city has no hotel price on file")
    hotel_price_age_days: int | None = Field(description="null when the city has no hotel price on file")


class DailyVolume(BaseModel):
    day: datetime.date
    observations_collected: int


class DataQuality(BaseModel):
    coverage: list[DestinationCoverage]
    collection_volume: list[DailyVolume]


# Per-destination coverage of both sources, gaps included, plus how many
# flight observations each collection day added.
@router.get("/data-quality")
def data_quality(cur: Cursor) -> DataQuality:
    return DataQuality(
        coverage=[DestinationCoverage.model_validate(row) for row in get_data_quality_report(cur)],
        collection_volume=[DailyVolume.model_validate(row) for row in get_collection_volume(cur)],
    )
