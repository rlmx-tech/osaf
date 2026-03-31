"""Backfill OSAF from the Global Shark Attack File (GSAF) spreadsheet.

Downloads GSAF5.xls and imports incidents from 2016 onward.
Uses Nominatim (OpenStreetMap) for geocoding.

Usage:
    python -m collector.backfill_gsaf [--dry-run] [--year-from 2016] [--year-to 2026]
"""

import argparse
import asyncio
import json
import logging
import re
import time
from datetime import date
from pathlib import Path

import httpx

from collector.config import COMMON_TO_SCIENTIFIC, settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

GSAF_URL = "https://www.sharkattackfile.net/spreadsheets/GSAF5.xls"
NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

# Geocode cache to avoid duplicate lookups
_geocode_cache: dict[str, tuple[float, float] | None] = {}
_last_nominatim_call = 0.0


# ---------------------------------------------------------------------------
# GSAF → OSAF field mapping
# ---------------------------------------------------------------------------

GSAF_TYPE_TO_CLASSIFICATION = {
    "unprovoked": "unprovoked",
    "provoked": "provoked",
    "watercraft": "boat_bite",
    "boat": "boat_bite",
    "sea disaster": "scavenge",
    "invalid": "doubtful",
    "questionable": "doubtful",
    "unverified": "not_confirmed",
    "unconfirmed": "not_confirmed",
    "under investigation": "not_confirmed",
}

GSAF_ACTIVITY_MAP = {
    "surfing": "surfing",
    "body surfing": "surfing",
    "boogie boarding": "surfing",
    "bodyboarding": "surfing",
    "board surfing": "surfing",
    "surf skiing": "surfing",
    "swimming": "swimming",
    "treading water": "swimming",
    "floating": "swimming",
    "bathing": "swimming",
    "wading": "wading",
    "standing": "wading",
    "walking": "wading",
    "diving": "diving",
    "scuba diving": "diving",
    "free diving": "diving",
    "snorkeling": "snorkeling",
    "snorkelling": "snorkeling",
    "fishing": "fishing",
    "wade fishing": "fishing",
    "net fishing": "fishing",
    "spearfishing": "spearfishing",
    "spear fishing": "spearfishing",
    "kayaking": "kayaking",
    "canoeing": "kayaking",
    "paddleboarding": "paddleboarding",
    "sup": "paddleboarding",
    "stand up paddleboarding": "paddleboarding",
    "stand-up paddleboarding": "paddleboarding",
}

MONTH_MAP = {
    "january": 1, "february": 2, "march": 3, "april": 4,
    "may": 5, "june": 6, "july": 7, "august": 8,
    "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4,
    "jun": 6, "jul": 7, "aug": 8, "sep": 9,
    "oct": 10, "nov": 11, "dec": 12,
}

# Country name normalization
COUNTRY_MAP = {
    "USA": "United States",
    "AUSTRALIA": "Australia",
    "SOUTH AFRICA": "South Africa",
    "NEW ZEALAND": "New Zealand",
    "BRAZIL": "Brazil",
    "BAHAMAS": "Bahamas",
    "PAPUA NEW GUINEA": "Papua New Guinea",
    "REUNION": "Réunion",
    "REUNION ISLAND": "Réunion",
    "NEW CALEDONIA": "New Caledonia",
    "EGYPT": "Egypt",
    "MEXICO": "Mexico",
    "FIJI": "Fiji",
    "MOZAMBIQUE": "Mozambique",
    "CUBA": "Cuba",
    "SPAIN": "Spain",
    "ITALY": "Italy",
    "JAPAN": "Japan",
    "PHILIPPINES": "Philippines",
    "INDONESIA": "Indonesia",
    "THAILAND": "Thailand",
    "GREECE": "Greece",
    "CROATIA": "Croatia",
    "FRANCE": "France",
    "ENGLAND": "United Kingdom",
    "SCOTLAND": "United Kingdom",
    "IRAN": "Iran",
    "TURKEY": "Turkey",
    "COSTA RICA": "Costa Rica",
    "COLOMBIA": "Colombia",
    "ECUADOR": "Ecuador",
    "CHILE": "Chile",
    "ARGENTINA": "Argentina",
    "INDIA": "India",
    "SRI LANKA": "Sri Lanka",
    "MALDIVES": "Maldives",
    "SEYCHELLES": "Seychelles",
    "KENYA": "Kenya",
    "TANZANIA": "Tanzania",
    "MADAGASCAR": "Madagascar",
    "MAURITIUS": "Mauritius",
    "RUSSIA": "Russia",
    "CHINA": "China",
    "TAIWAN": "Taiwan",
    "SOUTH KOREA": "South Korea",
    "HONG KONG": "China",
    "SINGAPORE": "Singapore",
    "MALAYSIA": "Malaysia",
    "VIETNAM": "Vietnam",
    "CAMBODIA": "Cambodia",
    "PORTUGAL": "Portugal",
    "IRELAND": "Ireland",
    "NORWAY": "Norway",
    "SWEDEN": "Sweden",
    "DENMARK": "Denmark",
    "ICELAND": "Iceland",
    "CANADA": "Canada",
    "BERMUDA": "Bermuda",
    "JAMAICA": "Jamaica",
    "PUERTO RICO": "Puerto Rico",
    "TRINIDAD & TOBAGO": "Trinidad and Tobago",
    "CAYMAN ISLANDS": "Cayman Islands",
    "VIRGIN ISLANDS": "US Virgin Islands",
    "TURKS & CAICOS": "Turks and Caicos Islands",
    "DOMINICAN REPUBLIC": "Dominican Republic",
    "HAITI": "Haiti",
    "PANAMA": "Panama",
    "HONDURAS": "Honduras",
    "BELIZE": "Belize",
    "NICARAGUA": "Nicaragua",
    "EL SALVADOR": "El Salvador",
    "GUATEMALA": "Guatemala",
    "PERU": "Peru",
    "VENEZUELA": "Venezuela",
    "GUYANA": "Guyana",
    "SURINAME": "Suriname",
    "URUGUAY": "Uruguay",
    "SAMOA": "Samoa",
    "TONGA": "Tonga",
    "VANUATU": "Vanuatu",
    "SOLOMON ISLANDS": "Solomon Islands",
    "MARSHALL ISLANDS": "Marshall Islands",
    "PALAU": "Palau",
    "GUAM": "Guam",
    "KIRIBATI": "Kiribati",
}


def _parse_gsaf_date(date_str: str, year_val: int) -> tuple[str | None, str]:
    """Parse GSAF date string like '18th March' with year → (YYYY-MM-DD, precision)."""
    if not date_str or not year_val:
        return None, "year"

    date_str = date_str.strip()

    # Remove ordinal suffixes
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)", r"\1", date_str, flags=re.IGNORECASE)

    # Try "DD Month" or "Month DD" patterns
    for pattern in [
        r"(\d{1,2})\s+(\w+)",  # "18 March"
        r"(\w+)\s+(\d{1,2})",  # "March 18"
    ]:
        m = re.match(pattern, cleaned, re.IGNORECASE)
        if m:
            g1, g2 = m.group(1), m.group(2)
            # Figure out which is day, which is month
            if g1.isdigit():
                day, month_str = int(g1), g2.lower()
            else:
                day, month_str = int(g2), g1.lower()

            month = MONTH_MAP.get(month_str)
            if month and 1 <= day <= 31:
                try:
                    d = date(year_val, month, day)
                    return d.isoformat(), "exact"
                except ValueError:
                    pass

    # Try just month name
    for month_name, month_num in MONTH_MAP.items():
        if month_name in date_str.lower():
            try:
                d = date(year_val, month_num, 1)
                return d.isoformat(), "month"
            except ValueError:
                pass

    # Fall back to just the year
    try:
        return date(year_val, 1, 1).isoformat(), "year"
    except ValueError:
        return None, "year"


def _parse_year(val) -> int | None:
    """Extract year from cell value (may be float or string)."""
    if isinstance(val, (int, float)):
        y = int(val)
        return y if 1900 <= y <= 2030 else None
    if isinstance(val, str):
        try:
            y = int(val.strip())
            return y if 1900 <= y <= 2030 else None
        except ValueError:
            return None
    return None


def _map_classification(gsaf_type: str) -> str:
    """Map GSAF 'Type' to OSAF classification."""
    if not gsaf_type:
        return "not_confirmed"
    lower = gsaf_type.strip().lower()
    return GSAF_TYPE_TO_CLASSIFICATION.get(lower, "not_confirmed")


def _map_activity(gsaf_activity: str) -> str | None:
    """Map GSAF 'Activity' to OSAF victim_activity."""
    if not gsaf_activity:
        return None
    lower = gsaf_activity.strip().lower()
    # Direct match
    if lower in GSAF_ACTIVITY_MAP:
        return GSAF_ACTIVITY_MAP[lower]
    # Partial match
    for key, val in GSAF_ACTIVITY_MAP.items():
        if key in lower:
            return val
    return None


def _infer_severity(injury: str, fatal: bool) -> str | None:
    """Infer injury severity from GSAF Injury text."""
    if fatal:
        return "fatal"
    if not injury:
        return None
    lower = injury.strip().lower()
    if any(w in lower for w in ["fatal", "died", "death", "killed"]):
        return "fatal"
    if any(w in lower for w in ["no injury", "no injuries", "uninjured", "not injured"]):
        return "no_injury"
    if any(w in lower for w in ["minor", "abrasion", "scratch", "laceration", "small"]):
        return "minor"
    if any(w in lower for w in ["severe", "amputation", "amputated", "lost", "severed"]):
        return "severe"
    return "moderate"


def _normalize_species(species_text: str | None) -> str | None:
    """Convert GSAF species to scientific name."""
    if not species_text:
        return None
    lower = species_text.lower().strip()
    if "unknown" in lower or "involvement" in lower or "not confirmed" in lower:
        return None
    # Extract size info separately
    # Check common name mapping
    for common, scientific in COMMON_TO_SCIENTIFIC.items():
        if common in lower:
            return scientific
    return None


def _extract_size(species_text: str | None) -> str | None:
    """Extract size estimate from GSAF species field."""
    if not species_text:
        return None
    # Patterns like "5ft", "2m", "3-4 meters", "1.5m"
    m = re.search(r"(\d+[\.\d]*\s*(?:ft|foot|feet|m|meter|metre|cm)[\w\s]*)", species_text, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    return None


def _parse_fatal(val: str) -> bool:
    """Parse GSAF Fatal Y/N field."""
    if not val:
        return False
    return val.strip().upper().startswith("Y")


def _parse_sex(val: str) -> str | None:
    """Parse GSAF Sex field."""
    if not val:
        return None
    v = val.strip().upper()
    if v == "M":
        return "male"
    if v == "F":
        return "female"
    return None


def _parse_age(val) -> int | None:
    """Parse GSAF Age field."""
    if not val:
        return None
    if isinstance(val, (int, float)):
        a = int(val)
        return a if 0 <= a <= 120 else None
    if isinstance(val, str):
        m = re.match(r"(\d+)", val.strip())
        if m:
            a = int(m.group(1))
            return a if 0 <= a <= 120 else None
    return None


def _normalize_country(val: str) -> str:
    """Normalize GSAF country name."""
    if not val:
        return "Unknown"
    upper = val.strip().upper()
    return COUNTRY_MAP.get(upper, val.strip().title())


def _parse_time(val: str) -> str | None:
    """Parse GSAF time like '1715hrs' → '17:15:00'."""
    if not val:
        return None
    m = re.match(r"(\d{2})(\d{2})\s*h", val.strip(), re.IGNORECASE)
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}:00"
    # Try "HH:MM" format
    m = re.match(r"(\d{1,2}):(\d{2})", val.strip())
    if m:
        h, mi = int(m.group(1)), int(m.group(2))
        if 0 <= h <= 23 and 0 <= mi <= 59:
            return f"{h:02d}:{mi:02d}:00"
    return None


async def geocode(location: str, country: str, state: str | None) -> tuple[float, float] | None:
    """Geocode a location using Nominatim. Returns (lat, lon) or None."""
    global _last_nominatim_call

    # Build query
    parts = []
    if location:
        parts.append(location)
    if state:
        parts.append(state)
    if country:
        parts.append(country)
    query = ", ".join(parts)

    if query in _geocode_cache:
        return _geocode_cache[query]

    # Rate limit: 1 request per second
    now = time.monotonic()
    wait = 1.0 - (now - _last_nominatim_call)
    if wait > 0:
        await asyncio.sleep(wait)

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            _last_nominatim_call = time.monotonic()
            resp = await client.get(
                NOMINATIM_URL,
                params={
                    "q": query,
                    "format": "json",
                    "limit": 1,
                },
                headers={"User-Agent": "OSAF-Backfill/0.1 (shark incident database)"},
            )
            resp.raise_for_status()
            results = resp.json()
            if results:
                lat = float(results[0]["lat"])
                lon = float(results[0]["lon"])
                _geocode_cache[query] = (lat, lon)
                return (lat, lon)
        except Exception:
            logger.debug("geocode failed for %r", query)

    # Try with just state + country
    if location and state:
        fallback = f"{state}, {country}"
        if fallback not in _geocode_cache:
            await asyncio.sleep(1.0)
            async with httpx.AsyncClient(timeout=10) as client:
                try:
                    _last_nominatim_call = time.monotonic()
                    resp = await client.get(
                        NOMINATIM_URL,
                        params={"q": fallback, "format": "json", "limit": 1},
                        headers={"User-Agent": "OSAF-Backfill/0.1 (shark incident database)"},
                    )
                    resp.raise_for_status()
                    results = resp.json()
                    if results:
                        lat = float(results[0]["lat"])
                        lon = float(results[0]["lon"])
                        _geocode_cache[fallback] = (lat, lon)
                        _geocode_cache[query] = (lat, lon)
                        return (lat, lon)
                except Exception:
                    pass

    _geocode_cache[query] = None
    return None


def parse_gsaf_row(row_values: list, col_count: int) -> dict | None:
    """Parse a single GSAF spreadsheet row into an OSAF-compatible dict."""
    if col_count < 14:
        return None

    year = _parse_year(row_values[1])
    if not year:
        return None

    date_str = str(row_values[0]).strip() if row_values[0] else ""
    incident_date, date_precision = _parse_gsaf_date(date_str, year)

    country = _normalize_country(str(row_values[3]) if row_values[3] else "")
    state = str(row_values[4]).strip() if row_values[4] else None
    location = str(row_values[5]).strip() if row_values[5] else ""
    activity_raw = str(row_values[6]).strip() if row_values[6] else ""
    name = str(row_values[7]).strip() if row_values[7] else None
    sex = _parse_sex(str(row_values[8]) if row_values[8] else "")
    age = _parse_age(row_values[9])
    injury = str(row_values[10]).strip() if row_values[10] else ""
    fatal = _parse_fatal(str(row_values[11]) if row_values[11] else "")
    time_str = str(row_values[12]).strip() if row_values[12] else ""
    species_raw = str(row_values[13]).strip() if row_values[13] else ""
    source_text = str(row_values[14]).strip() if col_count > 14 and row_values[14] else ""

    classification = _map_classification(str(row_values[2]) if row_values[2] else "")
    activity = _map_activity(activity_raw)
    severity = _infer_severity(injury, fatal)
    species = _normalize_species(species_raw)
    size = _extract_size(species_raw)
    incident_time = _parse_time(time_str)

    # Skip rows with no useful data
    if not location and not country:
        return None
    if name and name.lower() in ("unknown", "n/a", ""):
        name = None

    # Build description from available fields
    desc_parts = []
    if activity_raw:
        desc_parts.append(f"Victim was {activity_raw.lower()}.")
    if injury:
        desc_parts.append(f"Injury: {injury}.")
    if species_raw and "unknown" not in species_raw.lower():
        desc_parts.append(f"Species: {species_raw}.")
    description = " ".join(desc_parts) if desc_parts else None

    return {
        "incident_date": incident_date,
        "incident_time": incident_time,
        "date_precision": date_precision,
        "location_description": location or f"{state or ''}, {country}".strip(", "),
        "country": country,
        "state_province": state if state and state.lower() not in ("", "n/a") else None,
        "classification": classification,
        "report_source": "isaf",
        "shark_species_suspected": species,
        "shark_size_estimate": size,
        "species_identification_method": "witness" if species else None,
        "victim_activity": activity,
        "victim_injury_severity": severity,
        "victim_injury_description": injury if injury else None,
        "victim_name": name,
        "victim_age": age,
        "victim_sex": sex,
        "fatal": fatal,
        "description": description,
        "location_precision": "approximate",
        # For geocoding later
        "_location": location,
        "_state": state,
        "_source_text": source_text,
        "_year": year,
    }


async def authenticate(client: httpx.AsyncClient) -> str | None:
    """Get JWT token from the OSAF API."""
    try:
        resp = await client.post(
            f"{settings.osaf_api_url}/auth/login",
            data={
                "username": settings.osaf_username,
                "password": settings.osaf_password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        token = resp.json().get("access_token")
        if token:
            logger.info("Authenticated as %s", settings.osaf_username)
            return token
    except httpx.HTTPError:
        logger.exception("Authentication failed")
    return None


async def submit_incident(
    client: httpx.AsyncClient, token: str, payload: dict
) -> str | None:
    """Submit a single incident. Returns case number or None."""
    try:
        resp = await client.post(
            f"{settings.osaf_api_url}/submissions",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )
        if resp.status_code == 401:
            return "TOKEN_EXPIRED"
        resp.raise_for_status()
        return resp.json().get("case_number", "submitted")
    except httpx.HTTPStatusError as exc:
        detail = ""
        try:
            detail = exc.response.json().get("detail", "")
        except Exception:
            pass
        logger.warning("Submit failed (%d): %s", exc.response.status_code, detail)
        return None
    except httpx.HTTPError:
        logger.exception("Submit request failed")
        return None


async def main():
    parser = argparse.ArgumentParser(description="Backfill OSAF from GSAF spreadsheet")
    parser.add_argument("--dry-run", action="store_true", help="Parse and geocode but don't submit")
    parser.add_argument("--year-from", type=int, default=2016)
    parser.add_argument("--year-to", type=int, default=2026)
    parser.add_argument("--skip-geocode", action="store_true", help="Skip geocoding (faster)")
    parser.add_argument("--cache-file", default="/tmp/gsaf_geocode_cache.json")
    args = parser.parse_args()

    # Load geocode cache
    global _geocode_cache
    cache_path = Path(args.cache_file)
    if cache_path.exists():
        with open(cache_path) as f:
            raw = json.load(f)
            _geocode_cache = {k: tuple(v) if v else None for k, v in raw.items()}
        logger.info("Loaded %d cached geocode results", len(_geocode_cache))

    # Download GSAF spreadsheet
    xls_path = Path("/tmp/GSAF5.xls")
    if not xls_path.exists() or (time.time() - xls_path.stat().st_mtime > 3600):
        logger.info("Downloading GSAF spreadsheet...")
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.get(GSAF_URL)
            resp.raise_for_status()
            xls_path.write_bytes(resp.content)
        logger.info("Downloaded %.1f MB", xls_path.stat().st_size / 1e6)
    else:
        logger.info("Using cached GSAF spreadsheet")

    # Parse XLS
    import xlrd
    wb = xlrd.open_workbook(str(xls_path))
    ws = wb.sheet_by_index(0)

    incidents = []
    for r in range(1, ws.nrows):
        row_vals = [ws.cell_value(r, c) for c in range(ws.ncols)]
        parsed = parse_gsaf_row(row_vals, ws.ncols)
        if not parsed:
            continue
        year = parsed["_year"]
        if year < args.year_from or year > args.year_to:
            continue
        incidents.append(parsed)

    logger.info("Parsed %d incidents from %d-%d", len(incidents), args.year_from, args.year_to)

    # Geocode
    if not args.skip_geocode:
        geocoded = 0
        failed = 0
        for i, inc in enumerate(incidents):
            coords = await geocode(inc["_location"], inc["country"], inc["_state"])
            if coords:
                inc["coordinates"] = {"latitude": coords[0], "longitude": coords[1]}
                geocoded += 1
            else:
                inc["coordinates"] = None
                failed += 1
            if (i + 1) % 50 == 0:
                logger.info(
                    "Geocoding progress: %d/%d (%.0f%% success)",
                    i + 1, len(incidents), geocoded / (i + 1) * 100,
                )
                # Save cache periodically
                with open(cache_path, "w") as f:
                    json.dump(
                        {k: list(v) if v else None for k, v in _geocode_cache.items()},
                        f,
                    )

        logger.info("Geocoding complete: %d success, %d failed", geocoded, failed)
        # Save final cache
        with open(cache_path, "w") as f:
            json.dump(
                {k: list(v) if v else None for k, v in _geocode_cache.items()},
                f,
            )

    # Clean up internal fields and build submission payloads
    for inc in incidents:
        source_text = inc.pop("_source_text", "")
        inc.pop("_location", None)
        inc.pop("_state", None)
        inc.pop("_year", None)

        # Add source
        inc["sources"] = [{
            "source_type": "other",
            "source_title": "Global Shark Attack File (GSAF)",
            "source_publisher": "Shark Research Institute",
            "source_notes": f"GSAF source: {source_text}" if source_text else "Imported from GSAF5.xls",
        }]

    if args.dry_run:
        logger.info("DRY RUN — not submitting. Sample payloads:")
        for inc in incidents[:3]:
            print(json.dumps(inc, indent=2, default=str))
        logger.info("Total: %d incidents ready to submit", len(incidents))
        return

    # Submit to OSAF API
    async with httpx.AsyncClient(timeout=30) as client:
        token = await authenticate(client)
        if not token:
            logger.error("Cannot authenticate — aborting")
            return

        submitted = 0
        skipped = 0
        for i, inc in enumerate(incidents):
            result = await submit_incident(client, token, inc)
            if result == "TOKEN_EXPIRED":
                token = await authenticate(client)
                if not token:
                    logger.error("Re-auth failed — aborting at row %d", i)
                    break
                result = await submit_incident(client, token, inc)

            if result:
                submitted += 1
            else:
                skipped += 1

            if (i + 1) % 25 == 0:
                logger.info(
                    "Submit progress: %d/%d (submitted=%d, skipped=%d)",
                    i + 1, len(incidents), submitted, skipped,
                )

    logger.info("Backfill complete: %d submitted, %d skipped", submitted, skipped)


if __name__ == "__main__":
    asyncio.run(main())
