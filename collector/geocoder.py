"""Geocoding via OpenStreetMap Nominatim with coastline bias for shark incidents.

Strategy:
- For NEW incidents: Nominatim geocodes the location; falls back to LLM estimate.
- For BACKFILL: Only corrects coordinates that are clearly inland/wrong.

All shark incidents occur in or near water. Nominatim produces much better
coordinates than LLM guessing, especially for vague locations like "California
beach" which LLMs place at geographic centers (e.g., Fresno).
"""

import asyncio
import logging
import math
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
USER_AGENT = "OSAF-Collector/1.0 (https://osaf.net)"

# Nominatim fair use: max 1 request per second
_last_request_time: float = 0
_lock = asyncio.Lock()


@dataclass
class GeoResult:
    latitude: float
    longitude: float
    display_name: str
    importance: float
    osm_type: str  # node, way, relation


# State/province bounding boxes for validation (lat_min, lat_max, lon_min, lon_max)
# Prevents Nominatim from finding a same-named place in the wrong state
_STATE_BOUNDS: dict[str, tuple[float, float, float, float]] = {
    "florida": (24.5, 31.0, -87.6, -80.0),
    "california": (32.5, 42.0, -124.5, -114.1),
    "hawaii": (18.9, 22.3, -160.3, -154.8),
    "north carolina": (33.8, 36.6, -84.3, -75.5),
    "south carolina": (32.0, 35.2, -83.4, -78.5),
    "texas": (25.8, 36.5, -106.6, -93.5),
    "new york": (40.5, 45.0, -79.8, -71.9),
    "new jersey": (38.9, 41.4, -75.6, -73.9),
    "massachusetts": (41.2, 42.9, -73.5, -69.9),
    "oregon": (41.9, 46.3, -124.6, -116.5),
    "washington": (45.5, 49.0, -124.8, -116.9),
    "queensland": (-29.0, -10.0, 138.0, 154.0),
    "new south wales": (-37.5, -28.0, 141.0, 154.0),
    "western australia": (-35.0, -13.5, 112.0, 129.0),
    "south australia": (-38.1, -26.0, 129.0, 141.0),
    "victoria": (-39.2, -34.0, 141.0, 150.0),
    "kwazulu-natal": (-31.0, -27.0, 29.0, 33.0),
    "eastern cape": (-34.0, -30.5, 24.5, 30.2),
    "western cape": (-35.0, -31.0, 17.5, 21.0),
}


def _in_state_bounds(lat: float, lng: float, state: str | None) -> bool:
    """Check if coordinates fall within expected state bounds."""
    if not state:
        return True  # Can't validate without state info
    bounds = _STATE_BOUNDS.get(state.lower().strip())
    if not bounds:
        return True  # Unknown state — can't validate
    lat_min, lat_max, lon_min, lon_max = bounds
    return lat_min <= lat <= lat_max and lon_min <= lng <= lon_max


def _build_search_queries(
    location_description: str,
    country: str | None = None,
    state_province: str | None = None,
    body_of_water: str | None = None,
) -> list[str]:
    """Build a ranked list of search queries from most to least specific."""
    queries = []
    loc = location_description.strip()

    # Most specific: full location with state and country
    if state_province and country:
        queries.append(f"{loc}, {state_province}, {country}")

    # With country only
    if country and f"{loc}, {country}" not in queries:
        queries.append(f"{loc}, {country}")

    # For vague locations, try with "coast" appended
    vague_keywords = {"beach", "coast", "coastline", "shore"}
    loc_lower = loc.lower()
    is_vague = any(
        loc_lower.endswith(kw) or loc_lower == kw
        for kw in vague_keywords
    ) or loc_lower in {s.lower() for s in (state_province or "", country or "") if s}

    if is_vague and state_province:
        queries.append(f"{state_province} coast, {country or ''}")

    return queries


async def _rate_limit() -> None:
    """Enforce 1 request per second rate limit for Nominatim fair use."""
    global _last_request_time
    async with _lock:
        now = asyncio.get_event_loop().time()
        elapsed = now - _last_request_time
        if elapsed < 1.0:
            await asyncio.sleep(1.0 - elapsed)
        _last_request_time = asyncio.get_event_loop().time()


async def _search_nominatim(
    query: str,
    country_code: str | None = None,
    viewbox: tuple[float, float, float, float] | None = None,
) -> list[GeoResult]:
    """Search Nominatim for a location string."""
    await _rate_limit()

    params: dict[str, str] = {
        "q": query,
        "format": "json",
        "limit": "5",
    }
    if country_code:
        params["countrycodes"] = country_code
    if viewbox:
        # viewbox = lon_min, lat_min, lon_max, lat_max (Nominatim format)
        params["viewbox"] = f"{viewbox[2]},{viewbox[0]},{viewbox[3]},{viewbox[1]}"
        params["bounded"] = "0"  # Prefer but don't require results in viewbox

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            resp = await client.get(
                NOMINATIM_URL,
                params=params,
                headers={"User-Agent": USER_AGENT},
            )
            resp.raise_for_status()
            results = resp.json()
            return [
                GeoResult(
                    latitude=float(r["lat"]),
                    longitude=float(r["lon"]),
                    display_name=r.get("display_name", ""),
                    importance=float(r.get("importance", 0)),
                    osm_type=r.get("osm_type", ""),
                )
                for r in results
            ]
        except (httpx.HTTPError, KeyError, ValueError):
            logger.debug("geocoder: Nominatim search failed for %r", query)
            return []


# ISO 3166-1 alpha-2 codes for common shark-incident countries
_COUNTRY_CODES: dict[str, str] = {
    "united states": "us", "usa": "us",
    "australia": "au", "south africa": "za", "brazil": "br",
    "bahamas": "bs", "new zealand": "nz", "mexico": "mx",
    "egypt": "eg", "spain": "es", "france": "fr",
    "indonesia": "id", "fiji": "fj", "reunion": "re",
    "japan": "jp", "india": "in", "philippines": "ph",
    "mozambique": "mz", "thailand": "th", "italy": "it",
    "greece": "gr", "croatia": "hr", "portugal": "pt",
    "united kingdom": "gb", "canada": "ca",
    "papua new guinea": "pg", "cuba": "cu", "costa rica": "cr",
    "panama": "pa", "colombia": "co", "chile": "cl",
    "peru": "pe", "ecuador": "ec",
}


def _country_code(country: str | None) -> str | None:
    """Convert country name to ISO alpha-2 code."""
    if not country:
        return None
    return _COUNTRY_CODES.get(country.lower().strip())


def _get_viewbox(state: str | None) -> tuple[float, float, float, float] | None:
    """Get a viewbox for Nominatim search based on state/province."""
    if not state:
        return None
    bounds = _STATE_BOUNDS.get(state.lower().strip())
    if not bounds:
        return None
    # bounds = (lat_min, lat_max, lon_min, lon_max)
    return bounds


async def geocode_incident(
    location_description: str,
    country: str | None = None,
    state_province: str | None = None,
    body_of_water: str | None = None,
) -> tuple[float, float] | None:
    """Geocode a shark incident location using Nominatim.

    Returns (latitude, longitude) or None if geocoding fails.
    Validates results against state bounds to avoid same-named places
    in the wrong region (e.g., Shell Key FL vs Shell Key in the Keys).
    """
    queries = _build_search_queries(
        location_description, country, state_province, body_of_water
    )
    country_code = _country_code(country)
    viewbox = _get_viewbox(state_province)

    for query in queries:
        results = await _search_nominatim(query, country_code, viewbox)

        # Filter to results within expected state bounds
        for result in results:
            if _in_state_bounds(result.latitude, result.longitude, state_province):
                logger.debug(
                    "geocoder: %r -> (%.4f, %.4f) via %r [%s]",
                    location_description, result.latitude, result.longitude,
                    query, result.display_name[:60],
                )
                return (result.latitude, result.longitude)

        # If no results match state bounds, try next query
        if results:
            logger.debug(
                "geocoder: %r — %d results but none in %s bounds, trying next query",
                location_description, len(results), state_province,
            )

    logger.debug("geocoder: no valid results for %r", location_description)
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in kilometers."""
    r = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (math.sin(dlat / 2) ** 2 +
         math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) *
         math.sin(dlon / 2) ** 2)
    return r * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
