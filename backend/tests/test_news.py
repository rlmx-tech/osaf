from datetime import datetime, timezone

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


@pytest.mark.asyncio
async def test_service_upsert_idempotent(db):
    from app.schemas.news import NewsItemCreate
    from app.services.news_service import NewsService
    svc = NewsService(db)
    payload = NewsItemCreate(
        dedup_key="reddit:https://r/1", source_platform="reddit",
        source_name="r/sharks", source_url="https://r/1", title="White shark spotted",
    )
    first = await svc.upsert(payload)
    payload2 = payload.model_copy(update={"event_type": "sighting", "country": "Australia"})
    second = await svc.upsert(payload2)
    assert first.id == second.id
    listed = await svc.list_news()
    assert listed.meta.total == 1
    assert listed.data[0].event_type == "sighting"
    assert listed.data[0].country == "Australia"


@pytest.mark.asyncio
async def test_service_upsert_resolves_promoted_case_number(db, sample_incident):
    from app.schemas.news import NewsItemCreate
    from app.services.news_service import NewsService
    svc = NewsService(db)
    payload = NewsItemCreate(
        dedup_key="news_rss:https://n/9", source_platform="news_rss",
        source_name="GN", source_url="https://n/9", title="Shark attack reported",
        event_type="attack", promoted_case_number=sample_incident.case_number,
    )
    row = await svc.upsert(payload)
    assert row.promoted_incident_id == sample_incident.id


@pytest.mark.asyncio
async def test_service_list_filters_by_event_type(db):
    from app.schemas.news import NewsItemCreate
    from app.services.news_service import NewsService
    svc = NewsService(db)
    for i, et in enumerate(["news", "sighting", "attack"]):
        await svc.upsert(NewsItemCreate(
            dedup_key=f"youtube:https://y/{i}", source_platform="youtube",
            source_name="C", source_url=f"https://y/{i}", title=f"shark {i}", event_type=et,
        ))
    only_sightings = await svc.list_news(event_type="sighting")
    assert only_sightings.meta.total == 1
    assert only_sightings.data[0].event_type == "sighting"


@pytest.mark.asyncio
async def test_service_list_filters_by_csv_event_type(db):
    from app.schemas.news import NewsItemCreate
    from app.services.news_service import NewsService
    svc = NewsService(db)
    for i, et in enumerate(["sighting", "attack"]):
        await svc.upsert(NewsItemCreate(
            dedup_key=f"reddit:https://csv/{i}", source_platform="reddit",
            source_name="C", source_url=f"https://csv/{i}", title=f"shark csv {i}", event_type=et,
        ))
    multi = await svc.list_news(event_type="sighting,attack")
    assert multi.meta.total == 2


@pytest.mark.asyncio
async def test_service_list_sorts_by_publication_date_descending(db):
    from app.services.news_service import NewsService

    items = [
        NewsItem(
            dedup_key="news_rss:https://sort/old",
            source_platform="news_rss",
            source_name="N",
            source_url="https://sort/old",
            title="Old publication captured last",
            published_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
            captured_at=datetime(2026, 7, 3, tzinfo=timezone.utc),
            event_type="news",
        ),
        NewsItem(
            dedup_key="news_rss:https://sort/new",
            source_platform="news_rss",
            source_name="N",
            source_url="https://sort/new",
            title="Newest publication",
            published_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
            captured_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
            event_type="news",
        ),
        NewsItem(
            dedup_key="news_rss:https://sort/undated",
            source_platform="news_rss",
            source_name="N",
            source_url="https://sort/undated",
            title="Undated publication",
            published_at=None,
            captured_at=datetime(2026, 5, 1, tzinfo=timezone.utc),
            event_type="news",
        ),
    ]
    db.add_all(items)
    await db.commit()

    listed = await NewsService(db).list_news()

    assert [item.dedup_key for item in listed.data] == [
        "news_rss:https://sort/new",
        "news_rss:https://sort/undated",
        "news_rss:https://sort/old",
    ]


@pytest.mark.asyncio
async def test_post_news_requires_auth(client):
    resp = await client.post("/api/v1/news", json={
        "dedup_key": "youtube:https://z/1", "source_platform": "youtube",
        "source_name": "C", "source_url": "https://z/1", "title": "shark",
    })
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_post_news_as_verified_and_list_public(client, verified_user):
    from tests.conftest import auth_header
    payload = {
        "dedup_key": "youtube:https://z/2", "source_platform": "youtube",
        "source_name": "C", "source_url": "https://z/2", "title": "shark sighting",
        "event_type": "sighting",
    }
    created = await client.post("/api/v1/news", json=payload, headers=auth_header(verified_user))
    assert created.status_code == 201
    assert created.json()["event_type"] == "sighting"

    listed = await client.get("/api/v1/news?event_type=sighting")
    assert listed.status_code == 200
    body = listed.json()
    assert body["meta"]["total"] == 1
    assert body["data"][0]["dedup_key"] == "youtube:https://z/2"


@pytest.mark.asyncio
async def test_post_news_rejects_invalid_event_type(client, verified_user):
    """Final-review fix #2: event_type is a Literal -> bad value is 422, not a DB 500."""
    from tests.conftest import auth_header
    payload = {
        "dedup_key": "youtube:https://z/bad", "source_platform": "youtube",
        "source_name": "C", "source_url": "https://z/bad", "title": "shark",
        "event_type": "foo",
    }
    resp = await client.post("/api/v1/news", json=payload, headers=auth_header(verified_user))
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_news_search_escapes_wildcards(db):
    """Final-review fix #1: ILIKE metacharacters in search are escaped, not treated as wildcards."""
    from app.schemas.news import NewsItemCreate
    from app.services.news_service import NewsService
    svc = NewsService(db)
    await svc.upsert(NewsItemCreate(
        dedup_key="news_rss:https://s/1", source_platform="news_rss",
        source_name="N", source_url="https://s/1", title="100% shark danger",
    ))
    await svc.upsert(NewsItemCreate(
        dedup_key="news_rss:https://s/2", source_platform="news_rss",
        source_name="N", source_url="https://s/2", title="shark sighting",
    ))
    # "100%" must match only the literal-"100%" row, not act as a wildcard matching both.
    result = await svc.list_news(search="100%")
    assert result.meta.total == 1
    assert result.data[0].dedup_key == "news_rss:https://s/1"


@pytest.mark.asyncio
async def test_list_news_collapses_promoted_by_incident(db, sample_incident):
    from app.schemas.news import NewsItemCreate
    from app.services.news_service import NewsService
    svc = NewsService(db)
    # Two promoted news items for the SAME incident (two outlets)
    for i, pub in enumerate(["Yahoo", "WCIA"]):
        await svc.upsert(NewsItemCreate(
            dedup_key=f"news_rss:https://d/{i}", source_platform="news_rss",
            source_name=pub, source_url=f"https://d/{i}", title=f"shark {pub}",
            event_type="attack", promoted_case_number=sample_incident.case_number,
        ))
    # One general (non-event) news item
    await svc.upsert(NewsItemCreate(
        dedup_key="news_rss:https://g/1", source_platform="news_rss",
        source_name="GN", source_url="https://g/1", title="shark documentary",
        event_type="news",
    ))
    listed = await svc.list_news()
    # 1 collapsed promoted event + 1 general = 2, not 3
    assert listed.meta.total == 2
    promoted = [r for r in listed.data if r.promoted_incident_id is not None]
    assert len(promoted) == 1
