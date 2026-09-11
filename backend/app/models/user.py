import uuid
from datetime import datetime

from sqlalchemy import Boolean, CheckConstraint, DateTime, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(100))
    role: Mapped[str] = mapped_column(
        String(20), default="public", nullable=False
    )
    bio: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_login: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Relationships
    submitted_incidents = relationship(
        "Incident", back_populates="submitter", foreign_keys="Incident.submitted_by"
    )
    verified_incidents = relationship(
        "Incident", back_populates="verifier", foreign_keys="Incident.verified_by"
    )

    __table_args__ = (
        # The incidents table constrains its enum-like columns at the database
        # level; users.role — the column that decides who can publish and who
        # can delete — was relying entirely on API-layer allowlists.
        CheckConstraint(
            # Must match migration c4d5e6f7a8b9. Databases built from the models
            # (the test suite's) otherwise reject the backfill role.
            "role IN ('admin', 'verified_contributor', 'backfill_contributor', 'public')",
            name="valid_role",
        ),
        {"comment": "Users and contributors"},
    )
