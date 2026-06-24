"""Unit tests for async auth_service functions — get_current_user, require_authenticated, require_role."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services.auth_service import (
    create_access_token,
    get_current_user,
    require_authenticated,
    require_role,
)


def _mock_request(token: str | None, cookie: bool = False) -> MagicMock:
    request = MagicMock()
    if cookie and token:
        request.cookies = {"access_token": token}
        request.headers.get.return_value = ""
    elif token:
        request.cookies = {}
        request.headers.get.return_value = f"Bearer {token}"
    else:
        request.cookies = {}
        request.headers.get.return_value = ""
    return request


class TestGetCurrentUser:
    async def test_returns_none_when_no_token(self):
        request = _mock_request(None)
        db = AsyncMock()
        result = await get_current_user(request, db)
        assert result is None

    async def test_returns_none_for_invalid_jwt(self):
        request = _mock_request("not.a.valid.jwt")
        db = AsyncMock()
        result = await get_current_user(request, db)
        assert result is None

    async def test_returns_none_when_user_not_in_db(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "public")
        request = _mock_request(token)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_current_user(request, db)
        assert result is None

    async def test_returns_none_for_inactive_user(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "public")
        request = _mock_request(token)

        user = MagicMock()
        user.is_active = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_current_user(request, db)
        assert result is None

    async def test_returns_user_for_valid_active_token(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "admin")
        request = _mock_request(token)

        user = MagicMock()
        user.is_active = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_current_user(request, db)
        assert result is user

    async def test_reads_token_from_cookie(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "public")
        request = _mock_request(token, cookie=True)

        user = MagicMock()
        user.is_active = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db = AsyncMock()
        db.execute = AsyncMock(return_value=mock_result)

        result = await get_current_user(request, db)
        assert result is user


class TestRequireAuthenticated:
    async def test_raises_401_when_user_is_none(self):
        with pytest.raises(HTTPException) as exc:
            await require_authenticated(None)
        assert exc.value.status_code == 401
        assert "Not authenticated" in exc.value.detail

    async def test_returns_user_when_authenticated(self):
        user = MagicMock()
        result = await require_authenticated(user)
        assert result is user


class TestRequireRoleInner:
    async def test_raises_403_for_insufficient_role(self):
        user = MagicMock()
        user.role = "public"
        check_fn = require_role("admin", "verified_contributor")
        with pytest.raises(HTTPException) as exc:
            await check_fn(user)
        assert exc.value.status_code == 403
        assert "Insufficient permissions" in exc.value.detail

    async def test_allows_correct_role(self):
        user = MagicMock()
        user.role = "admin"
        check_fn = require_role("admin", "verified_contributor")
        result = await check_fn(user)
        assert result is user

    async def test_allows_any_of_multiple_roles(self):
        user = MagicMock()
        user.role = "verified_contributor"
        check_fn = require_role("admin", "verified_contributor")
        result = await check_fn(user)
        assert result is user
