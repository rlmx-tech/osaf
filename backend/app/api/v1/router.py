from fastapi import APIRouter

from app.api.v1 import incidents, map, species, stats

api_router = APIRouter()

api_router.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
api_router.include_router(map.router, prefix="/incidents/map", tags=["map"])
api_router.include_router(species.router, prefix="/species", tags=["species"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
