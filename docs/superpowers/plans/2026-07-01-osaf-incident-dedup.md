# Incident Deduplication (SP3) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop multiple news outlets covering one shark event from creating duplicate incidents, collapse the Shark News feed to one row per event, and clean up the existing duplicates.

**Architecture:** A deterministic event-signature matcher (`find_duplicate_incident`) is hooked into both incident-create paths so same-event coverage attaches as extra sources to the existing incident instead of creating a new one. The feed query collapses promoted items to one row per incident. A one-off, dry-run-first cleanup script merges existing duplicate clusters.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, PostgreSQL + PostGIS (geoalchemy2), Pydantic v2, pytest + pytest-asyncio.

## Global Constraints

- Python 3.12+, async; SQLAlchemy `Mapped`/`select()` style; PostGIS via geoalchemy2.
- **Event signature (same event = ALL of):** `date_precision == 'exact'` AND `incident_date` not null AND both have coordinates within **150 m** (`ST_DWithin` on `geography`) AND same `classification`; **victim guard:** not a match if both have `victim_age` and differ, or both have `victim_sex` and differ.
- Canonical record in any cluster = the one with the **lowest `case_number`**.
- Merge = append new outlets as `IncidentSource` rows (skip URLs already present) + `IncidentAuditLog` row (`action="source_merged"` for live prevention, `action="merged"` for cleanup). `action` column is `String(20)` — both fit.
- Feed shows **one row per event**: promoted news_items (`promoted_incident_id NOT NULL`) collapse to newest per incident; general news (`promoted_incident_id NULL`) stays per-article.
- No schema/migration change.
- Conventional commits; attribution disabled (no Co-Authored-By trailer).
- Backend tests: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest <args>` (PostGIS `osaf_test` DB on localhost:5432, `backend/.env` supplies config). Local script run: `POSTGRES_DB=osaf .venv/bin/python -m scripts.dedupe_incidents`.
- LLM same-event adjudication is explicitly OUT of scope (future layer).

---

## File Structure

**Create:**
- `backend/app/services/dedup_service.py` — `find_duplicate_incident`, `attach_sources_to_incident`, `_victim_conflict`.
- `backend/scripts/dedupe_incidents.py` — one-off cleanup (dry-run default).
- `backend/tests/test_dedup.py` — signature + prevention tests.
- `backend/tests/test_dedupe_script.py` — cleanup script tests.

**Modify:**
- `backend/app/services/submission_service.py` — dedup hook in `submit_incident`.
- `backend/app/services/incident_service.py` — dedup hook in `create_incident`; feed collapse in `NewsService`? (no — feed is in news_service).
- `backend/app/services/news_service.py` — `list_news` collapse.
- `backend/tests/test_news.py` — feed-collapse test (append).

---

## Task 1: Event-signature matcher

**Files:**
- Create: `backend/app/services/dedup_service.py`
- Test: `backend/tests/test_dedup.py`

**Interfaces:**
- Produces:
  - `async find_duplicate_incident(db: AsyncSession, data: IncidentCreate) -> Incident | None`
  - `_victim_conflict(inc: Incident, data: IncidentCreate) -> bool`

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_dedup.py`:
```python
import pytest
from app.models.incident import Incident
from app.schemas.incident import CoordinatesSchema, IncidentCreate
from app.services.dedup_service import find_duplicate_incident
from app.utils.geo import point_from_coords


async def _add_incident(db, *, case_number, classification="unprovoked", date="2026-06-25",
                        lon=-77.3434, lat=25.0764, date_precision="exact",
                        victim_age=None, victim_sex=None):
    from datetime import date as _d
    y, m, d = (int(x) for x in date.split("-"))
    inc = Incident(
        case_number=case_number, incident_date=_d(y, m, d), date_precision=date_precision,
        location_description="Bahamas", country="Bahamas", location_precision="approximate",
        classification=classification, fatal=False, victim_age=victim_age, victim_sex=victim_sex,
        coordinates=point_from_coords(lon, lat), verification_status="verified",
    )
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    return inc


def _create(**kw):
    base = dict(location_description="Bahamas", country="Bahamas", classification="unprovoked",
                incident_date="2026-06-25", date_precision="exact",
                coordinates=CoordinatesSchema(longitude=-77.3434, latitude=25.0764))
    base.update(kw)
    return IncidentCreate(**base)


@pytest.mark.asyncio
async def test_matches_same_event(db):
    inc = await _add_incident(db, case_number="OSAF-2026-0001")
    match = await find_duplicate_incident(db, _create())
    assert match is not None and match.id == inc.id


@pytest.mark.asyncio
async def test_no_match_when_date_precision_not_exact(db):
    await _add_incident(db, case_number="OSAF-2026-0002")
    assert await find_duplicate_incident(db, _create(date_precision="month")) is None


@pytest.mark.asyncio
async def test_no_match_when_far_apart(db):
    await _add_incident(db, case_number="OSAF-2026-0003")
    # ~1 degree away (>100 km)
    far = _create(coordinates=CoordinatesSchema(longitude=-78.5, latitude=25.0764))
    assert await find_duplicate_incident(db, far) is None


@pytest.mark.asyncio
async def test_victim_age_guard_blocks(db):
    await _add_incident(db, case_number="OSAF-2026-0004", victim_age=12)
    assert await find_duplicate_incident(db, _create(victim_age=40)) is None


@pytest.mark.asyncio
async def test_no_match_without_coords(db):
    await _add_incident(db, case_number="OSAF-2026-0005")
    assert await find_duplicate_incident(db, _create(coordinates=None)) is None


@pytest.mark.asyncio
async def test_lowest_case_number_wins(db):
    await _add_incident(db, case_number="OSAF-2026-0009")
    first = await _add_incident(db, case_number="OSAF-2026-0007")
    match = await find_duplicate_incident(db, _create())
    assert match.case_number == "OSAF-2026-0007"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedup.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.dedup_service'`

- [ ] **Step 3: Write minimal implementation**

`backend/app/services/dedup_service.py`:
```python
from geoalchemy2 import Geography
from sqlalchemy import cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.audit import IncidentAuditLog
from app.models.incident import Incident
from app.models.source import IncidentSource
from app.schemas.incident import IncidentCreate, SourceCreate
from app.utils.geo import point_from_coords

_MATCH_RADIUS_M = 150


def _victim_conflict(inc: Incident, data: IncidentCreate) -> bool:
    """True if the victim details positively contradict (both present and differ)."""
    if inc.victim_age is not None and data.victim_age is not None and inc.victim_age != data.victim_age:
        return True
    if inc.victim_sex and data.victim_sex and inc.victim_sex != data.victim_sex:
        return True
    return False


async def find_duplicate_incident(db: AsyncSession, data: IncidentCreate) -> Incident | None:
    """Return an existing incident that is the same real-world event as `data`, else None.

    Same event = exact-precision same date + coordinates within 150 m + same
    classification, with a victim age/sex guard. Conservative by design.
    """
    if data.date_precision != "exact" or data.incident_date is None or data.coordinates is None:
        return None

    point = point_from_coords(data.coordinates.longitude, data.coordinates.latitude)
    stmt = (
        select(Incident)
        .options(selectinload(Incident.sources))
        .where(
            Incident.incident_date == data.incident_date,
            Incident.classification == data.classification,
            Incident.coordinates.isnot(None),
            func.ST_DWithin(
                cast(Incident.coordinates, Geography),
                cast(point, Geography),
                _MATCH_RADIUS_M,
            ),
        )
        .order_by(Incident.case_number.asc())
    )
    candidates = (await db.execute(stmt)).scalars().all()
    for inc in candidates:
        if not _victim_conflict(inc, data):
            return inc
    return None


async def attach_sources_to_incident(
    db: AsyncSession,
    incident: Incident,
    new_sources: list[SourceCreate],
    changed_by=None,
) -> None:
    """Append new outlet sources to an existing incident (skipping URLs already
    present) and record a source_merged audit entry. Commits."""
    existing_urls = {s.source_url for s in incident.sources if s.source_url}
    added: list[str] = []
    for sd in new_sources:
        if sd.source_url and sd.source_url in existing_urls:
            continue
        incident.sources.append(
            IncidentSource(
                source_type=sd.source_type,
                source_url=sd.source_url,
                source_title=sd.source_title,
                source_publisher=sd.source_publisher,
                source_date=sd.source_date,
                source_notes=sd.source_notes,
            )
        )
        if sd.source_url:
            existing_urls.add(sd.source_url)
        added.append(sd.source_publisher or sd.source_url or sd.source_title or "source")

    db.add(
        IncidentAuditLog(
            incident_id=incident.id,
            action="source_merged",
            changed_by=changed_by,
            notes=(
                f"Merged duplicate coverage: {', '.join(added)}"
                if added
                else "Duplicate submission (no new sources)"
            ),
        )
    )
    await db.commit()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedup.py -v`
Expected: 6 PASS. If `ST_DWithin`/`cast(..., Geography)` raises a DB error, STOP and report it (the geography cast is the one risky line).

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/services/dedup_service.py backend/tests/test_dedup.py
git commit -m "feat(backend): event-signature duplicate-incident matcher"
```

---

## Task 2: Prevention — wire dedup into both create paths

**Files:**
- Modify: `backend/app/services/submission_service.py`
- Modify: `backend/app/services/incident_service.py`
- Test: `backend/tests/test_dedup.py` (append)

**Interfaces:**
- Consumes: `find_duplicate_incident`, `attach_sources_to_incident` (Task 1).
- Produces: same-event submissions attach sources to the existing incident and return it (no new incident/case number).

- [ ] **Step 1: Write the failing tests** (append to `backend/tests/test_dedup.py`)

```python
@pytest.mark.asyncio
async def test_submission_dedup_attaches_source(db, verified_user):
    from app.schemas.incident import IncidentCreate, CoordinatesSchema, SourceCreate
    from app.services.submission_service import SubmissionService
    svc = SubmissionService(db)

    def mk(pub, url):
        return IncidentCreate(
            location_description="Bahamas", country="Bahamas", classification="unprovoked",
            incident_date="2026-06-25", date_precision="exact",
            coordinates=CoordinatesSchema(longitude=-77.3434, latitude=25.0764),
            sources=[SourceCreate(source_type="news_article", source_url=url,
                                  source_title="t", source_publisher=pub)],
        )

    first = await svc.submit_incident(mk("Yahoo", "https://y/1"), verified_user)
    second = await svc.submit_incident(mk("WCIA", "https://w/2"), verified_user)

    # Same incident returned, no new case number
    assert second.case_number == first.case_number
    # Both outlets are now sources on the one incident
    assert len(second.sources) == 2
    pubs = {s.source_publisher for s in second.sources}
    assert pubs == {"Yahoo", "WCIA"}


@pytest.mark.asyncio
async def test_submission_distinct_event_creates_new(db, verified_user):
    from app.schemas.incident import IncidentCreate, CoordinatesSchema, SourceCreate
    from app.services.submission_service import SubmissionService
    svc = SubmissionService(db)

    def mk(date, url):
        return IncidentCreate(
            location_description="Bahamas", country="Bahamas", classification="unprovoked",
            incident_date=date, date_precision="exact",
            coordinates=CoordinatesSchema(longitude=-77.3434, latitude=25.0764),
            sources=[SourceCreate(source_type="news_article", source_url=url, source_title="t")],
        )

    a = await svc.submit_incident(mk("2026-06-25", "https://y/1"), verified_user)
    b = await svc.submit_incident(mk("2026-07-04", "https://y/2"), verified_user)  # different date
    assert a.case_number != b.case_number
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedup.py -k submission -v`
Expected: FAIL — `test_submission_dedup_attaches_source` gets two different case numbers (dedup not wired yet).

- [ ] **Step 3: Wire `submission_service.py`**

Add imports near the top of `backend/app/services/submission_service.py`:
```python
from app.services.dedup_service import attach_sources_to_incident, find_duplicate_incident
```
At the very start of `submit_incident`, before `case_number = await generate_case_number(self.db)`:
```python
        existing = await find_duplicate_incident(self.db, data)
        if existing is not None:
            await attach_sources_to_incident(self.db, existing, data.sources, changed_by=user.id)
            return await self._get_incident_response(existing.id)
```

- [ ] **Step 4: Wire `incident_service.py`**

Add import near the top of `backend/app/services/incident_service.py`:
```python
from app.services.dedup_service import attach_sources_to_incident, find_duplicate_incident
```
At the very start of `create_incident`, before `case_number = await generate_case_number(self.db)`:
```python
        existing = await find_duplicate_incident(self.db, data)
        if existing is not None:
            await attach_sources_to_incident(self.db, existing, data.sources)
            return await self.get_incident(existing.id)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedup.py -v`
Expected: all PASS (8 total). Also run the existing submission suite to check no regression:
`POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_submissions.py -v`
Expected: no NEW failures vs. baseline (the pre-existing 6 auth/register failures are unrelated and not in these files).

- [ ] **Step 6: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/services/submission_service.py backend/app/services/incident_service.py backend/tests/test_dedup.py
git commit -m "feat(backend): dedup same-event submissions into one incident (attach sources)"
```

---

## Task 3: Feed — one row per event

**Files:**
- Modify: `backend/app/services/news_service.py` (`list_news`)
- Test: `backend/tests/test_news.py` (append)

**Interfaces:**
- Consumes: existing `NewsService.list_news` signature (unchanged).
- Produces: `list_news` returns one row per `promoted_incident_id` (newest `captured_at`); general rows (`promoted_incident_id IS NULL`) all returned; `meta.total` = collapsed count.

- [ ] **Step 1: Write the failing test** (append to `backend/tests/test_news.py`)

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_news.py::test_list_news_collapses_promoted_by_incident -v`
Expected: FAIL — total is 3 (no collapse yet).

- [ ] **Step 3: Rewrite `list_news`**

Replace the `list_news` method body in `backend/app/services/news_service.py` with the version below. Add these imports at the top of the file (merge into existing import lines):
```python
from sqlalchemy import String, cast, func, or_, select
from sqlalchemy.orm import aliased
```
(`desc` is already imported; keep it. `math` already imported.)

New `list_news`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_news.py -v`
Expected: all PASS (the new collapse test + all prior news tests, incl. the CSV/idempotency/endpoint ones).

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/app/services/news_service.py backend/tests/test_news.py
git commit -m "feat(backend): collapse Shark News feed to one row per promoted incident"
```

---

## Task 4: Cleanup script (dry-run default)

**Files:**
- Create: `backend/scripts/dedupe_incidents.py`
- Test: `backend/tests/test_dedupe_script.py`

**Interfaces:**
- Consumes: `_victim_conflict` (Task 1), models.
- Produces: `async run(apply: bool) -> dict` returning `{clusters, incidents_merged}`; CLI `python -m scripts.dedupe_incidents [--apply]` (dry-run default).

- [ ] **Step 1: Write the failing test**

`backend/tests/test_dedupe_script.py`:
```python
import pytest
from sqlalchemy import select
from app.models.incident import Incident
from app.models.news import NewsItem
from app.models.source import IncidentSource
from app.utils.geo import point_from_coords
from scripts.dedupe_incidents import run


async def _incident(db, case_number, url, pub, age=None):
    from datetime import date
    inc = Incident(
        case_number=case_number, incident_date=date(2026, 6, 25), date_precision="exact",
        location_description="Bahamas", country="Bahamas", location_precision="approximate",
        classification="unprovoked", fatal=False, victim_age=age,
        coordinates=point_from_coords(-77.3434, 25.0764), verification_status="verified",
    )
    inc.sources.append(IncidentSource(source_type="news_article", source_url=url, source_publisher=pub))
    db.add(inc)
    await db.commit()
    await db.refresh(inc)
    db.add(NewsItem(dedup_key=f"backfill:{inc.id}", source_platform="web_scrape",
                    source_name=pub, source_url=url, title=f"t {pub}", event_type="attack",
                    promoted_incident_id=inc.id))
    await db.commit()
    return inc


@pytest.mark.asyncio
async def test_dryrun_changes_nothing(db):
    await _incident(db, "OSAF-2026-0001", "https://y/1", "Yahoo")
    await _incident(db, "OSAF-2026-0002", "https://w/2", "WCIA")
    stats = await run(apply=False)
    assert stats["incidents_merged"] == 1  # would merge 1 absorbed
    assert (await db.execute(select(Incident))).scalars().all().__len__() == 2  # unchanged


@pytest.mark.asyncio
async def test_apply_merges_cluster(db):
    a = await _incident(db, "OSAF-2026-0001", "https://y/1", "Yahoo")
    b = await _incident(db, "OSAF-2026-0002", "https://w/2", "WCIA")
    stats = await run(apply=True)
    assert stats["incidents_merged"] == 1
    incs = (await db.execute(select(Incident))).scalars().all()
    assert len(incs) == 1 and incs[0].case_number == "OSAF-2026-0001"  # canonical kept
    srcs = (await db.execute(select(IncidentSource))).scalars().all()
    assert {s.source_publisher for s in srcs} == {"Yahoo", "WCIA"}  # sources merged
    news = (await db.execute(select(NewsItem))).scalars().all()
    assert len(news) == 1  # absorbed backfill news deleted
    # idempotent
    assert (await run(apply=True))["incidents_merged"] == 0


@pytest.mark.asyncio
async def test_victim_conflict_not_merged(db):
    await _incident(db, "OSAF-2026-0001", "https://y/1", "Yahoo", age=12)
    await _incident(db, "OSAF-2026-0002", "https://w/2", "WCIA", age=40)
    stats = await run(apply=True)
    assert stats["incidents_merged"] == 0
    assert len((await db.execute(select(Incident))).scalars().all()) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedupe_script.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.dedupe_incidents'`

- [ ] **Step 3: Write the script**

`backend/scripts/dedupe_incidents.py`:
```python
"""Merge duplicate incidents created by multiple outlets covering one event.

Same event = exact-precision same date + coordinates (rounded to 3 dp ~= 111 m)
+ same classification, with a victim age/sex guard. Canonical = lowest case number.
Absorbed incidents: sources moved to canonical (dedup by URL), their news_items
re-pointed to canonical (backfill news deleted), audit-logged, then deleted.

Dry-run by default; pass --apply to perform the merges.
    python -m scripts.dedupe_incidents [--apply]
"""

import asyncio
import sys

from geoalchemy2.functions import ST_X, ST_Y
from sqlalchemy import Numeric, delete, func, select, update

from app.database import async_session
from app.models.audit import IncidentAuditLog
from app.models.incident import Incident
from app.models.news import NewsItem
from app.models.source import IncidentSource
from app.services.dedup_service import _victim_conflict


async def _clusters(db):
    """Return lists of incident ids sharing (date, classification, rounded coords)."""
    lat = func.round(ST_Y(Incident.coordinates).cast(Numeric), 3)
    lon = func.round(ST_X(Incident.coordinates).cast(Numeric), 3)
    stmt = (
        select(func.array_agg(Incident.id))
        .where(
            Incident.date_precision == "exact",
            Incident.incident_date.isnot(None),
            Incident.coordinates.isnot(None),
        )
        .group_by(Incident.incident_date, Incident.classification, lat, lon)
        .having(func.count() > 1)
    )
    return [row[0] for row in (await db.execute(stmt)).all()]


async def run(apply: bool) -> dict:
    merged = 0
    clusters = 0
    async with async_session() as db:
        for ids in await _clusters(db):
            rows = (
                await db.execute(
                    select(Incident)
                    .where(Incident.id.in_(ids))
                    .order_by(Incident.case_number.asc())
                )
            ).scalars().all()
            if len(rows) < 2:
                continue
            canonical = rows[0]
            # canonical source URLs (for dedup when moving absorbed sources)
            canon_urls = {
                s.source_url
                for s in (
                    await db.execute(
                        select(IncidentSource).where(IncidentSource.incident_id == canonical.id)
                    )
                ).scalars().all()
                if s.source_url
            }
            absorbed = [inc for inc in rows[1:] if not _victim_conflict(canonical, _as_create(inc))]
            if not absorbed:
                continue
            clusters += 1
            for inc in absorbed:
                print(f"  merge {inc.case_number} -> {canonical.case_number}")
                if apply:
                    # move sources not already present (by url)
                    srcs = (
                        await db.execute(
                            select(IncidentSource).where(IncidentSource.incident_id == inc.id)
                        )
                    ).scalars().all()
                    for s in srcs:
                        if s.source_url and s.source_url in canon_urls:
                            await db.execute(delete(IncidentSource).where(IncidentSource.id == s.id))
                        else:
                            await db.execute(
                                update(IncidentSource)
                                .where(IncidentSource.id == s.id)
                                .values(incident_id=canonical.id)
                            )
                            if s.source_url:
                                canon_urls.add(s.source_url)
                    # absorbed backfill news -> delete; other news -> re-point
                    await db.execute(
                        delete(NewsItem).where(
                            NewsItem.promoted_incident_id == inc.id,
                            NewsItem.dedup_key.like("backfill:%"),
                        )
                    )
                    await db.execute(
                        update(NewsItem)
                        .where(NewsItem.promoted_incident_id == inc.id)
                        .values(promoted_incident_id=canonical.id)
                    )
                    db.add(
                        IncidentAuditLog(
                            incident_id=canonical.id,
                            action="merged",
                            notes=f"Absorbed duplicate {inc.case_number}",
                        )
                    )
                    await db.execute(delete(Incident).where(Incident.id == inc.id))
                merged += 1
            if apply:
                await db.commit()
    print(f"dedupe_incidents: {'APPLIED' if apply else 'DRY-RUN'} — clusters={clusters}, incidents_merged={merged}")
    return {"clusters": clusters, "incidents_merged": merged}


def _as_create(inc: Incident):
    """Adapt an Incident to the minimal shape _victim_conflict's 2nd arg needs."""
    class _V:
        victim_age = inc.victim_age
        victim_sex = inc.victim_sex
    return _V()


if __name__ == "__main__":
    asyncio.run(run(apply="--apply" in sys.argv))
```

(`_as_create`, defined at the bottom of the script, adapts an absorbed incident to the
tiny `victim_age`/`victim_sex` shape `_victim_conflict`'s second argument expects, so the
absorbed record is compared against the canonical.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest tests/test_dedupe_script.py -v`
Expected: 3 PASS. If the `func.round(... .cast(Numeric), 3)` clustering SQL errors, STOP and report — that grouping expression is the risky line.

- [ ] **Step 5: Commit**

```bash
cd ~/claude/OSAF
git add backend/scripts/dedupe_incidents.py backend/tests/test_dedupe_script.py
git commit -m "feat(backend): dedupe_incidents cleanup script (dry-run default)"
```

---

## Task 5: Full-suite verification + changelog

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Run the full backend suite**

Run: `cd ~/claude/OSAF/backend && POSTGRES_DB=osaf_test .venv/bin/python -m pytest -q`
Expected: all pass except the 6 known pre-existing failures (`test_register` ×3, `test_login` ×2, `test_create_incident_invalid_classification`) — no NEW failures from SP3.

- [ ] **Step 2: Append CHANGELOG entry** under `## [Unreleased]` → `### Added`:

```markdown
- **Incident deduplication (SP3).** Multiple outlets covering one shark event no
  longer create duplicate incidents: a deterministic event signature
  (exact-date + coordinates within 150 m + classification, with a victim guard)
  attaches syndicated coverage as extra sources to the existing incident instead
  of creating a new one (`dedup_service.find_duplicate_incident`, wired into both
  submission and direct-create paths). The Shark News feed now shows one row per
  event (`list_news` collapses promoted items by incident). A one-off
  `scripts/dedupe_incidents.py` (dry-run default, `--apply` to execute) merges the
  pre-existing duplicate clusters — moving sources onto the canonical (lowest case
  number), re-pointing/pruning their news_items, and audit-logging each merge.
  Spec/plan: `docs/superpowers/specs/2026-07-01-osaf-incident-dedup-design.md`,
  `docs/superpowers/plans/2026-07-01-osaf-incident-dedup.md`.
```

- [ ] **Step 3: Commit**

```bash
cd ~/claude/OSAF
git add CHANGELOG.md
git commit -m "docs: changelog — SP3 incident deduplication"
```

---

## Deployment (after merge, run manually — not a plan task for subagents)

On the production host: update the working tree with a fast-forward-only pull, then rebuild the backend image.
(`docker compose -f docker-compose.yml up -d --build backend`), then
`docker cp backend/scripts/dedupe_incidents.py osaf-backend-1:/app/scripts/` and run
the **dry-run** (`docker compose -f docker-compose.yml exec -T backend python -m scripts.dedupe_incidents`),
review, then `--apply`. Verify `GET /api/v1/news` shows collapsed events. (Feed collapse
takes effect on backend restart even before the cleanup runs.)

---

## Notes / deviations

- The `create_incident` dedup path logs the merge audit with `changed_by=None` (that service method has no user in scope); the collector uses `/submissions` (`submit_incident`), which passes `user.id`, so the primary path is attributed.
- Cleanup clusters by rounded-3dp coordinates (~111 m) for efficient batch grouping — the practical equivalent of prevention's 150 m `ST_DWithin`. The victim guard is applied per absorbed-vs-canonical pair, mirroring prevention.
