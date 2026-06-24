"""Tests for coastline snapping of vague-location incidents.

LandIndex is constructed from explicit polygons so the snapping geometry can be
tested deterministically; one smoke test exercises the real vendored dataset.
"""

import pytest
from shapely.geometry import Polygon

from collector.coastline import LandIndex, is_vague_location, snap_if_inland


# A synthetic continent: a 10x10 degree square of land spanning lon 0..10,
# lat 0..10. Its boundary is the "coastline"; everything inside is land.
@pytest.fixture
def square_land() -> LandIndex:
    return LandIndex([Polygon([(0, 0), (10, 0), (10, 10), (0, 10)])])


# ---------------------------------------------------------------------------
# is_vague_location
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "loc,country,state,expected",
    [
        ("South Africa", "South Africa", None, True),   # location == country
        ("Florida", "United States", "Florida", True),  # location == state
        ("", "United States", "Florida", True),         # empty location
        (None, "Australia", None, True),                # missing location
        (" south africa ", "South Africa", None, True), # case / whitespace
        ("New Smyrna Beach", "United States", "Florida", False),  # specific
        ("Coral Sea", "Australia", None, False),        # named water, not vague
    ],
)
def test_is_vague_location(loc, country, state, expected):
    assert is_vague_location(loc, country, state) is expected


# ---------------------------------------------------------------------------
# snap_if_inland (synthetic, deterministic)
# ---------------------------------------------------------------------------

def test_inland_point_snaps_to_nearest_coast(square_land):
    # (lat=5, lon=8) is inside the square; nearest boundary is the lon=10 edge.
    result = snap_if_inland(5.0, 8.0, threshold_km=25.0, index=square_land)
    assert result is not None
    new_lat, new_lon, moved_km = result
    assert new_lon == pytest.approx(10.0, abs=0.01)   # snapped to east coast
    assert new_lat == pytest.approx(5.0, abs=0.01)    # same latitude
    assert moved_km > 25.0


def test_offshore_point_is_not_snapped(square_land):
    # (lat=5, lon=15) is outside the land polygon — must never be moved.
    assert snap_if_inland(5.0, 15.0, threshold_km=25.0, index=square_land) is None


def test_point_already_near_coast_is_not_snapped(square_land):
    # (lat=5, lon=9.9) is on land but ~11km from the lon=10 edge (< threshold).
    assert snap_if_inland(5.0, 9.9, threshold_km=25.0, index=square_land) is None


def test_on_land_just_over_threshold_snaps(square_land):
    # (lat=5, lon=9.6) is on land ~44km from the coast (> 25km threshold).
    result = snap_if_inland(5.0, 9.6, threshold_km=25.0, index=square_land)
    assert result is not None
    new_lat, new_lon, _ = result
    assert new_lon == pytest.approx(10.0, abs=0.01)
    assert new_lat == pytest.approx(5.0, abs=0.01)


def test_missing_index_is_noop():
    # An empty index (e.g. dataset failed to load) must be a safe no-op.
    assert snap_if_inland(5.0, 5.0, index=LandIndex([])) is None


# ---------------------------------------------------------------------------
# snap_if_inland (real vendored dataset)
# ---------------------------------------------------------------------------

def test_south_africa_centroid_snaps_to_coast():
    # The real bug: "South Africa" geocodes to the interior centroid.
    result = snap_if_inland(-30.559, 22.938)  # uses the default real dataset
    assert result is not None
    new_lat, new_lon, moved_km = result
    # Snapped point should land within South Africa's coastal bounding box...
    assert -35.5 <= new_lat <= -25.0
    assert 15.0 <= new_lon <= 34.0
    # ...and should have moved meaningfully inland->coast.
    assert moved_km > 25.0
