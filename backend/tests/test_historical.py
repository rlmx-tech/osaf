"""The historical flag: what earns it, and what it hides.

An incident is historical when OSAF first recorded it more than a year after
it happened. Until 2026-09-23 the flag meant "has a GSAF source", which hid 54
of 2026's incidents because the GSAF delta backfill had cited them, and the
public list, map and stats defaulted to leaving historical records out. The
site showed 251 of 6,619 incidents. Now everything is shown by default and
exclusion is opt-in.
"""

from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Incident
from app.models.audit import IncidentAuditLog
from app.schemas.incident import IncidentCreate, IncidentUpdate
from app.services.incident_service import IncidentService
from app.services.submission_service import SubmissionService
from app.utils.geo import point_from_coords
from app.utils.historical import recorded_late
from scripts.retag_historical import run

RECORDED = datetime(2026, 9, 18, 19, 0, tzinfo=UTC)


def _incident(case: str, incident_date: date | None, *, is_historical: bool = False) -> Incident:
    return Incident(
        case_number=case,
        incident_date=incident_date,
        location_description="Beach",
        country="Australia",
        classification="unprovoked",
        coordinates=point_from_coords(115.75, -31.83),
        verification_status="verified",
        submitted_at=RECORDED,
        is_historical=is_historical,
    )


def _create(incident_date: date | None) -> IncidentCreate:
    return IncidentCreate(
        incident_date=incident_date,
        location_description="Sorrento Beach",
        country="Australia",
        classification="unprovoked",
    )


class TestTheRule:
    def test_a_year_late_is_still_current(self):
        assert recorded_late(date(2025, 9, 18), RECORDED) is False

    def test_over_a_year_late_is_historical(self):
        assert recorded_late(date(2025, 9, 17), RECORDED) is True

    def test_a_recent_event_found_late_by_a_backfill_is_current(self):
        # The case the GSAF-source rule got wrong: a 2026 bite GSAF also cites.
        assert recorded_late(date(2026, 2, 3), RECORDED) is False

    def test_an_undated_incident_is_not_historical(self):
        assert recorded_late(None, RECORDED) is False

    def test_the_recording_time_is_read_in_utc(self):
        # 00:30 on the 19th in Perth is still the 18th in UTC.
        from zoneinfo import ZoneInfo

        perth = datetime(2026, 9, 19, 0, 30, tzinfo=ZoneInfo("Australia/Perth"))
        assert recorded_late(date(2025, 9, 18), perth) is False


class TestTaggedWhenRecorded:
    @pytest.mark.asyncio
    async def test_a_submission_about_an_old_bite_is_historical(self, db, verified_user):
        response = await SubmissionService(db).submit_incident(_create(date(2004, 12, 17)), verified_user)
        incident = await db.get(Incident, response.id)
        assert incident.is_historical is True

    @pytest.mark.asyncio
    async def test_a_submission_about_a_recent_bite_is_not(self, db, verified_user):
        response = await SubmissionService(db).submit_incident(
            _create(datetime.now(UTC).date()), verified_user
        )
        incident = await db.get(Incident, response.id)
        assert incident.is_historical is False

    @pytest.mark.asyncio
    async def test_a_direct_create_is_tagged_too(self, db, admin_user):
        response = await IncidentService(db).create_incident(_create(date(1998, 1, 4)), admin_user)
        incident = await db.get(Incident, response.id)
        assert incident.is_historical is True

    @pytest.mark.asyncio
    async def test_correcting_the_date_retags_and_audits_it(self, db, admin_user):
        incident = _incident("OSAF-2026-9001", date(2026, 9, 1))
        db.add(incident)
        await db.commit()
        incident_id = incident.id

        await IncidentService(db).update_incident(
            incident_id, IncidentUpdate(incident_date=date(2010, 9, 1)), admin_user
        )

        incident = await db.get(Incident, incident_id)
        await db.refresh(incident)
        assert incident.is_historical is True
        entry = (await db.execute(
            select(IncidentAuditLog).where(IncidentAuditLog.incident_id == incident_id)
        )).scalar_one()
        assert entry.changes["is_historical"] == {"from": False, "to": True}


class TestPublicDefaults:
    @pytest.fixture
    async def mixed(self, db):
        db.add_all([
            _incident("OSAF-2026-9101", date(2026, 9, 10)),
            _incident("OSAF-1990-9102", date(1990, 5, 5), is_historical=True),
        ])
        await db.commit()

    @pytest.mark.asyncio
    async def test_the_list_shows_everything_by_default(self, client: AsyncClient, mixed):
        response = await client.get("/api/v1/incidents")
        assert response.json()["meta"]["total"] == 2

    @pytest.mark.asyncio
    @pytest.mark.parametrize(("mode", "cases"), [
        ("exclude", {"OSAF-2026-9101"}),
        ("only", {"OSAF-1990-9102"}),
        ("all", {"OSAF-2026-9101", "OSAF-1990-9102"}),
    ])
    async def test_the_list_filters_on_request(self, client: AsyncClient, mixed, mode, cases):
        response = await client.get(f"/api/v1/incidents?historical={mode}")
        assert {row["case_number"] for row in response.json()["data"]} == cases

    @pytest.mark.asyncio
    async def test_an_unknown_mode_is_refused(self, client: AsyncClient):
        response = await client.get("/api/v1/incidents?historical=sometimes")
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_the_map_shows_everything_by_default(self, client: AsyncClient, mixed):
        response = await client.get("/api/v1/incidents/map")
        assert len(response.json()["features"]) == 2

    @pytest.mark.asyncio
    async def test_clusters_take_the_filter(self, client: AsyncClient, mixed):
        everything = await client.get("/api/v1/incidents/map/clusters?zoom=3")
        current = await client.get("/api/v1/incidents/map/clusters?zoom=3&historical=exclude")
        assert everything.status_code == current.status_code == 200
        total = sum(c["count"] for c in everything.json()["data"])
        assert total == 2
        assert sum(c["count"] for c in current.json()["data"]) == 1

    @pytest.mark.asyncio
    async def test_stats_count_historical_records(self, client: AsyncClient, mixed):
        response = await client.get("/api/v1/stats/overview")
        assert response.json()["data"]["total_incidents"] == 2


class TestRetag:
    @pytest.fixture
    async def mistagged(self, db):
        # As the 2026-09-18 SQL left them: tagged by source, not by lag.
        db.add_all([
            _incident("OSAF-2026-9201", date(2026, 2, 3), is_historical=True),
            _incident("OSAF-2004-9202", date(2004, 12, 17), is_historical=False),
            _incident("OSAF-1990-9203", date(1990, 5, 5), is_historical=True),
            _incident("OSAF-2026-9204", date(2026, 9, 10), is_historical=False),
        ])
        await db.commit()

    @pytest.mark.asyncio
    async def test_dry_run_reports_but_changes_nothing(self, db, mistagged):
        report = await run(db, apply=False)

        assert sorted(r.case_number for r in report.retagged) == ["OSAF-2004-9202", "OSAF-2026-9201"]
        rows = (await db.execute(select(Incident.case_number, Incident.is_historical))).all()
        assert dict(rows)["OSAF-2026-9201"] is True

    @pytest.mark.asyncio
    async def test_apply_fixes_each_mismatch_and_audits_it(self, db, mistagged):
        await run(db, apply=True)

        rows = dict((await db.execute(select(Incident.case_number, Incident.is_historical))).all())
        assert rows == {
            "OSAF-2026-9201": False,
            "OSAF-2004-9202": True,
            "OSAF-1990-9203": True,
            "OSAF-2026-9204": False,
        }
        entries = (await db.execute(
            select(IncidentAuditLog).where(IncidentAuditLog.action == "retagged")
        )).scalars().all()
        assert {e.case_number: e.changes for e in entries} == {
            "OSAF-2026-9201": {"is_historical": {"from": True, "to": False}},
            "OSAF-2004-9202": {"is_historical": {"from": False, "to": True}},
        }

    @pytest.mark.asyncio
    async def test_a_second_run_finds_nothing(self, db, mistagged):
        await run(db, apply=True)
        assert (await run(db, apply=True)).retagged == []
