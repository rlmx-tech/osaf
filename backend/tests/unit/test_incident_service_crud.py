"""Unit tests for IncidentService CRUD — mocked DB, no PostgreSQL required."""

import uuid
from datetime import date, datetime, time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.services.incident_service import IncidentService


def _make_valid_incident(**overrides) -> MagicMock:
    """Create a MagicMock with all fields required by IncidentResponse."""
    inc = MagicMock()
    inc.id = uuid.uuid4()
    inc.case_number = "OSAF-2025-0001"
    inc.incident_date = date(2025, 1, 15)
    inc.incident_time = time(10, 30)
    inc.date_precision = "exact"
    inc.location_description = "New Smyrna Beach, Florida"
    inc.country = "United States"
    inc.state_province = "Florida"
    inc.county_region = "Volusia County"
    inc.body_of_water = "Atlantic Ocean"
    inc.location_precision = "exact"
    inc.classification = "unprovoked"
    inc.classification_subtype = "hit_and_run"
    inc.provocation_subtype = None
    inc.report_source = None
    inc.report_platform = None
    inc.shark_species_confirmed = None
    inc.shark_species_suspected = "Carcharhinus limbatus"
    inc.shark_size_estimate = None
    inc.species_identification_method = "witness"
    inc.victim_activity = "surfing"
    inc.victim_injury_severity = "minor"
    inc.victim_injury_description = "Lacerations to right foot"
    inc.victim_age = 25
    inc.victim_sex = "male"
    inc.victim_name = None
    inc.fatal = False
    inc.description = "Surfer bitten on foot."
    inc.verification_status = "verified"
    inc.submitted_at = datetime(2025, 1, 15, 10, 30)
    inc.updated_at = datetime(2025, 1, 15, 10, 30)
    inc.coordinates = None
    inc.sources = []
    for k, v in overrides.items():
        setattr(inc, k, v)
    return inc


def _scalar_none_result() -> MagicMock:
    m = MagicMock()
    m.scalar_one_or_none.return_value = None
    return m


def _scalar_result(value) -> MagicMock:
    m = MagicMock()
    m.scalar_one.return_value = value
    m.scalar_one_or_none.return_value = value
    return m


def _scalars_unique_all(items) -> MagicMock:
    m = MagicMock()
    m.scalars.return_value.unique.return_value.all.return_value = items
    return m


class TestGetIncident:
    async def test_raises_404_when_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_none_result())
        service = IncidentService(db)
        with pytest.raises(HTTPException) as exc:
            await service.get_incident(uuid.uuid4())
        assert exc.value.status_code == 404
        assert "Incident not found" in exc.value.detail

    async def test_returns_incident_response_no_coords(self):
        incident = _make_valid_incident(coordinates=None)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_result(incident))
        service = IncidentService(db)
        result = await service.get_incident(incident.id)
        assert result.case_number == "OSAF-2025-0001"
        assert result.longitude is None
        assert result.latitude is None

    async def test_db_called_once_without_coords(self):
        incident = _make_valid_incident(coordinates=None)
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_result(incident))
        service = IncidentService(db)
        await service.get_incident(incident.id)
        assert db.execute.call_count == 1


class TestListIncidents:
    async def test_empty_db_returns_empty_list(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),        # count
            _scalars_unique_all([]),  # incidents
        ])
        service = IncidentService(db)
        result = await service.list_incidents()
        assert result.meta.total == 0
        assert result.data == []

    async def test_pagination_meta_calculated(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(100),      # count
            _scalars_unique_all([]),  # incidents (empty page)
        ])
        service = IncidentService(db)
        result = await service.list_incidents(page=2, per_page=25)
        assert result.meta.total == 100
        assert result.meta.page == 2
        assert result.meta.per_page == 25
        assert result.meta.pages == 4

    async def test_invalid_sort_falls_back_to_incident_date(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        # Should not raise — invalid sort is silently replaced
        result = await service.list_incidents(sort="description")
        assert result.meta.total == 0

    async def test_with_classification_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(classification="unprovoked,provoked")
        assert result.data == []

    async def test_with_country_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(country="Australia")
        assert result.data == []

    async def test_with_fatal_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(fatal=True)
        assert result.data == []

    async def test_with_date_range_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(date_from="2020-01-01", date_to="2025-12-31")
        assert result.data == []

    async def test_with_activity_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(activity="surfing,swimming")
        assert result.data == []

    async def test_with_severity_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(severity="fatal,severe")
        assert result.data == []

    async def test_with_verification_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(verification="verified")
        assert result.data == []

    async def test_with_search_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(search="new smyrna")
        assert result.data == []

    async def test_with_species_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(species="Carcharodon carcharias")
        assert result.data == []

    async def test_with_report_source_filter(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(report_source="news")
        assert result.data == []

    async def test_with_incident_in_results_no_coords(self):
        incident = _make_valid_incident(coordinates=None)
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(1),
            _scalars_unique_all([incident]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents()
        assert result.meta.total == 1
        assert len(result.data) == 1
        assert result.data[0].case_number == "OSAF-2025-0001"

    async def test_asc_order(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalars_unique_all([]),
        ])
        service = IncidentService(db)
        result = await service.list_incidents(order="asc")
        assert result.data == []


class TestDeleteIncident:
    async def test_raises_404_when_not_found(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_none_result())
        service = IncidentService(db)
        with pytest.raises(HTTPException) as exc:
            await service.delete_incident(uuid.uuid4())
        assert exc.value.status_code == 404

    async def test_deletes_and_commits(self):
        incident = _make_valid_incident()
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_result(incident))
        db.delete = AsyncMock()
        db.commit = AsyncMock()
        service = IncidentService(db)
        await service.delete_incident(incident.id)
        db.delete.assert_called_once_with(incident)
        db.commit.assert_called_once()


class TestUpdateIncident:
    async def test_raises_404_when_not_found(self):
        from app.schemas.incident import IncidentUpdate
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_scalar_none_result())
        service = IncidentService(db)
        with pytest.raises(HTTPException) as exc:
            await service.update_incident(uuid.uuid4(), IncidentUpdate())
        assert exc.value.status_code == 404
