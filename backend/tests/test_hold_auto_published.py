"""Re-judge machine-published incidents and pull the failures back for review.

On 2026-09-10 the auto-publisher was run with --apply before the date rule
existed. The hold script applies today's rule to what it published then, and
moves each failure from verified (public) to needs_review (the admin queue).
It never deletes, and it leaves anything a person published alone.
"""

import pytest
from sqlalchemy import select

from app.models import Incident
from app.models.audit import IncidentAuditLog
from app.models.ingestion import IncidentCandidate
from app.services.ingestion_service import IngestionService
from scripts.create_auto_publisher import ensure_auto_publisher
from scripts.hold_auto_published import run
from tests.test_auto_publish import PAYLOAD, _candidate


async def _published(db, actor, **payload_changes) -> Incident:
    """Publish a candidate the way the old rule did: straight through review_candidate."""
    candidate = await _candidate(db, payload={**PAYLOAD, **payload_changes})
    candidate_id = candidate.id
    await IngestionService(db).review_candidate(candidate_id, "publish", actor, "old rule")
    candidate = await db.get(IncidentCandidate, candidate_id)
    await db.refresh(candidate)
    return await db.get(Incident, candidate.canonical_incident_id)


async def _status(db, incident_id) -> str:
    incident = await db.get(Incident, incident_id)
    await db.refresh(incident)
    return incident.verification_status


@pytest.mark.asyncio
async def test_a_retrospective_is_pulled_back_and_a_good_one_stays(db):
    actor = await ensure_auto_publisher(db)
    old = await _published(db, actor, incident_date="2015-06-27", latitude=-34.06, longitude=23.0)
    good = await _published(db, actor)
    old_id, good_id = old.id, good.id

    report = await run(db, apply=True)

    assert [h.incident_id for h in report.held] == [old_id]
    assert await _status(db, old_id) == "needs_review"
    assert await _status(db, good_id) == "verified"


@pytest.mark.asyncio
async def test_the_hold_is_audited_with_its_reason(db):
    actor = await ensure_auto_publisher(db)
    held = await _published(db, actor, incident_date=None)
    held_id, actor_id = held.id, actor.id

    await run(db, apply=True)

    entry = (await db.execute(
        select(IncidentAuditLog).where(
            IncidentAuditLog.incident_id == held_id, IncidentAuditLog.action == "held"
        )
    )).scalar_one()
    assert entry.changed_by == actor_id
    assert entry.changes == {"verification_status": {"from": "verified", "to": "needs_review"}}
    assert "no incident date" in entry.notes


@pytest.mark.asyncio
async def test_dry_run_reports_but_changes_nothing(db):
    actor = await ensure_auto_publisher(db)
    old = await _published(db, actor, incident_date="2015-06-27")
    old_id = old.id

    report = await run(db, apply=False)

    assert [h.incident_id for h in report.held] == [old_id]
    assert await _status(db, old_id) == "verified"


@pytest.mark.asyncio
async def test_what_a_person_published_is_left_alone(db, admin_user):
    """A human who published a retrospective chose to. This only undoes the machine."""
    await ensure_auto_publisher(db)
    theirs = await _published(db, admin_user, incident_date="2015-06-27")
    theirs_id = theirs.id

    report = await run(db, apply=True)

    assert report.held == []
    assert await _status(db, theirs_id) == "verified"


@pytest.mark.asyncio
async def test_a_second_run_finds_nothing_left_to_hold(db):
    actor = await ensure_auto_publisher(db)
    await _published(db, actor, incident_date="2015-06-27")

    await run(db, apply=True)
    again = await run(db, apply=True)

    assert again.held == []
