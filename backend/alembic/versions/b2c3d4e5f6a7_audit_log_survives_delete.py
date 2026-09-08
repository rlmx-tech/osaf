"""Let incident_audit_log outlive the incident it describes

incident_audit_log.incident_id was ON DELETE CASCADE, so deleting an incident
destroyed every audit entry about it — including any entry recording the
deletion. The one action most worth auditing was the one that erased its own
evidence. On a project whose premise is public auditability that is the wrong
default.

The FK becomes ON DELETE SET NULL and incident_id becomes nullable, so entries
survive. Because an entry with a NULL incident_id would otherwise name nothing,
case_number is denormalized onto the table and backfilled from the incidents it
currently points at.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b2c3d4e5f6a7"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK = "incident_audit_log_incident_id_fkey"


def upgrade() -> None:
    op.add_column(
        "incident_audit_log",
        sa.Column("case_number", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_incident_audit_log_case_number", "incident_audit_log", ["case_number"]
    )

    # Backfill from the incidents these entries still point at, so existing
    # history is identifiable if those incidents are later deleted.
    op.execute(
        """
        UPDATE incident_audit_log AS a
        SET case_number = i.case_number
        FROM incidents AS i
        WHERE a.incident_id = i.id AND a.case_number IS NULL
        """
    )

    op.alter_column(
        "incident_audit_log",
        "incident_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=True,
    )
    op.drop_constraint(_FK, "incident_audit_log", type_="foreignkey")
    op.create_foreign_key(
        _FK,
        "incident_audit_log",
        "incidents",
        ["incident_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # Entries whose incident is already gone cannot be represented under the
    # old NOT NULL + CASCADE shape, so they are dropped on the way back.
    op.execute("DELETE FROM incident_audit_log WHERE incident_id IS NULL")

    op.drop_constraint(_FK, "incident_audit_log", type_="foreignkey")
    op.create_foreign_key(
        _FK,
        "incident_audit_log",
        "incidents",
        ["incident_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column(
        "incident_audit_log",
        "incident_id",
        existing_type=sa.dialects.postgresql.UUID(as_uuid=True),
        nullable=False,
    )
    op.drop_index("ix_incident_audit_log_case_number", "incident_audit_log")
    op.drop_column("incident_audit_log", "case_number")
