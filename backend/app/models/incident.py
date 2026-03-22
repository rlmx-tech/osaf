import uuid
from datetime import date, datetime, time

from geoalchemy2 import Geometry
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    Time,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    case_number: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )

    # When
    incident_date: Mapped[date | None] = mapped_column(Date)
    incident_time: Mapped[time | None] = mapped_column(Time)
    date_precision: Mapped[str] = mapped_column(String(10), default="exact")

    # Where
    location_description: Mapped[str] = mapped_column(Text, nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    state_province: Mapped[str | None] = mapped_column(String(100))
    county_region: Mapped[str | None] = mapped_column(String(100))
    body_of_water: Mapped[str | None] = mapped_column(String(200))
    coordinates = mapped_column(Geometry("POINT", srid=4326), nullable=True)
    location_precision: Mapped[str] = mapped_column(String(20), default="exact")

    # Classification
    classification: Mapped[str] = mapped_column(String(20), nullable=False)
    classification_subtype: Mapped[str | None] = mapped_column(String(20))
    provocation_subtype: Mapped[str | None] = mapped_column(String(20))

    # Shark
    shark_species_confirmed: Mapped[str | None] = mapped_column(String(100))
    shark_species_suspected: Mapped[str | None] = mapped_column(String(100))
    shark_size_estimate: Mapped[str | None] = mapped_column(String(100))
    species_identification_method: Mapped[str | None] = mapped_column(String(50))

    # Victim
    victim_activity: Mapped[str | None] = mapped_column(String(100))
    victim_injury_severity: Mapped[str | None] = mapped_column(String(20))
    victim_injury_description: Mapped[str | None] = mapped_column(Text)
    victim_age: Mapped[int | None] = mapped_column(Integer)
    victim_sex: Mapped[str | None] = mapped_column(String(10))
    victim_name: Mapped[str | None] = mapped_column(String(200))

    # Outcome
    fatal: Mapped[bool] = mapped_column(Boolean, default=False)

    # Narrative
    description: Mapped[str | None] = mapped_column(Text)

    # Metadata
    verification_status: Mapped[str] = mapped_column(
        String(20), default="pending"
    )
    verified_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    submitted_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    sources = relationship(
        "IncidentSource", back_populates="incident", cascade="all, delete-orphan"
    )
    audit_logs = relationship(
        "IncidentAuditLog", back_populates="incident", cascade="all, delete-orphan"
    )
    submitter = relationship(
        "User", back_populates="submitted_incidents", foreign_keys=[submitted_by]
    )
    verifier = relationship(
        "User", back_populates="verified_incidents", foreign_keys=[verified_by]
    )

    __table_args__ = (
        CheckConstraint(
            "classification IN ('unprovoked', 'provoked', 'boat_bite', 'scavenge', "
            "'aquaria', 'doubtful', 'no_assignment', 'not_confirmed')",
            name="valid_classification",
        ),
        CheckConstraint(
            "victim_injury_severity IN ('fatal', 'severe', 'moderate', 'minor', 'no_injury')"
            " OR victim_injury_severity IS NULL",
            name="valid_severity",
        ),
        CheckConstraint(
            "verification_status IN ('pending', 'verified', 'rejected', 'needs_review')",
            name="valid_verification",
        ),
    )
