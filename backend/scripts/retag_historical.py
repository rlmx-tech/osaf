"""Re-derive every incident's historical flag from the one-year rule.

The flag was first set on 2026-09-18 by hand, as "has a GSAF source", with no
audit entries. That hid 54 incidents from 2026 that the GSAF delta backfill
had also cited, and missed news pieces looking back at old bites. This applies
app.utils.historical.recorded_late to every incident and fixes each mismatch,
with an audit entry per change. Running it again finds nothing.

Dry-run by default.
    python -m scripts.retag_historical [--apply]
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.models import Incident
from app.models.audit import IncidentAuditLog
from app.utils.historical import recorded_late

NOTE = (
    "Historical flag re-derived: recorded more than a year after the incident "
    "(scripts.retag_historical). Replaces the 2026-09-18 tag by GSAF source."
)


@dataclass(frozen=True)
class Retag:
    incident_id: UUID
    case_number: str
    to: bool


@dataclass
class Report:
    judged: int = 0
    retagged: list[Retag] = field(default_factory=list)


async def _judge(db: AsyncSession) -> Report:
    rows = (await db.execute(
        select(
            Incident.id,
            Incident.case_number,
            Incident.incident_date,
            Incident.submitted_at,
            Incident.is_historical,
        ).order_by(Incident.case_number)
    )).all()

    report = Report(judged=len(rows))
    for row in rows:
        historical = recorded_late(row.incident_date, row.submitted_at)
        if historical != row.is_historical:
            report.retagged.append(Retag(row.id, row.case_number, historical))
    return report


async def run(db: AsyncSession, *, apply: bool) -> Report:
    report = await _judge(db)
    if not apply or not report.retagged:
        return report

    for to in (True, False):
        ids = [r.incident_id for r in report.retagged if r.to is to]
        if ids:
            await db.execute(update(Incident).where(Incident.id.in_(ids)).values(is_historical=to))
    db.add_all(
        IncidentAuditLog(
            incident_id=r.incident_id,
            case_number=r.case_number,
            action="retagged",
            changes={"is_historical": {"from": not r.to, "to": r.to}},
            notes=NOTE,
        )
        for r in report.retagged
    )
    await db.commit()
    return report


def _print(report: Report, *, apply: bool) -> None:
    now_historical = sum(r.to for r in report.retagged)
    print(f"incidents judged : {report.judged}")
    print(f"to historical    : {now_historical}")
    print(f"to current       : {len(report.retagged) - now_historical}")
    for r in report.retagged[:40]:
        print(f"  {r.case_number}  -> {'historical' if r.to else 'current'}")
    if len(report.retagged) > 40:
        print(f"  ... and {len(report.retagged) - 40} more")
    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="write the corrected flags")
    args = parser.parse_args()

    async with async_session() as db:
        report = await run(db, apply=args.apply)
    _print(report, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
