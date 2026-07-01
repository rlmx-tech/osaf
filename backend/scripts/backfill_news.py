"""Backfill news_items from existing incidents so the Shark News feed has content.

The collector only captures NEW items into news_items (previously-seen source URLs
are deduped out), so a freshly-deployed feed starts empty. This one-off backfill
creates one news_item per existing incident, linked back to it, so the feed shows
the historical record immediately.

Idempotent: keyed `dedup_key="backfill:<incident_id>"` and inserted with
ON CONFLICT DO NOTHING — safe to re-run (re-runs skip existing rows).

Run inside the backend container:
    python -m scripts.backfill_news
"""

import asyncio
from datetime import datetime, time, timezone

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.incident import Incident
from app.models.news import NewsItem


def _event_type(classification: str) -> str:
    """Map an incident classification to a news_items.event_type value."""
    return "sighting" if classification == "sighting" else "attack"


async def main() -> None:
    inserted = 0
    skipped = 0
    async with async_session() as db:
        result = await db.execute(
            select(Incident).options(selectinload(Incident.sources))
        )
        incidents = result.scalars().unique().all()

        for inc in incidents:
            source = inc.sources[0] if inc.sources else None

            # captured_at drives feed ordering — use the incident date so the feed
            # reads chronologically, falling back to when the record was submitted.
            if inc.incident_date:
                captured = datetime.combine(
                    inc.incident_date, time(12, 0), tzinfo=timezone.utc
                )
            else:
                captured = inc.submitted_at

            title = (
                source.source_title
                if source and source.source_title
                else f"{inc.classification.replace('_', ' ').title()} — {inc.location_description}"
            )

            values = {
                "dedup_key": f"backfill:{inc.id}",
                "source_platform": inc.report_platform or "web_scrape",
                "source_name": (
                    source.source_publisher
                    if source and source.source_publisher
                    else (inc.report_source or "OSAF")
                ),
                "source_url": (source.source_url if source and source.source_url else ""),
                "title": title,
                "summary": inc.description,
                "author": source.source_publisher if source else None,
                "image_url": None,
                "published_at": captured,
                "captured_at": captured,
                "event_type": _event_type(inc.classification),
                "country": inc.country,
                "ai_confidence": None,
                "promoted_incident_id": inc.id,
            }

            stmt = (
                pg_insert(NewsItem)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["dedup_key"])
                .returning(NewsItem.id)
            )
            res = await db.execute(stmt)
            if res.scalar_one_or_none() is not None:
                inserted += 1
            else:
                skipped += 1

        await db.commit()

    print(f"backfill_news: inserted {inserted}, skipped (already present) {skipped}")


if __name__ == "__main__":
    asyncio.run(main())
