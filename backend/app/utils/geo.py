from geoalchemy2.elements import WKTElement


def point_from_coords(longitude: float, latitude: float) -> WKTElement:
    """Create a PostGIS POINT from longitude and latitude (WGS84)."""
    return WKTElement(f"POINT({longitude} {latitude})", srid=4326)
