"""Unit tests for app/services/map_service.py — pure function tests."""

import pytest

from app.services.map_service import _parse_bbox


class TestParseBbox:
    def test_valid_bbox(self):
        result = _parse_bbox("-82,28,-80,30")
        assert result == (-82.0, 28.0, -80.0, 30.0)

    def test_floats_parsed(self):
        result = _parse_bbox("-82.5,28.1,-80.3,30.7")
        assert result[0] == pytest.approx(-82.5)
        assert result[1] == pytest.approx(28.1)
        assert result[2] == pytest.approx(-80.3)
        assert result[3] == pytest.approx(30.7)

    def test_returns_tuple_of_four(self):
        result = _parse_bbox("0,0,10,10")
        assert len(result) == 4

    def test_raises_for_too_few_values(self):
        with pytest.raises((ValueError, IndexError)):
            _parse_bbox("-82,28,-80")

    def test_raises_for_too_many_values(self):
        with pytest.raises(ValueError):
            _parse_bbox("-82,28,-80,30,extra")

    def test_spaces_around_values(self):
        result = _parse_bbox(" -82 , 28 , -80 , 30 ")
        assert result == (-82.0, 28.0, -80.0, 30.0)

    def test_global_bbox(self):
        result = _parse_bbox("-180,-90,180,90")
        assert result == (-180.0, -90.0, 180.0, 90.0)
