"""Tests for incident CRUD endpoints."""

import pytest
from httpx import AsyncClient

from app.models.incident import Incident
from tests.conftest import SAMPLE_INCIDENT_PAYLOAD


@pytest.mark.asyncio
async def test_create_incident(client: AsyncClient):
    response = await client.post("/api/v1/incidents", json=SAMPLE_INCIDENT_PAYLOAD)
    assert response.status_code == 201
    data = response.json()
    assert data["case_number"].startswith("OSAF-")
    assert data["country"] == "Australia"
    assert data["classification"] == "unprovoked"
    assert data["classification_subtype"] == "hit_and_run"
    assert data["victim_activity"] == "swimming"
    assert data["fatal"] is False
    assert data["longitude"] is not None
    assert data["latitude"] is not None
    assert len(data["sources"]) == 1
    assert data["sources"][0]["source_type"] == "news_article"


@pytest.mark.asyncio
async def test_create_incident_minimal(client: AsyncClient):
    """Create incident with only required fields."""
    response = await client.post(
        "/api/v1/incidents",
        json={
            "location_description": "Unknown beach",
            "country": "Unknown",
            "classification": "not_confirmed",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["country"] == "Unknown"
    assert data["classification"] == "not_confirmed"
    assert data["fatal"] is False
    assert data["longitude"] is None
    assert data["latitude"] is None


@pytest.mark.asyncio
async def test_create_incident_invalid_classification(client: AsyncClient):
    """Invalid classification should be rejected by the DB constraint."""
    response = await client.post(
        "/api/v1/incidents",
        json={
            "location_description": "Some beach",
            "country": "Nowhere",
            "classification": "invalid_classification",
        },
    )
    # The DB CHECK constraint will cause a 500 since the API doesn't validate
    # classification values before insert
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_get_incident(client: AsyncClient, sample_incident: Incident):
    response = await client.get(f"/api/v1/incidents/{sample_incident.id}")
    assert response.status_code == 200
    data = response.json()
    assert data["case_number"] == "OSAF-2025-0001"
    assert data["country"] == "United States"
    assert data["classification"] == "unprovoked"
    assert data["longitude"] is not None
    assert data["latitude"] is not None


@pytest.mark.asyncio
async def test_get_incident_not_found(client: AsyncClient):
    import uuid

    fake_id = uuid.uuid4()
    response = await client.get(f"/api/v1/incidents/{fake_id}")
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_incidents_empty(client: AsyncClient):
    response = await client.get("/api/v1/incidents")
    assert response.status_code == 200
    data = response.json()
    assert data["data"] == []
    assert data["meta"]["total"] == 0
    assert data["meta"]["page"] == 1


@pytest.mark.asyncio
async def test_list_incidents_with_data(client: AsyncClient, sample_incident: Incident):
    response = await client.get("/api/v1/incidents")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 1
    assert len(data["data"]) == 1
    assert data["data"][0]["case_number"] == "OSAF-2025-0001"


@pytest.mark.asyncio
async def test_list_incidents_pagination(client: AsyncClient, db):
    """Create multiple incidents and test pagination."""
    from app.utils.geo import point_from_coords

    for i in range(5):
        incident = Incident(
            case_number=f"OSAF-2025-{i + 10:04d}",
            location_description=f"Beach {i}",
            country="TestCountry",
            classification="unprovoked",
        )
        db.add(incident)
    await db.commit()

    # Page 1 with 2 per page
    response = await client.get("/api/v1/incidents?page=1&per_page=2")
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 5
    assert data["meta"]["pages"] == 3
    assert len(data["data"]) == 2

    # Page 3 should have 1 item
    response = await client.get("/api/v1/incidents?page=3&per_page=2")
    data = response.json()
    assert len(data["data"]) == 1


@pytest.mark.asyncio
async def test_list_incidents_filter_classification(
    client: AsyncClient, sample_incident: Incident, db
):
    """Filter by classification."""
    # Add a provoked incident
    provoked = Incident(
        case_number="OSAF-2025-0099",
        location_description="Another beach",
        country="Bahamas",
        classification="provoked",
    )
    db.add(provoked)
    await db.commit()

    response = await client.get("/api/v1/incidents?classification=provoked")
    data = response.json()
    assert data["meta"]["total"] == 1
    assert data["data"][0]["classification"] == "provoked"


@pytest.mark.asyncio
async def test_list_incidents_filter_country(
    client: AsyncClient, sample_incident: Incident
):
    response = await client.get("/api/v1/incidents?country=United States")
    data = response.json()
    assert data["meta"]["total"] == 1

    response = await client.get("/api/v1/incidents?country=Japan")
    data = response.json()
    assert data["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_list_incidents_filter_fatal(client: AsyncClient, db):
    nonfatal = Incident(
        case_number="OSAF-2025-0050",
        location_description="Beach A",
        country="USA",
        classification="unprovoked",
        fatal=False,
    )
    fatal = Incident(
        case_number="OSAF-2025-0051",
        location_description="Beach B",
        country="Australia",
        classification="unprovoked",
        fatal=True,
    )
    db.add_all([nonfatal, fatal])
    await db.commit()

    response = await client.get("/api/v1/incidents?fatal=true")
    data = response.json()
    assert data["meta"]["total"] == 1
    assert data["data"][0]["fatal"] is True


@pytest.mark.asyncio
async def test_list_incidents_filter_date_range(
    client: AsyncClient, sample_incident: Incident
):
    response = await client.get(
        "/api/v1/incidents?date_from=2025-01-01&date_to=2025-12-31"
    )
    data = response.json()
    assert data["meta"]["total"] == 1

    response = await client.get(
        "/api/v1/incidents?date_from=2026-01-01&date_to=2026-12-31"
    )
    data = response.json()
    assert data["meta"]["total"] == 0


@pytest.mark.asyncio
async def test_list_incidents_sort_order(client: AsyncClient, db):
    from datetime import date

    i1 = Incident(
        case_number="OSAF-2025-0060",
        location_description="First",
        country="A-Country",
        classification="unprovoked",
        incident_date=date(2025, 1, 1),
    )
    i2 = Incident(
        case_number="OSAF-2025-0061",
        location_description="Second",
        country="B-Country",
        classification="unprovoked",
        incident_date=date(2025, 6, 1),
    )
    db.add_all([i1, i2])
    await db.commit()

    # Default: desc by date
    response = await client.get("/api/v1/incidents?sort=incident_date&order=desc")
    data = response.json()
    assert data["data"][0]["incident_date"] == "2025-06-01"

    # Ascending
    response = await client.get("/api/v1/incidents?sort=incident_date&order=asc")
    data = response.json()
    assert data["data"][0]["incident_date"] == "2025-01-01"


@pytest.mark.asyncio
async def test_update_incident(client: AsyncClient, sample_incident: Incident):
    response = await client.put(
        f"/api/v1/incidents/{sample_incident.id}",
        json={
            "victim_injury_severity": "severe",
            "description": "Updated description after more details emerged.",
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["victim_injury_severity"] == "severe"
    assert "Updated description" in data["description"]
    # Unchanged fields remain
    assert data["country"] == "United States"


@pytest.mark.asyncio
async def test_update_incident_not_found(client: AsyncClient):
    import uuid

    response = await client.put(
        f"/api/v1/incidents/{uuid.uuid4()}",
        json={"country": "Nowhere"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_incident(client: AsyncClient, sample_incident: Incident):
    response = await client.delete(f"/api/v1/incidents/{sample_incident.id}")
    assert response.status_code == 204

    # Verify it's gone
    response = await client.get(f"/api/v1/incidents/{sample_incident.id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_incident_not_found(client: AsyncClient):
    import uuid

    response = await client.delete(f"/api/v1/incidents/{uuid.uuid4()}")
    assert response.status_code == 404
