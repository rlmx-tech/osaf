"""Tests for map GeoJSON and cluster endpoints."""

from datetime import date

import pytest
from httpx import AsyncClient

from app.models.incident import Incident
from app.utils.geo import point_from_coords


@pytest.mark.asyncio
async def test_geojson_empty(client: AsyncClient):
    response = await client.get("/api/v1/incidents/map")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert data["features"] == []


@pytest.mark.asyncio
async def test_geojson_with_data(client: AsyncClient, sample_incident: Incident):
    response = await client.get("/api/v1/incidents/map")
    assert response.status_code == 200
    data = response.json()
    assert data["type"] == "FeatureCollection"
    assert len(data["features"]) == 1

    feature = data["features"][0]
    assert feature["type"] == "Feature"
    assert feature["geometry"]["type"] == "Point"
    props = feature["properties"]
    assert props["case_number"] == "OSAF-2025-0001"
    assert props["classification"] == "unprovoked"
    assert props["country"] == "United States"
    assert props["fatal"] is False


@pytest.mark.asyncio
async def test_geojson_only_verified(client: AsyncClient, db):
    """Map should only show verified incidents."""
    verified = Incident(
        case_number="OSAF-2025-0200",
        location_description="Verified beach",
        country="Australia",
        classification="unprovoked",
        verification_status="verified",
        coordinates=point_from_coords(151.0, -33.0),
    )
    pending = Incident(
        case_number="OSAF-2025-0201",
        location_description="Pending beach",
        country="Australia",
        classification="unprovoked",
        verification_status="pending",
        coordinates=point_from_coords(152.0, -34.0),
    )
    db.add_all([verified, pending])
    await db.commit()

    response = await client.get("/api/v1/incidents/map")
    data = response.json()
    assert len(data["features"]) == 1
    assert data["features"][0]["properties"]["case_number"] == "OSAF-2025-0200"


@pytest.mark.asyncio
async def test_geojson_only_with_coordinates(client: AsyncClient, db):
    """Map should only show incidents that have coordinates."""
    with_coords = Incident(
        case_number="OSAF-2025-0210",
        location_description="Known location",
        country="USA",
        classification="unprovoked",
        verification_status="verified",
        coordinates=point_from_coords(-80.0, 29.0),
    )
    without_coords = Incident(
        case_number="OSAF-2025-0211",
        location_description="Unknown location",
        country="USA",
        classification="unprovoked",
        verification_status="verified",
    )
    db.add_all([with_coords, without_coords])
    await db.commit()

    response = await client.get("/api/v1/incidents/map")
    data = response.json()
    assert len(data["features"]) == 1


@pytest.mark.asyncio
async def test_geojson_bbox_filter(client: AsyncClient, db):
    """Filter by bounding box."""
    florida = Incident(
        case_number="OSAF-2025-0220",
        location_description="Florida",
        country="USA",
        classification="unprovoked",
        verification_status="verified",
        coordinates=point_from_coords(-80.927, 29.026),
    )
    australia = Incident(
        case_number="OSAF-2025-0221",
        location_description="Australia",
        country="Australia",
        classification="unprovoked",
        verification_status="verified",
        coordinates=point_from_coords(151.274, -33.891),
    )
    db.add_all([florida, australia])
    await db.commit()

    # BBox covering Florida only
    response = await client.get(
        "/api/v1/incidents/map?bbox=-82,28,-79,30"
    )
    data = response.json()
    assert len(data["features"]) == 1
    assert data["features"][0]["properties"]["country"] == "USA"


@pytest.mark.asyncio
async def test_geojson_classification_filter(client: AsyncClient, db):
    unprovoked = Incident(
        case_number="OSAF-2025-0230",
        location_description="Beach A",
        country="USA",
        classification="unprovoked",
        verification_status="verified",
        coordinates=point_from_coords(-80.0, 29.0),
    )
    provoked = Incident(
        case_number="OSAF-2025-0231",
        location_description="Beach B",
        country="USA",
        classification="provoked",
        verification_status="verified",
        coordinates=point_from_coords(-81.0, 29.0),
    )
    db.add_all([unprovoked, provoked])
    await db.commit()

    response = await client.get(
        "/api/v1/incidents/map?classification=provoked"
    )
    data = response.json()
    assert len(data["features"]) == 1
    assert data["features"][0]["properties"]["classification"] == "provoked"


@pytest.mark.asyncio
async def test_clusters_empty(client: AsyncClient):
    response = await client.get("/api/v1/incidents/map/clusters")
    assert response.status_code == 200
    data = response.json()
    assert data["data"] == []


@pytest.mark.asyncio
async def test_clusters_with_data(client: AsyncClient, db):
    """Clusters should group nearby incidents."""
    for i in range(3):
        db.add(Incident(
            case_number=f"OSAF-2025-024{i}",
            location_description=f"Florida spot {i}",
            country="USA",
            classification="unprovoked",
            verification_status="verified",
            coordinates=point_from_coords(-80.927 + i * 0.001, 29.026 + i * 0.001),
        ))
    await db.commit()

    response = await client.get("/api/v1/incidents/map/clusters?zoom=3")
    assert response.status_code == 200
    data = response.json()["data"]
    # At low zoom, these close points should cluster together
    assert len(data) >= 1
    total_count = sum(c["count"] for c in data)
    assert total_count == 3
