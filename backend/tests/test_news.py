import pytest
from sqlalchemy import select
from app.models.news import NewsItem


@pytest.mark.asyncio
async def test_news_item_persists(db):
    item = NewsItem(
        dedup_key="youtube:https://x/1",
        source_platform="youtube",
        source_name="TestChannel",
        source_url="https://x/1",
        title="Shark seen offshore",
        event_type="news",
    )
    db.add(item)
    await db.commit()
    row = (await db.execute(select(NewsItem).where(NewsItem.dedup_key == "youtube:https://x/1"))).scalar_one()
    assert row.event_type == "news"
    assert row.captured_at is not None
    assert row.promoted_incident_id is None


def test_news_schemas_importable_and_defaults():
    from app.schemas.news import NewsItemCreate, PaginatedNewsResponse
    c = NewsItemCreate(
        dedup_key="news_rss:https://x/2",
        source_platform="news_rss",
        source_name="Google News",
        source_url="https://x/2",
        title="Shark sighting at beach",
    )
    assert c.event_type == "news"
    assert c.promoted_case_number is None
    assert PaginatedNewsResponse(data=[], meta={"total": 0, "page": 1, "per_page": 50, "pages": 0}).meta.total == 0
