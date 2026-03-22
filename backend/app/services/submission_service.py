import math
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import asc, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import IncidentAuditLog
from app.models.incident import Incident
from app.models.source import IncidentSource
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentResponse, PaginatedIncidentResponse, PaginationMeta
from app.services.incident_service import _incident_to_response
from app.utils.case_number import generate_case_number
from app.utils.geo import point_from_coords


class SubmissionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def submit_incident(
        self, data: IncidentCreate, user: User
    ) -> IncidentResponse:
        """Public or verified contributor submission."""
        case_number = await generate_case_number(self.db)

        # Verified contributors get auto-published
        auto_verify = user.role in ("admin", "verified_contributor")

        incident = Incident(
            case_number=case_number,
            incident_date=data.incident_date,
            incident_time=data.incident_time,
            date_precision=data.date_precision,
            location_description=data.location_description,
            country=data.country,
            state_province=data.state_province,
            county_region=data.county_region,
            body_of_water=data.body_of_water,
            location_precision=data.location_precision,
            classification=data.classification,
            classification_subtype=data.classification_subtype,
            provocation_subtype=data.provocation_subtype,
            shark_species_confirmed=data.shark_species_confirmed,
            shark_species_suspected=data.shark_species_suspected,
            shark_size_estimate=data.shark_size_estimate,
            species_identification_method=data.species_identification_method,
            victim_activity=data.victim_activity,
            victim_injury_severity=data.victim_injury_severity,
            victim_injury_description=data.victim_injury_description,
            victim_age=data.victim_age,
            victim_sex=data.victim_sex,
            victim_name=data.victim_name,
            fatal=data.fatal,
            description=data.description,
            verification_status="verified" if auto_verify else "pending",
            submitted_by=user.id,
        )

        if auto_verify:
            incident.verified_by = user.id
            incident.verified_at = datetime.now(timezone.utc)

        if data.coordinates:
            incident.coordinates = point_from_coords(
                data.coordinates.longitude, data.coordinates.latitude
            )

        for source_data in data.sources:
            source = IncidentSource(
                source_type=source_data.source_type,
                source_url=source_data.source_url,
                source_title=source_data.source_title,
                source_publisher=source_data.source_publisher,
                source_date=source_data.source_date,
                source_notes=source_data.source_notes,
            )
            incident.sources.append(source)

        self.db.add(incident)
        await self.db.flush()

        # Audit log
        audit = IncidentAuditLog(
            incident_id=incident.id,
            action="created",
            changed_by=user.id,
            notes="submitted" if not auto_verify else "auto-verified submission",
        )
        self.db.add(audit)
        await self.db.commit()

        return await self._get_incident_response(incident.id)

    async def list_pending(
        self, page: int = 1, per_page: int = 25
    ) -> PaginatedIncidentResponse:
        """Admin: list pending submissions."""
        query = (
            select(Incident)
            .options(selectinload(Incident.sources))
            .where(Incident.verification_status.in_(["pending", "needs_review"]))
            .order_by(desc(Incident.submitted_at))
        )

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar_one()

        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await self.db.execute(query)
        incidents = result.scalars().unique().all()

        response_data = []
        for incident in incidents:
            data = _incident_to_response(incident)
            if incident.coordinates is not None:
                coord_result = await self.db.execute(
                    select(
                        ST_X(Incident.coordinates).label("lon"),
                        ST_Y(Incident.coordinates).label("lat"),
                    ).where(Incident.id == incident.id)
                )
                row = coord_result.one()
                data["longitude"] = row.lon
                data["latitude"] = row.lat
            response_data.append(IncidentResponse(**data))

        return PaginatedIncidentResponse(
            data=response_data,
            meta=PaginationMeta(
                total=total,
                page=page,
                per_page=per_page,
                pages=math.ceil(total / per_page) if total > 0 else 0,
            ),
        )

    async def verify_submission(
        self, incident_id: UUID, admin: User, notes: str | None = None
    ) -> IncidentResponse:
        incident = await self._get_incident(incident_id)
        if incident.verification_status == "verified":
            raise HTTPException(status_code=400, detail="Already verified")

        incident.verification_status = "verified"
        incident.verified_by = admin.id
        incident.verified_at = datetime.now(timezone.utc)

        audit = IncidentAuditLog(
            incident_id=incident.id,
            action="verified",
            changed_by=admin.id,
            notes=notes,
        )
        self.db.add(audit)
        await self.db.commit()

        return await self._get_incident_response(incident_id)

    async def reject_submission(
        self, incident_id: UUID, admin: User, notes: str | None = None
    ) -> IncidentResponse:
        incident = await self._get_incident(incident_id)

        incident.verification_status = "rejected"
        incident.verified_by = admin.id
        incident.verified_at = datetime.now(timezone.utc)

        audit = IncidentAuditLog(
            incident_id=incident.id,
            action="rejected",
            changed_by=admin.id,
            notes=notes,
        )
        self.db.add(audit)
        await self.db.commit()

        return await self._get_incident_response(incident_id)

    async def update_user_role(
        self, user_id: UUID, new_role: str, admin: User
    ) -> dict:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        old_role = user.role
        user.role = new_role
        await self.db.commit()

        return {
            "id": user.id,
            "username": user.username,
            "old_role": old_role,
            "new_role": new_role,
        }

    async def list_audit_log(
        self, incident_id: UUID | None = None, page: int = 1, per_page: int = 50
    ) -> dict:
        query = select(IncidentAuditLog).order_by(desc(IncidentAuditLog.changed_at))
        if incident_id:
            query = query.where(IncidentAuditLog.incident_id == incident_id)

        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar_one()

        offset = (page - 1) * per_page
        result = await self.db.execute(query.offset(offset).limit(per_page))
        logs = result.scalars().all()

        return {
            "data": [
                {
                    "id": log.id,
                    "incident_id": log.incident_id,
                    "action": log.action,
                    "changed_by": log.changed_by,
                    "changed_at": log.changed_at,
                    "changes": log.changes,
                    "notes": log.notes,
                }
                for log in logs
            ],
            "meta": {
                "total": total,
                "page": page,
                "per_page": per_page,
                "pages": math.ceil(total / per_page) if total > 0 else 0,
            },
        }

    async def _get_incident(self, incident_id: UUID) -> Incident:
        result = await self.db.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")
        return incident

    async def _get_incident_response(self, incident_id: UUID) -> IncidentResponse:
        from app.services.incident_service import IncidentService
        service = IncidentService(self.db)
        return await service.get_incident(incident_id)
