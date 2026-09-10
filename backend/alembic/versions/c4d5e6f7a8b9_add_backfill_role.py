"""Add the backfill_contributor role

The collector account is a verified_contributor, which auto-publishes on
submission. That is correct for the news pipeline, but it made every bulk
backfill script that reused the collector credentials publish directly — and
when the GSAF backfill hit the publisher-title dedup bug (2026-09-10), the
failure mode was a bulk write with no review gate behind it. A dedicated
lower-privilege role for batch tools closes that: submissions still run
through find_duplicate_incident, but they land as `pending` for review
instead of publishing, and the role cannot log into the review UI paths
(publish/reject/promote remain admin-only).

Revision ID: c4d5e6f7a8b9
Revises: a1b2c3d4e5f6
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4d5e6f7a8b9"
down_revision: str | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_ROLES = "('admin', 'verified_contributor', 'public')"
_NEW_ROLES = "('admin', 'verified_contributor', 'backfill_contributor', 'public')"


def upgrade() -> None:
    op.drop_constraint("valid_role", "users", type_="check")
    op.create_check_constraint("valid_role", "users", f"role IN {_NEW_ROLES}")


def downgrade() -> None:
    # Normalize any backfill accounts to public (least-privileged) before
    # shrinking the constraint, mirroring the a1b2c3d4e5f6 approach.
    op.execute("UPDATE users SET role = 'public' WHERE role = 'backfill_contributor'")
    op.drop_constraint("valid_role", "users", type_="check")
    op.create_check_constraint("valid_role", "users", f"role IN {_OLD_ROLES}")