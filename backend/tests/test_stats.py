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
            location_description="Beach A",
            country="United States",
            classification="unprovoked",
            incident_date=date(2025, 1, 1),
            shark_species_confirmed="Carcharodon carcharias",
            fatal=False,
        ),
        Incident(
            case_number="OSAF-2025-0071",
            location_description="Beach B",
            country="Australia",
            classification="unprovoked",
            incident_date=date(2025, 2, 1),
            fatal=True,
        ),
        Incident(
            case_number="OSAF-2025-0072",
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
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            incident_date=date(2024, 6, 1),
            fatal=False,
        ),
        Incident(
            case_number="OSAF-2025-0081",
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
            location_description="Beach",
            country="Australia",
            classification="unprovoked",
            fatal=i == 0,
        ))
    db.add(Incident(
        case_number="OSAF-2025-0093",
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
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            shark_species_confirmed="Carcharodon carcharias",
        ),
        Incident(
            case_number="OSAF-2025-0101",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            shark_species_confirmed="Carcharodon carcharias",
        ),
        Incident(
            case_number="OSAF-2025-0102",
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
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            victim_activity="surfing",
        ),
        Incident(
            case_number="OSAF-2025-0111",
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            victim_activity="surfing",
        ),
        Incident(
            case_number="OSAF-2025-0112",
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
            location_description="Beach",
            country="USA",
            classification="unprovoked",
            incident_date=date(2025, 1, 1),
            fatal=True,
        ),
        Incident(
            case_number="OSAF-2025-0121",
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
