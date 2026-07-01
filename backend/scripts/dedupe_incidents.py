"""Merge duplicate incidents created by multiple outlets covering one event.

Same event = exact-precision same date + coordinates (rounded to 3 dp ~= 111 m)
+ same classification, with a victim age/sex guard. Canonical = lowest case number.
Absorbed incidents: sources moved to canonical (dedup by URL), their news_items
re-pointed to canonical (backfill news deleted), audit-logged, then deleted.

Note: the cleanup clusters by rounded-3dp coordinate GRID CELLS (~111 m), which can
leave a few near-cell-boundary duplicates that the live 150 m-radius matcher would
catch; that residual is expected and safe (under-inclusive, never wrong-merging).

Dry-run by default; pass --apply to perform the merges.
    python -m scripts.dedupe_incidents [--apply]
"""

import asyncio
import sys

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import Numeric, func, select

from app.database import async_session
from app.models.incident import Incident
from app.services.dedup_service import _victim_conflict, _would_fill, merge_cluster


async def _clusters(db):
    """Return lists of incident ids sharing (date, classification, rounded coords)."""
    lat = func.round(ST_Y(Incident.coordinates).cast(Numeric), 3)
    lon = func.round(ST_X(Incident.coordinates).cast(Numeric), 3)
    stmt = (
        select(func.array_agg(Incident.id))
        .where(
            Incident.date_precision == "exact",
            Incident.incident_date.isnot(None),
            Incident.coordinates.isnot(None),
        )
        .group_by(Incident.incident_date, Incident.classification, lat, lon)
        .having(func.count() > 1)
    )
    return [row[0] for row in (await db.execute(stmt)).all()]


async def run(apply: bool) -> dict:
    merged = 0
    clusters = 0
    async with async_session() as db:
        for ids in await _clusters(db):
            rows = (
                await db.execute(
                    select(Incident).where(Incident.id.in_(ids)).order_by(Incident.case_number.asc())
                )
            ).scalars().all()
            if len(rows) < 2:
                continue
            canonical = rows[0]
            absorbed = [inc for inc in rows[1:] if not _victim_conflict(canonical, _as_create(inc))]
            if not absorbed:
                continue
            clusters += 1
            if apply:
                merged += await merge_cluster(db, [canonical.id] + [i.id for i in absorbed], "merged")
            else:
                for inc in absorbed:
                    print(f"  merge {inc.case_number} -> {canonical.case_number}")
                    wf = _would_fill(canonical, inc)
                    if wf:
                        print(f"    would fill from {inc.case_number}: {', '.join(wf)}")
                    merged += 1
    print(f"dedupe_incidents: {'APPLIED' if apply else 'DRY-RUN'} — clusters={clusters}, incidents_merged={merged}")
    return {"clusters": clusters, "incidents_merged": merged}


def _as_create(inc: Incident):
    """Adapt an Incident to the minimal shape _victim_conflict's 2nd arg needs."""
    class _V:
        victim_age = inc.victim_age
        victim_sex = inc.victim_sex
    return _V()


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
