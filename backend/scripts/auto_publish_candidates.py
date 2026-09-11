"""Publish incident candidates that pass the automatic eligibility rule.

The rule
--------
A candidate awaiting review is eligible when its newest observation — the one
review_candidate would publish — has all of:

  * extraction confidence and verification confidence of at least 0.8
  * a verifier verdict of valid, and not a likely duplicate
  * no validation errors
  * an event type of attack or sighting
  * a source document that carried a real article body
  * an incident date no more than a day after the article's date and no more
    than 30 days before it

The body clause is the one confidence cannot replace. A queued sighting was
verified at 0.9 with the notes "The text only provides a headline ... No
contradictions found." The verifier was right: nothing contradicted the
extraction, because there was nothing there. Verification measures agreement
with the text, not whether the text was worth anything.

The date clause exists because a manual --apply on 2026-09-10, run before it
did, published a 2015, a 2004 and a 2010 bite as 2026 cases, two incidents
with no date, and several dated after the article reporting them. News covers
an incident within days; anything else is a retrospective or a misread date.

A run publishes at most one candidate per article. The others wait, and on the
next run submit_incident's source-URL match attaches them to the first as
citations rather than creating near-copies.

Everything that fails stays in needs_review for a person. Nothing here rejects.

Publication goes through IngestionService.review_candidate, the same path an
admin's Publish button takes, attributed to the auto-publisher service account
(see scripts.create_auto_publisher). Deactivating that account switches
--apply off.

Dry-run by default.
    python -m scripts.auto_publish_candidates [--apply] [--limit N]
"""

import argparse
import asyncio
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, date, timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models import User
from app.models.ingestion import ExtractedObservation, IncidentCandidate, SourceDocument
from app.services.ingestion_service import IngestionService
from scripts.create_auto_publisher import AUTO_PUBLISHER_USERNAME

MIN_CONFIDENCE = 0.8
MIN_VERIFICATION = 0.8
PUBLISHABLE_EVENT_TYPES = frozenset({"attack", "sighting"})

# The article's date is taken in UTC and the incident's is local, so an
# incident can fall on the article's next calendar day.
TIME_ZONE_SLACK = timedelta(days=1)
MAX_REPORTING_LAG = timedelta(days=30)
SAME_ARTICLE = "another candidate from the same article"

# One run publishes at most this many. A rule that turns out to be wrong should
# only be able to do so much before someone reads the output.
DEFAULT_LIMIT = 25


class AutoPublisherMissing(RuntimeError):
    """--apply was asked for, but there is no active account to publish as."""


@dataclass(frozen=True)
class Decision:
    """What the rule saw, captured as plain values.

    Deliberately not the ORM row: a failed publish rolls the session back and
    expires every loaded object, and reading an expired attribute afterwards
    would fail mid-run.
    """

    id: object
    confidence: float
    verification_confidence: float
    event_type: str
    source_url: str
    match_key: str | None


@dataclass
class Report:
    considered: int = 0
    eligible: list[Decision] = field(default_factory=list)
    published: list[Decision] = field(default_factory=list)
    failed: list[tuple[Decision, str]] = field(default_factory=list)
    refusals: Counter = field(default_factory=Counter)


def eligibility(
    observation: ExtractedObservation | None, source: SourceDocument | None
) -> tuple[bool, str]:
    """Judge one observation. Returns (eligible, reason); the reason names the failure."""
    if observation is None or source is None:
        return False, "no observation"

    if observation.event_type not in PUBLISHABLE_EVENT_TYPES:
        return False, f"event type {observation.event_type}"

    # `is True` throughout, not truthiness: absent is not a pass, and a flag that
    # round-tripped through JSON as the string "false" would otherwise count.
    if (source.raw_metadata or {}).get("has_article_body") is not True:
        return False, "no article body"

    verdict = observation.verification or {}
    if verdict.get("is_valid") is not True:
        # Includes the observations the 2026-09-08 truncation bug stranded with
        # an empty verdict: they failed for a reason that no longer exists, but
        # nothing here can tell that apart from a genuine refusal.
        return False, "verifier did not pass it"
    if verdict.get("is_duplicate_likely") is True:
        return False, "likely duplicate"

    if observation.validation_errors:
        return False, "validation errors"

    if observation.confidence is None or observation.confidence < MIN_CONFIDENCE:
        return False, "extraction confidence below bar"
    if (
        observation.verification_confidence is None
        or observation.verification_confidence < MIN_VERIFICATION
    ):
        return False, "verification confidence below bar"

    problem = date_problem(observation, source)
    if problem:
        return False, problem

    return True, "eligible"


def date_problem(observation: ExtractedObservation, source: SourceDocument) -> str | None:
    """Name what is wrong with the incident date against the article's, or None."""
    raw = (observation.payload or {}).get("incident_date")
    if not raw:
        return "no incident date"
    try:
        incident = date.fromisoformat(str(raw))
    except ValueError:
        return "unreadable incident date"
    if source.published_at is None:
        return "no article date"

    article = source.published_at.astimezone(UTC).date()
    if incident > article + TIME_ZONE_SLACK:
        return "incident dated after the article"
    if incident < article - MAX_REPORTING_LAG:
        return "incident over 30 days before the article"
    return None


def _newest(candidate: IncidentCandidate) -> ExtractedObservation | None:
    # The same choice review_candidate makes, so the observation judged is the
    # observation published.
    if not candidate.observations:
        return None
    return max(candidate.observations, key=lambda item: item.created_at)


async def _active_auto_publisher(db: AsyncSession) -> User:
    user = (
        await db.execute(select(User).where(User.username == AUTO_PUBLISHER_USERNAME))
    ).scalar_one_or_none()
    if user is None or not user.is_active or user.role != "admin":
        raise AutoPublisherMissing(
            f"no active admin account named {AUTO_PUBLISHER_USERNAME!r}; "
            "run `python -m scripts.create_auto_publisher` to create it"
        )
    return user


async def _judge(db: AsyncSession, report: Report) -> None:
    candidates = (
        await db.execute(
            select(IncidentCandidate)
            .where(IncidentCandidate.status == "needs_review")
            .options(
                selectinload(IncidentCandidate.observations).selectinload(
                    ExtractedObservation.source_document
                )
            )
            .order_by(IncidentCandidate.created_at)
        )
    ).scalars().all()

    articles_taken: set[str] = set()
    for candidate in candidates:
        report.considered += 1
        observation = _newest(candidate)
        source = observation.source_document if observation else None
        ok, reason = eligibility(observation, source)
        if not ok:
            report.refusals[reason] += 1
            continue
        # Oldest candidate first, so the earliest extraction of an article wins.
        if source.source_url in articles_taken:
            report.refusals[SAME_ARTICLE] += 1
            continue
        articles_taken.add(source.source_url)
        report.eligible.append(Decision(
            id=candidate.id,
            confidence=observation.confidence,
            verification_confidence=observation.verification_confidence,
            event_type=observation.event_type,
            source_url=source.source_url,
            match_key=candidate.match_key,
        ))


def _note(decision: Decision) -> str:
    return (
        f"Auto-published: extraction confidence {decision.confidence:.2f}, "
        f"verification confidence {decision.verification_confidence:.2f}, "
        "verifier verdict valid, source carried an article body."
    )


async def run(db: AsyncSession, *, apply: bool, limit: int = DEFAULT_LIMIT) -> Report:
    """Judge every candidate awaiting review, and publish the eligible ones if asked."""
    # Checked before anything is judged, so a missing account never leaves a
    # run half done.
    actor = await _active_auto_publisher(db) if apply else None

    report = Report()
    await _judge(db, report)
    if not apply:
        return report

    service = IngestionService(db)
    for decision in report.eligible[:limit]:
        try:
            await service.review_candidate(decision.id, "publish", actor, _note(decision))
        except HTTPException as exc:
            # review_candidate commits only on success; roll back whatever the
            # failed attempt left so the next candidate starts clean. The
            # rollback expires every loaded object, the actor included, and an
            # expired row cannot lazy-load under asyncio, so fetch it again. That
            # also re-checks it is still active mid-run.
            await db.rollback()
            report.failed.append((decision, str(exc.detail)))
            actor = await _active_auto_publisher(db)
            continue
        report.published.append(decision)
    return report


def _print(report: Report, *, apply: bool, limit: int) -> None:
    print(f"awaiting review : {report.considered}")
    print(f"eligible        : {len(report.eligible)}")
    for reason, count in report.refusals.most_common():
        print(f"  held — {reason:<34} {count}")

    if not apply:
        print(f"\nDRY RUN — nothing written. --apply would publish up to {limit}:")
        for d in report.eligible[:limit]:
            print(f"  {d.event_type:<8} ext {d.confidence:.2f}  ver "
                  f"{d.verification_confidence:.2f}  {d.source_url}")
        return

    print(f"\npublished       : {len(report.published)}")
    print(f"failed          : {len(report.failed)}")
    for d, detail in report.failed:
        print(f"  {d.id}  {detail}")
    deferred = max(len(report.eligible) - limit, 0)
    if deferred:
        print(f"deferred        : {deferred} (over the per-run limit of {limit})")


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="publish eligible candidates")
    parser.add_argument(
        "--limit", type=int, default=DEFAULT_LIMIT,
        help=f"publish at most this many in one run (default {DEFAULT_LIMIT})",
    )
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be at least 1")

    async with async_session() as db:
        try:
            report = await run(db, apply=args.apply, limit=args.limit)
        except AutoPublisherMissing as exc:
            print(f"auto_publish_candidates: {exc}", file=sys.stderr)
            return 1

    _print(report, apply=args.apply, limit=args.limit)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
