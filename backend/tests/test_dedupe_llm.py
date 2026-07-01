import pytest
from datetime import date, timedelta
from app.models.incident import Incident
from scripts.dedupe_llm import candidate_clusters


async def _inc(db, case, d, country="Bahamas", cls="unprovoked"):
    i = Incident(case_number=case, incident_date=d, date_precision="exact",
                 location_description="X", country=country, location_precision="approximate",
                 classification=cls, fatal=False, verification_status="verified")
    db.add(i); await db.commit(); await db.refresh(i)
    return i


@pytest.mark.asyncio
async def test_clusters_within_window(db):
    await _inc(db, "OSAF-1", date(2026, 6, 25))
    await _inc(db, "OSAF-2", date(2026, 6, 26))      # 1 day apart, same country+class
    clusters = await candidate_clusters(db)
    assert len(clusters) == 1 and len(clusters[0]) == 2


@pytest.mark.asyncio
async def test_no_cluster_outside_window(db):
    await _inc(db, "OSAF-1", date(2026, 6, 25))
    await _inc(db, "OSAF-2", date(2026, 7, 10))      # >3 days
    assert await candidate_clusters(db) == []


@pytest.mark.asyncio
async def test_no_cluster_across_classification(db):
    await _inc(db, "OSAF-1", date(2026, 6, 25), cls="unprovoked")
    await _inc(db, "OSAF-2", date(2026, 6, 26), cls="provoked")
    assert await candidate_clusters(db) == []


@pytest.mark.asyncio
async def test_oversize_cluster_skipped(db):
    for n in range(12):
        await _inc(db, f"OSAF-{n:02d}", date(2026, 6, 25) + timedelta(days=n))  # chain within 3d
    assert await candidate_clusters(db, max_cluster=10) == []
