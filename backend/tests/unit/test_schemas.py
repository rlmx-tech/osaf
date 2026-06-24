"""Unit tests for Pydantic schemas — validates structure and validators."""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from app.schemas.stats import (
    ActivityCount,
    CountryCount,
    FatalityTrend,
    OverviewStats,
    SpeciesCount,
    YearCount,
)
from app.schemas.user import UserCreate, UserResponse


class TestOverviewStats:
    def test_all_fields(self):
        s = OverviewStats(
            total_incidents=100,
            total_fatal=10,
            fatality_rate=10.0,
            most_active_country="Australia",
            most_common_species="Carcharodon carcharias",
            year_range="2000-2025",
        )
        assert s.total_incidents == 100
        assert s.fatality_rate == 10.0

    def test_optional_fields_default_none(self):
        s = OverviewStats(total_incidents=0, total_fatal=0, fatality_rate=0.0)
        assert s.most_active_country is None
        assert s.most_common_species is None
        assert s.year_range is None


class TestYearCount:
    def test_fields(self):
        yc = YearCount(year=2024, count=55, fatal=3)
        assert yc.year == 2024
        assert yc.count == 55
        assert yc.fatal == 3


class TestCountryCount:
    def test_fields(self):
        cc = CountryCount(country="USA", count=200, fatal=15)
        assert cc.country == "USA"
        assert cc.count == 200
        assert cc.fatal == 15


class TestSpeciesCount:
    def test_fields(self):
        sc = SpeciesCount(species="Carcharodon carcharias", count=88)
        assert sc.species == "Carcharodon carcharias"
        assert sc.count == 88


class TestActivityCount:
    def test_fields(self):
        ac = ActivityCount(activity="surfing", count=300)
        assert ac.activity == "surfing"
        assert ac.count == 300


class TestFatalityTrend:
    def test_fields(self):
        ft = FatalityTrend(year=2022, fatal=5, non_fatal=47)
        assert ft.year == 2022
        assert ft.fatal == 5
        assert ft.non_fatal == 47


class TestUserCreate:
    def _valid_password(self) -> str:
        return "Str0ng!Pass"

    def test_valid_user(self):
        u = UserCreate(
            email="user@example.com",
            username="testuser",
            password=self._valid_password(),
        )
        assert u.email == "user@example.com"
        assert u.username == "testuser"

    def test_password_too_short(self):
        with pytest.raises(ValidationError):
            UserCreate(email="a@b.com", username="u", password="Sh0rt!")

    def test_password_no_uppercase(self):
        with pytest.raises(ValidationError):
            UserCreate(email="a@b.com", username="u", password="nouppercase1!")

    def test_password_no_lowercase(self):
        with pytest.raises(ValidationError):
            UserCreate(email="a@b.com", username="u", password="NOLOWER1!")

    def test_password_no_digit(self):
        with pytest.raises(ValidationError):
            UserCreate(email="a@b.com", username="u", password="NoDigit!!")

    def test_password_no_special_char(self):
        with pytest.raises(ValidationError):
            UserCreate(email="a@b.com", username="u", password="NoSpecial1")

    def test_display_name_optional(self):
        u = UserCreate(
            email="a@b.com", username="u", password=self._valid_password()
        )
        assert u.display_name is None

    def test_display_name_set(self):
        u = UserCreate(
            email="a@b.com",
            username="u",
            password=self._valid_password(),
            display_name="John Doe",
        )
        assert u.display_name == "John Doe"


class TestUserResponse:
    def test_fields(self):
        user_id = uuid.uuid4()
        ur = UserResponse(
            id=user_id,
            email="test@example.com",
            username="testuser",
            role="public",
            created_at=datetime(2025, 1, 1),
            is_active=True,
        )
        assert ur.id == user_id
        assert ur.role == "public"
        assert ur.bio is None
        assert ur.display_name is None
