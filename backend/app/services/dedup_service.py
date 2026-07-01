from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import IncidentAuditLog
from app.models.incident import Incident
from app.models.source import IncidentSource
from app.schemas.incident import IncidentCreate, SourceCreate
from app.utils.geo import point_from_coords

_MATCH_RADIUS_M = 150


def _victim_conflict(inc: Incident, data: IncidentCreate) -> bool:
    """True if the victim details positively contradict (both present and differ)."""
    if inc.victim_age is not None and data.victim_age is not None and inc.victim_age != data.victim_age:
        return True
    if inc.victim_sex is not None and data.victim_sex is not None and inc.victim_sex != data.victim_sex:
        return True
    return False


async def find_duplicate_incident(db: AsyncSession, data: IncidentCreate) -> Incident | None:
    """Return an existing incident that is the same real-world event as `data`, else None.

    Same event = exact-precision same date + coordinates within 150 m + same
    classification, with a victim age/sex guard. Conservative by design.
    """
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
