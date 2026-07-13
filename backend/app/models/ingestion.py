import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class SourceDocument(Base):
    """Immutable source evidence captured before interpretation."""

    __tablename__ = "source_documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedup_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    source_platform: Mapped[str] = mapped_column(String(30), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body_excerpt: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(200))
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    content_sha256: Mapped[str | None] = mapped_column(String(64))
    raw_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    jobs = relationship("CollectionJob", back_populates="source_document")
    observations = relationship("ExtractedObservation", back_populates="source_document")

    __table_args__ = (
        Index("idx_source_documents_captured_at", "captured_at"),
        Index("idx_source_documents_content_sha256", "content_sha256"),
    )


class CollectionJob(Base):
    """Durable, leased unit of collector work."""

    __tablename__ = "collection_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    job_type: Mapped[str] = mapped_column(String(30), nullable=False, default="extract")
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="queued")
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    leased_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    leased_by: Mapped[str | None] = mapped_column(String(100))
    last_error: Mapped[str | None] = mapped_column(Text)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    source_document = relationship("SourceDocument", back_populates="jobs")

    __table_args__ = (
        UniqueConstraint("source_document_id", "job_type", name="uq_collection_job_source_type"),
        CheckConstraint(
            "status IN ('queued', 'leased', 'retrying', 'completed', 'dead_letter')",
            name="valid_collection_job_status",
        ),
        Index("idx_collection_jobs_claim", "status", "available_at", "leased_until"),
    )


class IncidentCandidate(Base):
    """A reviewable real-world incident hypothesis supported by observations."""

    __tablename__ = "incident_candidates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="needs_review")
    match_key: Mapped[str | None] = mapped_column(String(512))
    match_score: Mapped[float | None] = mapped_column(Float)
    match_rationale: Mapped[str | None] = mapped_column(Text)
    canonical_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL")
    )
    review_notes: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL")
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    observations = relationship("ExtractedObservation", back_populates="candidate")

    __table_args__ = (
        CheckConstraint(
            "status IN ('needs_review', 'approved', 'rejected', 'published', 'merged')",
            name="valid_incident_candidate_status",
        ),
        Index("idx_incident_candidates_status_created", "status", "created_at"),
        Index("idx_incident_candidates_match_key", "match_key"),
    )


class ExtractedObservation(Base):
    """Versioned structured claims extracted from one source document."""

    __tablename__ = "extracted_observations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    source_document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("source_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    candidate_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incident_candidates.id", ondelete="SET NULL")
    )
    extractor_name: Mapped[str] = mapped_column(String(100), nullable=False)
    model_name: Mapped[str] = mapped_column(String(200), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(100), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(30), nullable=False, default="1")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    event_type: Mapped[str] = mapped_column(String(20), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    verification_confidence: Mapped[float | None] = mapped_column(Float)
    verification: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    validation_errors: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    source_document = relationship("SourceDocument", back_populates="observations")
    candidate = relationship("IncidentCandidate", back_populates="observations")

    __table_args__ = (
        UniqueConstraint(
            "source_document_id", "extractor_name", "prompt_version", "payload_sha256",
            name="uq_observation_extraction_version",
        ),
        CheckConstraint(
            "event_type IN ('attack', 'sighting', 'news', 'not_relevant')",
            name="valid_observation_event_type",
        ),
        Index("idx_observations_source_created", "source_document_id", "created_at"),
    )
