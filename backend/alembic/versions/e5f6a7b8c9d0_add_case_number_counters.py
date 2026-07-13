"""Add durable yearly case-number counters.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a1b2c3
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a1b2c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "case_number_counters",
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("year"),
    )
    op.execute(
        """
        INSERT INTO case_number_counters (year, last_value)
        SELECT
            substring(case_number, 6, 4)::integer,
            max(substring(case_number, 11)::integer)
        FROM incidents
        WHERE case_number ~ '^OSAF-[0-9]{4}-[0-9]+$'
        GROUP BY substring(case_number, 6, 4)::integer
        """
    )


def downgrade() -> None:
    op.drop_table("case_number_counters")
