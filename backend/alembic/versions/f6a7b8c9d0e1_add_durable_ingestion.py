"""add durable evidence and ingestion workflow

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f6a7b8c9d0e1"
down_revision: str | None = "e5f6a7b8c9d0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "source_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dedup_key", sa.String(512), nullable=False),
        sa.Column("source_platform", sa.String(30), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("body_excerpt", sa.Text(), nullable=True),
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_sha256", sa.String(64), nullable=True),
        sa.Column("raw_metadata", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dedup_key"),
    )
    op.create_index("idx_source_documents_captured_at", "source_documents", ["captured_at"])
    op.create_index("idx_source_documents_content_sha256", "source_documents", ["content_sha256"])

    op.create_table(
        "collection_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_type", sa.String(30), server_default="extract", nullable=False),
        sa.Column("status", sa.String(20), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="8", nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("leased_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("leased_by", sa.String(100), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("result", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued', 'leased', 'retrying', 'completed', 'dead_letter')",
            name="valid_collection_job_status",
        ),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("source_document_id", "job_type", name="uq_collection_job_source_type"),
    )
    op.create_index(
        "idx_collection_jobs_claim", "collection_jobs", ["status", "available_at", "leased_until"]
    )

    op.create_table(
        "incident_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="needs_review", nullable=False),
        sa.Column("match_key", sa.String(512), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("match_rationale", sa.Text(), nullable=True),
        sa.Column("canonical_incident_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("review_notes", sa.Text(), nullable=True),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "status IN ('needs_review', 'approved', 'rejected', 'published', 'merged')",
            name="valid_incident_candidate_status",
        ),
        sa.ForeignKeyConstraint(["canonical_incident_id"], ["incidents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "idx_incident_candidates_status_created", "incident_candidates", ["status", "created_at"]
    )
    op.create_index("idx_incident_candidates_match_key", "incident_candidates", ["match_key"])

    op.create_table(
        "extracted_observations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("extractor_name", sa.String(100), nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False),
        sa.Column("prompt_version", sa.String(100), nullable=False),
        sa.Column("schema_version", sa.String(30), server_default="1", nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("payload_sha256", sa.String(64), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("verification_confidence", sa.Float(), nullable=True),
        sa.Column("verification", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("validation_errors", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('attack', 'sighting', 'news', 'not_relevant')",
            name="valid_observation_event_type",
        ),
        sa.ForeignKeyConstraint(["candidate_id"], ["incident_candidates.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_document_id"], ["source_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_document_id", "extractor_name", "prompt_version", "payload_sha256",
            name="uq_observation_extraction_version",
        ),
    )
    op.create_index(
        "idx_observations_source_created", "extracted_observations", ["source_document_id", "created_at"]
    )

    op.add_column(
        "news_items", sa.Column("source_document_id", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.create_foreign_key(
        "fk_news_items_source_document", "news_items", "source_documents",
        ["source_document_id"], ["id"], ondelete="SET NULL",
    )

    # Preserve the existing news capture history as evidence and completed jobs.
    op.execute(
        """
        INSERT INTO source_documents (
            id, dedup_key, source_platform, source_name, source_url, title,
            body_excerpt, author, published_at, captured_at, last_seen_at, raw_metadata
        )
        SELECT gen_random_uuid(), dedup_key, source_platform, source_name, source_url,
               title, summary, author, published_at, captured_at, captured_at,
               jsonb_build_object('migrated_from', 'news_items')
        FROM news_items
        ON CONFLICT (dedup_key) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE news_items n
        SET source_document_id = s.id
        FROM source_documents s
        WHERE s.dedup_key = n.dedup_key
        """
    )
    op.execute(
        """
        INSERT INTO collection_jobs (
            id, source_document_id, job_type, status, attempts, result,
            created_at, updated_at, completed_at
        )
        SELECT gen_random_uuid(), id, 'extract', 'completed', 1,
               jsonb_build_object('outcome', 'migrated'), captured_at, captured_at, captured_at
        FROM source_documents
        ON CONFLICT (source_document_id, job_type) DO NOTHING
        """
    )
    op.execute(
        """
        INSERT INTO incident_candidates (
            id, status, match_key, match_score, match_rationale,
            canonical_incident_id, created_at, updated_at
        )
        SELECT gen_random_uuid(), 'published',
               CASE
                   WHEN i.incident_date IS NOT NULL
                    AND i.country IS NOT NULL
                    AND i.location_description IS NOT NULL
                    AND i.classification IS NOT NULL
                   THEN concat_ws('|', i.incident_date::text,
                        lower(regexp_replace(trim(i.country), '[[:space:]]+', ' ', 'g')),
                        lower(regexp_replace(trim(i.location_description), '[[:space:]]+', ' ', 'g')),
                        lower(regexp_replace(trim(i.classification), '[[:space:]]+', ' ', 'g')))
                   ELSE NULL
               END,
               1.0, 'Migrated canonical incident lineage', i.id,
               min(n.captured_at), max(n.captured_at)
        FROM incidents i
        JOIN news_items n ON n.promoted_incident_id = i.id
        GROUP BY i.id, i.incident_date, i.country, i.location_description, i.classification
        """
    )
    op.execute(
        """
        INSERT INTO extracted_observations (
            id, source_document_id, candidate_id, extractor_name, model_name,
            prompt_version, schema_version, payload, payload_sha256, event_type,
            confidence, verification_confidence, verification, validation_errors,
            created_at
        )
        SELECT gen_random_uuid(), s.id, c.id, 'osaf-collector', 'legacy',
               'migration-v1', '1',
               jsonb_strip_nulls(jsonb_build_object(
                   'incident_date', i.incident_date,
                   'location_description', i.location_description,
                   'country', i.country,
                   'state_province', i.state_province,
                   'body_of_water', i.body_of_water,
                   'classification', i.classification,
                   'shark_species_suspected', i.shark_species_suspected,
                   'victim_activity', i.victim_activity,
                   'victim_injury_severity', i.victim_injury_severity,
                   'fatal', i.fatal,
                   'description', i.description,
                   'source_url', n.source_url,
                   'source_title', n.title,
                   'source_publisher', n.source_name,
                   'source_date', n.published_at::date
               )),
               encode(sha256(convert_to(
                   jsonb_strip_nulls(jsonb_build_object(
                       'incident_id', i.id, 'source_document_id', s.id,
                       'classification', i.classification
                   ))::text, 'UTF8'
               )), 'hex'),
               CASE WHEN n.event_type IN ('attack', 'sighting')
                    THEN n.event_type
                    WHEN i.classification = 'sighting' THEN 'sighting'
                    ELSE 'attack' END,
               n.ai_confidence, NULL, '{"migrated": true}'::jsonb, '[]'::jsonb,
               n.captured_at
        FROM news_items n
        JOIN source_documents s ON s.id = n.source_document_id
        JOIN incidents i ON i.id = n.promoted_incident_id
        JOIN incident_candidates c ON c.canonical_incident_id = i.id
        """
    )


def downgrade() -> None:
    op.drop_constraint("fk_news_items_source_document", "news_items", type_="foreignkey")
    op.drop_column("news_items", "source_document_id")
    op.drop_index("idx_observations_source_created", table_name="extracted_observations")
    op.drop_table("extracted_observations")
    op.drop_index("idx_incident_candidates_match_key", table_name="incident_candidates")
    op.drop_index("idx_incident_candidates_status_created", table_name="incident_candidates")
    op.drop_table("incident_candidates")
    op.drop_index("idx_collection_jobs_claim", table_name="collection_jobs")
    op.drop_table("collection_jobs")
    op.drop_index("idx_source_documents_content_sha256", table_name="source_documents")
    op.drop_index("idx_source_documents_captured_at", table_name="source_documents")
    op.drop_table("source_documents")
