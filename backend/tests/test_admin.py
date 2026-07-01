"""Tests for admin endpoints (user management, audit log, role-based access)."""

import pytest
from httpx import AsyncClient

from app.models.incident import Incident
from app.models.user import User
from tests.conftest import SAMPLE_INCIDENT_PAYLOAD, auth_header


@pytest.mark.asyncio
async def test_admin_list_users(client: AsyncClient, admin_user: User, test_user: User):
    headers = auth_header(admin_user)
    response = await client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 2
    usernames = {u["username"] for u in data["data"]}
    assert "admin" in usernames
    assert "testuser" in usernames


@pytest.mark.asyncio
async def test_admin_list_users_forbidden_for_public(
    client: AsyncClient, test_user: User
):
    """Non-admin cannot access admin endpoints."""
    headers = auth_header(test_user)
    response = await client.get("/api/v1/admin/users", headers=headers)
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_list_users_unauthenticated(client: AsyncClient):
    response = await client.get("/api/v1/admin/users")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_update_user_role(
    client: AsyncClient, admin_user: User, test_user: User
):
    headers = auth_header(admin_user)
    response = await client.put(
        f"/api/v1/admin/users/{test_user.id}/role",
        json={"role": "verified_contributor"},
        headers=headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["old_role"] == "public"
    assert data["new_role"] == "verified_contributor"


@pytest.mark.asyncio
async def test_update_user_role_not_found(client: AsyncClient, admin_user: User):
    import uuid

    headers = auth_header(admin_user)
    response = await client.put(
        f"/api/v1/admin/users/{uuid.uuid4()}/role",
        json={"role": "admin"},
        headers=headers,
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_user_role_forbidden(
    client: AsyncClient, test_user: User, admin_user: User
):
    """Non-admin cannot change roles."""
    headers = auth_header(test_user)
    response = await client.put(
        f"/api/v1/admin/users/{admin_user.id}/role",
        json={"role": "public"},
        headers=headers,
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_submissions_queue(
    client: AsyncClient, admin_user: User, test_user: User
):
    """Admin sees pending submissions in queue."""
    user_headers = auth_header(test_user)
    admin_headers = auth_header(admin_user)

    # Submit 2 DISTINCT incidents (different dates) as public user — distinct dates
    # keep them separate events so incident dedup doesn't merge them.
    for i in range(2):
        await client.post(
            "/api/v1/submissions",
            json={**SAMPLE_INCIDENT_PAYLOAD, "incident_date": f"2025-03-{15 + i}"},
            headers=user_headers,
        )

    response = await client.get("/api/v1/admin/submissions", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] == 2


@pytest.mark.asyncio
async def test_admin_submissions_pagination(
    client: AsyncClient, admin_user: User, test_user: User
):
    user_headers = auth_header(test_user)
    admin_headers = auth_header(admin_user)

    # Distinct dates so incident dedup keeps these as 3 separate submissions.
    for i in range(3):
        await client.post(
            "/api/v1/submissions",
            json={**SAMPLE_INCIDENT_PAYLOAD, "incident_date": f"2025-03-{15 + i}"},
            headers=user_headers,
        )

    response = await client.get(
        "/api/v1/admin/submissions?page=1&per_page=2",
        headers=admin_headers,
    )
    data = response.json()
    assert data["meta"]["total"] == 3
    assert len(data["data"]) == 2


@pytest.mark.asyncio
async def test_audit_log(client: AsyncClient, admin_user: User, test_user: User):
    """Verify audit logs are created for submissions."""
    user_headers = auth_header(test_user)
    admin_headers = auth_header(admin_user)

    # Submit incident
    submit_resp = await client.post(
        "/api/v1/submissions",
        json=SAMPLE_INCIDENT_PAYLOAD,
        headers=user_headers,
    )
    incident_id = submit_resp.json()["id"]

    # Verify it
    await client.put(
        f"/api/v1/admin/submissions/{incident_id}/verify",
        json={"notes": "Looks good"},
        headers=admin_headers,
    )

    # Check audit log
    response = await client.get("/api/v1/admin/audit-log", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] >= 2  # created + verified

    actions = [log["action"] for log in data["data"]]
    assert "created" in actions
    assert "verified" in actions


@pytest.mark.asyncio
async def test_audit_log_filter_by_incident(
    client: AsyncClient, admin_user: User, test_user: User
):
    """Filter audit log by incident_id."""
    user_headers = auth_header(test_user)
    admin_headers = auth_header(admin_user)

    submit_resp = await client.post(
        "/api/v1/submissions",
        json=SAMPLE_INCIDENT_PAYLOAD,
        headers=user_headers,
    )
    incident_id = submit_resp.json()["id"]

    response = await client.get(
        f"/api/v1/admin/audit-log?incident_id={incident_id}",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["meta"]["total"] >= 1
    for log in data["data"]:
        assert log["incident_id"] == incident_id


@pytest.mark.asyncio
async def test_audit_log_forbidden_for_non_admin(
    client: AsyncClient, test_user: User
):
    headers = auth_header(test_user)
    response = await client.get("/api/v1/admin/audit-log", headers=headers)
    assert response.status_code == 403
