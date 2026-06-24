"""Extended tests for submission_service covering verify/reject bodies and audit log filter."""

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.services.submission_service import SubmissionService


def _scalar_result(value) -> MagicMock:
    m = MagicMock()
    m.scalar_one.return_value = value
    m.scalar_one_or_none.return_value = value
    return m


class TestListAuditLogFilter:
    async def test_with_incident_id_filter(self):
        """Covers the `if incident_id:` branch (line 221)."""
        db = AsyncMock()
        count_result = _scalar_result(0)
        rows_result = MagicMock()
        rows_result.scalars.return_value.all.return_value = []
        db.execute = AsyncMock(side_effect=[count_result, rows_result])

        service = SubmissionService(db)
        result = await service.list_audit_log(incident_id=uuid.uuid4())
        assert result["data"] == []
        assert result["meta"]["total"] == 0


class TestVerifySubmissionBody:
    async def test_sets_verified_status_and_commits(self):
        """Covers verify_submission body: status update, audit creation, commit."""
        db = AsyncMock()
        incident = MagicMock()
        incident.id = uuid.uuid4()
        incident.verification_status = "pending"
        db.execute = AsyncMock(return_value=_scalar_result(incident))
        db.add = MagicMock()
        db.commit = AsyncMock()

        service = SubmissionService(db)
        admin = MagicMock()
        admin.id = uuid.uuid4()

        # Patch _get_incident_response to skip the DB round-trip for the return value
        expected_response = MagicMock()
        service._get_incident_response = AsyncMock(return_value=expected_response)

        result = await service.verify_submission(incident.id, admin, notes="confirmed")

        assert incident.verification_status == "verified"
        assert incident.verified_by == admin.id
        assert db.add.called
        assert db.commit.called
        assert result is expected_response

    async def test_verify_sets_notes_on_audit(self):
        db = AsyncMock()
        incident = MagicMock()
        incident.id = uuid.uuid4()
        incident.verification_status = "needs_review"
        db.execute = AsyncMock(return_value=_scalar_result(incident))
        db.commit = AsyncMock()

        audit_records = []
        db.add = MagicMock(side_effect=audit_records.append)

        service = SubmissionService(db)
        admin = MagicMock()
        admin.id = uuid.uuid4()
        service._get_incident_response = AsyncMock(return_value=MagicMock())

        await service.verify_submission(incident.id, admin, notes="all sources verified")

        assert len(audit_records) == 1


class TestRejectSubmissionBody:
    async def test_sets_rejected_status_and_commits(self):
        db = AsyncMock()
        incident = MagicMock()
        incident.id = uuid.uuid4()
        incident.verification_status = "pending"
        db.execute = AsyncMock(return_value=_scalar_result(incident))
        db.add = MagicMock()
        db.commit = AsyncMock()

        service = SubmissionService(db)
        admin = MagicMock()
        admin.id = uuid.uuid4()
        service._get_incident_response = AsyncMock(return_value=MagicMock())

        await service.reject_submission(incident.id, admin, notes="insufficient sources")

        assert incident.verification_status == "rejected"
        assert incident.verified_by == admin.id
        assert db.commit.called
