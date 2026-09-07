"""Tests for statistics endpoints."""

from datetime import date

import pytest
from httpx import AsyncClient

from app.models.incident import Incident


@pytest.mark.asyncio
async def test_overview_empty(client: AsyncClient):
    response = await client.get("/api/v1/stats/overview")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total_incidents"] == 0
    assert data["total_fatal"] == 0
    assert data["fatality_rate"] == 0


@pytest.mark.asyncio
async def test_overview_with_data(client: AsyncClient, db):
    incidents = [
        Incident(
            case_number="OSAF-2025-0070",
            verification_status="verified",
            location_description="Beach A",
            country="United States",
            classification="unprovoked",
            incident_date=date(2025, 1, 1),
            shark_species_confirmed="Carcharodon carcharias",
            fatal=False,
        ),
        Incident(
            case_number="OSAF-2025-0071",
            verification_status="verified",
            location_description="Beach B",
            country="Australia",
            classification="unprovoked",
            incident_date=date(2025, 2, 1),
            fatal=True,
        ),
        Incident(
            case_number="OSAF-2025-0072",
            verification_status="verified",
            location_description="Beach C",
            country="United States",
            classification="provoked",
            incident_date=date(2025, 3, 1),
            shark_species_confirmed="Carcharodon carcharias",
            fatal=False,
        ),
    ]
    db.add_all(incidents)
    await db.commit()

    response = await client.get("/api/v1/stats/overview")
    data = response.json()["data"]
    assert data["total_incidents"] == 3
    assert data["total_fatal"] == 1
    assert data["fatality_rate"] == pytest.approx(33.3, abs=0.1)
    assert data["most_active_country"] == "United States"
    assert data["most_common_species"] == "Carcharodon carcharias"


@pytest.mark.asyncio
async def test_by_year(client: AsyncClient, db):
    db.add_all([
        Incident(
            case_number="OSAF-2024-0080",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            incident_date=date(2024, 6, 1),
            fatal=False,
        ),
        Incident(
            case_number="OSAF-2025-0081",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            incident_date=date(2025, 3, 1),
            fatal=True,
        ),
    ])
    await db.commit()

    response = await client.get("/api/v1/stats/by-year")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 2
    years = {r["year"] for r in data}
    assert 2024 in years
    assert 2025 in years


@pytest.mark.asyncio
async def test_by_country(client: AsyncClient, db):
    for i in range(3):
        db.add(Incident(
            case_number=f"OSAF-2025-009{i}",
            verification_status="verified",
            location_description="Beach",
            country="Australia",
            classification="unprovoked",
            fatal=i == 0,
        ))
    db.add(Incident(
        case_number="OSAF-2025-0093",
        verification_status="verified",
        location_description="Beach",
        country="South Africa",
        classification="unprovoked",
        fatal=False,
    ))
    await db.commit()

    response = await client.get("/api/v1/stats/by-country")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["country"] == "Australia"
    assert data[0]["count"] == 3


@pytest.mark.asyncio
async def test_by_species(client: AsyncClient, db):
    db.add_all([
        Incident(
            case_number="OSAF-2025-0100",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            shark_species_confirmed="Carcharodon carcharias",
        ),
        Incident(
            case_number="OSAF-2025-0101",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            shark_species_confirmed="Carcharodon carcharias",
        ),
        Incident(
            case_number="OSAF-2025-0102",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            shark_species_confirmed="Galeocerdo cuvier",
        ),
    ])
    await db.commit()

    response = await client.get("/api/v1/stats/by-species")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["species"] == "Carcharodon carcharias"
    assert data[0]["count"] == 2


@pytest.mark.asyncio
async def test_by_activity(client: AsyncClient, db):
    db.add_all([
        Incident(
            case_number="OSAF-2025-0110",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            victim_activity="surfing",
        ),
        Incident(
            case_number="OSAF-2025-0111",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            victim_activity="surfing",
        ),
        Incident(
            case_number="OSAF-2025-0112",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            victim_activity="swimming",
        ),
    ])
    await db.commit()

    response = await client.get("/api/v1/stats/by-activity")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data[0]["activity"] == "surfing"
    assert data[0]["count"] == 2


@pytest.mark.asyncio
async def test_fatality_trends(client: AsyncClient, db):
    db.add_all([
        Incident(
            case_number="OSAF-2025-0120",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            incident_date=date(2025, 1, 1),
            fatal=True,
        ),
        Incident(
            case_number="OSAF-2025-0121",
            verification_status="verified",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            incident_date=date(2025, 6, 1),
            fatal=False,
        ),
    ])
    await db.commit()

    response = await client.get("/api/v1/stats/fatality-trends")
    assert response.status_code == 200
    data = response.json()["data"]
    assert len(data) == 1  # Both are 2025
    assert data[0]["year"] == 2025
    assert data[0]["fatal"] == 1
    assert data[0]["non_fatal"] == 1


@pytest.mark.asyncio
async def test_by_year_empty(client: AsyncClient):
    response = await client.get("/api/v1/stats/by-year")
    assert response.status_code == 200
    assert response.json()["data"] == []


@pytest.mark.asyncio
async def test_by_country_empty(client: AsyncClient):
    response = await client.get("/api/v1/stats/by-country")
    assert response.status_code == 200
    assert response.json()["data"] == []


async def _seed_mix(db):
    # 2 attacks (1 fatal) + 2 sightings + 1 near_miss, same year/country/activity
    rows = [
        Incident(case_number="OSAF-2099-0001", incident_date=date(2099, 1, 1), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="unprovoked", fatal=True, victim_activity="surfing",
                 shark_species_suspected="Carcharodon carcharias", verification_status="verified"),
        Incident(case_number="OSAF-2099-0002", incident_date=date(2099, 1, 2), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="provoked", fatal=False, victim_activity="surfing",
                 shark_species_suspected="Carcharodon carcharias", verification_status="verified"),
        Incident(case_number="OSAF-2099-0003", incident_date=date(2099, 1, 3), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="sighting", fatal=False, victim_activity="swimming",
                 shark_species_suspected="Galeocerdo cuvier", verification_status="verified"),
        Incident(case_number="OSAF-2099-0004", incident_date=date(2099, 1, 4), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="sighting", fatal=False, victim_activity="swimming",
                 shark_species_suspected="Galeocerdo cuvier", verification_status="verified"),
        Incident(case_number="OSAF-2099-0005", incident_date=date(2099, 1, 5), date_precision="exact",
                 location_description="X", country="Testland", location_precision="approximate",
                 classification="near_miss", fatal=False, victim_activity="diving",
                 verification_status="verified"),
    ]
    for r in rows:
        db.add(r)
    await db.commit()


@pytest.mark.asyncio
async def test_overview_counts_attacks_only(db):
    from app.services.stats_service import StatsService
    await _seed_mix(db)
    ov = (await StatsService(db).overview())["data"]
    assert ov["total_incidents"] == 2          # 2 attacks, not 5
    assert ov["total_fatal"] == 1
    assert ov["fatality_rate"] == 50.0


@pytest.mark.asyncio
async def test_breakdowns_exclude_non_attacks(db):
    from app.services.stats_service import StatsService
    await _seed_mix(db)
    svc = StatsService(db)
    by_year = (await svc.by_year())["data"]
    assert sum(r["count"] for r in by_year) == 2
    activities = {r["activity"] for r in (await svc.by_activity())["data"]}
    assert "swimming" not in activities          # sighting activity excluded
    assert "diving" not in activities            # near_miss activity excluded
    assert activities == {"surfing"}
    species = {r["species"] for r in (await svc.by_species())["data"]}
    assert "Galeocerdo cuvier" not in species     # only sightings had tiger shark


async def _seed_verification_mix(db):
    """One verified attack alongside a pending, a rejected, and a needs_review one.

    All four are attack-classification and fatal, so anything that reaches the
    aggregates shows up in both total_incidents and total_fatal.
    """
    db.add_all([
        Incident(
            case_number="OSAF-2025-0400",
            location_description="Verified Beach",
            country="United States",
            classification="unprovoked",
            incident_date=date(2025, 5, 1),
            victim_activity="surfing",
            shark_species_confirmed="Carcharodon carcharias",
            fatal=True,
            verification_status="verified",
        ),
        Incident(
            case_number="OSAF-2025-0401",
            location_description="Pending Beach",
            country="Hoaxland",
            classification="unprovoked",
            incident_date=date(2025, 5, 2),
            victim_activity="swimming",
            shark_species_confirmed="Galeocerdo cuvier",
            fatal=True,
            verification_status="pending",
        ),
        Incident(
            case_number="OSAF-2025-0402",
            location_description="Rejected Beach",
            country="Hoaxland",
            classification="unprovoked",
            incident_date=date(2025, 5, 3),
            victim_activity="swimming",
            shark_species_confirmed="Galeocerdo cuvier",
            fatal=True,
            verification_status="rejected",
        ),
        Incident(
            case_number="OSAF-2025-0403",
            location_description="Needs Review Beach",
            country="Hoaxland",
            classification="unprovoked",
            incident_date=date(2025, 5, 4),
            victim_activity="swimming",
            shark_species_confirmed="Galeocerdo cuvier",
            fatal=True,
            verification_status="needs_review",
        ),
    ])
    await db.commit()


@pytest.mark.asyncio
async def test_overview_counts_verified_only(db):
    """Public stats must not count unverified submissions.

    Registration is open and any authenticated user can submit, so an
    unfiltered aggregate lets anyone move the public headline numbers. A
    rejected incident — one an admin ruled a hoax — must not count either.
    """
    from app.services.stats_service import StatsService

    await _seed_verification_mix(db)
    ov = (await StatsService(db).overview())["data"]

    assert ov["total_incidents"] == 1
    assert ov["total_fatal"] == 1
    assert ov["most_active_country"] == "United States"
    assert ov["most_common_species"] == "Carcharodon carcharias"


@pytest.mark.asyncio
async def test_breakdowns_exclude_unverified(db):
    """Every breakdown carries the same verified-only filter as overview."""
    from app.services.stats_service import StatsService

    await _seed_verification_mix(db)
    svc = StatsService(db)

    assert sum(r["count"] for r in (await svc.by_year())["data"]) == 1

    countries = {r["country"] for r in (await svc.by_country())["data"]}
    assert "Hoaxland" not in countries

    assert {r["species"] for r in (await svc.by_species())["data"]} == {
        "Carcharodon carcharias"
    }
    assert {r["activity"] for r in (await svc.by_activity())["data"]} == {"surfing"}

    trends = (await svc.fatality_trends())["data"]
    assert sum(r["fatal"] for r in trends) == 1
    assert sum(r["non_fatal"] for r in trends) == 0
