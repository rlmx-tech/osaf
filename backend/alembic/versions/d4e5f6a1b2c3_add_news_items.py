"""add news_items table

Revision ID: d4e5f6a1b2c3
Revises: c3a1f9d82b4e
Create Date: 2026-06-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d4e5f6a1b2c3"
down_revision: Union[str, None] = "c3a1f9d82b4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dedup_key", sa.String(512), nullable=False),
        sa.Column("source_platform", sa.String(20), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False, server_default="news"),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("ai_confidence", sa.Float, nullable=True),
        sa.Column("promoted_incident_id", UUID(as_uuid=True), sa.ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("dedup_key", name="uq_news_items_dedup_key"),
        sa.CheckConstraint("event_type IN ('attack', 'sighting', 'news')", name="valid_event_type"),
    )
    op.create_index("idx_news_items_captured_at", "news_items", ["captured_at"])
    op.create_index("idx_news_items_event_type", "news_items", ["event_type"])
    op.create_index("idx_news_items_country", "news_items", ["country"])


def downgrade() -> None:
    op.drop_index("idx_news_items_country", table_name="news_items")
    op.drop_index("idx_news_items_event_type", table_name="news_items")
    op.drop_index("idx_news_items_captured_at", table_name="news_items")
    op.drop_table("news_items")
