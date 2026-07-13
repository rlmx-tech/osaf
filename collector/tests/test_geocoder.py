import pytest

import collector.coastline as coastline
import collector.geocoder as geocoder
import collector.backfill_gsaf as gsaf
from collector.geocoder import GeoResult


def _result(lat: float, lon: float, name: str = "result") -> GeoResult:
    return GeoResult(
        latitude=lat,
        longitude=lon,
        display_name=name,
        importance=0.5,
        osm_type="node",
    )


def test_state_aliases_use_canonical_bounds():
    assert geocoder._get_viewbox("NSW") == geocoder._get_viewbox("New South Wales")
    assert geocoder._in_state_bounds(-31.3, 153.0, "NSW")
    assert not geocoder._in_state_bounds(-31.3, 140.0, "NSW")


def test_vague_state_query_does_not_duplicate_state_name():
    queries = geocoder._build_search_queries("Maine", "United States", "Maine")

    assert queries[0] == "Maine, United States"
    assert "Maine, Maine, United States" not in queries


@pytest.mark.parametrize(
    "location,state,expected",
    [
        ("near Ossabaw Island, Georgia", "Georgia", "Ossabaw Island, Georgia, United States"),
        (
            "Point Plomber North of Port Macquarie",
            "NSW",
            "Point Plomer North of Port Macquarie, New South Wales, Australia",
        ),
        (
            "Cooee Beach west of Burnie",
            "Tasmania",
            "Cooee Beach, Tasmania, Australia",
        ),
    ],
)
def test_query_variants_recover_landmarks_from_qualified_locations(
    location, state, expected
):
    queries = geocoder._build_search_queries(location, "Australia" if state != "Georgia" else "United States", state)

    assert expected in queries


def test_known_ambiguous_place_uses_coastal_alias():
    queries = geocoder._build_search_queries(
        "Newport", "United States", "California"
    )

    assert queries[0] == "Newport Beach, California, United States"


@pytest.mark.asyncio
async def test_geocoder_selects_coastal_namesake_not_first_inland_result(monkeypatch):
    candidates = [
        _result(42.9048, -76.3941, "Jones Beach, Onondaga County"),
        _result(43.3745, -78.1481, "Jones Beach, Orleans County"),
        _result(40.5945, -73.5029, "Jones Beach, Nassau County"),
    ]

    async def fake_search(*args, **kwargs):
        return candidates

    distances = {42.9048: 270.0, 43.3745: 329.0, 40.5945: 0.0}
    monkeypatch.setattr(geocoder, "_search_nominatim", fake_search)
    monkeypatch.setattr(
        coastline,
        "inland_distance_km",
        lambda lat, lon: distances[lat],
    )

    result = await geocoder.geocode_incident(
        "Jones Beach, Long Island, New York",
        "United States",
        "New York",
        "Atlantic Ocean",
    )

    assert result == (40.5945, -73.5029)


@pytest.mark.asyncio
async def test_geocoder_rejects_specific_marine_results_far_inland(monkeypatch):
    async def fake_search(*args, **kwargs):
        return [_result(33.8989, -84.5895, "Atlanta")]

    monkeypatch.setattr(geocoder, "_search_nominatim", fake_search)
    monkeypatch.setattr(coastline, "inland_distance_km", lambda lat, lon: 413.0)

    result = await geocoder.geocode_incident(
        "Mystery Beach", "United States", "Georgia", "Atlantic Ocean"
    )

    assert result is None


@pytest.mark.asyncio
async def test_geocoder_does_not_guess_for_vague_regional_location(monkeypatch):
    async def fake_search(*args, **kwargs):
        return [_result(-27.47, 153.02, "coastal city centre")]

    monkeypatch.setattr(geocoder, "_search_nominatim", fake_search)
    result = await geocoder.geocode_incident(
        "Qld island", "Australia", "Queensland", "Pacific Ocean"
    )

    assert result is None


@pytest.mark.asyncio
async def test_geocoder_preserves_explicit_inland_water_incident(monkeypatch):
    async def fake_search(*args, **kwargs):
        return [_result(-21.1, 149.1, "Pioneer River")]

    monkeypatch.setattr(geocoder, "_search_nominatim", fake_search)
    monkeypatch.setattr(coastline, "inland_distance_km", lambda lat, lon: 80.0)

    result = await geocoder.geocode_incident(
        "Pioneer River", "Australia", "Queensland", "Pioneer River"
    )

    assert result == (-21.1, 149.1)


@pytest.mark.asyncio
async def test_gsaf_backfill_uses_shared_validated_geocoder(monkeypatch):
    calls = []

    async def fake_geocode(**kwargs):
        calls.append(kwargs)
        return (1.0, 2.0)

    gsaf._geocode_cache.clear()
    monkeypatch.setattr(gsaf, "geocode_incident", fake_geocode)

    first = await gsaf.geocode("Named Beach", "Australia", "NSW")
    second = await gsaf.geocode("Named Beach", "Australia", "NSW")

    assert first == second == (1.0, 2.0)
    assert calls == [{
        "location_description": "Named Beach",
        "country": "Australia",
        "state_province": "NSW",
    }]
