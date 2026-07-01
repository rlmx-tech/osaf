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
from sqlalchemy import Numeric, delete, func, select, update

from app.database import async_session
from app.models.audit import IncidentAuditLog
from app.models.incident import Incident
from app.models.news import NewsItem
from app.models.source import IncidentSource
from app.services.dedup_service import _victim_conflict

_ENRICH_FIELDS = [
    "incident_time", "state_province", "county_region", "body_of_water",
    "classification_subtype", "provocation_subtype", "shark_species_confirmed",
    "shark_species_suspected", "shark_size_estimate", "species_identification_method",
    "victim_activity", "victim_injury_severity", "victim_injury_description",
    "victim_age", "victim_sex", "victim_name", "description",
]


def _enrich(canonical: Incident, absorbed: Incident) -> list[str]:
    """Fill canonical's NULL fields from absorbed's non-null values.

    Returns the list of field names that were filled (empty if nothing changed).
    NEVER overwrites a non-null canonical value.
    """
    filled: list[str] = []
    for field in _ENRICH_FIELDS:
        if getattr(canonical, field) is None and getattr(absorbed, field) is not None:
            setattr(canonical, field, getattr(absorbed, field))
            filled.append(field)
    # fatal is a non-null bool — upgrade to True if absorbed was fatal
    if absorbed.fatal and not canonical.fatal:
        canonical.fatal = True
        filled.append("fatal")
    return filled


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
                    select(Incident)
                    .where(Incident.id.in_(ids))
                    .order_by(Incident.case_number.asc())
                )
            ).scalars().all()
            if len(rows) < 2:
                continue
            canonical = rows[0]
            # canonical source URLs (for dedup when moving absorbed sources)
            canon_urls = {
                s.source_url
                for s in (
                    await db.execute(
                        select(IncidentSource).where(IncidentSource.incident_id == canonical.id)
                    )
                ).scalars().all()
                if s.source_url
            }
            absorbed = [inc for inc in rows[1:] if not _victim_conflict(canonical, _as_create(inc))]
            if not absorbed:
                continue
            clusters += 1
            for inc in absorbed:
                print(f"  merge {inc.case_number} -> {canonical.case_number}")
                if apply:
                    # move sources not already present (by url)
                    srcs = (
                        await db.execute(
                            select(IncidentSource).where(IncidentSource.incident_id == inc.id)
                        )
                    ).scalars().all()
                    for s in srcs:
                        if s.source_url and s.source_url in canon_urls:
                            await db.execute(delete(IncidentSource).where(IncidentSource.id == s.id))
                        else:
                            await db.execute(
                                update(IncidentSource)
                                .where(IncidentSource.id == s.id)
                                .values(incident_id=canonical.id)
                            )
                            if s.source_url:
                                canon_urls.add(s.source_url)
                    # absorbed backfill news -> delete; other news -> re-point
                    await db.execute(
                        delete(NewsItem).where(
                            NewsItem.promoted_incident_id == inc.id,
                            NewsItem.dedup_key.like("backfill:%"),
                        )
                    )
                    await db.execute(
                        update(NewsItem)
                        .where(NewsItem.promoted_incident_id == inc.id)
                        .values(promoted_incident_id=canonical.id)
                    )
                    db.add(
                        IncidentAuditLog(
                            incident_id=canonical.id,
                            action="merged",
                            notes=f"Absorbed duplicate {inc.case_number}",
                        )
                    )
                    # enrich canonical with non-null fields from absorbed before deleting it
                    filled = _enrich(canonical, inc)
                    if filled:
                        db.add(canonical)
                    await db.execute(delete(Incident).where(Incident.id == inc.id))
                else:
                    would_fill = _enrich(canonical, inc)
                    if would_fill:
                        print(f"    would fill from {inc.case_number}: {', '.join(would_fill)}")
                merged += 1
            if apply:
                await db.commit()
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
