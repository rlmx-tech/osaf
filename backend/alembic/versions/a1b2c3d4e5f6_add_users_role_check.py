"""Add a CHECK constraint on users.role

The incidents table constrains its enum-like columns at the database level
(valid_classification, valid_verification, valid_severity, ...). users.role —
the column that decides who can publish and who can delete — had no equivalent,
relying entirely on API-layer allowlists. No current code path writes an
unvalidated role, so this is defense in depth rather than a fix for a live bug.

Any row already holding a role outside the three valid values would block the
constraint, so upgrade() normalizes those to 'public' — the least-privileged
value — before adding it. That is deliberately the safe direction: an
unrecognized role should lose access, never gain it.

Revision ID: a1b2c3d4e5f6
Revises: f6a7b8c9d0e1
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALID_ROLES = "('admin', 'verified_contributor', 'public')"


def upgrade() -> None:
    op.execute(
        f"UPDATE users SET role = 'public' WHERE role NOT IN {_VALID_ROLES}"
    )
    op.create_check_constraint(
        "valid_role",
        "users",
        f"role IN {_VALID_ROLES}",
    )


def downgrade() -> None:
    op.drop_constraint("valid_role", "users", type_="check")
