import math
import re
from datetime import date
from uuid import UUID

from fastapi import HTTPException
from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import asc, desc, func, literal_column, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.incident import Incident
from app.models.source import IncidentSource
from app.schemas.incident import (
    IncidentCreate,
    IncidentResponse,
    IncidentUpdate,
    PaginatedIncidentResponse,
    PaginationMeta,
    PublicIncidentResponse,
)
from app.services.dedup_service import attach_sources_to_incident, find_duplicate_incident
from app.utils.case_number import generate_case_number
from app.utils.geo import point_from_coords

ALLOWED_SORT_FIELDS = {
    "incident_date", "case_number", "country", "classification",
    "victim_injury_severity", "fatal", "submitted_at", "updated_at",
}


def _incident_to_response(incident: Incident) -> dict:
    """Convert an Incident ORM object to a response dict with extracted coordinates."""
    data = {
        "id": incident.id,
        "case_number": incident.case_number,
        "incident_date": incident.incident_date,
        "incident_time": incident.incident_time,
        "date_precision": incident.date_precision,
        "location_description": incident.location_description,
        "country": incident.country,
        "state_province": incident.state_province,
        "county_region": incident.county_region,
        "body_of_water": incident.body_of_water,
        "longitude": None,
        "latitude": None,
        "location_precision": incident.location_precision,
        "classification": incident.classification,
        "classification_subtype": incident.classification_subtype,
        "provocation_subtype": incident.provocation_subtype,
        "report_source": incident.report_source,
        "report_platform": incident.report_platform,
        "shark_species_confirmed": incident.shark_species_confirmed,
        "shark_species_suspected": incident.shark_species_suspected,
        "shark_size_estimate": incident.shark_size_estimate,
        "species_identification_method": incident.species_identification_method,
        "victim_activity": incident.victim_activity,
        "victim_injury_severity": incident.victim_injury_severity,
        "victim_injury_description": incident.victim_injury_description,
        "victim_age": incident.victim_age,
        "victim_sex": incident.victim_sex,
        "victim_name": incident.victim_name,
        "fatal": incident.fatal,
        "description": incident.description,
        "verification_status": incident.verification_status,
        "submitted_at": incident.submitted_at,
        "updated_at": incident.updated_at,
        "sources": incident.sources,
    }
    return data


def _incident_to_public_response(data: dict) -> PublicIncidentResponse:
    """Apply the public disclosure boundary to a fully populated record."""
    precision = 2 if data["location_precision"] != "exact" else 3
    longitude = data.get("longitude")
    latitude = data.get("latitude")
    if longitude is not None:
        longitude = round(longitude, precision)
    if latitude is not None:
        latitude = round(latitude, precision)

    return PublicIncidentResponse(
        **{
            key: value
            for key, value in data.items()
            if key in PublicIncidentResponse.model_fields
            and key not in {"longitude", "latitude"}
        },
        longitude=longitude,
        latitude=latitude,
    )


class IncidentService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_incidents(
        self,
        classification: str | None = None,
        country: str | None = None,
        species: str | None = None,
        fatal: bool | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        activity: str | None = None,
        severity: str | None = None,
        report_source: str | None = None,
        search: str | None = None,
        sort: str = "incident_date",
        order: str = "desc",
        page: int = 1,
        per_page: int = 50,
    ) -> PaginatedIncidentResponse:
        query = (
            select(Incident)
            .options(selectinload(Incident.sources))
            .where(Incident.verification_status == "verified")
        )

        # Filters
        if classification:
            values = [v.strip() for v in classification.split(",")]
            query = query.where(Incident.classification.in_(values))

        if country:
            values = [v.strip() for v in country.split(",")]
            query = query.where(Incident.country.in_(values))

        if species:
            query = query.where(
                or_(
                    Incident.shark_species_confirmed == species,
                    Incident.shark_species_suspected == species,
                )
            )

        if fatal is not None:
            query = query.where(Incident.fatal == fatal)

        if date_from:
            query = query.where(Incident.incident_date >= date.fromisoformat(date_from))

        if date_to:
            query = query.where(Incident.incident_date <= date.fromisoformat(date_to))

        if activity:
            values = [v.strip() for v in activity.split(",")]
            query = query.where(Incident.victim_activity.in_(values))

        if severity:
            values = [v.strip() for v in severity.split(",")]
            query = query.where(Incident.victim_injury_severity.in_(values))

        if report_source:
            values = [v.strip() for v in report_source.split(",")]
            query = query.where(Incident.report_source.in_(values))

        if search:
            # Escape ILIKE metacharacters so user input is treated as literal text
            safe_search = re.sub(r"([%_\\])", r"\\\1", search)
            # Use PostgreSQL full-text search with fallback to ILIKE for case numbers
            ts_vector = func.to_tsvector(
                "english",
                func.coalesce(Incident.location_description, "")
                + " "
                + func.coalesce(Incident.description, "")
                + " "
                + func.coalesce(Incident.country, "")
                + " "
                + func.coalesce(Incident.victim_name, ""),
            )
            ts_query = func.plainto_tsquery("english", search)
            query = query.where(
                or_(
                    ts_vector.op("@@")(ts_query),
                    Incident.case_number.ilike(f"%{safe_search}%"),
                )
            )

        # Count total before pagination
        count_query = select(func.count()).select_from(query.subquery())
        total = (await self.db.execute(count_query)).scalar_one()

        # Sort
        if sort not in ALLOWED_SORT_FIELDS:
            sort = "incident_date"
        sort_column = getattr(Incident, sort, Incident.incident_date)
        order_func = desc if order == "desc" else asc
        query = query.order_by(order_func(sort_column))

        # Paginate
        offset = (page - 1) * per_page
        query = query.offset(offset).limit(per_page)

        result = await self.db.execute(query)
        incidents = result.scalars().unique().all()

        # Extract coordinates via separate queries for incidents with geometry
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
            response_data.append(_incident_to_public_response(data))

        return PaginatedIncidentResponse(
            data=response_data,
            meta=PaginationMeta(
                total=total,
                page=page,
                per_page=per_page,
                pages=math.ceil(total / per_page) if total > 0 else 0,
            ),
        )

    async def get_incident(self, incident_id: UUID) -> IncidentResponse:
        result = await self.db.execute(
            select(Incident)
            .options(selectinload(Incident.sources))
            .where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

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

        return IncidentResponse(**data)

    async def get_public_incident(self, incident_id: UUID) -> PublicIncidentResponse:
        result = await self.db.execute(
            select(Incident)
            .options(selectinload(Incident.sources))
            .where(
                Incident.id == incident_id,
                Incident.verification_status == "verified",
            )
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

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

        return _incident_to_public_response(data)

    async def create_incident(self, data: IncidentCreate) -> IncidentResponse:
        existing = await find_duplicate_incident(self.db, data)
        if existing is not None:
            await attach_sources_to_incident(self.db, existing, data.sources)
            return await self.get_incident(existing.id)

        case_number = await generate_case_number(self.db)

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
            report_source=data.report_source,
            report_platform=data.report_platform,
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
        )

        if data.coordinates:
            incident.coordinates = point_from_coords(
                data.coordinates.longitude, data.coordinates.latitude
            )

        # Add sources
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
        await self.db.commit()
        await self.db.refresh(incident, attribute_names=["sources"])

        return await self.get_incident(incident.id)

    async def update_incident(
        self, incident_id: UUID, data: IncidentUpdate
    ) -> IncidentResponse:
        result = await self.db.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        update_data = data.model_dump(exclude_unset=True)

        # Handle coordinates separately
        coords = update_data.pop("coordinates", None)
        if coords is not None:
            incident.coordinates = point_from_coords(coords["longitude"], coords["latitude"])

        for field, value in update_data.items():
            setattr(incident, field, value)

        await self.db.commit()
        return await self.get_incident(incident_id)

    async def delete_incident(self, incident_id: UUID) -> None:
        result = await self.db.execute(
            select(Incident).where(Incident.id == incident_id)
        )
        incident = result.scalar_one_or_none()
        if not incident:
            raise HTTPException(status_code=404, detail="Incident not found")

        await self.db.delete(incident)
        await self.db.commit()
