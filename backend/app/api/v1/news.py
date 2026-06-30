from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.news import NewsItemCreate, NewsItemRead, PaginatedNewsResponse
from app.services.auth_service import require_role
from app.services.news_service import NewsService

router = APIRouter()


@router.get("", response_model=PaginatedNewsResponse)
async def list_news(
    event_type: str | None = Query(None, description="Comma-separated event types"),
    country: str | None = Query(None, description="Comma-separated countries"),
    source_platform: str | None = Query(None, description="Comma-separated platforms"),
    date_from: date | None = Query(None, description="Captured from (ISO date)"),
    date_to: date | None = Query(None, description="Captured to (ISO date)"),
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    return await NewsService(db).list_news(
        event_type=event_type, country=country, source_platform=source_platform,
        date_from=date_from, date_to=date_to, search=search, page=page, per_page=per_page,
    )


@router.post("", response_model=NewsItemRead, status_code=201)
async def create_news(
    data: NewsItemCreate,
    user: User = Depends(require_role("admin", "verified_contributor")),
    db: AsyncSession = Depends(get_db),
):
    return await NewsService(db).upsert(data)
