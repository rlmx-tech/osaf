from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.species import SharkSpecies
from app.schemas.species import SpeciesResponse

router = APIRouter()


@router.get("", response_model=list[SpeciesResponse])
async def list_species(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(SharkSpecies).order_by(SharkSpecies.common_name)
    )
    return result.scalars().all()
