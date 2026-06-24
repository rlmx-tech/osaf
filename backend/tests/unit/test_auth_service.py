"""Unit tests for app/services/auth_service.py — no database required."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException
from jose import jwt

from app.config import settings
from app.services.auth_service import (
    AuthService,
    _extract_token,
    create_access_token,
    hash_password,
    require_role,
    verify_password,
)


class TestHashPassword:
    def test_returns_string(self):
        result = hash_password("mysecretpassword")
        assert isinstance(result, str)

    def test_not_plaintext(self):
        result = hash_password("mysecretpassword")
        assert result != "mysecretpassword"

    def test_unique_each_call(self):
        h1 = hash_password("same_password")
        h2 = hash_password("same_password")
        # bcrypt generates unique salts
        assert h1 != h2

    def test_non_empty(self):
        result = hash_password("x")
        assert len(result) > 0


class TestVerifyPassword:
    def test_correct_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("correct_password", hashed) is True

    def test_wrong_password(self):
        hashed = hash_password("correct_password")
        assert verify_password("wrong_password", hashed) is False

    def test_empty_vs_nonempty(self):
        hashed = hash_password("nonempty")
        assert verify_password("", hashed) is False

    def test_case_sensitive(self):
        hashed = hash_password("Password")
        assert verify_password("password", hashed) is False


class TestCreateAccessToken:
    def test_returns_string(self):
        token = create_access_token(uuid.uuid4(), "public")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_user_id(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "public")
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["sub"] == str(user_id)

    def test_token_contains_role(self):
        user_id = uuid.uuid4()
        token = create_access_token(user_id, "admin")
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert payload["role"] == "admin"

    def test_token_contains_expiry(self):
        token = create_access_token(uuid.uuid4(), "public")
        payload = jwt.decode(
            token, settings.secret_key, algorithms=[settings.jwt_algorithm]
        )
        assert "exp" in payload

    def test_different_tokens_for_different_users(self):
        t1 = create_access_token(uuid.uuid4(), "public")
        t2 = create_access_token(uuid.uuid4(), "public")
        assert t1 != t2


class TestExtractToken:
    def test_extracts_from_cookie(self):
        request = MagicMock()
        request.cookies = {"access_token": "cookie_token"}
        result = _extract_token(request)
        assert result == "cookie_token"

    def test_cookie_takes_priority_over_header(self):
        request = MagicMock()
        request.cookies = {"access_token": "cookie_token"}
        request.headers.get.return_value = "Bearer header_token"
        result = _extract_token(request)
        assert result == "cookie_token"

    def test_extracts_from_bearer_header(self):
        request = MagicMock()
        request.cookies = {}
        request.headers.get.return_value = "Bearer header_token"
        result = _extract_token(request)
        assert result == "header_token"

    def test_returns_none_when_no_token(self):
        request = MagicMock()
        request.cookies = {}
        request.headers.get.return_value = ""
        result = _extract_token(request)
        assert result is None

    def test_returns_none_for_malformed_header(self):
        request = MagicMock()
        request.cookies = {}
        request.headers.get.return_value = "Token abc123"
        result = _extract_token(request)
        assert result is None

    def test_strips_bearer_prefix(self):
        request = MagicMock()
        request.cookies = {}
        request.headers.get.return_value = "Bearer mytoken123"
        result = _extract_token(request)
        assert result == "mytoken123"
        assert not result.startswith("Bearer ")


class TestRequireRole:
    def test_returns_callable(self):
        dep = require_role("admin")
        assert callable(dep)

    def test_multiple_roles_returns_callable(self):
        dep = require_role("admin", "verified_contributor")
        assert callable(dep)


class TestAuthServiceRegister:
    async def test_raises_409_when_user_exists(self):
        db = AsyncMock()
        existing_user = MagicMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = existing_user
        db.execute = AsyncMock(return_value=mock_result)

        service = AuthService(db)
        with pytest.raises(HTTPException) as exc:
            await service.register("taken@example.com", "takenuser", "pass123")
        assert exc.value.status_code == 409

    async def test_creates_user_when_unique(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        new_user = MagicMock()
        new_user.id = uuid.uuid4()
        new_user.email = "new@example.com"
        new_user.role = "public"
        db.refresh = AsyncMock(return_value=None)

        # Capture the user added to session
        added = []
        db.add = MagicMock(side_effect=added.append)
        db.commit = AsyncMock()

        service = AuthService(db)
        # refresh is called on the user object — mock it to set attrs
        async def _mock_refresh(user):
            user.id = uuid.uuid4()
            user.role = "public"

        db.refresh = _mock_refresh

        user = await service.register("new@example.com", "newuser", "pass123")
        assert db.add.called
        assert db.commit.called


class TestAuthServiceAuthenticate:
    async def test_raises_401_when_user_not_found(self):
        db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        db.execute = AsyncMock(return_value=mock_result)

        service = AuthService(db)
        with pytest.raises(HTTPException) as exc:
            await service.authenticate("nobody", "pass")
        assert exc.value.status_code == 401

    async def test_raises_401_for_wrong_password(self):
        db = AsyncMock()
        user = MagicMock()
        user.password_hash = hash_password("correct_pass")
        user.is_active = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=mock_result)

        service = AuthService(db)
        with pytest.raises(HTTPException) as exc:
            await service.authenticate("theuser", "wrong_pass")
        assert exc.value.status_code == 401

    async def test_raises_403_for_inactive_user(self):
        db = AsyncMock()
        user = MagicMock()
        user.password_hash = hash_password("correct_pass")
        user.is_active = False
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=mock_result)

        service = AuthService(db)
        with pytest.raises(HTTPException) as exc:
            await service.authenticate("theuser", "correct_pass")
        assert exc.value.status_code == 403

    async def test_returns_user_on_valid_credentials(self):
        db = AsyncMock()
        user = MagicMock()
        user.password_hash = hash_password("correct_pass")
        user.is_active = True
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = user
        db.execute = AsyncMock(return_value=mock_result)
        db.commit = AsyncMock()

        service = AuthService(db)
        result = await service.authenticate("theuser", "correct_pass")
        assert result is user
        assert db.commit.called
