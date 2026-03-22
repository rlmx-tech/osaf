from pydantic import BaseModel


class OverviewStats(BaseModel):
    total_incidents: int
    total_fatal: int
    fatality_rate: float
    most_active_country: str | None = None
    most_common_species: str | None = None
    year_range: str | None = None


class YearCount(BaseModel):
    year: int
    count: int
    fatal: int


class CountryCount(BaseModel):
    country: str
    count: int
    fatal: int


class SpeciesCount(BaseModel):
    species: str
    count: int


class ActivityCount(BaseModel):
    activity: str
    count: int


class FatalityTrend(BaseModel):
    year: int
    fatal: int
    non_fatal: int
