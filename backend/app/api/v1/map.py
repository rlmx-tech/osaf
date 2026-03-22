from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.map_service import MapService

router = APIRouter()


@router.get("")
async def get_map_geojson(
    bbox: str | None = Query(None, description="Bounding box: west,south,east,north"),
    classification: str | None = Query(None, description="Comma-separated classifications"),
    species: str | None = Query(None, description="Scientific name filter"),
    fatal: bool | None = Query(None, description="Fatal only"),
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    activity: str | None = Query(None, description="Comma-separated activities"),
    severity: str | None = Query(None, description="Comma-separated severities"),
    db: AsyncSession = Depends(get_db),
):
    """Return incidents as GeoJSON FeatureCollection, optionally filtered by bounding box."""
    service = MapService(db)
    return await service.get_geojson(
        bbox=bbox,
        classification=classification,
        species=species,
        fatal=fatal,
        date_from=date_from,
        date_to=date_to,
        activity=activity,
        severity=severity,
    )


@router.get("/clusters")
async def get_map_clusters(
    bbox: str | None = Query(None, description="Bounding box: west,south,east,north"),
    zoom: int = Query(3, ge=0, le=20, description="Map zoom level"),
    classification: str | None = Query(None, description="Comma-separated classifications"),
    fatal: bool | None = Query(None, description="Fatal only"),
    date_from: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncSession = Depends(get_db),
):
    """Return clustered incident points for the given zoom level."""
    service = MapService(db)
    return await service.get_clusters(
        bbox=bbox,
        zoom=zoom,
        classification=classification,
        fatal=fatal,
        date_from=date_from,
        date_to=date_to,
    )
