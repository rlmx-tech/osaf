import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class IncidentAuditLog(Base):
    __tablename__ = "incident_audit_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # SET NULL rather than CASCADE: the audit trail has to outlive the record
    # it describes. Under CASCADE, deleting an incident destroyed every entry
    # about it — including the entry saying it had been deleted — so the one
    # action most worth auditing was the one that erased its own evidence.
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True
    )
    # Denormalized so an entry still identifies its subject after incident_id
    # goes NULL. Without it a deletion entry would be an orphan naming nothing.
    case_number: Mapped[str | None] = mapped_column(String(20), index=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    changes: Mapped[dict | None] = mapped_column(JSONB)
    notes: Mapped[str | None] = mapped_column(Text)

    # Relationships
    incident = relationship("Incident", back_populates="audit_logs")
