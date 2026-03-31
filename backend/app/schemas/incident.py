from datetime import date, datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class CoordinatesSchema(BaseModel):
    longitude: float = Field(..., ge=-180, le=180)
    latitude: float = Field(..., ge=-90, le=90)


class SourceCreate(BaseModel):
    source_type: str = Field(..., max_length=30)
    source_url: str | None = Field(None, max_length=2048)
    source_title: str | None = Field(None, max_length=500)
    source_publisher: str | None = Field(None, max_length=200)
    source_date: date | None = None
    source_notes: str | None = Field(None, max_length=2000)


class SourceResponse(SourceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    incident_id: UUID
    created_at: datetime


class IncidentBase(BaseModel):
    incident_date: date | None = None
    incident_time: time | None = None
    date_precision: str = Field("exact", max_length=10)
    location_description: str = Field(..., max_length=500)
    country: str = Field(..., max_length=100)
    state_province: str | None = Field(None, max_length=100)
    county_region: str | None = Field(None, max_length=100)
    body_of_water: str | None = Field(None, max_length=200)
    coordinates: CoordinatesSchema | None = None
    location_precision: str = Field("exact", max_length=20)
    classification: str = Field(..., max_length=20)
    classification_subtype: str | None = Field(None, max_length=20)
    provocation_subtype: str | None = Field(None, max_length=20)
    report_source: str | None = Field(None, max_length=50)
    report_platform: str | None = Field(None, max_length=50)
    shark_species_confirmed: str | None = Field(None, max_length=100)
    shark_species_suspected: str | None = Field(None, max_length=100)
    shark_size_estimate: str | None = Field(None, max_length=100)
    species_identification_method: str | None = Field(None, max_length=50)
    victim_activity: str | None = Field(None, max_length=100)
    victim_injury_severity: str | None = Field(None, max_length=20)
    victim_injury_description: str | None = Field(None, max_length=2000)
    victim_age: int | None = Field(None, ge=0, le=120)
    victim_sex: str | None = Field(None, max_length=10)
    victim_name: str | None = Field(None, max_length=200)
    fatal: bool = False
    description: str | None = Field(None, max_length=10000)


class IncidentCreate(IncidentBase):
    sources: list[SourceCreate] = Field(default_factory=list)


class IncidentUpdate(BaseModel):
    """All fields optional for partial updates."""
    incident_date: date | None = None
    incident_time: time | None = None
    date_precision: str | None = None
    location_description: str | None = None
    country: str | None = None
    state_province: str | None = None
    county_region: str | None = None
    body_of_water: str | None = None
    coordinates: CoordinatesSchema | None = None
    location_precision: str | None = None
    classification: str | None = None
    classification_subtype: str | None = None
    provocation_subtype: str | None = None
    report_source: str | None = None
    report_platform: str | None = None
    shark_species_confirmed: str | None = None
    shark_species_suspected: str | None = None
    shark_size_estimate: str | None = None
    species_identification_method: str | None = None
    victim_activity: str | None = None
    victim_injury_severity: str | None = None
    victim_injury_description: str | None = None
    victim_age: int | None = Field(None, ge=0, le=120)
    victim_sex: str | None = None
    victim_name: str | None = None
    fatal: bool | None = None
    description: str | None = None


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    case_number: str
    incident_date: date | None = None
    incident_time: time | None = None
    date_precision: str
    location_description: str
    country: str
    state_province: str | None = None
    county_region: str | None = None
    body_of_water: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    location_precision: str
    classification: str
    classification_subtype: str | None = None
    provocation_subtype: str | None = None
    report_source: str | None = None
    report_platform: str | None = None
    shark_species_confirmed: str | None = None
    shark_species_suspected: str | None = None
    shark_size_estimate: str | None = None
    species_identification_method: str | None = None
    victim_activity: str | None = None
    victim_injury_severity: str | None = None
    victim_injury_description: str | None = None
    victim_age: int | None = None
    victim_sex: str | None = None
    victim_name: str | None = None
    fatal: bool
    description: str | None = None
    verification_status: str
    submitted_at: datetime
    updated_at: datetime
    sources: list[SourceResponse] = Field(default_factory=list)


class PaginationMeta(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedIncidentResponse(BaseModel):
    data: list[IncidentResponse]
    meta: PaginationMeta
