"""Idempotently promote the collector user to verified_contributor.

Run inside the backend container after the collector user exists:
    python -m scripts.promote_collector
"""

import asyncio

from sqlalchemy import select

from app.database import async_session
from app.models.user import User


async def main() -> None:
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.username == "collector"))).scalar_one_or_none()
        if user is None:
            print("collector user not found — create it first (register), then re-run")
            return
        if user.role == "verified_contributor":
            print("collector already verified_contributor — no change")
            return
        old = user.role
        user.role = "verified_contributor"
        await db.commit()
        print(f"collector role: {old} -> verified_contributor")


if __name__ == "__main__":
    asyncio.run(main())
