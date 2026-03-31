"""Tests for species reference endpoints."""

import pytest
from httpx import AsyncClient

from app.models.species import SharkSpecies


@pytest.mark.asyncio
async def test_list_species_empty(client: AsyncClient):
    response = await client.get("/api/v1/species")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_list_species_with_data(
    client: AsyncClient, sample_species: list[SharkSpecies]
):
    response = await client.get("/api/v1/species")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 3
    # Should be sorted by common_name
    names = [s["common_name"] for s in data]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_species_response_fields(
    client: AsyncClient, sample_species: list[SharkSpecies]
):
    response = await client.get("/api/v1/species")
    data = response.json()
    great_white = next(s for s in data if s["common_name"] == "Great White Shark")
    assert great_white["scientific_name"] == "Carcharodon carcharias"
    assert great_white["family"] == "Lamnidae"
    assert great_white["danger_rating"] == "high"
    assert float(great_white["max_size_meters"]) == 6.1
