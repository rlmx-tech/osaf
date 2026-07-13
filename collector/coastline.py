"""Coastal validation utilities for marine incident locations.

Broad regional descriptions are marked as vague so callers can leave them
unmapped instead of inventing a precise point. For specific place names,
land-distance checks can reject a bad same-name geocode or move a nearby
on-land result to the coast. Offshore and already-coastal points are unchanged.

The land geometry is Natural Earth 1:50m land polygons (public domain),
vendored at collector/data/ne_50m_land.geojson. The polygon boundary is the
coastline, so one dataset gives us both the on-land test and the snap target.
"""

import json
import logging
from pathlib import Path
import re

from shapely.geometry import Point, shape
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from collector.geocoder import haversine_km

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).parent / "data" / "ne_50m_land.geojson"

# Default distance (km) a point must be from the coast before we snap it.
DEFAULT_THRESHOLD_KM = 25.0

_PLACE_ALIASES = {
    "calif": "california",
    "norcal": "northern california",
    "socal": "southern california",
    "qld": "queensland",
    "nsw": "new south wales",
    "south australian": "south australia",
    "western australian": "western australia",
}
_VAGUE_MODIFIERS = {
    "a", "at", "east", "eastern", "far", "in", "near", "north", "northern",
    "of", "off", "on", "south", "southern", "the", "west", "western",
}
_GENERIC_COASTAL_PLACES = {
    "beach", "coast", "coastline", "island", "ocean", "pier", "shore", "waters",
}


def _normalize_place(value: str | None) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", (value or "").lower()).strip()
    for alias, canonical in _PLACE_ALIASES.items():
        normalized = re.sub(rf"\b{re.escape(alias)}\b", canonical, normalized)
    return " ".join(normalized.split())


def is_vague_location(
    location_description: str | None,
    country: str | None,
    state_province: str | None,
) -> bool:
    """Return whether the description is too broad for a trustworthy marker.

    This includes missing text, bare country/state names, and generic regional
    phrases such as ``California beach`` or ``island, Queensland``.
    """
    loc = _normalize_place(location_description)
    if not loc:
        return True
    regions = {
        _normalize_place(country),
        _normalize_place(state_province),
    } - {""}
    if loc in regions:
        return True

    tokens = set(loc.split()) - _VAGUE_MODIFIERS - _GENERIC_COASTAL_PLACES
    if not tokens:
        return True
    return any(tokens == set(region.split()) for region in regions)


class LandIndex:
    """Spatial index over land polygons for on-land tests and coast snapping."""

    def __init__(self, polygons: list) -> None:
        self._polygons = polygons
        self._boundaries = [p.boundary for p in polygons]
        # STRtree construction rejects an empty list; keep trees None instead.
        self._poly_tree = STRtree(polygons) if polygons else None
        self._boundary_tree = STRtree(self._boundaries) if self._boundaries else None

    def contains(self, lat: float, lon: float) -> bool:
        """True if (lat, lon) falls on land."""
        if self._poly_tree is None:
            return False
        pt = Point(lon, lat)
        for idx in self._poly_tree.query(pt):
            if self._polygons[idx].contains(pt):
                return True
        return False

    def nearest_coast(self, lat: float, lon: float) -> tuple[float, float] | None:
        """Return the nearest coastline point (lat, lon), or None if empty."""
        if self._boundary_tree is None:
            return None
        pt = Point(lon, lat)
        idx = int(self._boundary_tree.nearest(pt))
        snapped = nearest_points(pt, self._boundaries[idx])[1]
        return (snapped.y, snapped.x)


_default_index: LandIndex | None = None


def _load_default_index() -> LandIndex:
    """Load and cache the vendored land dataset. Failure -> empty (no-op) index."""
    try:
        data = json.loads(_DATA_PATH.read_text())
        polygons = []
        for feature in data["features"]:
            geom = shape(feature["geometry"])
            if geom.geom_type == "Polygon":
                polygons.append(geom)
            elif geom.geom_type == "MultiPolygon":
                polygons.extend(geom.geoms)
        logger.info("coastline: loaded %d land polygons", len(polygons))
        return LandIndex(polygons)
    except Exception:
        logger.exception("coastline: failed to load land dataset %s", _DATA_PATH)
        return LandIndex([])


def _get_default_index() -> LandIndex:
    global _default_index
    if _default_index is None:
        _default_index = _load_default_index()
    return _default_index


def snap_if_inland(
    lat: float,
    lon: float,
    *,
    threshold_km: float = DEFAULT_THRESHOLD_KM,
    index: LandIndex | None = None,
) -> tuple[float, float, float] | None:
    """Snap an on-land, clearly-inland point to the nearest coast.

    Returns (new_lat, new_lon, moved_km) when the point is on land and at least
    threshold_km from the coast; otherwise None (caller keeps original coords).
    Offshore points and already-coastal points return None, as does an empty
    index (e.g. a dataset that failed to load).
    """
    idx = index if index is not None else _get_default_index()

    try:
        measured = _measure_inland(lat, lon, idx)
        if measured is None:
            return None
        new_lat, new_lon, moved_km = measured
        if moved_km < threshold_km:
            return None
        return (new_lat, new_lon, moved_km)
    except Exception:
        logger.exception("coastline: snap failed for (%.4f, %.4f)", lat, lon)
        return None


def _measure_inland(
    lat: float,
    lon: float,
    index: LandIndex,
) -> tuple[float, float, float] | None:
    if not index.contains(lat, lon):
        return None
    coast = index.nearest_coast(lat, lon)
    if coast is None:
        return None
    new_lat, new_lon = coast
    return (new_lat, new_lon, haversine_km(lat, lon, new_lat, new_lon))


def inland_distance_km(
    lat: float,
    lon: float,
    *,
    index: LandIndex | None = None,
) -> float:
    """Distance to land boundary, or zero when already offshore/on the boundary."""
    idx = index if index is not None else _get_default_index()
    try:
        measured = _measure_inland(lat, lon, idx)
        return measured[2] if measured else 0.0
    except Exception:
        logger.exception("coastline: distance check failed for (%.4f, %.4f)", lat, lon)
        return 0.0
