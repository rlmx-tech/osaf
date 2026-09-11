"""Automatic publication of incident candidates.

The costly failure is over-publication: a record reaching the public database
that no human would have accepted. The case that shaped the rule is real — a
queued sighting verified at 0.9 whose verifier notes read "The text only
provides a headline". The verifier was right that nothing contradicted the
extraction, because there was nothing there. Verification measures agreement
with the text, not whether the text was worth anything, so eligibility also
requires the source to have carried a real article body.
"""

import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models import Incident, User
from app.models.ingestion import ExtractedObservation, IncidentCandidate, SourceDocument
from app.services.auth_service import verify_password
from scripts.auto_publish_candidates import (
    AUTO_PUBLISHER_USERNAME,
    MIN_CONFIDENCE,
    MIN_VERIFICATION,
    AutoPublisherMissing,
    eligibility,
    run,
)
from scripts.create_auto_publisher import ensure_auto_publisher

PAYLOAD = {
    "incident_date": "2026-09-07",
    "country": "Australia",
    "location_description": "Coogee Beach, Sydney",
    "classification": "unprovoked",
    "fatal": False,
    "source_type": "news_article",
    "latitude": -33.92,
    "longitude": 151.26,
}

# The article reporting PAYLOAD's 2026-09-07 incident came out the next morning.
ARTICLE_DATE = datetime(2026, 9, 8, 6, 0, tzinfo=UTC)

GOOD_VERIFICATION = {
    "is_valid": True,
    "is_duplicate_likely": False,
    "confidence": 0.9,
    "corrections": {},
    "notes": "Consistent with the article.",
}


async def _candidate(
    db,
    *,
    confidence=0.9,
    verification_confidence=0.9,
    verification=None,
    validation_errors=None,
    event_type="attack",
    raw_metadata=None,
    payload=None,
    status="needs_review",
    created_at=None,
    published_at=ARTICLE_DATE,
    source_url=None,
):
    """A candidate with one observation over one source document."""
    candidate = IncidentCandidate(id=uuid.uuid4(), status=status)
    db.add(candidate)
    await db.flush()
    await _observation(
        db, candidate,
        confidence=confidence,
        verification_confidence=verification_confidence,
        verification=GOOD_VERIFICATION if verification is None else verification,
        validation_errors=validation_errors or [],
        event_type=event_type,
        raw_metadata={"has_article_body": True} if raw_metadata is None else raw_metadata,
        payload=payload or PAYLOAD,
        created_at=created_at,
        published_at=published_at,
        source_url=source_url,
    )
    await db.commit()
    return candidate


async def _observation(
    db, candidate, *, raw_metadata, created_at=None, published_at=ARTICLE_DATE,
    source_url=None, **fields,
):
    doc = SourceDocument(
        id=uuid.uuid4(),
        dedup_key=f"test:{uuid.uuid4()}",
        source_platform="news_rss",
        source_name="Test Feed",
        source_url=source_url or f"https://example.com/{uuid.uuid4()}",
        published_at=published_at,
        title="Surfer bitten at Coogee Beach",
        body_excerpt="A surfer was bitten at Coogee Beach on Monday. " * 30,
        raw_metadata=raw_metadata,
    )
    db.add(doc)
    await db.flush()
    observation = ExtractedObservation(
        id=uuid.uuid4(),
        source_document_id=doc.id,
        candidate_id=candidate.id,
        extractor_name="osaf-collector",
        model_name="glm-5.3-flash:cloud",
        prompt_version="extract-v3",
        payload_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        **fields,
    )
    if created_at is not None:
        observation.created_at = created_at
    db.add(observation)
    await db.flush()
    return observation


async def _auto_publisher(db) -> User:
    return await ensure_auto_publisher(db)


async def _eligible_ids(db) -> set[uuid.UUID]:
    report = await run(db, apply=False)
    return {c.id for c in report.eligible}


# --- the rule -------------------------------------------------------------


class TestEligibility:
    @pytest.mark.asyncio
    async def test_a_well_supported_candidate_is_eligible(self, db):
        candidate = await _candidate(db)
        assert await _eligible_ids(db) == {candidate.id}

    @pytest.mark.asyncio
    async def test_thresholds_are_inclusive(self, db):
        candidate = await _candidate(
            db, confidence=MIN_CONFIDENCE, verification_confidence=MIN_VERIFICATION
        )
        assert await _eligible_ids(db) == {candidate.id}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["confidence", "verification_confidence"])
    async def test_a_score_just_under_the_bar_is_not_eligible(self, db, field):
        await _candidate(db, **{field: 0.79})
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("field", ["confidence", "verification_confidence"])
    async def test_a_missing_score_is_not_eligible(self, db, field):
        """No score is not a passing score."""
        await _candidate(db, **{field: None})
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_the_verifier_must_have_said_valid(self, db):
        await _candidate(db, verification={**GOOD_VERIFICATION, "is_valid": False})
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_a_verifier_that_never_ran_is_not_a_pass(self, db):
        """The truncation bug left observations with an empty verdict and 0.0.

        They failed for a reason that no longer exists, but auto-publish cannot
        tell that from here; they wait for a person or a re-verify pass.
        """
        await _candidate(
            db, verification_confidence=0.0,
            verification={"is_valid": False, "notes": "Ollama verification failed"},
        )
        await _candidate(db, verification={})
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_a_likely_duplicate_is_not_eligible(self, db):
        await _candidate(
            db, verification={**GOOD_VERIFICATION, "is_duplicate_likely": True}
        )
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_validation_errors_block_publication(self, db):
        await _candidate(db, validation_errors=["incident_date in the future"])
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    @pytest.mark.parametrize("event_type", ["news", "not_relevant"])
    async def test_only_attacks_and_sightings_are_eligible(self, db, event_type):
        await _candidate(db, event_type=event_type)
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_sightings_are_eligible(self, db):
        candidate = await _candidate(
            db, event_type="sighting",
            payload={**PAYLOAD, "classification": "sighting"},
        )
        assert await _eligible_ids(db) == {candidate.id}


class TestTheSourceMustHaveCarriedAnArticle:
    @pytest.mark.asyncio
    async def test_headline_only_source_is_not_eligible_however_confident(self, db):
        """The real case: 0.9 verification over a headline."""
        await _candidate(
            db,
            raw_metadata={"has_article_body": False},
            verification={
                **GOOD_VERIFICATION,
                "notes": "The text only provides a headline. No contradictions found.",
            },
        )
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_a_source_that_predates_the_body_flag_is_not_eligible(self, db):
        """Absent is not true. Pre-gate stragglers wait for a person."""
        await _candidate(db, raw_metadata={})
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_a_string_flag_is_not_a_body(self, db):
        """JSON round trips can turn booleans into strings; "false" is truthy."""
        await _candidate(db, raw_metadata={"has_article_body": "false"})
        assert await _eligible_ids(db) == set()


class TestTheNewestObservationGoverns:
    """review_candidate publishes the newest observation, so that is the one judged.

    Judging a different observation from the one published would let a good old
    extraction vouch for a bad new one.
    """

    @pytest.mark.asyncio
    async def test_a_bad_newer_observation_blocks_a_good_older_one(self, db):
        now = datetime.now(UTC)
        candidate = await _candidate(db, created_at=now - timedelta(hours=2))
        await _observation(
            db, candidate,
            confidence=0.4, verification_confidence=0.9,
            verification=GOOD_VERIFICATION, validation_errors=[],
            event_type="attack", raw_metadata={"has_article_body": True},
            payload=PAYLOAD, created_at=now,
        )
        await db.commit()
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_a_good_newer_observation_qualifies_despite_a_bad_older_one(self, db):
        now = datetime.now(UTC)
        candidate = await _candidate(
            db, confidence=0.4, created_at=now - timedelta(hours=2)
        )
        await _observation(
            db, candidate,
            confidence=0.9, verification_confidence=0.9,
            verification=GOOD_VERIFICATION, validation_errors=[],
            event_type="attack", raw_metadata={"has_article_body": True},
            payload=PAYLOAD, created_at=now,
        )
        await db.commit()
        assert await _eligible_ids(db) == {candidate.id}


def _dated(incident_date):
    return {**PAYLOAD, "incident_date": incident_date}


class TestTheIncidentDateMustFitTheArticle:
    """News reports an incident within days. A date far from the article's is a bad
    extraction or a retrospective, and either one needs a person.

    The 2026-09-10 manual --apply ran without this rule. It published a 2015, a
    2004 and a 2010 bite as 2026 cases, two incidents with no date at all, and
    several dated after the article that reported them.
    """

    @pytest.mark.asyncio
    async def test_an_incident_the_day_before_the_article_is_eligible(self, db):
        candidate = await _candidate(db)
        assert await _eligible_ids(db) == {candidate.id}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("incident_date", [None, "", "last Tuesday", "2026-13-01"])
    async def test_a_missing_or_unreadable_date_is_not_eligible(self, db, incident_date):
        await _candidate(db, payload=_dated(incident_date))
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_an_article_with_no_date_is_not_eligible(self, db):
        """Without the article's date there is nothing to check the incident's against."""
        await _candidate(db, published_at=None)
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_one_day_after_the_article_is_allowed_for_time_zones(self, db):
        """A 06:00 UTC article can report an incident on the same local day in Sydney."""
        candidate = await _candidate(db, payload=_dated("2026-09-09"))
        assert await _eligible_ids(db) == {candidate.id}

    @pytest.mark.asyncio
    async def test_an_incident_after_the_article_is_not_eligible(self, db):
        await _candidate(db, payload=_dated("2026-09-10"))
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_thirty_days_before_the_article_is_the_limit(self, db):
        candidate = await _candidate(db, payload=_dated("2026-08-09"))
        assert await _eligible_ids(db) == {candidate.id}

    @pytest.mark.asyncio
    @pytest.mark.parametrize("incident_date", ["2026-08-08", "2015-06-27"])
    async def test_a_retrospective_is_not_eligible(self, db, incident_date):
        await _candidate(db, payload=_dated(incident_date))
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_the_article_date_is_taken_in_utc(self, db):
        """23:30 on 09-08 in Hawaii is 09:30 on 09-09 in UTC, so 09-10 is within a day."""
        hawaii = timezone(timedelta(hours=-10))
        candidate = await _candidate(
            db,
            payload=_dated("2026-09-10"),
            published_at=datetime(2026, 9, 8, 23, 30, tzinfo=hawaii),
        )
        assert await _eligible_ids(db) == {candidate.id}


class TestOneCandidatePerArticle:
    """One article yields one publication per run.

    Later candidates from the same article wait for the next run. By then the
    first one is published, and submit_incident's source-URL match attaches them
    as citations instead of creating a new incident.
    """

    @pytest.mark.asyncio
    async def test_only_the_first_candidate_from_an_article_is_eligible(self, db):
        url = "https://example.com/one-article"
        first = await _candidate(db, source_url=url)
        await _candidate(db, source_url=url)

        report = await run(db, apply=False)

        assert [c.id for c in report.eligible] == [first.id]
        assert report.refusals["another candidate from the same article"] == 1

    @pytest.mark.asyncio
    async def test_different_articles_are_judged_separately(self, db):
        a = await _candidate(db, source_url="https://example.com/a")
        b = await _candidate(db, source_url="https://example.com/b")
        assert await _eligible_ids(db) == {a.id, b.id}


class TestScope:
    @pytest.mark.asyncio
    @pytest.mark.parametrize("status", ["published", "rejected", "merged", "approved"])
    async def test_only_candidates_awaiting_review_are_considered(self, db, status):
        await _candidate(db, status=status)
        assert await _eligible_ids(db) == set()

    @pytest.mark.asyncio
    async def test_a_candidate_with_no_observations_is_skipped(self, db):
        db.add(IncidentCandidate(id=uuid.uuid4(), status="needs_review"))
        await db.commit()
        assert await _eligible_ids(db) == set()


class TestEligibilityExplainsItself:
    def test_every_refusal_carries_a_reason(self):
        ok, reason = eligibility(None, None)
        assert ok is False and reason


# --- dry run and apply ----------------------------------------------------


async def _incident_count(db) -> int:
    return (await db.execute(select(func.count()).select_from(Incident))).scalar_one()


class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_writes_nothing(self, db):
        await _auto_publisher(db)
        candidate = await _candidate(db)

        report = await run(db, apply=False)

        assert [c.id for c in report.eligible] == [candidate.id]
        assert report.published == []
        await db.refresh(candidate)
        assert candidate.status == "needs_review"
        assert await _incident_count(db) == 0

    @pytest.mark.asyncio
    async def test_dry_run_does_not_need_the_account(self, db):
        """Reading the rule's judgment must not require the power to act on it."""
        await _candidate(db)
        report = await run(db, apply=False)
        assert len(report.eligible) == 1


class TestApply:
    @pytest.mark.asyncio
    async def test_publishes_through_the_admin_path(self, db):
        actor = await _auto_publisher(db)
        candidate = await _candidate(db)

        report = await run(db, apply=True)

        assert len(report.published) == 1
        await db.refresh(candidate)
        assert candidate.status == "published"
        assert candidate.canonical_incident_id is not None
        assert candidate.reviewed_by == actor.id
        assert await _incident_count(db) == 1

    @pytest.mark.asyncio
    async def test_the_review_note_records_why(self, db):
        """Someone auditing a record later must see it was the machine, and on what."""
        await _auto_publisher(db)
        candidate = await _candidate(db, confidence=0.91, verification_confidence=0.86)

        await run(db, apply=True)

        await db.refresh(candidate)
        note = candidate.review_notes or ""
        assert "auto" in note.lower()
        assert "0.91" in note and "0.86" in note

    @pytest.mark.asyncio
    async def test_ineligible_candidates_are_left_for_a_person(self, db):
        await _auto_publisher(db)
        weak = await _candidate(db, confidence=0.5)

        await run(db, apply=True)

        await db.refresh(weak)
        assert weak.status == "needs_review"

    @pytest.mark.asyncio
    async def test_refuses_to_apply_without_the_account(self, db):
        candidate = await _candidate(db)

        with pytest.raises(AutoPublisherMissing):
            await run(db, apply=True)

        await db.refresh(candidate)
        assert candidate.status == "needs_review"
        assert await _incident_count(db) == 0

    @pytest.mark.asyncio
    async def test_an_inactive_account_is_the_same_as_none(self, db):
        """Deactivating the account is how you switch this off without a deploy."""
        actor = await _auto_publisher(db)
        actor.is_active = False
        await db.commit()
        await _candidate(db)

        with pytest.raises(AutoPublisherMissing):
            await run(db, apply=True)
        assert await _incident_count(db) == 0

    @pytest.mark.asyncio
    async def test_one_unpublishable_candidate_does_not_stop_the_rest(self, db):
        """The payload passed the rule but fails IncidentCreate validation."""
        await _auto_publisher(db)
        # Dated, so the date rule passes it and IncidentCreate is what refuses it.
        broken = await _candidate(
            db, payload={"country": "Australia", "incident_date": "2026-09-07"}
        )
        good = await _candidate(db)
        # Read the ids now. run() rolls the shared session back after the failed
        # publish, which expires these objects too, and an expired attribute
        # cannot lazy-load under asyncio.
        broken_id, good_id = broken.id, good.id

        report = await run(db, apply=True)

        assert [c.id for c in report.published] == [good_id]
        assert [c.id for c, _ in report.failed] == [broken_id]
        still_waiting = await db.get(IncidentCandidate, broken_id)
        assert still_waiting.status == "needs_review"

    @pytest.mark.asyncio
    async def test_a_limit_caps_one_run(self, db):
        """A bad rule should be able to do only so much damage before you notice."""
        await _auto_publisher(db)
        # Three genuinely different incidents. Same beach and day would be merged
        # into one by submit_incident's duplicate check, which is correct.
        for day, (lat, lon) in enumerate([(-33.9, 151.3), (21.3, -157.8), (-34.0, 18.4)]):
            await _candidate(db, payload={
                **PAYLOAD,
                "incident_date": f"2026-09-0{day + 1}",
                "location_description": f"Beach {day}",
                "latitude": lat,
                "longitude": lon,
            })

        report = await run(db, apply=True, limit=2)

        assert len(report.published) == 2
        assert await _incident_count(db) == 2


# --- the account ----------------------------------------------------------


class TestAutoPublisherAccount:
    @pytest.mark.asyncio
    async def test_is_an_admin(self, db):
        actor = await ensure_auto_publisher(db)
        assert actor.username == AUTO_PUBLISHER_USERNAME
        assert actor.role == "admin"
        assert actor.is_active

    @pytest.mark.asyncio
    async def test_is_idempotent(self, db):
        first = await ensure_auto_publisher(db)
        second = await ensure_auto_publisher(db)
        assert first.id == second.id
        count = (await db.execute(
            select(func.count()).select_from(User)
            .where(User.username == AUTO_PUBLISHER_USERNAME)
        )).scalar_one()
        assert count == 1

    @pytest.mark.asyncio
    @pytest.mark.parametrize("guess", ["", "auto-publisher", "password", "admin"])
    async def test_cannot_be_logged_into(self, db, guess):
        """Its password is random and discarded, so no one holds a credential for it."""
        actor = await ensure_auto_publisher(db)
        assert not verify_password(guess, actor.password_hash)

    @pytest.mark.asyncio
    async def test_login_endpoint_refuses_it(self, db, client):
        await ensure_auto_publisher(db)
        response = await client.post(
            "/api/v1/auth/login",
            data={"username": AUTO_PUBLISHER_USERNAME, "password": ""},
        )
        assert response.status_code in (401, 422)

    @pytest.mark.asyncio
    async def test_does_not_reactivate_a_deliberately_disabled_account(self, db):
        """Re-running the bootstrap must not undo someone switching it off."""
        actor = await ensure_auto_publisher(db)
        actor.is_active = False
        await db.commit()

        again = await ensure_auto_publisher(db)
        assert again.is_active is False
