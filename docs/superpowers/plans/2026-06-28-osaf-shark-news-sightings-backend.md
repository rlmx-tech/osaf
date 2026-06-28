# Shark News + Sightings Capture Backend (SP1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Capture every shark-related item the collector finds into a new `news_items` store, and auto-promote attacks and sightings into the existing `incidents` table with no human gate.

**Architecture:** A new additive `news_items` Postgres table is the catch-all feed store. The collector runs a cheap keyword gate (shark-relevant → persist to `news_items`) then the existing AI extractor (event → promote to `incidents`). `event_type` is derived from the extractor's classification. Sightings are `incidents` rows with `classification='sighting'` (already schema-legal). Promoted records auto-publish because the `collector` user is a `verified_contributor` posting to the existing `/submissions` path.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async, `Mapped`), Alembic, PostgreSQL+PostGIS, Pydantic v2, httpx, pytest + pytest-asyncio.

## Global Constraints

- Python 3.12+, async endpoints; SQLAlchemy `Mapped[...]` + `mapped_column` style.
- ALL schema changes via Alembic — never modify the DB directly.
- API list responses use the envelope `{"data": [...], "meta": {total, page, per_page, pages}}`.
- Coordinates WGS84 (SRID 4326); all timestamps UTC.
- Conventional commits (`feat:`, `fix:`, `test:`, `chore:`). Attribution disabled — no Co-Authored-By trailer.
- Backend tests require the Docker Compose Postgres stack on `localhost:5432` (see `backend/tests/conftest.py`).
- Collector unit tests are pure (no DB/network); `COLLECTOR_OSAF_PASSWORD` is set by `collector/tests/conftest.py`.
- `news_items.event_type ∈ {'attack','sighting','news'}`. `incidents.classification` already includes `'sighting'`.
- Run backend commands from `~/claude/OSAF/backend`; collector commands from `~/claude/OSAF`.

---

## File Structure

**Backend (create):**
- `app/models/news.py` — `NewsItem` ORM model
- `app/schemas/news.py` — `NewsItemCreate`, `NewsItemRead`, `NewsMeta`, `PaginatedNewsResponse`
- `app/services/news_service.py` — `NewsService` (upsert + list)
- `app/api/v1/news.py` — `GET`/`POST /api/v1/news`
- `alembic/versions/d4e5f6a1b2c3_add_news_items.py` — migration
- `backend/scripts/promote_collector.py` — idempotent role promotion
- `tests/test_news.py`, `tests/test_sighting_submission.py`

**Backend (modify):**
- `app/models/__init__.py` — register `NewsItem`
- `app/api/v1/router.py` — include news router
- `tests/conftest.py` — add `news_items` to cleanup

**Collector (create):**
- `collector/relevance.py` — `is_shark_relevant` keyword gate
- `collector/news_client.py` — `NewsClient` API client
- `tests/test_relevance.py`, `tests/test_event_type.py`, `tests/test_pipeline_capture.py`

**Collector (modify):**
- `collector/pipeline.py` — capture + routing + promotion link + `derive_event_type` + new stats
- `collector/main.py` — instantiate/auth/close `NewsClient`; pass to `process_items`; updated log

---

## Task 1: `NewsItem` model + registration + test cleanup

**Files:**
- Create: `app/models/news.py`
- Modify: `app/models/__init__.py`
- Modify: `tests/conftest.py` (cleanup_db)
- Test: `tests/test_news.py`

**Interfaces:**
- Produces: `NewsItem` ORM with columns `id, dedup_key, source_platform, source_name, source_url, title, summary, author, image_url, published_at, captured_at, event_type, country, ai_confidence, promoted_incident_id`. Table `news_items`. Unique `dedup_key`. CHECK `valid_event_type`.

- [ ] **Step 1: Write the failing test**

`tests/test_news.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF/backend && pytest tests/test_news.py::test_news_item_persists -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.models.news'`

- [ ] **Step 3: Write minimal implementation**

`app/models/news.py`:
```python
import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class NewsItem(Base):
    __tablename__ = "news_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dedup_key: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    source_platform: Mapped[str] = mapped_column(String(20), nullable=False)
    source_name: Mapped[str] = mapped_column(String(200), nullable=False)
    source_url: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str | None] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String(200))
    image_url: Mapped[str | None] = mapped_column(Text)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    captured_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(20), nullable=False, default="news")
    country: Mapped[str | None] = mapped_column(String(100))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    promoted_incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL")
    )

    __table_args__ = (
        CheckConstraint("event_type IN ('attack', 'sighting', 'news')", name="valid_event_type"),
        Index("idx_news_items_captured_at", "captured_at"),
        Index("idx_news_items_event_type", "event_type"),
        Index("idx_news_items_country", "country"),
    )
```

Add to `app/models/__init__.py` — import and `__all__` entry:
```python
from app.models.news import NewsItem
```
(add `"NewsItem",` to the `__all__` list)

In `tests/conftest.py`, inside `cleanup_db`, add `news_items` as the FIRST delete (it FK-references incidents):
```python
        await session.execute(text("DELETE FROM news_items"))
        await session.execute(text("DELETE FROM incident_audit_log"))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd ~/claude/OSAF/backend && pytest tests/test_news.py::test_news_item_persists -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/models/news.py backend/app/models/__init__.py backend/tests/conftest.py backend/tests/test_news.py
git commit -m "feat(backend): add NewsItem model for shark news capture"
```

---

## Task 2: Alembic migration for `news_items`

**Files:**
- Create: `alembic/versions/d4e5f6a1b2c3_add_news_items.py`

**Interfaces:**
- Consumes: `NewsItem` table shape from Task 1.
- Produces: migration `d4e5f6a1b2c3` (down_revision `c3a1f9d82b4e`) creating `news_items`.

- [ ] **Step 1: Write the migration (hand-written, deterministic)**

`alembic/versions/d4e5f6a1b2c3_add_news_items.py`:
```python
"""add news_items table

Revision ID: d4e5f6a1b2c3
Revises: c3a1f9d82b4e
Create Date: 2026-06-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d4e5f6a1b2c3"
down_revision: Union[str, None] = "c3a1f9d82b4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "news_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("dedup_key", sa.String(512), nullable=False),
        sa.Column("source_platform", sa.String(20), nullable=False),
        sa.Column("source_name", sa.String(200), nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("summary", sa.Text, nullable=True),
        sa.Column("author", sa.String(200), nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("captured_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False, server_default="news"),
        sa.Column("country", sa.String(100), nullable=True),
        sa.Column("ai_confidence", sa.Float, nullable=True),
        sa.Column("promoted_incident_id", UUID(as_uuid=True), sa.ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True),
        sa.UniqueConstraint("dedup_key", name="uq_news_items_dedup_key"),
        sa.CheckConstraint("event_type IN ('attack', 'sighting', 'news')", name="valid_event_type"),
    )
    op.create_index("idx_news_items_captured_at", "news_items", ["captured_at"])
    op.create_index("idx_news_items_event_type", "news_items", ["event_type"])
    op.create_index("idx_news_items_country", "news_items", ["country"])


def downgrade() -> None:
    op.drop_index("idx_news_items_country", table_name="news_items")
    op.drop_index("idx_news_items_event_type", table_name="news_items")
    op.drop_index("idx_news_items_captured_at", table_name="news_items")
    op.drop_table("news_items")
```

- [ ] **Step 2: Apply the migration**

Run: `cd ~/claude/OSAF/backend && alembic upgrade head`
Expected: `Running upgrade c3a1f9d82b4e -> d4e5f6a1b2c3, add news_items table`

- [ ] **Step 3: Verify downgrade then re-upgrade**

Run: `alembic downgrade -1 && alembic upgrade head`
Expected: table dropped then recreated, no errors.

- [ ] **Step 4: Commit**

```bash
cd ~/claude/OSAF
git add backend/alembic/versions/d4e5f6a1b2c3_add_news_items.py
git commit -m "feat(backend): migration for news_items table"
```

---

## Task 3: News Pydantic schemas

**Files:**
- Create: `app/schemas/news.py`
- Test: `tests/test_news.py` (append)

**Interfaces:**
- Produces: `NewsItemCreate` (fields incl. `promoted_case_number: str | None`), `NewsItemRead` (incl. `id`, `captured_at`, `promoted_incident_id`), `NewsMeta`, `PaginatedNewsResponse {data, meta}`.

- [ ] **Step 1: Write the failing test** (append to `tests/test_news.py`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF/backend && pytest tests/test_news.py::test_news_schemas_importable_and_defaults -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.schemas.news'`

- [ ] **Step 3: Write minimal implementation**

`app/schemas/news.py`:
```python
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NewsItemCreate(BaseModel):
    dedup_key: str = Field(..., max_length=512)
    source_platform: str = Field(..., max_length=20)
    source_name: str = Field(..., max_length=200)
    source_url: str
    title: str
    summary: str | None = None
    author: str | None = Field(None, max_length=200)
    image_url: str | None = None
    published_at: datetime | None = None
    event_type: str = Field("news", max_length=20)
    country: str | None = Field(None, max_length=100)
    ai_confidence: float | None = None
    promoted_case_number: str | None = Field(None, max_length=20)


class NewsItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    dedup_key: str
    source_platform: str
    source_name: str
    source_url: str
    title: str
    summary: str | None = None
    author: str | None = None
    image_url: str | None = None
    published_at: datetime | None = None
    captured_at: datetime
    event_type: str
    country: str | None = None
    ai_confidence: float | None = None
    promoted_incident_id: UUID | None = None


class NewsMeta(BaseModel):
    total: int
    page: int
    per_page: int
    pages: int


class PaginatedNewsResponse(BaseModel):
    data: list[NewsItemRead]
    meta: NewsMeta
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_news.py::test_news_schemas_importable_and_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/schemas/news.py backend/tests/test_news.py
git commit -m "feat(backend): news Pydantic schemas"
```

---

## Task 4: `NewsService` (upsert + list)

**Files:**
- Create: `app/services/news_service.py`
- Test: `tests/test_news.py` (append)

**Interfaces:**
- Consumes: `NewsItem` (Task 1), schemas (Task 3).
- Produces: `NewsService(db)` with `async upsert(data: NewsItemCreate) -> NewsItem` (idempotent on `dedup_key`; resolves `promoted_case_number` → `promoted_incident_id`) and `async list_news(...) -> PaginatedNewsResponse`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_news.py`)

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_news.py -k service -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.news_service'`

- [ ] **Step 3: Write minimal implementation**

`app/services/news_service.py`:
```python
import math

from sqlalchemy import desc, func, or_, select
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
        row = await self.db.execute(select(NewsItem).where(NewsItem.id == new_id))
        return row.scalar_one()

    async def list_news(
        self,
        event_type: str | None = None,
        country: str | None = None,
        source_platform: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        search: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> PaginatedNewsResponse:
        query = select(NewsItem)
        if event_type:
            query = query.where(NewsItem.event_type.in_([e.strip() for e in event_type.split(",")]))
        if country:
            query = query.where(NewsItem.country.in_([c.strip() for c in country.split(",")]))
        if source_platform:
            query = query.where(NewsItem.source_platform.in_([s.strip() for s in source_platform.split(",")]))
        if date_from:
            query = query.where(NewsItem.captured_at >= date_from)
        if date_to:
            query = query.where(NewsItem.captured_at <= date_to)
        if search:
            like = f"%{search}%"
            query = query.where(or_(NewsItem.title.ilike(like), NewsItem.summary.ilike(like)))

        total = (await self.db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
        offset = (page - 1) * per_page
        query = query.order_by(desc(NewsItem.captured_at)).offset(offset).limit(per_page)
        rows = (await self.db.execute(query)).scalars().all()

        return PaginatedNewsResponse(
            data=[NewsItemRead.model_validate(r) for r in rows],
            meta=NewsMeta(
                total=total, page=page, per_page=per_page,
                pages=math.ceil(total / per_page) if total > 0 else 0,
            ),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_news.py -k service -v`
Expected: 3 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/services/news_service.py backend/tests/test_news.py
git commit -m "feat(backend): NewsService upsert + list with case-number promotion link"
```

---

## Task 5: News API router (`GET` public, `POST` auth) + registration

**Files:**
- Create: `app/api/v1/news.py`
- Modify: `app/api/v1/router.py`
- Test: `tests/test_news.py` (append)

**Interfaces:**
- Consumes: `NewsService` (Task 4), `require_role` from `app.services.auth_service`, `auth_header`/`verified_user` fixtures.
- Produces: `GET /api/v1/news` (public, filters + pagination), `POST /api/v1/news` (requires `admin`/`verified_contributor`).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_news.py`)

```python
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
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_news.py -k "post_news or list_public" -v`
Expected: FAIL (404 — route not registered)

- [ ] **Step 3: Write minimal implementation**

`app/api/v1/news.py`:
```python
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
    date_from: str | None = Query(None, description="Captured from (ISO)"),
    date_to: str | None = Query(None, description="Captured to (ISO)"),
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
```

In `app/api/v1/router.py`, add `news` to the import line and register it:
```python
from app.api.v1 import admin, auth, incidents, map, news, species, stats, submissions
```
```python
api_router.include_router(news.router, prefix="/news", tags=["news"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_news.py -k "post_news or list_public" -v`
Expected: 2 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/api/v1/news.py backend/app/api/v1/router.py backend/tests/test_news.py
git commit -m "feat(backend): /api/v1/news endpoints (public GET, contributor POST)"
```

---

## Task 6: Verify sighting auto-publish through existing `/submissions`

**Files:**
- Create: `tests/test_sighting_submission.py`

**Interfaces:**
- Consumes: existing `POST /api/v1/submissions`, `IncidentCreate`, `verified_user`/`auth_header`, `GET /api/v1/incidents`.
- Produces: proof that `classification='sighting'` with null victim fields submitted by a verified contributor auto-publishes and is queryable. (This validates the spec's two "must-verify" assumptions; if it fails, fix the create path before proceeding.)

- [ ] **Step 1: Write the failing test**

`tests/test_sighting_submission.py`:
```python
import pytest
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_sighting_autopublishes_for_verified_contributor(client, verified_user):
    payload = {
        "location_description": "Bondi Beach",
        "country": "Australia",
        "classification": "sighting",
        "incident_date": "2026-06-20",
        "shark_species_suspected": "Carcharodon carcharias",
        "coordinates": {"longitude": 151.274, "latitude": -33.891},
        "sources": [{"source_type": "video", "source_url": "https://youtu.be/abc",
                     "source_title": "Drone shark footage"}],
    }
    resp = await client.post("/api/v1/submissions", json=payload, headers=auth_header(verified_user))
    assert resp.status_code == 201
    body = resp.json()
    assert body["classification"] == "sighting"
    assert body["verification_status"] == "verified"
    assert body["victim_name"] is None
    assert body["fatal"] is False

    listed = await client.get("/api/v1/incidents?classification=sighting")
    assert listed.status_code == 200
    assert any(i["classification"] == "sighting" for i in listed.json()["data"])
```

- [ ] **Step 2: Run test to verify status**

Run: `cd ~/claude/OSAF/backend && pytest tests/test_sighting_submission.py -v`
Expected: PASS (the existing path already supports this). If it FAILS, read the error: most likely an enum/validation rejection — fix `app/schemas/incident.py` / create path to accept `classification='sighting'`, then re-run until PASS.

- [ ] **Step 3: Commit**

```bash
cd ~/claude/OSAF
git add backend/tests/test_sighting_submission.py
git commit -m "test(backend): sighting auto-publishes via verified-contributor submission"
```

---

## Task 7: Collector keyword relevance gate (`is_shark_relevant`)

**Files:**
- Create: `collector/relevance.py`
- Test: `collector/tests/test_relevance.py`

**Interfaces:**
- Produces: `is_shark_relevant(title: str, content: str) -> bool` — recall-favoring keyword screen over `"shark"` + species common names from `COMMON_TO_SCIENTIFIC`.

- [ ] **Step 1: Write the failing test**

`collector/tests/test_relevance.py`:
```python
import pytest
from collector.relevance import is_shark_relevant


@pytest.mark.parametrize("title,content,expected", [
    ("Great white shark spotted off Bondi", "", True),
    ("Mako breaches near boat", "fishermen stunned", True),   # species w/o "shark"
    ("New documentary about the ocean", "whales and dolphins", False),
    ("Local council budget meeting", "", False),
    ("", "A wobbegong rested on the reef", True),
])
def test_is_shark_relevant(title, content, expected):
    assert is_shark_relevant(title, content) is expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF && pytest collector/tests/test_relevance.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collector.relevance'`

- [ ] **Step 3: Write minimal implementation**

`collector/relevance.py`:
```python
"""Gate 1: cheap keyword screen for shark-relevance.

Favors recall — the whole point of the capture layer is to stop missing items.
Precision is handled downstream by the AI event gate (and SP2 feed tabs).
"""

from collector.config import COMMON_TO_SCIENTIFIC

# "shark" plus every species common name (mako, wobbegong, thresher, etc. lack "shark")
SHARK_RELEVANCE_TERMS: frozenset[str] = frozenset(
    {"shark", *COMMON_TO_SCIENTIFIC.keys()}
)


def is_shark_relevant(title: str, content: str) -> bool:
    """True if the text plausibly concerns a shark (recall-favoring)."""
    text = f"{title or ''} {content or ''}".lower()
    return any(term in text for term in SHARK_RELEVANCE_TERMS)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest collector/tests/test_relevance.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add collector/relevance.py collector/tests/test_relevance.py
git commit -m "feat(collector): keyword relevance gate for news capture"
```

---

## Task 8: `derive_event_type` helper

**Files:**
- Modify: `collector/pipeline.py` (add helper near top)
- Test: `collector/tests/test_event_type.py`

**Interfaces:**
- Consumes: `ExtractedIncident` from `collector.models`.
- Produces: `derive_event_type(incident: ExtractedIncident | None) -> str` → `"news"` (None), `"sighting"` (classification == "sighting"), else `"attack"`.

- [ ] **Step 1: Write the failing test**

`collector/tests/test_event_type.py`:
```python
import pytest
from collector.models import ExtractedIncident
from collector.pipeline import derive_event_type


def _incident(classification: str) -> ExtractedIncident:
    return ExtractedIncident(
        location_description="X", country="Y", classification=classification,
        source_url="https://u", source_title="t",
    )


@pytest.mark.parametrize("inc,expected", [
    (None, "news"),
    (_incident("sighting"), "sighting"),
    (_incident("unprovoked"), "attack"),
    (_incident("boat_bite"), "attack"),
    (_incident("not_confirmed"), "attack"),
])
def test_derive_event_type(inc, expected):
    assert derive_event_type(inc) == expected
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF && pytest collector/tests/test_event_type.py -v`
Expected: FAIL with `ImportError: cannot import name 'derive_event_type'`

- [ ] **Step 3: Write minimal implementation** (add near the top of `collector/pipeline.py`, after imports)

```python
from collector.models import ExtractedIncident, RawItem  # extend existing import


def derive_event_type(incident: "ExtractedIncident | None") -> str:
    """Map an extraction result to a news_items.event_type value."""
    if incident is None:
        return "news"
    return "sighting" if incident.classification == "sighting" else "attack"
```
Note: `collector/pipeline.py` currently imports only `RawItem` from `collector.models`; change that import line to include `ExtractedIncident` as shown.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest collector/tests/test_event_type.py -v`
Expected: 5 PASS

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add collector/pipeline.py collector/tests/test_event_type.py
git commit -m "feat(collector): derive_event_type from extraction result"
```

---

## Task 9: `NewsClient` API client

**Files:**
- Create: `collector/news_client.py`
- Test: `collector/tests/test_news_client.py`

**Interfaces:**
- Produces: `NewsClient` with `async authenticate() -> bool`, `async upsert(payload: dict) -> str | None` (returns news item id), `async close()`. Mirrors `OsafSubmitter` JWT + 401-retry pattern.

- [ ] **Step 1: Write the failing test**

`collector/tests/test_news_client.py`:
```python
import pytest
from collector.news_client import NewsClient


@pytest.mark.asyncio
async def test_upsert_posts_and_returns_id(monkeypatch):
    client = NewsClient()
    client._token = "tok"  # skip auth

    calls = {}

    class FakeResp:
        status_code = 201
        def raise_for_status(self): pass
        def json(self): return {"id": "abc-123"}

    async def fake_post(path, json=None, headers=None):
        calls["path"] = path
        calls["json"] = json
        return FakeResp()

    monkeypatch.setattr(client._client, "post", fake_post)
    result = await client.upsert({"dedup_key": "k", "title": "shark"})
    assert result == "abc-123"
    assert calls["path"] == "/news"
    assert calls["json"]["dedup_key"] == "k"
    await client.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF && pytest collector/tests/test_news_client.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'collector.news_client'`

- [ ] **Step 3: Write minimal implementation**

`collector/news_client.py`:
```python
"""OSAF API client for the news_items capture store."""

import logging

import httpx

from collector.config import settings

logger = logging.getLogger(__name__)


class NewsClient:
    """Authenticates with the OSAF API and upserts news items."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.osaf_api_url, timeout=30)
        self._token: str | None = None

    async def authenticate(self) -> bool:
        try:
            resp = await self._client.post(
                "/auth/login",
                data={"username": settings.osaf_username, "password": settings.osaf_password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            self._token = resp.json().get("access_token")
            return bool(self._token)
        except httpx.HTTPError:
            logger.exception("news_client: authentication failed")
            return False

    async def upsert(self, payload: dict) -> str | None:
        """Upsert a news item. Returns the row id or None."""
        if not self._token and not await self.authenticate():
            return None
        try:
            resp = await self._client.post(
                "/news", json=payload, headers={"Authorization": f"Bearer {self._token}"}
            )
            if resp.status_code == 401:
                if await self.authenticate():
                    resp = await self._client.post(
                        "/news", json=payload, headers={"Authorization": f"Bearer {self._token}"}
                    )
                else:
                    return None
            resp.raise_for_status()
            return resp.json().get("id")
        except httpx.HTTPError:
            logger.exception("news_client: upsert failed for %s", payload.get("source_url"))
            return None

    async def close(self) -> None:
        await self._client.aclose()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest collector/tests/test_news_client.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add collector/news_client.py collector/tests/test_news_client.py
git commit -m "feat(collector): NewsClient for /api/v1/news upserts"
```

---

## Task 10: Pipeline rewrite — capture, route, promote-link, stats; wire into main

**Files:**
- Modify: `collector/pipeline.py`
- Modify: `collector/main.py`
- Test: `collector/tests/test_pipeline_capture.py`

**Interfaces:**
- Consumes: `is_shark_relevant` (Task 7), `derive_event_type` (Task 8), `NewsClient` (Task 9), existing `extract_incident`/`verify_incident`/`apply_corrections`, `OsafSubmitter`, `StateManager`.
- Produces: `process_items(items, state, submitter, news_client) -> dict` with stats keys including `captured_news`, `promoted_attack`, `promoted_sighting`, `skipped_not_shark` (plus all existing keys). New module-level helper `_news_payload(raw, event_type="news", country=None, ai_confidence=None, promoted_case_number=None) -> dict`.

- [ ] **Step 1: Write the failing test**

`collector/tests/test_pipeline_capture.py`:
```python
import pytest
from unittest.mock import AsyncMock

from collector.models import ExtractedIncident, RawItem, SourcePlatform, VerificationResult
import collector.pipeline as pipeline


class FakeState:
    def __init__(self): self.seen = {}
    def is_seen(self, k): return k in self.seen
    def mark_seen(self, k, case_number=None): self.seen[k] = case_number
    def mark_skipped(self, k, reason): self.seen[k] = f"skip:{reason}"


class FakeNews:
    def __init__(self): self.calls = []
    async def upsert(self, payload): self.calls.append(payload); return "id1"


def _raw(url, title, content):
    return RawItem(source_platform=SourcePlatform.YOUTUBE, source_name="C",
                   source_url=url, title=title, content=content)


@pytest.mark.asyncio
async def test_non_shark_skipped_no_capture(monkeypatch):
    news = FakeNews()
    submitter = AsyncMock()
    items = [_raw("https://u/1", "City council meeting", "budget")]
    stats = await pipeline.process_items(items, FakeState(), submitter, news)
    assert stats["skipped_not_shark"] == 1
    assert news.calls == []
    submitter.submit.assert_not_called()


@pytest.mark.asyncio
async def test_shark_news_only_captured_not_promoted(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=None))
    news = FakeNews()
    submitter = AsyncMock()
    items = [_raw("https://u/2", "New shark documentary released", "about great white shark")]
    stats = await pipeline.process_items(items, FakeState(), submitter, news)
    assert stats["captured_news"] == 1
    assert len(news.calls) == 1 and news.calls[0]["event_type"] == "news"
    submitter.submit.assert_not_called()


@pytest.mark.asyncio
async def test_sighting_captured_and_promoted(monkeypatch):
    inc = ExtractedIncident(location_description="Bondi", country="Australia",
                            classification="sighting", source_url="https://u/3",
                            source_title="t", confidence=0.9)
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=inc))
    monkeypatch.setattr(pipeline, "verify_incident",
                        AsyncMock(return_value=VerificationResult(is_valid=True, confidence=0.9)))
    news = FakeNews()
    submitter = AsyncMock()
    submitter.submit = AsyncMock(return_value="OSAF-2026-0007")
    items = [_raw("https://u/3", "Great white shark spotted", "drone footage")]
    stats = await pipeline.process_items(items, FakeState(), submitter, news)
    assert stats["promoted_sighting"] == 1
    assert stats["submitted"] == 1
    # two upserts: initial news capture + promotion link
    assert len(news.calls) == 2
    promo = news.calls[-1]
    assert promo["event_type"] == "sighting"
    assert promo["promoted_case_number"] == "OSAF-2026-0007"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF && pytest collector/tests/test_pipeline_capture.py -v`
Expected: FAIL (`process_items` takes 3 args, not 4 / `_news_payload` missing)

- [ ] **Step 3: Write the implementation**

Edit `collector/pipeline.py` surgically — do NOT delete existing content. Keep the
module constants (`MIN_EXTRACTION_CONFIDENCE`, `MIN_VERIFICATION_CONFIDENCE`) and the
`derive_event_type` helper added in Task 8. Make these changes: (a) add the imports
below, (b) add the `_news_payload` helper, (c) replace ONLY the existing
`process_items` function with the new version.

Add import:
```python
from collector.relevance import is_shark_relevant
```

Add the payload helper (module level):
```python
def _news_payload(
    raw: RawItem,
    event_type: str = "news",
    country: str | None = None,
    ai_confidence: float | None = None,
    promoted_case_number: str | None = None,
) -> dict:
    return {
        "dedup_key": raw.dedup_key,
        "source_platform": raw.source_platform.value,
        "source_name": raw.source_name,
        "source_url": raw.source_url,
        "title": raw.title,
        "summary": raw.content[:2000] if raw.content else None,
        "author": raw.author,
        "image_url": raw.extra.get("image_url") if raw.extra else None,
        "published_at": raw.published_at.isoformat() if raw.published_at else None,
        "event_type": event_type,
        "country": country,
        "ai_confidence": ai_confidence,
        "promoted_case_number": promoted_case_number,
    }
```

Replace `process_items` with:
```python
async def process_items(
    items: list[RawItem],
    state: StateManager,
    submitter: OsafSubmitter,
    news_client: "NewsClient",
) -> dict:
    """Poll batch → capture all shark items → promote events to incidents."""
    stats = {
        "processed": 0,
        "captured_news": 0,
        "extracted": 0,
        "verified": 0,
        "submitted": 0,
        "promoted_attack": 0,
        "promoted_sighting": 0,
        "skipped_seen": 0,
        "skipped_not_shark": 0,
        "skipped_irrelevant": 0,
        "skipped_low_confidence": 0,
        "skipped_duplicate": 0,
        "errors": 0,
    }

    for raw in items:
        stats["processed"] += 1

        if state.is_seen(raw.dedup_key):
            stats["skipped_seen"] += 1
            continue

        # GATE 1 — shark-relevant at all?
        if not is_shark_relevant(raw.title, raw.content):
            stats["skipped_not_shark"] += 1
            state.mark_skipped(raw.dedup_key, "not_shark")
            continue

        # Capture into news_items first (resilient — survives extraction failure)
        try:
            await news_client.upsert(_news_payload(raw, event_type="news"))
            stats["captured_news"] += 1
        except Exception:
            logger.exception("pipeline: news capture failed for %s", raw.source_url)

        # GATE 2 — is it a promotable event?
        try:
            incident = await extract_incident(raw)
        except Exception:
            logger.exception("pipeline: extraction failed for %s", raw.source_url)
            stats["errors"] += 1
            state.mark_skipped(raw.dedup_key, "extraction_error")
            continue

        if not incident or not incident.is_relevant:
            # Shark-related but not an event — lives in the feed only.
            stats["skipped_irrelevant"] += 1
            state.mark_seen(raw.dedup_key)
            continue

        stats["extracted"] += 1

        if incident.confidence < MIN_EXTRACTION_CONFIDENCE:
            stats["skipped_low_confidence"] += 1
            state.mark_skipped(raw.dedup_key, f"low_extraction_confidence ({incident.confidence:.0%})")
            continue

        try:
            verification = await verify_incident(incident, raw)
        except Exception:
            logger.exception("pipeline: verification failed for %s", raw.source_url)
            stats["errors"] += 1
            if incident.confidence >= 0.7:
                verification = None
            else:
                state.mark_skipped(raw.dedup_key, "verification_error")
                continue

        if verification:
            stats["verified"] += 1
            if verification.is_duplicate_likely:
                stats["skipped_duplicate"] += 1
                state.mark_skipped(raw.dedup_key, "likely_duplicate")
                continue
            if not verification.is_valid:
                if verification.confidence >= 0.6:
                    stats["skipped_low_confidence"] += 1
                    state.mark_skipped(raw.dedup_key, f"verification_rejected: {verification.notes}")
                    continue
                logger.warning(
                    "pipeline: verifier uncertain (%.0f%%), submitting anyway: %s",
                    verification.confidence * 100, verification.notes,
                )
            incident = apply_corrections(incident, verification)

        event_type = derive_event_type(incident)

        try:
            case_number = await submitter.submit(incident)
        except Exception:
            logger.exception("pipeline: submission failed for %s", raw.source_url)
            stats["errors"] += 1
            continue

        if case_number:
            stats["submitted"] += 1
            if event_type == "sighting":
                stats["promoted_sighting"] += 1
            else:
                stats["promoted_attack"] += 1
            # Link the news item to the promoted incident.
            try:
                await news_client.upsert(_news_payload(
                    raw, event_type=event_type, country=incident.country,
                    ai_confidence=incident.confidence, promoted_case_number=case_number,
                ))
            except Exception:
                logger.exception("pipeline: news promotion-link failed for %s", raw.source_url)
            state.mark_seen(raw.dedup_key, case_number)
            logger.info(
                "pipeline: ✓ %s [%s] — %s, %s (%s)",
                case_number, event_type, incident.location_description,
                incident.country, raw.source_platform.value,
            )
        else:
            stats["errors"] += 1
            state.mark_skipped(raw.dedup_key, "submission_failed")

    return stats
```

Add a `TYPE_CHECKING` import for `NewsClient` near the top of `pipeline.py` (avoids a runtime import cycle):
```python
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from collector.news_client import NewsClient
```

Now wire `main.py`. In `Scheduler.__init__`, add:
```python
        self._news = NewsClient()
```
Add the import at top of `main.py`:
```python
from collector.news_client import NewsClient
```
In `_poll_loop`, change the `process_items` call to pass `self._news`:
```python
                stats = await process_items(items, self._state, self._submitter, self._news)
```
Update the log line in `_poll_loop` to include captured count:
```python
                logger.info(
                    "scheduler: %s batch — %d processed, %d captured, %d submitted, %d skipped, %d errors",
                    poller.name,
                    stats["processed"],
                    stats["captured_news"],
                    stats["submitted"],
                    stats["skipped_seen"] + stats["skipped_not_shark"]
                    + stats["skipped_irrelevant"] + stats["skipped_low_confidence"]
                    + stats["skipped_duplicate"],
                    stats["errors"],
                )
```
In `run()`, after the submitter authenticates, authenticate the news client:
```python
        if not await self._news.authenticate():
            logger.error("Failed to authenticate news client with OSAF API")
            sys.exit(1)
```
In `_cleanup()`, add:
```python
        await self._news.close()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claude/OSAF && pytest collector/tests/test_pipeline_capture.py -v`
Expected: 3 PASS

- [ ] **Step 5: Run the full collector + backend suites**

Run: `cd ~/claude/OSAF && pytest collector/tests -v && cd backend && pytest tests/test_news.py tests/test_sighting_submission.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
cd ~/claude/OSAF
git add collector/pipeline.py collector/main.py collector/tests/test_pipeline_capture.py
git commit -m "feat(collector): two-tier capture + auto-promote pipeline"
```

---

## Task 11: Promote the `collector` user to `verified_contributor` (deploy step)

**Files:**
- Create: `backend/scripts/promote_collector.py`

**Interfaces:**
- Consumes: `app.database.async_session`, `app.models.user.User`.
- Produces: idempotent script setting `collector` user role to `verified_contributor` so AI-promoted records auto-publish via `/submissions`.

- [ ] **Step 1: Write the script**

`backend/scripts/promote_collector.py`:
```python
"""Idempotently promote the collector user to verified_contributor.

Run inside the backend container after the collector user exists:
    python -m scripts.promote_collector
"""

import asyncio

from sqlalchemy import select

from app.database import async_session
from app.models.user import User


async def main() -> None:
    async with async_session() as db:
        user = (await db.execute(select(User).where(User.username == "collector"))).scalar_one_or_none()
        if user is None:
            print("collector user not found — create it first (register), then re-run")
            return
        if user.role == "verified_contributor":
            print("collector already verified_contributor — no change")
            return
        old = user.role
        user.role = "verified_contributor"
        await db.commit()
        print(f"collector role: {old} -> verified_contributor")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Run it (deploy environment, against the live DB)**

Run (in the backend container / venv with DB env set):
`cd ~/claude/OSAF/backend && python -m scripts.promote_collector`
Expected: `collector role: public -> verified_contributor` (or "already" / "not found").

- [ ] **Step 3: Commit**

```bash
cd ~/claude/OSAF
git add backend/scripts/promote_collector.py
git commit -m "chore(backend): idempotent collector-role promotion script"
```

---

## Task 12: Full-suite verification + docs note

**Files:**
- Modify: `~/claude/OSAF/CHANGELOG.md` (if present; else skip)

- [ ] **Step 1: Run the complete test suites**

Run: `cd ~/claude/OSAF && pytest collector/tests -v && cd backend && pytest -v`
Expected: all PASS (no regressions in existing tests).

- [ ] **Step 2: Confirm migration is current**

Run: `cd ~/claude/OSAF/backend && alembic current`
Expected: `d4e5f6a1b2c3 (head)`

- [ ] **Step 3: Append a CHANGELOG entry** (only if `CHANGELOG.md` exists)

Add under a new dated heading: "Add Shark News capture (`news_items`) + AI auto-promotion of sightings & attacks (SP1)."

- [ ] **Step 4: Commit**

```bash
cd ~/claude/OSAF
git add CHANGELOG.md
git commit -m "docs: changelog — SP1 shark news capture + sightings"
```

---

## Notes on spec deviations (intentional, same outcome)

1. **`event_type` derived, not prompted.** The spec proposed adding `event_type` to the extractor prompt/`ExtractedIncident`. The existing extractor already classifies sightings, so `event_type` is derived in the pipeline (`derive_event_type`) — less LLM churn, no re-tuning. The `news_items.event_type` column is unchanged.
2. **Auto-publish via role, not endpoint switch.** The spec proposed switching the collector to `POST /incidents`. The existing `/submissions` path already auto-publishes for `verified_contributor`, so `submitter.py` is untouched; we only promote the `collector` user's role (Task 11).
3. **Promotion link by `case_number`.** `submitter.submit` returns the case number, not the incident UUID. `NewsItemCreate.promoted_case_number` carries it; `NewsService.upsert` resolves it to the `promoted_incident_id` FK — avoids changing `submitter`.
