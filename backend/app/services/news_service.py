import math
import re
from datetime import date

from sqlalchemy import String, cast, desc, func, or_, select
from sqlalchemy.orm import aliased
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.incident import Incident
from app.models.news import NewsItem
from app.schemas.news import NewsItemCreate, NewsItemRead, NewsMeta, PaginatedNewsResponse


class NewsService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def upsert(self, data: NewsItemCreate) -> NewsItem:
        promoted_id = None
        if data.promoted_case_number:
            res = await self.db.execute(
                select(Incident.id).where(Incident.case_number == data.promoted_case_number)
            )
            promoted_id = res.scalar_one_or_none()

        values = {
            "dedup_key": data.dedup_key,
            "source_platform": data.source_platform,
            "source_name": data.source_name,
            "source_url": data.source_url,
            "title": data.title,
            "summary": data.summary,
            "author": data.author,
            "image_url": data.image_url,
            "published_at": data.published_at,
            "event_type": data.event_type,
            "country": data.country,
            "ai_confidence": data.ai_confidence,
            "promoted_incident_id": promoted_id,
        }
        stmt = pg_insert(NewsItem).values(**values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["dedup_key"],
            set_={
                "event_type": stmt.excluded.event_type,
                "country": stmt.excluded.country,
                "ai_confidence": stmt.excluded.ai_confidence,
                "promoted_incident_id": stmt.excluded.promoted_incident_id,
            },
        ).returning(NewsItem.id)
        result = await self.db.execute(stmt)
        await self.db.commit()
        new_id = result.scalar_one()
        row = await self.db.execute(
            select(NewsItem).where(NewsItem.id == new_id).execution_options(populate_existing=True)
        )
        return row.scalar_one()

    async def list_news(
        self,
        event_type: str | None = None,
        country: str | None = None,
        source_platform: str | None = None,
        date_from: "date | None" = None,
        date_to: "date | None" = None,
        search: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> PaginatedNewsResponse:
        filters = []
        if event_type:
            filters.append(NewsItem.event_type.in_([e.strip() for e in event_type.split(",")]))
        if country:
            filters.append(NewsItem.country.in_([c.strip() for c in country.split(",")]))
        if source_platform:
            filters.append(NewsItem.source_platform.in_([s.strip() for s in source_platform.split(",")]))
        if date_from:
            filters.append(NewsItem.captured_at >= date_from)
        if date_to:
            filters.append(NewsItem.captured_at <= date_to)
        if search:
            safe_search = re.sub(r"([%_\\])", r"\\\1", search)
            like = f"%{safe_search}%"
            filters.append(or_(NewsItem.title.ilike(like), NewsItem.summary.ilike(like)))

        # Collapse promoted rows to one per incident (newest captured_at); general
        # rows (no promoted_incident_id) each form their own partition, so all kept.
        partition = func.coalesce(
            cast(NewsItem.promoted_incident_id, String), cast(NewsItem.id, String)
        )
        rn = func.row_number().over(
            partition_by=partition, order_by=NewsItem.captured_at.desc()
        ).label("rn")

        ranked = select(NewsItem, rn).where(*filters).subquery()
        item = aliased(NewsItem, ranked)

        total = (
            await self.db.execute(
                select(func.count()).select_from(ranked).where(ranked.c.rn == 1)
            )
        ).scalar_one()

        offset = (page - 1) * per_page
        rows = (
            await self.db.execute(
                select(item)
                .where(ranked.c.rn == 1)
                .order_by(ranked.c.captured_at.desc())
                .offset(offset)
                .limit(per_page)
            )
        ).scalars().all()

        return PaginatedNewsResponse(
            data=[NewsItemRead.model_validate(r) for r in rows],
            meta=NewsMeta(
                total=total, page=page, per_page=per_page,
                pages=math.ceil(total / per_page) if total > 0 else 0,
            ),
        )
