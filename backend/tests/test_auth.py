"""Tests for authentication endpoints (register, login, JWT)."""

import pytest
from httpx import AsyncClient

from app.models.user import User
from tests.conftest import auth_header


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "new@example.com",
            "username": "newuser",
            "password": "securepassword123",
            "display_name": "New User",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "new@example.com"
    assert data["username"] == "newuser"
    assert data["display_name"] == "New User"
    assert data["role"] == "public"
    assert data["is_active"] is True
    assert "id" in data


@pytest.mark.asyncio
async def test_register_duplicate_email(client: AsyncClient, test_user: User):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "testuser@example.com",
            "username": "different",
            "password": "password123",
        },
    )
    assert response.status_code == 409
    assert "already registered" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient, test_user: User):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "different@example.com",
            "username": "testuser",
            "password": "password123",
        },
    )
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_register_invalid_email(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": "not-an-email",
            "username": "baduser",
            "password": "password123",
        },
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, test_user: User):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "password123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["user"]["username"] == "testuser"
    assert data["user"]["role"] == "public"


@pytest.mark.asyncio
async def test_login_with_email(client: AsyncClient, test_user: User):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser@example.com", "password": "password123"},
    )
    assert response.status_code == 200
    assert "access_token" in response.json()


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, test_user: User):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "testuser", "password": "wrongpassword"},
    )
    assert response.status_code == 401
    assert "Invalid credentials" in response.json()["detail"]


@pytest.mark.asyncio
async def test_login_nonexistent_user(client: AsyncClient):
    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "nobody", "password": "password123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_inactive_user(client: AsyncClient, db):
    from app.services.auth_service import hash_password

    user = User(
        email="inactive@example.com",
        username="inactive",
        password_hash=hash_password("password123"),
        role="public",
        is_active=False,
    )
    db.add(user)
    await db.commit()

    response = await client.post(
        "/api/v1/auth/login",
        data={"username": "inactive", "password": "password123"},
    )
    assert response.status_code == 403
    assert "deactivated" in response.json()["detail"]


@pytest.mark.asyncio
async def test_authenticated_endpoint_with_valid_token(
    client: AsyncClient, test_user: User
):
    """Verify a valid JWT token grants access to authenticated endpoints."""
    headers = auth_header(test_user)
    response = await client.post(
        "/api/v1/submissions",
        json={
            "location_description": "Test Beach",
            "country": "Test Country",
            "classification": "unprovoked",
            "sources": [],
        },
        headers=headers,
    )
    assert response.status_code == 201


@pytest.mark.asyncio
async def test_authenticated_endpoint_without_token(client: AsyncClient):
    """Endpoints requiring auth return 401 without a token."""
    response = await client.post(
        "/api/v1/submissions",
        json={
            "location_description": "Test Beach",
            "country": "Test Country",
            "classification": "unprovoked",
            "sources": [],
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_endpoint_with_invalid_token(client: AsyncClient):
    """Endpoints requiring auth return 401 with an invalid token."""
    response = await client.post(
        "/api/v1/submissions",
        json={
            "location_description": "Test Beach",
            "country": "Test Country",
            "classification": "unprovoked",
            "sources": [],
        },
        headers={"Authorization": "Bearer invalid-token-here"},
    )
    assert response.status_code == 401
