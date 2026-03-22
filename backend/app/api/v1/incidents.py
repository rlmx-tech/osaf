from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.incident import (
    IncidentCreate,
    IncidentResponse,
    IncidentUpdate,
    PaginatedIncidentResponse,
)
from app.services.incident_service import IncidentService

router = APIRouter()


@router.get("", response_model=PaginatedIncidentResponse)
async def list_incidents(
    classification: str | None = Query(None, description="Comma-separated classifications"),
    country: str | None = Query(None, description="Comma-separated countries"),
    species: str | None = Query(None, description="Scientific name filter"),
    fatal: bool | None = Query(None, description="Fatal only"),
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    activity: str | None = Query(None, description="Comma-separated activities"),
    severity: str | None = Query(None, description="Comma-separated severities"),
    verification: str | None = Query(None, description="Verification status"),
    search: str | None = Query(None, description="Full-text search"),
    sort: str = Query("incident_date", description="Sort field"),
    order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    per_page: int = Query(50, ge=1, le=200, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    service = IncidentService(db)
    return await service.list_incidents(
        classification=classification,
        country=country,
        species=species,
        fatal=fatal,
        date_from=date_from,
        date_to=date_to,
        activity=activity,
        severity=severity,
        verification=verification,
        search=search,
        sort=sort,
        order=order,
        page=page,
        per_page=per_page,
    )


@router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = IncidentService(db)
    return await service.get_incident(incident_id)


@router.post("", response_model=IncidentResponse, status_code=201)
async def create_incident(
    data: IncidentCreate,
    db: AsyncSession = Depends(get_db),
):
    service = IncidentService(db)
    return await service.create_incident(data)


@router.put("/{incident_id}", response_model=IncidentResponse)
async def update_incident(
    incident_id: UUID,
    data: IncidentUpdate,
    db: AsyncSession = Depends(get_db),
):
    service = IncidentService(db)
    return await service.update_incident(incident_id, data)


@router.delete("/{incident_id}", status_code=204)
async def delete_incident(
    incident_id: UUID,
    db: AsyncSession = Depends(get_db),
):
    service = IncidentService(db)
    await service.delete_incident(incident_id)
