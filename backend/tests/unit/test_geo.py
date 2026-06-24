"""Unit tests for app/utils/geo.py — no database required."""

import pytest
from geoalchemy2.elements import WKTElement

from app.utils.geo import point_from_coords


class TestPointFromCoords:
    def test_returns_wkt_element(self):
        result = point_from_coords(-80.927, 29.026)
        assert isinstance(result, WKTElement)

    def test_srid_is_4326(self):
        result = point_from_coords(-80.927, 29.026)
        assert result.srid == 4326

    def test_wkt_contains_point_keyword(self):
        result = point_from_coords(-80.927, 29.026)
        assert "POINT" in result.data

    def test_wkt_contains_longitude(self):
        result = point_from_coords(-80.927, 29.026)
        assert "-80.927" in result.data

    def test_wkt_contains_latitude(self):
        result = point_from_coords(-80.927, 29.026)
        assert "29.026" in result.data

    def test_negative_longitude_and_latitude(self):
        result = point_from_coords(-151.274, -33.891)
        assert isinstance(result, WKTElement)
        assert "-151.274" in result.data
        assert "-33.891" in result.data

    def test_origin_zero_zero(self):
        result = point_from_coords(0.0, 0.0)
        assert isinstance(result, WKTElement)
        assert result.srid == 4326

    def test_positive_coords(self):
        result = point_from_coords(151.274, 33.891)
        assert "151.274" in result.data
        assert "33.891" in result.data

    def test_longitude_before_latitude_in_wkt(self):
        # PostGIS POINT format is (longitude latitude)
        result = point_from_coords(10.5, 20.5)
        wkt = result.data
        lon_pos = wkt.index("10.5")
        lat_pos = wkt.index("20.5")
        assert lon_pos < lat_pos
