from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


class SourceDocumentCreate(BaseModel):
    dedup_key: str = Field(..., max_length=512)
    source_platform: str = Field(..., max_length=30)
    source_name: str = Field(..., max_length=200)
    source_url: str
    title: str
    body_excerpt: str | None = Field(None, max_length=12000)
    author: str | None = Field(None, max_length=200)
    published_at: datetime | None = None
    content_sha256: str | None = Field(None, min_length=64, max_length=64)
    raw_metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("content_sha256")
    @classmethod
    def validate_sha256(cls, value: str | None) -> str | None:
        if value is not None and any(char not in "0123456789abcdef" for char in value.lower()):
            raise ValueError("content_sha256 must be hexadecimal")
        return value.lower() if value else value


class SourceCaptureResponse(BaseModel):
    source_document_id: UUID
    job_id: UUID
    job_status: str
    should_process: bool
    attempts: int


class ObservationCreate(BaseModel):
    extractor_name: str = Field(..., max_length=100)
    model_name: str = Field(..., max_length=200)
    prompt_version: str = Field(..., max_length=100)
    schema_version: str = Field("1", max_length=30)
    event_type: Literal["attack", "sighting", "news", "not_relevant"]
    confidence: float | None = Field(None, ge=0, le=1)
    verification_confidence: float | None = Field(None, ge=0, le=1)
    payload: dict[str, Any]
    verification: dict[str, Any] = Field(default_factory=dict)
    validation_errors: list[Any] = Field(default_factory=list)
    promoted_case_number: str | None = Field(None, max_length=20)


class ObservationResponse(BaseModel):
    observation_id: UUID
    candidate_id: UUID | None
    candidate_status: str | None
    canonical_incident_id: UUID | None
    job_status: str


class JobFailure(BaseModel):
    error: str = Field(..., min_length=1, max_length=4000)
    retryable: bool = True


class JobFailureResponse(BaseModel):
    id: UUID
    status: str
    attempts: int
    available_at: datetime
