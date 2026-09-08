"""Bulk-reject incident candidates that were extracted from headline-only sources.

Why these cannot be salvaged
----------------------------
Google News RSS serves an item whose body is the headline wrapped in an anchor
tag, and its `link` is an opaque `news.google.com/rss/articles/CBMi...` wrapper
that does not redirect to the publisher. Measured 2026-09-08: following
redirects lands back on news.google.com, base64-decoding the wrapper yielded a
URL for 0 of 6 samples, and the rendered page exposes no publisher link. So
there is no article to go back and fetch for these rows.

The extractor was therefore asked to produce a dated, geocoded, classified
incident from a headline. It did what it had to: it guessed. The result is
records like "Three years after fatal shark attack, community cements teacher's
legacy" becoming a NEW fatality dated 2026, and "Australia expands
shark-spotting drone program" becoming an unprovoked attack. Retrospectives,
follow-ups, policy pieces and survivor profiles all read as fresh incidents.

Publishing them would fabricate shark attacks, including deaths, in a public
database. Rejecting is the correct outcome, not a concession.

This is a one-off for the pre-2026-09-08 backlog. The durable fix is the
promotion gate in the collector pipeline, which stops headline-only sources
becoming candidates at all.

Dry-run by default; pass --apply to perform the rejections.
    python -m scripts.reject_headline_only_candidates [--apply] [--min-body N]
"""

import argparse
import asyncio
import sys

from sqlalchemy import func, select

from app.database import async_session
from app.models.ingestion import ExtractedObservation, IncidentCandidate, SourceDocument

# Below this many characters of body text (after stripping HTML) a source cannot
# support an incident record. Google News stubs land near the headline length;
# a genuine article runs into the thousands.
DEFAULT_MIN_BODY_CHARS = 400

REJECT_NOTE = (
    "Bulk-rejected: extracted from a headline-only source with no retrievable "
    "article body (Google News RSS wrapper URLs do not resolve to the "
    "publisher), so the extraction could not be grounded in article text."
)


def _stripped_body_length():
    """Length of body_excerpt with HTML tags removed."""
    return func.length(
        func.regexp_replace(func.coalesce(SourceDocument.body_excerpt, ""), "<[^>]+>", "", "g")
    )


async def _candidates_to_reject(db, min_body: int):
    """Candidates in needs_review whose every source is below the body floor.

    A candidate is spared if ANY of its observations came from a real body — one
    good source is enough to make the record reviewable.
    """
    body_len = _stripped_body_length()

    has_real_body = (
        select(ExtractedObservation.candidate_id)
        .join(SourceDocument, SourceDocument.id == ExtractedObservation.source_document_id)
        .where(body_len >= min_body)
        .distinct()
    )

    stmt = (
        select(IncidentCandidate)
        .where(
            IncidentCandidate.status == "needs_review",
            IncidentCandidate.id.not_in(has_real_body),
        )
        .order_by(IncidentCandidate.created_at)
    )
    return list((await db.execute(stmt)).scalars().all())


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="perform the rejections")
    parser.add_argument(
        "--min-body",
        type=int,
        default=DEFAULT_MIN_BODY_CHARS,
        help=f"body-text floor in characters (default {DEFAULT_MIN_BODY_CHARS})",
    )
    args = parser.parse_args()

    async with async_session() as db:
        total_pending = (
            await db.execute(
                select(func.count())
                .select_from(IncidentCandidate)
                .where(IncidentCandidate.status == "needs_review")
            )
        ).scalar_one()

        doomed = await _candidates_to_reject(db, args.min_body)

        print(f"candidates in needs_review : {total_pending}")
        print(f"body floor                 : {args.min_body} chars")
        print(f"to reject (no real body)   : {len(doomed)}")
        print(f"left for human review      : {total_pending - len(doomed)}")

        if not doomed:
            print("\nNothing to do.")
            return 0

        if not args.apply:
            print("\nDRY RUN — nothing written. Re-run with --apply to reject.")
            print("Sample of what would be rejected:")
            for c in doomed[:5]:
                print(f"  {c.id}  created={c.created_at:%Y-%m-%d}  key={(c.match_key or '')[:60]}")
            return 0

        now = func.now()
        for candidate in doomed:
            candidate.status = "rejected"
            candidate.review_notes = REJECT_NOTE
            candidate.reviewed_at = now
            # reviewed_by stays NULL: no human made this call, and recording a
            # person as the reviewer would misattribute a bulk operation.
        await db.commit()

        print(f"\nRejected {len(doomed)} candidates.")
        print("reviewed_by left NULL — this was a bulk operation, not a human review.")
        return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
