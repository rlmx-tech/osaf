"""Tests for IncidentService.update_incident success path."""

import uuid
from datetime import date, datetime, time
from unittest.mock import AsyncMock, MagicMock

from app.schemas.incident import IncidentUpdate
from app.services.incident_service import IncidentService


def _make_valid_incident(**overrides) -> MagicMock:
    inc = MagicMock()
    inc.id = uuid.uuid4()
    inc.case_number = "OSAF-2025-0001"
    inc.incident_date = date(2025, 1, 15)
    inc.incident_time = time(10, 30)
    inc.date_precision = "exact"
    inc.location_description = "Somewhere"
    inc.country = "United States"
    inc.state_province = "Florida"
    inc.county_region = None
    inc.body_of_water = None
    inc.location_precision = "exact"
    inc.classification = "unprovoked"
    inc.classification_subtype = None
    inc.provocation_subtype = None
    inc.report_source = None
    inc.report_platform = None
    inc.shark_species_confirmed = None
    inc.shark_species_suspected = None
    inc.shark_size_estimate = None
    inc.species_identification_method = None
    inc.victim_activity = None
    inc.victim_injury_severity = None
    inc.victim_injury_description = None
    inc.victim_age = None
    inc.victim_sex = None
    inc.victim_name = None
    inc.fatal = False
    inc.description = None
    inc.verification_status = "verified"
    inc.submitted_at = datetime(2025, 1, 15, 10, 30)
    inc.updated_at = datetime(2025, 1, 15, 10, 30)
    inc.coordinates = None
    inc.sources = []
    for k, v in overrides.items():
        setattr(inc, k, v)
    return inc


def _scalar_result(value) -> MagicMock:
    m = MagicMock()
    m.scalar_one_or_none.return_value = value
    return m


class TestUpdateIncidentSuccess:
    async def test_commits_and_returns_response(self):
        """Covers update_incident body: model_dump, setattr loop, commit, get_incident."""
        incident = _make_valid_incident()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(incident),   # update_incident SELECT
            _scalar_result(incident),   # get_incident SELECT (for response)
        ])
        db.commit = AsyncMock()

        service = IncidentService(db)
        result = await service.update_incident(
            incident.id, IncidentUpdate(country="Australia")
        )
        assert db.commit.called
        assert result.case_number == "OSAF-2025-0001"

    async def test_sets_field_on_incident(self):
        """Verifies setattr is called for updated fields."""
        incident = _make_valid_incident()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(incident),
            _scalar_result(incident),
        ])
        db.commit = AsyncMock()

        service = IncidentService(db)
        await service.update_incident(
            incident.id, IncidentUpdate(fatal=True)
        )
        # setattr was called on the mock incident
        assert incident.fatal is True

    async def test_empty_update_still_commits(self):
        incident = _make_valid_incident()
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(incident),
            _scalar_result(incident),
        ])
        db.commit = AsyncMock()

        service = IncidentService(db)
        await service.update_incident(incident.id, IncidentUpdate())
        assert db.commit.called

    async def test_explicit_null_clears_coordinates(self):
        incident = _make_valid_incident(coordinates=object())
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(incident),
            _scalar_result(incident),
        ])

        service = IncidentService(db)
        await service.update_incident(
            incident.id,
            IncidentUpdate(coordinates=None, location_precision="unknown"),
        )

        assert incident.coordinates is None
        assert incident.location_precision == "unknown"
