"""Tests for submission workflow (public submit, verified auto-publish, admin review)."""

import pytest
from httpx import AsyncClient

from app.models.user import User
from tests.conftest import SAMPLE_INCIDENT_PAYLOAD, auth_header


@pytest.mark.asyncio
async def test_submit_as_public_user(client: AsyncClient, test_user: User):
    """Public user submission goes to pending review."""
    headers = auth_header(test_user)
    response = await client.post(
        "/api/v1/submissions",
        json=SAMPLE_INCIDENT_PAYLOAD,
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["verification_status"] == "pending"
    assert data["case_number"].startswith("OSAF-")


@pytest.mark.asyncio
async def test_submit_as_verified_contributor(
    client: AsyncClient, verified_user: User
):
    """Verified contributor auto-publishes."""
    headers = auth_header(verified_user)
    response = await client.post(
        "/api/v1/submissions",
        json=SAMPLE_INCIDENT_PAYLOAD,
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_submit_as_admin(client: AsyncClient, admin_user: User):
    """Admin submissions auto-publish."""
    headers = auth_header(admin_user)
    response = await client.post(
        "/api/v1/submissions",
        json=SAMPLE_INCIDENT_PAYLOAD,
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["verification_status"] == "verified"


@pytest.mark.asyncio
async def test_submit_without_auth(client: AsyncClient):
    """Unauthenticated submission should fail."""
    response = await client.post(
        "/api/v1/submissions",
        json=SAMPLE_INCIDENT_PAYLOAD,
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_submit_with_coordinates(client: AsyncClient, test_user: User):
    """Submission with coordinates stores location."""
    headers = auth_header(test_user)
    payload = {
        **SAMPLE_INCIDENT_PAYLOAD,
        "coordinates": {"longitude": -80.927, "latitude": 29.026},
    }
    response = await client.post(
        "/api/v1/submissions",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["longitude"] is not None
    assert data["latitude"] is not None


@pytest.mark.asyncio
async def test_submit_with_sources(client: AsyncClient, test_user: User):
    """Submission includes sources."""
    headers = auth_header(test_user)
    payload = {
        **SAMPLE_INCIDENT_PAYLOAD,
        "sources": [
            {
                "source_type": "news_article",
                "source_title": "Source 1",
                "source_url": "https://example.com/article1",
                "source_publisher": "Test Publisher",
            },
            {
                "source_type": "government_report",
                "source_title": "Source 2",
                "source_publisher": "Government",
            },
        ],
    }
    response = await client.post(
        "/api/v1/submissions",
        json=payload,
        headers=headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert len(data["sources"]) == 2


@pytest.mark.asyncio
async def test_full_review_workflow(
    client: AsyncClient, test_user: User, admin_user: User
):
    """Full workflow: submit -> pending -> admin verify."""
    # Step 1: Public user submits
    user_headers = auth_header(test_user)
    submit_resp = await client.post(
        "/api/v1/submissions",
        json=SAMPLE_INCIDENT_PAYLOAD,
        headers=user_headers,
    )
    assert submit_resp.status_code == 201
    incident_id = submit_resp.json()["id"]
    assert submit_resp.json()["verification_status"] == "pending"

    # Step 2: Admin sees it in pending queue
    admin_headers = auth_header(admin_user)
    queue_resp = await client.get(
        "/api/v1/admin/submissions",
        headers=admin_headers,
    )
    assert queue_resp.status_code == 200
    assert queue_resp.json()["meta"]["total"] >= 1

    # Step 3: Admin verifies
    verify_resp = await client.put(
        f"/api/v1/admin/submissions/{incident_id}/verify",
        json={"notes": "Verified by admin after source check"},
        headers=admin_headers,
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["verification_status"] == "verified"

    # Step 4: No longer in pending queue
    queue_resp = await client.get(
        "/api/v1/admin/submissions",
        headers=admin_headers,
    )
    pending_ids = [i["id"] for i in queue_resp.json()["data"]]
    assert incident_id not in pending_ids


@pytest.mark.asyncio
async def test_reject_submission(
    client: AsyncClient, test_user: User, admin_user: User
):
    """Admin rejects a submission."""
    user_headers = auth_header(test_user)
    submit_resp = await client.post(
        "/api/v1/submissions",
        json=SAMPLE_INCIDENT_PAYLOAD,
        headers=user_headers,
    )
    incident_id = submit_resp.json()["id"]

    admin_headers = auth_header(admin_user)
    reject_resp = await client.put(
        f"/api/v1/admin/submissions/{incident_id}/reject",
        json={"notes": "Insufficient evidence"},
        headers=admin_headers,
    )
    assert reject_resp.status_code == 200
    assert reject_resp.json()["verification_status"] == "rejected"


@pytest.mark.asyncio
async def test_verify_already_verified(
    client: AsyncClient, admin_user: User
):
    """Cannot re-verify an already verified submission."""
    admin_headers = auth_header(admin_user)
    # Admin submits (auto-verified)
    submit_resp = await client.post(
        "/api/v1/submissions",
        json=SAMPLE_INCIDENT_PAYLOAD,
        headers=admin_headers,
    )
    incident_id = submit_resp.json()["id"]

    # Try to verify again
    verify_resp = await client.put(
        f"/api/v1/admin/submissions/{incident_id}/verify",
        headers=admin_headers,
    )
    assert verify_resp.status_code == 400
    assert "Already verified" in verify_resp.json()["detail"]
