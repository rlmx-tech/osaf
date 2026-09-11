"""Re-judge incidents the auto-publisher created, and hold the ones that now fail.

On 2026-09-10 the auto-publisher was run with --apply before its date rule
existed, and published retrospectives, undated incidents and incidents dated
after their own articles. This applies the current eligibility rule to every
incident the machine created and moves each failure from verified (public) to
needs_review, where it shows up in the admin review queue.

It never deletes, and it only touches incidents the auto-publisher created.
Something a person published stays as they left it. The candidate stays
published and linked to its incident, so a reviewer who approves the incident
does not also get a candidate that would mint a second copy.

Dry-run by default.
    python -m scripts.hold_auto_published [--apply]
"""

import argparse
import asyncio
import sys
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models import Incident, User
from app.models.audit import IncidentAuditLog
from app.models.ingestion import ExtractedObservation, IncidentCandidate
from scripts.auto_publish_candidates import (
    AutoPublisherMissing,
    _active_auto_publisher,
    _newest,
    eligibility,
)
from scripts.create_auto_publisher import AUTO_PUBLISHER_USERNAME

HELD_STATUS = "needs_review"


@dataclass(frozen=True)
class Hold:
    incident_id: UUID
    case_number: str
    reason: str


@dataclass
class Report:
    judged: int = 0
    held: list[Hold] = field(default_factory=list)
    no_candidate: list[str] = field(default_factory=list)


async def _machine_created(db: AsyncSession, actor_id: UUID) -> list[Incident]:
    return list((
        await db.execute(
            select(Incident)
            .join(IncidentAuditLog, IncidentAuditLog.incident_id == Incident.id)
            .where(
                IncidentAuditLog.action == "created",
                IncidentAuditLog.changed_by == actor_id,
                Incident.verification_status == "verified",
            )
            .order_by(Incident.case_number)
        )
    ).scalars().unique().all())


async def _originating_candidates(
    db: AsyncSession, actor_id: UUID, incident_ids: list[UUID]
) -> dict[UUID, IncidentCandidate]:
    """The candidate whose publication created each incident.

    Later candidates merged into the same incident point at it too; the one
    reviewed first is the one that created it.
    """
    candidates = (
        await db.execute(
            select(IncidentCandidate)
            .where(
                IncidentCandidate.canonical_incident_id.in_(incident_ids),
                IncidentCandidate.reviewed_by == actor_id,
            )
            .options(
                selectinload(IncidentCandidate.observations).selectinload(
                    ExtractedObservation.source_document
                )
            )
            .order_by(IncidentCandidate.reviewed_at)
        )
    ).scalars().all()
    first: dict[UUID, IncidentCandidate] = {}
    for candidate in candidates:
        first.setdefault(candidate.canonical_incident_id, candidate)
    return first


async def _judge(db: AsyncSession, actor_id: UUID) -> Report:
    report = Report()
    incidents = await _machine_created(db, actor_id)
    origins = await _originating_candidates(db, actor_id, [i.id for i in incidents])

    for incident in incidents:
        report.judged += 1
        candidate = origins.get(incident.id)
        if candidate is None:
            report.no_candidate.append(incident.case_number)
            continue
        observation = _newest(candidate)
        source = observation.source_document if observation else None
        ok, reason = eligibility(observation, source)
        if not ok:
            report.held.append(Hold(incident.id, incident.case_number, reason))
    return report


def _hold(db: AsyncSession, incident: Incident, hold: Hold, actor_id: UUID) -> None:
    incident.verification_status = HELD_STATUS
    db.add(IncidentAuditLog(
        incident_id=incident.id,
        case_number=incident.case_number,
        action="held",
        changed_by=actor_id,
        changes={"verification_status": {"from": "verified", "to": HELD_STATUS}},
        notes=(
            f"Held for review: {hold.reason}. Auto-published before the date rule "
            "existed; re-judged by scripts.hold_auto_published."
        ),
    ))


async def run(db: AsyncSession, *, apply: bool) -> Report:
    """Judge every incident the auto-publisher created; hold the failures if asked."""
    if apply:
        actor = await _active_auto_publisher(db)
    else:
        actor = (
            await db.execute(select(User).where(User.username == AUTO_PUBLISHER_USERNAME))
        ).scalar_one_or_none()
        if actor is None:
            return Report()

    actor_id = actor.id
    report = await _judge(db, actor_id)
    if not apply or not report.held:
        return report

    for hold in report.held:
        incident = await db.get(Incident, hold.incident_id)
        _hold(db, incident, hold, actor_id)
    await db.commit()
    return report


def _print(report: Report, *, apply: bool) -> None:
    print(f"machine-published and public : {report.judged}")
    print(f"fail the current rule        : {len(report.held)}")
    for hold in report.held:
        print(f"  {hold.case_number}  {hold.reason}")
    if report.no_candidate:
        print(f"no originating candidate     : {', '.join(report.no_candidate)}")
    if not apply:
        print("\nDRY RUN — nothing written. --apply moves the above to needs_review.")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="hold the failures")
    args = parser.parse_args()

    async with async_session() as db:
        try:
            report = await run(db, apply=args.apply)
        except AutoPublisherMissing as exc:
            print(f"hold_auto_published: {exc}", file=sys.stderr)
            return 1

    _print(report, apply=args.apply)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
