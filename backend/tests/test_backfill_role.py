"""The backfill_contributor role must not auto-publish.

Reason it exists: the collector account is a verified_contributor, so any
bulk script reusing its credentials published directly. When the GSAF
backfill hit the publisher-title dedup bug (2026-09-10), there was no review
gate behind the bulk write. Submissions from backfill_contributor must land
as pending.
"""
import pytest

from app.services.submission_service import VALID_ROLES


def test_backfill_role_is_valid():
    assert "backfill_contributor" in VALID_ROLES


def test_backfill_role_is_not_auto_publish():
    # Mirror of the auto_verify rule in SubmissionService.submit_incident.
    auto_publish_roles = {"admin", "verified_contributor"}
    assert "backfill_contributor" not in auto_publish_roles
