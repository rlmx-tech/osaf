"""Unit tests for app/utils/case_number.py — mocked DB."""

from datetime import date
from unittest.mock import AsyncMock, MagicMock

from app.utils.case_number import generate_case_number


def _mock_db(highest_suffix: int | None) -> AsyncMock:
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = highest_suffix
    db = AsyncMock()
    bind = MagicMock()
    bind.dialect.name = "sqlite"
    db.get_bind = MagicMock(return_value=bind)
    db.execute = AsyncMock(return_value=mock_result)
    return db


class TestGenerateCaseNumber:
    async def test_first_case_of_year(self):
        db = _mock_db(0)
        result = await generate_case_number(db)
        year = date.today().year
        assert result == f"OSAF-{year}-0001"

    async def test_second_case(self):
        db = _mock_db(1)
        result = await generate_case_number(db)
        year = date.today().year
        assert result == f"OSAF-{year}-0002"

    async def test_uses_highest_suffix_instead_of_row_count(self):
        db = _mock_db(6573)
        result = await generate_case_number(db)
        year = date.today().year
        assert result == f"OSAF-{year}-6574"

    async def test_tenth_case_zero_padded(self):
        db = _mock_db(9)
        result = await generate_case_number(db)
        year = date.today().year
        assert result == f"OSAF-{year}-0010"

    async def test_hundredth_case(self):
        db = _mock_db(99)
        result = await generate_case_number(db)
        year = date.today().year
        assert result == f"OSAF-{year}-0100"

    async def test_large_case_number_exceeds_padding(self):
        db = _mock_db(9999)
        result = await generate_case_number(db)
        year = date.today().year
        assert result == f"OSAF-{year}-10000"

    async def test_includes_current_year(self):
        db = _mock_db(0)
        result = await generate_case_number(db)
        year = date.today().year
        assert str(year) in result

    async def test_format_prefix(self):
        db = _mock_db(0)
        result = await generate_case_number(db)
        assert result.startswith("OSAF-")

    async def test_queries_db_once(self):
        db = _mock_db(5)
        await generate_case_number(db)
        assert db.execute.call_count == 1
