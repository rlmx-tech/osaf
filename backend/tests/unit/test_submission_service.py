"""Unit tests for app/services/submission_service.py — mocked DB."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services.submission_service import VALID_ROLES, SubmissionService


def _scalar_result(value) -> MagicMock:
    m = MagicMock()
    m.scalar_one.return_value = value
    m.scalar_one_or_none.return_value = value
    return m


def _scalars_result(items) -> MagicMock:
    m = MagicMock()
    inner = MagicMock()
    inner.unique.return_value.all.return_value = items
    m.scalars.return_value = inner
    return m


class TestValidRoles:
    def test_contains_public(self):
        assert "public" in VALID_ROLES

    def test_contains_verified_contributor(self):
        assert "verified_contributor" in VALID_ROLES

    def test_contains_admin(self):
        assert "admin" in VALID_ROLES

    def test_is_frozenset(self):
        assert isinstance(VALID_ROLES, frozenset)


class TestUpdateUserRole:
    async def test_raises_404_when_user_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_result(None))
        service = SubmissionService(db)
        admin = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await service.update_user_role(uuid.uuid4(), "admin", admin)
        assert exc.value.status_code == 404

    async def test_raises_400_for_invalid_role(self):
        db = AsyncMock()
        user = MagicMock()
        db.execute = AsyncMock(return_value=_scalar_result(user))
        service = SubmissionService(db)
        admin = MagicMock()
        with pytest.raises(HTTPException) as exc:
            await service.update_user_role(uuid.uuid4(), "superuser", admin)
        assert exc.value.status_code == 400
        assert "superuser" not in VALID_ROLES

    async def test_updates_role_successfully(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id
        user.username = "testuser"
        user.role = "public"
        db.execute = AsyncMock(return_value=_scalar_result(user))
        db.commit = AsyncMock()
        service = SubmissionService(db)
        admin = MagicMock()
        result = await service.update_user_role(user_id, "verified_contributor", admin)
        assert user.role == "verified_contributor"
        assert db.commit.called
        assert result["new_role"] == "verified_contributor"
        assert result["old_role"] == "public"

    async def test_returns_id_and_username(self):
        db = AsyncMock()
        user_id = uuid.uuid4()
        user = MagicMock()
        user.id = user_id
        user.username = "johndoe"
        user.role = "public"
        db.execute = AsyncMock(return_value=_scalar_result(user))
        db.commit = AsyncMock()
        service = SubmissionService(db)
        result = await service.update_user_role(user_id, "admin", MagicMock())
        assert result["id"] == user_id
        assert result["username"] == "johndoe"


class TestVerifySubmission:
    async def test_raises_404_when_incident_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_result(None))
        service = SubmissionService(db)
        with pytest.raises(HTTPException) as exc:
            await service.verify_submission(uuid.uuid4(), MagicMock())
        assert exc.value.status_code == 404

    async def test_raises_400_when_already_verified(self):
        db = AsyncMock()
        incident = MagicMock()
        incident.verification_status = "verified"
        db.execute = AsyncMock(return_value=_scalar_result(incident))
        service = SubmissionService(db)
        with pytest.raises(HTTPException) as exc:
            await service.verify_submission(uuid.uuid4(), MagicMock())
        assert exc.value.status_code == 400
        assert "Already verified" in exc.value.detail


class TestRejectSubmission:
    async def test_raises_404_when_incident_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_result(None))
        service = SubmissionService(db)
        with pytest.raises(HTTPException) as exc:
            await service.reject_submission(uuid.uuid4(), MagicMock())
        assert exc.value.status_code == 404


class TestListAuditLog:
    async def test_returns_dict_with_data_and_meta(self):
        db = AsyncMock()

        count_result = _scalar_result(0)
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []

        db.execute = AsyncMock(side_effect=[count_result, rows_result])
        service = SubmissionService(db)
        result = await service.list_audit_log()
        assert "data" in result
        assert "meta" in result
        assert result["data"] == []
        assert result["meta"]["total"] == 0

    async def test_pagination_meta(self):
        db = AsyncMock()
        count_result = _scalar_result(50)
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_result, rows_result])

        service = SubmissionService(db)
        result = await service.list_audit_log(page=2, per_page=25)
        assert result["meta"]["total"] == 50
        assert result["meta"]["page"] == 2
        assert result["meta"]["per_page"] == 25
        assert result["meta"]["pages"] == 2

    async def test_log_entries_serialized(self):
        db = AsyncMock()
        log = MagicMock()
        log.id = uuid.uuid4()
        log.incident_id = uuid.uuid4()
        log.action = "verified"
        log.changed_by = uuid.uuid4()
        log.changed_at = None
        log.changes = None
        log.notes = "Looks good"

        count_result = _scalar_result(1)
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = [log]
        db.execute = AsyncMock(side_effect=[count_result, rows_result])

        service = SubmissionService(db)
        result = await service.list_audit_log()
        assert len(result["data"]) == 1
        assert result["data"][0]["action"] == "verified"
        assert result["data"][0]["notes"] == "Looks good"


class TestListPending:
    async def test_returns_paginated_response(self):
        db = AsyncMock()
        count_result = _scalar_result(0)
        rows_result = _scalars_result([])
        db.execute = AsyncMock(side_effect=[count_result, rows_result])

        service = SubmissionService(db)
        result = await service.list_pending()
        assert result.meta.total == 0
        assert result.data == []

    async def test_pagination_meta_pages(self):
        db = AsyncMock()
        count_result = _scalar_result(100)
        rows_result = _scalars_result([])
        db.execute = AsyncMock(side_effect=[count_result, rows_result])

        service = SubmissionService(db)
        result = await service.list_pending(page=1, per_page=25)
        assert result.meta.total == 100
        assert result.meta.pages == 4
