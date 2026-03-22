from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident


async def generate_case_number(db: AsyncSession) -> str:
    """Generate the next OSAF-YYYY-NNNN case number for the current year."""
    year = date.today().year
    prefix = f"OSAF-{year}-"

    result = await db.execute(
        select(func.count())
        .select_from(Incident)
        .where(Incident.case_number.like(f"{prefix}%"))
    )
    count = result.scalar_one()

    return f"{prefix}{count + 1:04d}"
