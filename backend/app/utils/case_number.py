from datetime import date

from sqlalchemy import Integer, cast, func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.case_number_counter import CaseNumberCounter
from app.models.incident import Incident


async def generate_case_number(db: AsyncSession) -> str:
    """Generate the next OSAF-YYYY-NNNN case number for the current year.

    Case numbers are identifiers, so deleted or merged rows must not cause an
    old number to be reused. PostgreSQL stores a durable yearly high-water mark
    and increments it atomically. The max-suffix query remains as a lightweight
    fallback for non-PostgreSQL unit tests.
    """
    year = date.today().year
    prefix = f"OSAF-{year}-"

    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        existing_max = await _highest_suffix(db, prefix)
        await db.execute(
            pg_insert(CaseNumberCounter)
            .values(year=year, last_value=existing_max)
            .on_conflict_do_nothing(index_elements=[CaseNumberCounter.year])
        )
        result = await db.execute(
            update(CaseNumberCounter)
            .where(CaseNumberCounter.year == year)
            .values(last_value=CaseNumberCounter.last_value + 1)
            .returning(CaseNumberCounter.last_value)
        )
        next_suffix = result.scalar_one()
        return f"{prefix}{next_suffix:04d}"

    highest_suffix = await _highest_suffix(db, prefix)
    return f"{prefix}{highest_suffix + 1:04d}"


async def _highest_suffix(db: AsyncSession, prefix: str) -> int:
    """Return the largest numeric suffix currently present for a prefix."""

    result = await db.execute(
        select(
            func.max(
                cast(func.substr(Incident.case_number, len(prefix) + 1), Integer)
            )
        )
        .select_from(Incident)
        .where(Incident.case_number.like(f"{prefix}%"))
    )
    return result.scalar_one_or_none() or 0
