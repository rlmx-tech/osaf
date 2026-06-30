from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NewsItemCreate(BaseModel):
    dedup_key: str = Field(..., max_length=512)
    source_platform: str = Field(..., max_length=20)
    source_name: str = Field(..., max_length=200)
    source_url: str
    title: str
    summary: str | None = None
    author: str | None = Field(None, max_length=200)
    image_url: str | None = None
    published_at: datetime | None = None
    event_type: Literal["attack", "sighting", "news"] = "news"
    country: str | None = Field(None, max_length=100)
    ai_confidence: float | None = None
    promoted_case_number: str | None = Field(None, max_length=20)


class NewsItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dedup_key: str
    source_platform: str
    source_name: str
    source_url: str
    title: str
    summary: str | None = None
    author: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None
    captured_at: datetime
    event_type: str
    country: str | None = None
    ai_confidence: float | None = None
    promoted_incident_id: UUID | None = None


class NewsMeta(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedNewsResponse(BaseModel):
    data: list[NewsItemRead]
    meta: NewsMeta
