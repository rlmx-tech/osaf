"""Create the service account bulk-import tools should submit as.

Unlike `create_auto_publisher`, this account CAN be logged into by scripts —
its password is printed once at creation and must be stored in the deploy
env (`BACKFILL_PASSWORD`). Its role (`backfill_contributor`) submits through
the same dedup guard as everyone else, but its submissions land as `pending`
for human review instead of publishing directly. That is the point: a bulk
import mistake becomes a review-queue problem, not a public-data problem.

To revoke batch-write access without a deploy, deactivate the account.

    python -m scripts.create_backfill_user
"""

import asyncio
import secrets

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import User
from app.services.auth_service import hash_password

BACKFILL_USERNAME = "backfill"
BACKFILL_EMAIL = "backfill@osaf.invalid"


async def ensure_backfill_user(db: AsyncSession) -> User:
    existing = (
        await db.execute(select(User).where(User.username == BACKFILL_USERNAME))
    ).scalar_one_or_none()
    if existing is not None:
        print(f"backfill account exists (role={existing.role}, active={existing.is_active})")
        return existing

    password = secrets.token_urlsafe(24)
    user = User(
        email=BACKFILL_EMAIL,
        username=BACKFILL_USERNAME,
        password_hash=hash_password(password),
        display_name="Backfill",
        role="backfill_contributor",
        bio="Service account for bulk imports. Submissions land in the review "
            "queue (pending), never published directly.",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    print("created backfill account")
    print("password (store now, shown once):", password)
    return user


async def main() -> None:
    async with async_session() as db:
        await ensure_backfill_user(db)


if __name__ == "__main__":
    asyncio.run(main())
