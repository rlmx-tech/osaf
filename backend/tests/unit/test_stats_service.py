"""Unit tests for app/services/stats_service.py — mocked DB."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.stats_service import StatsService


def _scalar_result(value) -> MagicMock:
    """Helper: mock execute() result with scalar_one() returning value."""
    m = MagicMock()
    m.scalar_one.return_value = value
    m.scalar_one_or_none.return_value = value
    return m


def _rows_result(rows) -> MagicMock:
    """Helper: mock execute() result with .all() returning rows."""
    m = MagicMock()
    m.all.return_value = rows
    return m


class TestOverview:
    async def test_empty_database(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),    # total
            _scalar_result(0),    # fatal_count
            _scalar_result(None), # top_country
            _scalar_result(None), # top_species
            _scalar_result(None), # min_year
            _scalar_result(None), # max_year
        ])
        service = StatsService(db)
        result = await service.overview()
        data = result["data"]
        assert data["total_incidents"] == 0
        assert data["total_fatal"] == 0
        assert data["fatality_rate"] == 0
        assert data["most_active_country"] is None
        assert data["most_common_species"] is None
        assert data["year_range"] is None

    async def test_fatality_rate_calculated(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(100),           # total
            _scalar_result(20),            # fatal
            _scalar_result("Australia"),   # top_country
            _scalar_result("Carcharodon carcharias"),  # top_species
            _scalar_result(2020.0),        # min_year
            _scalar_result(2025.0),        # max_year
        ])
        service = StatsService(db)
        result = await service.overview()
        data = result["data"]
        assert data["total_incidents"] == 100
        assert data["total_fatal"] == 20
        assert data["fatality_rate"] == 20.0
        assert data["most_active_country"] == "Australia"
        assert data["most_common_species"] == "Carcharodon carcharias"
        assert data["year_range"] == "2020-2025"

    async def test_year_range_formatted(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(5),
            _scalar_result(1),
            _scalar_result("USA"),
            _scalar_result(None),
            _scalar_result(2010.0),
            _scalar_result(2015.0),
        ])
        service = StatsService(db)
        result = await service.overview()
        assert result["data"]["year_range"] == "2010-2015"

    async def test_fatality_rate_zero_division_guarded(self):
        db = AsyncMock()
        db.execute = AsyncMock(side_effect=[
            _scalar_result(0),
            _scalar_result(0),
            _scalar_result(None),
            _scalar_result(None),
            _scalar_result(None),
            _scalar_result(None),
        ])
        service = StatsService(db)
        result = await service.overview()
        # Should not raise ZeroDivisionError
        assert result["data"]["fatality_rate"] == 0


class TestByYear:
    async def test_empty_returns_empty_list(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_result([]))
        service = StatsService(db)
        result = await service.by_year()
        assert result["data"] == []

    async def test_rows_transformed_correctly(self):
        db = AsyncMock()
        row = MagicMock()
        row.year = 2024.0
        row.count = 42
        row.fatal = 3
        db.execute = AsyncMock(return_value=_rows_result([row]))
        service = StatsService(db)
        result = await service.by_year()
        assert len(result["data"]) == 1
        assert result["data"][0] == {"year": 2024, "count": 42, "fatal": 3}

    async def test_year_cast_to_int(self):
        db = AsyncMock()
        row = MagicMock()
        row.year = 2023.0
        row.count = 10
        row.fatal = 0
        db.execute = AsyncMock(return_value=_rows_result([row]))
        service = StatsService(db)
        result = await service.by_year()
        assert isinstance(result["data"][0]["year"], int)


class TestByCountry:
    async def test_empty_returns_empty_list(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_result([]))
        service = StatsService(db)
        result = await service.by_country()
        assert result["data"] == []

    async def test_rows_include_country_count_fatal(self):
        db = AsyncMock()
        row = MagicMock()
        row.country = "Australia"
        row.count = 150
        row.fatal = 10
        db.execute = AsyncMock(return_value=_rows_result([row]))
        service = StatsService(db)
        result = await service.by_country()
        assert result["data"][0] == {"country": "Australia", "count": 150, "fatal": 10}


class TestBySpecies:
    async def test_empty_returns_empty_list(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_result([]))
        service = StatsService(db)
        result = await service.by_species()
        assert result["data"] == []

    async def test_rows_include_species_and_count(self):
        db = AsyncMock()
        row = MagicMock()
        row.species = "Carcharodon carcharias"
        row.count = 88
        db.execute = AsyncMock(return_value=_rows_result([row]))
        service = StatsService(db)
        result = await service.by_species()
        assert result["data"][0] == {"species": "Carcharodon carcharias", "count": 88}


class TestSpeciesLabel:
    def test_species_coalesces_confirmed_then_suspected(self):
        # Species aggregation must fall back to the suspected column (what the
        # collector populates), not only the rarely-set confirmed column.
        sql = str(
            StatsService._species_label().compile(
                compile_kwargs={"literal_binds": True}
            )
        ).lower()
        assert "coalesce" in sql
        assert "shark_species_confirmed" in sql
        assert "shark_species_suspected" in sql


class TestByActivity:
    async def test_empty_returns_empty_list(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_result([]))
        service = StatsService(db)
        result = await service.by_activity()
        assert result["data"] == []

    async def test_rows_include_activity_and_count(self):
        db = AsyncMock()
        row = MagicMock()
        row.activity = "surfing"
        row.count = 300
        db.execute = AsyncMock(return_value=_rows_result([row]))
        service = StatsService(db)
        result = await service.by_activity()
        assert result["data"][0] == {"activity": "surfing", "count": 300}


class TestFatalityTrends:
    async def test_empty_returns_empty_list(self):
        db = AsyncMock()
        db.execute = AsyncMock(return_value=_rows_result([]))
        service = StatsService(db)
        result = await service.fatality_trends()
        assert result["data"] == []

    async def test_rows_include_year_fatal_nonfatal(self):
        db = AsyncMock()
        row = MagicMock()
        row.year = 2022.0
        row.fatal = 5
        row.non_fatal = 47
        db.execute = AsyncMock(return_value=_rows_result([row]))
        service = StatsService(db)
        result = await service.fatality_trends()
        assert result["data"][0] == {"year": 2022, "fatal": 5, "non_fatal": 47}

    async def test_year_cast_to_int(self):
        db = AsyncMock()
        row = MagicMock()
        row.year = 2021.0
        row.fatal = 2
        row.non_fatal = 18
        db.execute = AsyncMock(return_value=_rows_result([row]))
        service = StatsService(db)
        result = await service.fatality_trends()
        assert isinstance(result["data"][0]["year"], int)
