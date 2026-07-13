from fastapi import APIRouter

from app.api.v1 import admin, auth, incidents, ingestion, map, news, species, stats, submissions

api_router = APIRouter()

api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(map.router, prefix="/incidents/map", tags=["map"])
api_router.include_router(incidents.router, prefix="/incidents", tags=["incidents"])
api_router.include_router(ingestion.router, prefix="/ingestion", tags=["ingestion"])
api_router.include_router(news.router, prefix="/news", tags=["news"])
api_router.include_router(species.router, prefix="/species", tags=["species"])
api_router.include_router(stats.router, prefix="/stats", tags=["stats"])
api_router.include_router(submissions.router, prefix="/submissions", tags=["submissions"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
