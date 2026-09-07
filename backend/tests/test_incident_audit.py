"""Audit-trail coverage for direct incident writes.

The submission-review flows already log to incident_audit_log. The direct
routes — POST /incidents, PUT /incidents/{id} — are reachable by any admin or
verified_contributor and were writing no audit entry at all, so a compromised
or rogue elevated account could alter a public record and leave
/admin/audit-log showing nothing. On a project whose premise is public
auditability that is the trail that matters most.
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.audit import IncidentAuditLog
from app.models.incident import Incident
from app.models.user import User
from tests.conftest import auth_header

PAYLOAD = {
    "location_description": "Audit Beach",
    "country": "Australia",
    "classification": "unprovoked",
}


async def _entries_for(db, incident_id) -> list[IncidentAuditLog]:
    result = await db.execute(
        select(IncidentAuditLog)
        .where(IncidentAuditLog.incident_id == incident_id)
        .order_by(IncidentAuditLog.changed_at)
    )
    return list(result.scalars().all())


@pytest.mark.asyncio
async def test_direct_create_is_audited(client: AsyncClient, verified_user: User, db):
    response = await client.post(
        "/api/v1/incidents", json=PAYLOAD, headers=auth_header(verified_user)
    )
    assert response.status_code == 201
    incident_id = response.json()["id"]

    entries = await _entries_for(db, incident_id)
    assert len(entries) == 1
    assert entries[0].action == "created"
    assert entries[0].changed_by == verified_user.id


@pytest.mark.asyncio
async def test_update_is_audited_with_a_field_diff(
    client: AsyncClient, admin_user: User, sample_incident: Incident, db
):
    """The diff is the point: knowing a record changed is not knowing what changed."""
    response = await client.put(
        f"/api/v1/incidents/{sample_incident.id}",
        json={"country": "New Zealand", "fatal": True},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 200

    entries = await _entries_for(db, sample_incident.id)
    assert len(entries) == 1
    entry = entries[0]
    assert entry.action == "updated"
    assert entry.changed_by == admin_user.id

    assert entry.changes["country"] == {"from": "United States", "to": "New Zealand"}
    assert entry.changes["fatal"] == {"from": False, "to": True}


@pytest.mark.asyncio
async def test_update_records_only_fields_that_actually_changed(
    client: AsyncClient, admin_user: User, sample_incident: Incident, db
):
    """Resubmitting an unchanged value must not manufacture a diff entry."""
    response = await client.put(
        f"/api/v1/incidents/{sample_incident.id}",
        json={"country": sample_incident.country, "fatal": True},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 200

    entry = (await _entries_for(db, sample_incident.id))[0]
    assert "country" not in entry.changes
    assert entry.changes["fatal"] == {"from": False, "to": True}


@pytest.mark.asyncio
async def test_no_op_update_writes_no_audit_entry(
    client: AsyncClient, admin_user: User, sample_incident: Incident, db
):
    response = await client.put(
        f"/api/v1/incidents/{sample_incident.id}",
        json={"country": sample_incident.country},
        headers=auth_header(admin_user),
    )
    assert response.status_code == 200
    assert await _entries_for(db, sample_incident.id) == []
