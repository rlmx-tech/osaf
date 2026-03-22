"""add report_source and new classifications

Revision ID: c3a1f9d82b4e
Revises: b7aa62a2c65e
Create Date: 2026-03-22
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "c3a1f9d82b4e"
down_revision: Union[str, None] = "b7aa62a2c65e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns
    op.add_column("incidents", sa.Column("report_source", sa.String(20), nullable=True))
    op.add_column("incidents", sa.Column("report_platform", sa.String(30), nullable=True))

    # Drop old classification CHECK constraint and recreate with new values
    op.drop_constraint("valid_classification", "incidents", type_="check")
    op.create_check_constraint(
        "valid_classification",
        "incidents",
        "classification IN ('unprovoked', 'provoked', 'boat_bite', 'scavenge', "
        "'aquaria', 'doubtful', 'no_assignment', 'not_confirmed', "
        "'sighting', 'near_miss', 'equipment_bite', 'unverified_report')",
    )

    # Add CHECK constraints for new columns
    op.create_check_constraint(
        "valid_report_source",
        "incidents",
        "report_source IN ('isaf', 'news_media', 'social_media', 'government', 'community') "
        "OR report_source IS NULL",
    )
    op.create_check_constraint(
        "valid_report_platform",
        "incidents",
        "report_platform IN ('twitter', 'reddit', 'instagram', 'youtube', "
        "'facebook', 'tiktok', 'tv', 'print', 'radio', 'wire_service', 'other') "
        "OR report_platform IS NULL",
    )

    # Add indexes for common queries on new columns
    op.create_index("idx_incidents_report_source", "incidents", ["report_source"])


def downgrade() -> None:
    op.drop_index("idx_incidents_report_source", table_name="incidents")
    op.drop_constraint("valid_report_platform", "incidents", type_="check")
    op.drop_constraint("valid_report_source", "incidents", type_="check")

    # Restore original classification constraint
    op.drop_constraint("valid_classification", "incidents", type_="check")
    op.create_check_constraint(
        "valid_classification",
        "incidents",
        "classification IN ('unprovoked', 'provoked', 'boat_bite', 'scavenge', "
        "'aquaria', 'doubtful', 'no_assignment', 'not_confirmed')",
    )

    op.drop_column("incidents", "report_platform")
    op.drop_column("incidents", "report_source")
