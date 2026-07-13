import re

from geoalchemy2 import Geography
from sqlalchemy import cast, delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import IncidentAuditLog
from app.models.incident import Incident
from app.models.news import NewsItem
from app.models.source import IncidentSource
from app.schemas.incident import IncidentCreate, SourceCreate
from app.utils.geo import point_from_coords

_MATCH_RADIUS_M = 150
_GENERIC_HEADLINE_PREFIXES = (
    "a full list of",
    "latest articles",
    "recent articles",
)


def _headline_fingerprint(title: str | None) -> str | None:
    """Normalize syndicated headlines while discarding outlet suffixes."""
    if not title:
        return None
    headline = title.rsplit(" - ", 1)[0]
    fingerprint = re.sub(r"\s+", " ", headline).strip().casefold()
    if len(fingerprint) < 30 or fingerprint.startswith(_GENERIC_HEADLINE_PREFIXES):
        return None
    return fingerprint


async def _find_source_duplicate(
    db: AsyncSession, sources: list[SourceCreate]
) -> Incident | None:
    """Match exact URLs or syndicated versions of the exact same headline."""
    urls = {source.source_url for source in sources if source.source_url}
    if urls:
        result = await db.execute(
            select(Incident)
            .join(IncidentSource)
            .options(selectinload(Incident.sources))
            .where(
                IncidentSource.source_url.in_(urls),
                Incident.verification_status != "rejected",
            )
            .order_by(Incident.case_number.asc())
        )
        match = result.scalars().first()
        if match:
            return match

    fingerprints = {
        fingerprint
        for source in sources
        if (fingerprint := _headline_fingerprint(source.source_title))
    }
    for fingerprint in fingerprints:
        prefix = fingerprint[:80]
        escaped = prefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        result = await db.execute(
            select(Incident)
            .join(IncidentSource)
            .options(selectinload(Incident.sources))
            .where(
                func.lower(IncidentSource.source_title).like(f"{escaped}%", escape="\\"),
                Incident.verification_status != "rejected",
            )
            .order_by(Incident.case_number.asc())
        )
        for incident in result.scalars().unique():
            if any(
                _headline_fingerprint(source.source_title) == fingerprint
                for source in incident.sources
            ):
                return incident
    return None


def _victim_conflict(inc: Incident, data: IncidentCreate) -> bool:
    """True if the victim details positively contradict (both present and differ)."""
    if inc.victim_age is not None and data.victim_age is not None and inc.victim_age != data.victim_age:
        return True
    if inc.victim_sex is not None and data.victim_sex is not None and inc.victim_sex != data.victim_sex:
        return True
    return False


async def find_duplicate_incident(db: AsyncSession, data: IncidentCreate) -> Incident | None:
    """Return an existing incident that is the same real-world event as `data`, else None.

    Exact source URLs and syndicated copies of the same specific headline are
    definitive matches. Otherwise, same event = exact-precision same date +
    coordinates within 150 m + same classification, with a victim age/sex
    guard. Conservative by design.
    """
    source_match = await _find_source_duplicate(db, data.sources)
    if source_match:
        return source_match

    if data.date_precision != "exact" or data.incident_date is None or data.coordinates is None:
        return None

    point = point_from_coords(data.coordinates.longitude, data.coordinates.latitude)
    stmt = (
        select(Incident)
        .options(selectinload(Incident.sources))
        .where(
            Incident.incident_date == data.incident_date,
            Incident.classification == data.classification,
            Incident.verification_status != "rejected",
            Incident.coordinates.isnot(None),
            func.ST_DWithin(
                cast(Incident.coordinates, Geography),
                cast(point, Geography),
                _MATCH_RADIUS_M,
            ),
        )
        .order_by(Incident.case_number.asc())
    )
    candidates = (await db.execute(stmt)).scalars().all()
    for inc in candidates:
        if not _victim_conflict(inc, data):
            return inc
    return None


async def attach_sources_to_incident(
    db: AsyncSession,
    incident: Incident,
    new_sources: list[SourceCreate],
    changed_by=None,
) -> None:
    """Append new outlet sources to an existing incident (skipping URLs already
    present) and record a source_merged audit entry. Commits."""
    existing_urls = {s.source_url for s in incident.sources if s.source_url}
    added: list[str] = []
    for sd in new_sources:
        if sd.source_url and sd.source_url in existing_urls:
            continue
        incident.sources.append(
            IncidentSource(
                source_type=sd.source_type,
                source_url=sd.source_url,
                source_title=sd.source_title,
                source_publisher=sd.source_publisher,
                source_date=sd.source_date,
                source_notes=sd.source_notes,
            )
        )
        if sd.source_url:
            existing_urls.add(sd.source_url)
        added.append(sd.source_publisher or sd.source_url or sd.source_title or "source")

    db.add(
        IncidentAuditLog(
            incident_id=incident.id,
            action="source_merged",
            changed_by=changed_by,
            notes=(
                f"Merged duplicate coverage: {', '.join(added)}"
                if added
                else "Duplicate submission (no new sources)"
            ),
        )
    )
    await db.commit()


_ENRICH_FIELDS = [
    "incident_time", "state_province", "county_region", "body_of_water",
    "classification_subtype", "provocation_subtype", "shark_species_confirmed",
    "shark_species_suspected", "shark_size_estimate", "species_identification_method",
    "victim_activity", "victim_injury_severity", "victim_injury_description",
    "victim_age", "victim_sex", "victim_name", "description",
]


def _would_fill(canonical, absorbed) -> list[str]:
    """Field names that would be filled on canonical from absorbed (no mutation)."""
    filled = [f for f in _ENRICH_FIELDS
              if getattr(canonical, f) is None and getattr(absorbed, f) is not None]
    if absorbed.fatal and not canonical.fatal:
        filled.append("fatal")
    return filled


def _enrich(canonical, absorbed) -> list[str]:
    """Fill canonical's NULL fields from absorbed's non-null values. Returns filled names."""
    filled: list[str] = []
    for f in _ENRICH_FIELDS:
        if getattr(canonical, f) is None and getattr(absorbed, f) is not None:
            setattr(canonical, f, getattr(absorbed, f))
            filled.append(f)
    if absorbed.fatal and not canonical.fatal:
        canonical.fatal = True
        filled.append("fatal")
    return filled


async def merge_cluster(db, incident_ids, action: str) -> int:
    """Merge the given incidents into the lowest-case-number canonical. Commits.
    Moves sources (dedup by URL), prunes absorbed backfill news + re-points others,
    enriches canonical, audit-logs, deletes absorbed. Returns absorbed count."""
    rows = (
        await db.execute(
            select(Incident).where(Incident.id.in_(incident_ids)).order_by(Incident.case_number.asc())
        )
    ).scalars().all()
    if len(rows) < 2:
        return 0
    canonical = rows[0]
    canon_urls = {
        s.source_url
        for s in (
            await db.execute(select(IncidentSource).where(IncidentSource.incident_id == canonical.id))
        ).scalars().all()
        if s.source_url
    }
    absorbed_count = 0
    for inc in rows[1:]:
        srcs = (
            await db.execute(select(IncidentSource).where(IncidentSource.incident_id == inc.id))
        ).scalars().all()
        for s in srcs:
            if s.source_url and s.source_url in canon_urls:
                await db.execute(delete(IncidentSource).where(IncidentSource.id == s.id))
            else:
                await db.execute(
                    update(IncidentSource).where(IncidentSource.id == s.id).values(incident_id=canonical.id)
                )
                if s.source_url:
                    canon_urls.add(s.source_url)
        await db.execute(
            delete(NewsItem).where(
                NewsItem.promoted_incident_id == inc.id, NewsItem.dedup_key.like("backfill:%")
            )
        )
        await db.execute(
            update(NewsItem).where(NewsItem.promoted_incident_id == inc.id).values(
                promoted_incident_id=canonical.id
            )
        )
        db.add(IncidentAuditLog(incident_id=canonical.id, action=action,
                                notes=f"Absorbed duplicate {inc.case_number}"))
        if _enrich(canonical, inc):
            db.add(canonical)
        await db.execute(delete(Incident).where(Incident.id == inc.id))
        absorbed_count += 1
    await db.commit()
    return absorbed_count
