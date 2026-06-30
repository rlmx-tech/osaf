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
