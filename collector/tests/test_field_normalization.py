"""Regression tests for collector field normalization helpers.

Covers the value-validation and country-canonicalization logic used during
incident extraction. The provoked/unprovoked case guards against a real bug
where substring fuzzy-matching reclassified provoked incidents as unprovoked.
"""

import pytest

from collector.config import VALID_ACTIVITIES, VALID_CLASSIFICATIONS, VALID_SEVERITIES
from collector.extractor import (
    _normalize_bool,
    _normalize_country,
    _validate_field,
    apply_corrections,
)
from collector.models import ExtractedIncident, VerificationResult


@pytest.mark.parametrize(
    "value,options,expected",
    [
        # Exact matches
        ("provoked", VALID_CLASSIFICATIONS, "provoked"),
        ("unprovoked", VALID_CLASSIFICATIONS, "unprovoked"),
        # Regression: "provoked" must NOT collapse into "unprovoked"
        ("Provoked", VALID_CLASSIFICATIONS, "provoked"),
        # Option-as-substring-of-phrase (longest match wins)
        ("Unprovoked attack", VALID_CLASSIFICATIONS, "unprovoked"),
        ("severe injuries", VALID_SEVERITIES, "severe"),
        ("no injury", VALID_SEVERITIES, "no_injury"),
        ("boat bite", VALID_CLASSIFICATIONS, "boat_bite"),
        ("spearfishing", VALID_ACTIVITIES, "spearfishing"),
        # No match / empty
        ("gibberish", VALID_CLASSIFICATIONS, None),
        ("", VALID_CLASSIFICATIONS, None),
        (None, VALID_CLASSIFICATIONS, None),
    ],
)
def test_validate_field(value, options, expected):
    assert _validate_field(value, options) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        ("USA", "United States"),
        ("usa", "United States"),
        ("U.S.", "United States"),
        ("united states of america", "United States"),
        ("UK", "United Kingdom"),
        ("RSA", "South Africa"),
        ("NZ", "New Zealand"),
        # Canonical names pass through unchanged
        ("Australia", "Australia"),
        ("South Africa", "South Africa"),
        # Unknown names are preserved (stripped), not dropped
        ("  Fiji ", "Fiji"),
        (None, None),
    ],
)
def test_normalize_country(value, expected):
    assert _normalize_country(value) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (True, True),
        (False, False),
        ("true", True),
        ("FALSE", False),
        (None, False),
        ("unknown", False),
    ],
)
def test_normalize_bool(value, expected):
    assert _normalize_bool(value) is expected


def test_null_fatal_correction_preserves_existing_boolean():
    incident = ExtractedIncident(
        location_description="Jones Beach",
        country="United States",
        fatal=False,
        source_url="https://example.test/report",
        source_title="Report",
    )
    verification = VerificationResult(corrections={"fatal": None})

    corrected = apply_corrections(incident, verification)

    assert corrected.fatal is False
