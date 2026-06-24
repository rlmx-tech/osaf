"""Integration test: extract_incident snaps vague-location coordinates to coast."""

import asyncio
import json

from collector.models import RawItem, SourcePlatform


def _raw() -> RawItem:
    return RawItem(
        source_platform=SourcePlatform.NEWS_RSS,
        source_name="Test Feed",
        source_url="https://example.com/sa-shark",
        title="Shark incident in South Africa",
        content="A shark was involved in an incident in South Africa.",
    )


def test_vague_location_is_snapped_to_coast(monkeypatch):
    import collector.extractor as ex

    # Ollama returns a vague, country-only location.
    async def fake_ollama(prompt: str) -> str:
        return json.dumps({
            "is_relevant": True,
            "confidence": 0.6,
            "location_description": "South Africa",
            "country": "South Africa",
            "classification": "unprovoked",
            "fatal": False,
            "description": "A shark incident.",
        })

    # Geocoder returns the inland country centroid (the bug we're fixing).
    async def fake_geocode(**kwargs):
        return (-30.559, 22.938)

    monkeypatch.setattr(ex, "_call_ollama", fake_ollama)
    monkeypatch.setattr(ex, "geocode_incident", fake_geocode)

    incident = asyncio.run(ex.extract_incident(_raw()))

    assert incident is not None
    # The inland centroid must have been snapped to the South African coast.
    assert incident.latitude != -30.559
    assert -35.5 <= incident.latitude <= -25.0
    assert 15.0 <= incident.longitude <= 34.0


def test_specific_location_is_not_snapped(monkeypatch):
    import collector.extractor as ex

    async def fake_ollama(prompt: str) -> str:
        return json.dumps({
            "is_relevant": True,
            "confidence": 0.8,
            "location_description": "Jeffreys Bay",
            "country": "South Africa",
            "classification": "unprovoked",
            "fatal": False,
            "description": "A shark incident at a specific beach.",
        })

    # A specific, correct coastal coordinate — must be left untouched.
    async def fake_geocode(**kwargs):
        return (-34.049, 24.909)

    monkeypatch.setattr(ex, "_call_ollama", fake_ollama)
    monkeypatch.setattr(ex, "geocode_incident", fake_geocode)

    incident = asyncio.run(ex.extract_incident(_raw()))

    assert incident is not None
    assert incident.latitude == -34.049
    assert incident.longitude == 24.909
