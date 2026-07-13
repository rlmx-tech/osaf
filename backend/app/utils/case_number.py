from datetime import date

from sqlalchemy import Integer, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident


async def generate_case_number(db: AsyncSession) -> str:
    """Generate the next OSAF-YYYY-NNNN case number for the current year.

    Case numbers are identifiers, so deleted or merged rows must not cause an
    old number to be reused.  PostgreSQL callers also take a transaction-level
    advisory lock, keeping concurrent submissions from selecting the same
    suffix before either transaction commits.
    """
    year = date.today().year
    prefix = f"OSAF-{year}-"

    bind = db.get_bind()
    if bind.dialect.name == "postgresql":
        # "OSAF" as a stable lock namespace, with the year as the second key.
        await db.execute(select(func.pg_advisory_xact_lock(0x4F534146, year)))

    result = await db.execute(
        select(
            func.max(
                cast(func.substr(Incident.case_number, len(prefix) + 1), Integer)
            )
        )
        .select_from(Incident)
        .where(Incident.case_number.like(f"{prefix}%"))
    )
    highest_suffix = result.scalar_one_or_none() or 0

    return f"{prefix}{highest_suffix + 1:04d}"
