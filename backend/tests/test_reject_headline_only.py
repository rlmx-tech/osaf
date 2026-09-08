"""Selection logic for the headline-only candidate bulk reject.

The dangerous failure here is over-selection: rejecting a candidate that had a
real article behind it. The rule is deliberately generous — one good source
spares the whole candidate.
"""

import uuid

import pytest
from sqlalchemy import select

from app.models.ingestion import ExtractedObservation, IncidentCandidate, SourceDocument
from scripts.reject_headline_only_candidates import (
    DEFAULT_MIN_BODY_CHARS,
    _candidates_to_reject,
)

# The real shape of a Google News stub: the headline, repeated, in an anchor tag.
HEADLINE = "Three years after fatal shark attack, community cements teacher's legacy"
GOOGLE_STUB = f'{HEADLINE}\n\n<a href="https://news.google.com/rss/articles/CBMiqwFB">{HEADLINE}</a>'
REAL_ARTICLE = "A surfer was bitten at Bondi Beach on Tuesday afternoon. " * 40


async def _make_candidate(db, bodies: list[str]) -> IncidentCandidate:
    """A candidate with one observation per supplied source body."""
    candidate = IncidentCandidate(id=uuid.uuid4(), status="needs_review")
    db.add(candidate)
    await db.flush()

    for i, body in enumerate(bodies):
        doc = SourceDocument(
            id=uuid.uuid4(),
            dedup_key=f"test:{candidate.id}:{i}",
            source_platform="news_rss",
            source_name="Test Feed",
            source_url=f"https://example.com/{candidate.id}/{i}",
            title=HEADLINE,
            body_excerpt=body,
        )
        db.add(doc)
        await db.flush()
        db.add(ExtractedObservation(
            id=uuid.uuid4(),
            source_document_id=doc.id,
            candidate_id=candidate.id,
            extractor_name="test",
            model_name="test-model",
            prompt_version="1",
            payload={"country": "Australia"},
            payload_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
            event_type="attack",
        ))
    await db.commit()
    return candidate


@pytest.mark.asyncio
async def test_headline_only_candidate_is_selected(db):
    candidate = await _make_candidate(db, [GOOGLE_STUB])
    doomed = await _candidates_to_reject(db, DEFAULT_MIN_BODY_CHARS)
    assert [c.id for c in doomed] == [candidate.id]


@pytest.mark.asyncio
async def test_candidate_with_a_real_article_is_spared(db):
    await _make_candidate(db, [REAL_ARTICLE])
    assert await _candidates_to_reject(db, DEFAULT_MIN_BODY_CHARS) == []


@pytest.mark.asyncio
async def test_one_good_source_spares_the_whole_candidate(db):
    """Mixed sources must not be rejected — the good one makes it reviewable."""
    await _make_candidate(db, [GOOGLE_STUB, REAL_ARTICLE, GOOGLE_STUB])
    assert await _candidates_to_reject(db, DEFAULT_MIN_BODY_CHARS) == []


@pytest.mark.asyncio
async def test_html_tags_do_not_count_toward_the_body_floor(db):
    """A stub padded with markup must not sneak past the floor."""
    padded = "<div>" + ("<span></span>" * 80) + f"{HEADLINE}</div>"
    assert len(padded) > DEFAULT_MIN_BODY_CHARS  # long only because of tags
    candidate = await _make_candidate(db, [padded])
    doomed = await _candidates_to_reject(db, DEFAULT_MIN_BODY_CHARS)
    assert [c.id for c in doomed] == [candidate.id]


@pytest.mark.asyncio
async def test_already_reviewed_candidates_are_left_alone(db):
    candidate = await _make_candidate(db, [GOOGLE_STUB])
    candidate.status = "published"
    await db.commit()
    assert await _candidates_to_reject(db, DEFAULT_MIN_BODY_CHARS) == []


@pytest.mark.asyncio
async def test_null_body_is_selected(db):
    candidate = await _make_candidate(db, [None])
    doomed = await _candidates_to_reject(db, DEFAULT_MIN_BODY_CHARS)
    assert [c.id for c in doomed] == [candidate.id]


@pytest.mark.asyncio
async def test_floor_is_configurable(db):
    """A lower floor spares borderline sources."""
    medium = "x" * 300
    await _make_candidate(db, [medium])
    assert len(await _candidates_to_reject(db, 400)) == 1   # 300 < 400 → rejected
    assert await _candidates_to_reject(db, 200) == []       # 300 >= 200 → spared


@pytest.mark.asyncio
async def test_candidate_with_no_observations_at_all_is_selected(db):
    """Nothing to ground it in, so it cannot support an incident either."""
    candidate = IncidentCandidate(id=uuid.uuid4(), status="needs_review")
    db.add(candidate)
    await db.commit()
    doomed = await _candidates_to_reject(db, DEFAULT_MIN_BODY_CHARS)
    assert [c.id for c in doomed] == [candidate.id]


@pytest.mark.asyncio
async def test_orphaned_observation_does_not_suppress_selection(db):
    """An observation with a NULL candidate_id must not blind the query.

    Regression for a real bug: the first version used
    `IncidentCandidate.id.not_in(subquery)`, and in SQL `x NOT IN (... NULL ...)`
    is never true. candidate_id is nullable, so one orphaned observation made
    the script select zero candidates — it reported "nothing to do" against a
    production backlog of 672. Failed safe, but silently wrong.
    """
    candidate = await _make_candidate(db, [GOOGLE_STUB])

    orphan_doc = SourceDocument(
        id=uuid.uuid4(),
        dedup_key=f"test:orphan:{uuid.uuid4()}",
        source_platform="news_rss",
        source_name="Orphan Feed",
        source_url="https://example.com/orphan",
        title="Orphan",
        body_excerpt=REAL_ARTICLE,
    )
    db.add(orphan_doc)
    await db.flush()
    db.add(ExtractedObservation(
        id=uuid.uuid4(),
        source_document_id=orphan_doc.id,
        candidate_id=None,                     # the NULL that broke NOT IN
        extractor_name="test",
        model_name="test-model",
        prompt_version="1",
        payload={},
        payload_sha256=uuid.uuid4().hex + uuid.uuid4().hex,
        event_type="attack",
    ))
    await db.commit()

    doomed = await _candidates_to_reject(db, DEFAULT_MIN_BODY_CHARS)
    assert [c.id for c in doomed] == [candidate.id]


@pytest.mark.asyncio
async def test_another_candidates_good_source_does_not_spare_this_one(db):
    """The body check must be scoped per candidate, not global."""
    stub_candidate = await _make_candidate(db, [GOOGLE_STUB])
    await _make_candidate(db, [REAL_ARTICLE])

    doomed = await _candidates_to_reject(db, DEFAULT_MIN_BODY_CHARS)
    assert [c.id for c in doomed] == [stub_candidate.id]
