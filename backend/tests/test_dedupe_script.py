import pytest
from sqlalchemy import select
from app.models.incident import Incident
from app.models.news import NewsItem
from app.models.source import IncidentSource
from app.utils.geo import point_from_coords
from scripts.dedupe_incidents import run


async def _incident(db, case_number, url, pub, age=None, description=None):
    from datetime import date
    inc = Incident(
        case_number=case_number, incident_date=date(2026, 6, 25), date_precision="exact",
        location_description="Bahamas", country="Bahamas", location_precision="approximate",
        classification="unprovoked", fatal=False, victim_age=age, description=description,
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
    assert len((await db.execute(select(IncidentSource))).scalars().all()) == 2
    assert len((await db.execute(select(NewsItem))).scalars().all()) == 2


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
async def test_enrich_fills_canonical_nulls(db):
    """After merge, canonical's NULL fields are populated from absorbed's non-null values."""
    # canonical has no description or victim_age
    await _incident(db, "OSAF-2026-0001", "https://y/1", "Yahoo")
    # absorbed has both
    await _incident(db, "OSAF-2026-0002", "https://w/2", "WCIA",
                    age=30, description="Incident near beach.")
    stats = await run(apply=True)
    assert stats["incidents_merged"] == 1
    # force fresh load from DB (run() committed in its own session)
    db.expire_all()
    surviving = (await db.execute(select(Incident))).scalars().one()
    assert surviving.case_number == "OSAF-2026-0001"
    assert surviving.description == "Incident near beach."
    assert surviving.victim_age == 30


@pytest.mark.asyncio
async def test_victim_conflict_not_merged(db):
    await _incident(db, "OSAF-2026-0001", "https://y/1", "Yahoo", age=12)
    await _incident(db, "OSAF-2026-0002", "https://w/2", "WCIA", age=40)
    stats = await run(apply=True)
    assert stats["incidents_merged"] == 0
    assert len((await db.execute(select(Incident))).scalars().all()) == 2
