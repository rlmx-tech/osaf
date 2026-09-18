"""add is_historical flag to incidents

Revision ID: b7c8d9e0f1a2
Revises: c4d5e6f7a8b9
Create Date: 2026-09-18

Marks incidents ingested long after the event (GSAF historical imports,
past-attack news rehashes). Historical records stay searchable but are
excluded from current-event feeds and recent-activity statistics.
"""
from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a2"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "incidents",
        sa.Column("is_historical", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.create_index("ix_incidents_is_historical", "incidents", ["is_historical"])


def downgrade():
    op.drop_index("ix_incidents_is_historical", table_name="incidents")
    op.drop_column("incidents", "is_historical")