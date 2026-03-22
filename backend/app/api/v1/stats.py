from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.stats_service import StatsService

router = APIRouter()


@router.get("/overview")
async def overview(db: AsyncSession = Depends(get_db)):
    service = StatsService(db)
    return await service.overview()


@router.get("/by-year")
async def by_year(db: AsyncSession = Depends(get_db)):
    service = StatsService(db)
    return await service.by_year()


@router.get("/by-country")
async def by_country(db: AsyncSession = Depends(get_db)):
    service = StatsService(db)
    return await service.by_country()


@router.get("/by-species")
async def by_species(db: AsyncSession = Depends(get_db)):
    service = StatsService(db)
    return await service.by_species()


@router.get("/by-activity")
async def by_activity(db: AsyncSession = Depends(get_db)):
    service = StatsService(db)
    return await service.by_activity()


@router.get("/fatality-trends")
async def fatality_trends(db: AsyncSession = Depends(get_db)):
    service = StatsService(db)
    return await service.fatality_trends()
