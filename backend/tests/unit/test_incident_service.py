"""Unit tests for app/services/incident_service.py — no database required."""

import uuid
from datetime import date, time
from unittest.mock import MagicMock

import pytest

from app.services.incident_service import (
    ALLOWED_SORT_FIELDS,
    _incident_to_public_response,
    _incident_to_response,
)


class TestAllowedSortFields:
    def test_contains_incident_date(self):
        assert "incident_date" in ALLOWED_SORT_FIELDS

    def test_contains_case_number(self):
        assert "case_number" in ALLOWED_SORT_FIELDS

    def test_contains_country(self):
        assert "country" in ALLOWED_SORT_FIELDS

    def test_contains_classification(self):
        assert "classification" in ALLOWED_SORT_FIELDS

    def test_contains_fatal(self):
        assert "fatal" in ALLOWED_SORT_FIELDS

    def test_contains_submitted_at(self):
        assert "submitted_at" in ALLOWED_SORT_FIELDS

    def test_contains_updated_at(self):
        assert "updated_at" in ALLOWED_SORT_FIELDS

    def test_does_not_contain_description(self):
        # Free-text fields not allowed for sort (SQL injection risk)
        assert "description" not in ALLOWED_SORT_FIELDS

    def test_is_a_set(self):
        assert isinstance(ALLOWED_SORT_FIELDS, (set, frozenset))


class TestIncidentToResponse:
    def _make_incident(self, **overrides) -> MagicMock:
        incident = MagicMock()
        incident.id = uuid.uuid4()
        incident.case_number = "OSAF-2025-0001"
        incident.incident_date = date(2025, 1, 15)
        incident.incident_time = time(10, 30)
        incident.date_precision = "exact"
        incident.location_description = "New Smyrna Beach, Florida"
        incident.country = "United States"
        incident.state_province = "Florida"
        incident.county_region = "Volusia County"
        incident.body_of_water = "Atlantic Ocean"
        incident.location_precision = "exact"
        incident.classification = "unprovoked"
        incident.classification_subtype = "hit_and_run"
        incident.provocation_subtype = None
        incident.report_source = None
        incident.report_platform = None
        incident.shark_species_confirmed = None
        incident.shark_species_suspected = "Carcharhinus limbatus"
        incident.shark_size_estimate = None
        incident.species_identification_method = "witness"
        incident.victim_activity = "surfing"
        incident.victim_injury_severity = "minor"
        incident.victim_injury_description = "Lacerations to right foot"
        incident.victim_age = 25
        incident.victim_sex = "male"
        incident.victim_name = None
        incident.fatal = False
        incident.description = "Surfer bitten on foot."
        incident.verification_status = "verified"
        incident.submitted_at = None
        incident.updated_at = None
        incident.coordinates = None
        incident.sources = []
        for k, v in overrides.items():
            setattr(incident, k, v)
        return incident

    def test_returns_dict(self):
        incident = self._make_incident()
        result = _incident_to_response(incident)
        assert isinstance(result, dict)

    def test_case_number_in_result(self):
        incident = self._make_incident()
        result = _incident_to_response(incident)
        assert result["case_number"] == "OSAF-2025-0001"

    def test_coordinates_none_when_no_geometry(self):
        incident = self._make_incident(coordinates=None)
        result = _incident_to_response(incident)
        assert result["longitude"] is None
        assert result["latitude"] is None

    def test_country_preserved(self):
        incident = self._make_incident(country="Australia")
        result = _incident_to_response(incident)
        assert result["country"] == "Australia"

    def test_classification_preserved(self):
        incident = self._make_incident(classification="provoked")
        result = _incident_to_response(incident)
        assert result["classification"] == "provoked"

    def test_fatal_preserved(self):
        incident = self._make_incident(fatal=True)
        result = _incident_to_response(incident)
        assert result["fatal"] is True

    def test_sources_preserved(self):
        source = MagicMock()
        incident = self._make_incident(sources=[source])
        result = _incident_to_response(incident)
        assert result["sources"] == [source]

    def test_id_preserved(self):
        incident_id = uuid.uuid4()
        incident = self._make_incident(id=incident_id)
        result = _incident_to_response(incident)
        assert result["id"] == incident_id

    def test_all_expected_keys_present(self):
        incident = self._make_incident()
        result = _incident_to_response(incident)
        expected_keys = {
            "id", "case_number", "incident_date", "incident_time", "date_precision",
            "location_description", "country", "state_province", "county_region",
            "body_of_water", "longitude", "latitude", "location_precision",
            "classification", "classification_subtype", "provocation_subtype",
            "shark_species_confirmed", "shark_species_suspected", "shark_size_estimate",
            "species_identification_method", "victim_activity", "victim_injury_severity",
            "victim_injury_description", "victim_age", "victim_sex", "victim_name",
            "fatal", "description", "verification_status", "submitted_at", "updated_at",
            "sources",
        }
        for key in expected_keys:
            assert key in result, f"Missing key: {key}"


class TestIncidentToPublicResponse:
    def test_sensitive_fields_are_not_published(self):
        incident = TestIncidentToResponse()._make_incident(
            victim_name="Private Person",
            victim_age=12,
            victim_injury_description="Private medical detail",
            description="Narrative containing personal details",
        )
        data = _incident_to_response(incident)
        result = _incident_to_public_response(data).model_dump()

        for field in {
            "victim_name",
            "victim_age",
            "victim_injury_description",
            "description",
            "incident_time",
            "submitted_at",
            "updated_at",
        }:
            assert field not in result

    def test_coordinates_are_rounded(self):
        incident = TestIncidentToResponse()._make_incident()
        data = _incident_to_response(incident)
        data["longitude"] = -80.927456
        data["latitude"] = 29.026789

        result = _incident_to_public_response(data)

        assert result.longitude == -80.927
        assert result.latitude == 29.027
