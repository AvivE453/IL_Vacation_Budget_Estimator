from fastapi import APIRouter
from pydantic import BaseModel

from api.deps import Cursor
from app.queries import list_origin_airports

router = APIRouter()


class Origin(BaseModel):
    iata_code: str
    airport_name: str
    city_name: str


# Airports a search can depart from (Israeli airports only).
@router.get("/origins")
def origins(cur: Cursor) -> list[Origin]:
    return [Origin.model_validate(row) for row in list_origin_airports(cur)]
