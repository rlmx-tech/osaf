from geoalchemy2.elements import WKTElement

# Decimal places published for each location_precision value.
#   3 dp ~= 110 m, 2 dp ~= 1.1 km at the equator.
# An incident marked approximate or region was marked that way on purpose —
# often to avoid pinpointing a residence or a minor — so it must not be
# published at the same granularity as an exact one.
_EXACT_DECIMALS = 3
COARSE_DECIMALS = 2


def point_from_coords(longitude: float, latitude: float) -> WKTElement:
    """Create a PostGIS POINT from longitude and latitude (WGS84)."""
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)


def public_decimals(location_precision: str | None) -> int:
    """Decimal places a coordinate may be published at.

    Shared by every public read path — incident list/detail, map GeoJSON, and
    clusters — so that one of them cannot quietly publish finer coordinates
    than the others. Anything that is not explicitly "exact", including None,
    is treated as coarse.
    """
    return _EXACT_DECIMALS if location_precision == "exact" else COARSE_DECIMALS


def round_coord(value: float | None, location_precision: str | None) -> float | None:
    """Round one coordinate to the precision its incident permits."""
    if value is None:
        return None
    return round(value, public_decimals(location_precision))
