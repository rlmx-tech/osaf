"""Coastline snapping for vague-location shark incidents.

Incidents whose location is only known to a country/region geocode to the
country centroid, which lands inland. Since shark incidents occur in/near
water, we relocate such points to the nearest coastline — but only when the
point is genuinely on land (offshore points are left alone) and clearly inland
(already-coastal points are left alone).

Detection of "vague" is the caller's first gate (is_vague_location); the
on-land + distance checks live in snap_if_inland. Specific-location incidents
are never passed in, so genuine inland river/lake incidents are never moved.

The land geometry is Natural Earth 1:50m land polygons (public domain),
vendored at collector/data/ne_50m_land.geojson. The polygon boundary is the
coastline, so one dataset gives us both the on-land test and the snap target.
"""

import json
import logging
from pathlib import Path

from shapely.geometry import Point, shape
from shapely.ops import nearest_points
from shapely.strtree import STRtree

from collector.geocoder import haversine_km

logger = logging.getLogger(__name__)

_DATA_PATH = Path(__file__).parent / "data" / "ne_50m_land.geojson"

# Default distance (km) a point must be from the coast before we snap it.
DEFAULT_THRESHOLD_KM = 25.0


def is_vague_location(
    location_description: str | None,
    country: str | None,
    state_province: str | None,
) -> bool:
    """True when the location is too vague to trust as a real place.

    Vague means: no location text, or the location is just the country or the
    state/province name. These are the only incidents eligible for snapping.
    """
    loc = (location_description or "").strip().lower()
    if not loc:
        return True
    return loc in {
        (country or "").strip().lower(),
        (state_province or "").strip().lower(),
    } - {""}


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
        if not idx.contains(lat, lon):
            return None
        coast = idx.nearest_coast(lat, lon)
        if coast is None:
            return None
        new_lat, new_lon = coast
        moved_km = haversine_km(lat, lon, new_lat, new_lon)
        if moved_km < threshold_km:
            return None
        return (new_lat, new_lon, moved_km)
    except Exception:
        logger.exception("coastline: snap failed for (%.4f, %.4f)", lat, lon)
        return None
