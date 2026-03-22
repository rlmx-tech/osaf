from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class SpeciesResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    common_name: str
    scientific_name: str
    family: str | None = None
    danger_rating: str | None = None
    max_size_meters: Decimal | None = None
    notes: str | None = None
