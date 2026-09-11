"""The backfill_contributor role must not publish.

Why it exists: the collector account is a verified_contributor, so any bulk
script reusing its credentials published directly. When the GSAF backfill hit
the publisher-title dedup bug (2026-09-10), there was no review gate behind
the bulk write. Submissions from backfill_contributor land as pending.

These go through SubmissionService and a real users row, so they fail if the
publish rule changes or if the model's role constraint drifts from the
migration's.
"""

import pytest

from app.models import User
from app.schemas.incident import CoordinatesSchema, IncidentCreate
from app.services.auth_service import hash_password
from app.services.submission_service import SubmissionService


async def _user(db, role: str) -> User:
    user = User(
        email=f"{role}@example.com",
        username=role,
        password_hash=hash_password("not-a-real-password"),
        role=role,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


def _submission() -> IncidentCreate:
    return IncidentCreate(
        location_description="Muizenberg Beach",
        country="South Africa",
        classification="unprovoked",
        incident_date="2026-09-01",
        date_precision="exact",
        coordinates=CoordinatesSchema(longitude=18.47, latitude=-34.11),
        sources=[{
            "source_type": "news_article",
            "source_url": "https://example.com/muizenberg",
            "source_title": "Surfer bitten at Muizenberg",
        }],
    )


@pytest.mark.asyncio
async def test_a_backfill_submission_waits_for_review(db):
    backfill = await _user(db, "backfill_contributor")
    incident = await SubmissionService(db).submit_incident(_submission(), backfill)
    assert incident.verification_status == "pending"


@pytest.mark.asyncio
async def test_a_verified_contributor_submission_still_publishes(db):
    """The control: the same submission from the collector's role goes live."""
    verified = await _user(db, "verified_contributor")
    incident = await SubmissionService(db).submit_incident(_submission(), verified)
    assert incident.verification_status == "verified"
