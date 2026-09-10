"""Create the service account that auto-published incidents are attributed to.

A separate one-off, not something the publisher does for itself: a script that
can mint admin accounts is a worse idea than a script that refuses to run
without one. Run it once per environment.

The account is an admin because review_candidate publishes on behalf of one,
but no one can log into it. Its password is 48 random bytes that are hashed
and then discarded, so no credential for it exists anywhere — not in this
output, not in an env file. It exists only to make the audit trail say "the
machine did this" instead of naming a person who never saw the record.

To switch auto-publishing off without a deploy, deactivate the account. Re-running
this script will not turn it back on.

    python -m scripts.create_auto_publisher
"""

import asyncio
import secrets
import sys

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import User
from app.services.auth_service import hash_password

AUTO_PUBLISHER_USERNAME = "auto-publisher"
AUTO_PUBLISHER_EMAIL = "auto-publisher@osaf.invalid"


async def ensure_auto_publisher(db: AsyncSession) -> User:
    """Return the auto-publisher account, creating it if it does not exist.

    An existing account is returned untouched — in particular, a deactivated one
    stays deactivated.
    """
    existing = (
        await db.execute(select(User).where(User.username == AUTO_PUBLISHER_USERNAME))
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    user = User(
        email=AUTO_PUBLISHER_EMAIL,
        username=AUTO_PUBLISHER_USERNAME,
        password_hash=hash_password(secrets.token_urlsafe(48)),
        display_name="Auto-publisher",
        role="admin",
        bio="Service account. Publishes incident candidates that pass the "
            "automatic eligibility rule. Cannot be logged into.",
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def main() -> int:
    async with async_session() as db:
        before = (
            await db.execute(select(User.id).where(User.username == AUTO_PUBLISHER_USERNAME))
        ).scalar_one_or_none()
        user = await ensure_auto_publisher(db)

    state = "already existed" if before else "created"
    print(f"{AUTO_PUBLISHER_USERNAME}: {state} (id {user.id}, role {user.role}, "
          f"active {user.is_active})")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
