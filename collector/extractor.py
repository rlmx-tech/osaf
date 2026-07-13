"""Ollama-powered extraction and verification pipeline.

Uses glm-5.2:cloud on Ollama Cloud (configurable via COLLECTOR_OLLAMA_MODEL) to:
1. Extract structured incident data from raw text
2. Verify extracted data for consistency and accuracy

A general instruction-following model is used (not a code model) because the
task is structured extraction from prose news/social text, not code generation.
"""

import json
import logging
import re
from datetime import date

import httpx

from collector.coastline import is_vague_location, snap_if_inland
from collector.config import (
    COMMON_TO_SCIENTIFIC,
    COUNTRY_ALIASES,
    VALID_ACTIVITIES,
    VALID_CLASSIFICATIONS,
    VALID_SEVERITIES,
    settings,
)
from collector.geocoder import geocode_incident
from collector.models import ExtractedIncident, RawItem, SourcePlatform, VerificationResult

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """\
You are an expert at extracting structured shark incident data from text.
Analyze the following text and extract any shark incident information.
Today's date is {today}.

IMPORTANT: Extract ONLY information explicitly stated or directly implied in the text below. Do not supplement with external knowledge about incidents, locations, or species. If a field cannot be determined from the text, use null. For latitude/longitude, estimate ONLY from the location description given — if the location is too vague for a reasonable estimate, use null.

If the text does NOT describe a shark incident, sighting, or encounter, respond with:
{{"is_relevant": false}}

If it DOES describe a shark incident/sighting/encounter, extract the following JSON:

{{
  "is_relevant": true,
  "confidence": 0.0-1.0,
  "incident_date": "YYYY-MM-DD or null — IMPORTANT: convert relative dates (yesterday, last weekend, on Thursday, this morning, etc.) to absolute YYYY-MM-DD using today's date above. If the article was published on a specific date and describes a recent incident without an explicit date, use the publication date. Only return null if there is absolutely no date information.",
  "location_description": "specific location name",
  "country": "country name",
  "state_province": "state or province or null",
  "body_of_water": "ocean, sea, bay name or null",
  "classification": "one of: unprovoked, provoked, boat_bite, scavenge, sighting, near_miss, equipment_bite, unverified_report, not_confirmed",
  "shark_species": "common name of shark species or null",
  "victim_activity": "one of: swimming, surfing, diving, snorkeling, fishing, spearfishing, wading, kayaking, paddleboarding, or null",
  "victim_injury_severity": "one of: fatal, severe, moderate, minor, no_injury, or null",
  "victim_name": "name or null",
  "victim_age": number or null,
  "victim_sex": "male, female, or null",
  "fatal": true/false,
  "description": "2-3 sentence summary of the incident"
}}

Classification guide:
- "unprovoked": shark bites human unprovoked in natural habitat
- "provoked": human provoked the shark (touching, feeding, spearfishing nearby)
- "boat_bite": shark bites a boat/kayak/watercraft
- "sighting": shark spotted but no contact with humans
- "near_miss": shark approached closely but didn't bite
- "equipment_bite": shark bites surfboard, fishing gear, etc. (not person)
- "unverified_report": incident reported but not independently verified
- "not_confirmed": unclear if shark was actually involved

Respond with ONLY valid JSON, no markdown formatting.

TEXT:
{text}"""

VERIFICATION_PROMPT = """\
You are verifying extracted shark incident data for accuracy and consistency.

Review the extracted data below against the original text. ONLY flag issues that are contradicted by the original text. Do not flag fields as incorrect based on external knowledge — only based on what the text actually says. If the text is ambiguous or lacks detail, note that rather than assuming an error.

Check for:
1. Does the classification match the described incident in the text?
2. Is the species name consistent with what the text states?
3. Is the location/country consistent with the text?
4. Is the severity consistent with the described injuries in the text?
5. Are there any fields that contradict the original text?

Respond with ONLY valid JSON:
{{
  "is_valid": true/false,
  "is_duplicate_likely": true/false,
  "confidence": 0.0-1.0,
  "corrections": {{
    "field_name": "corrected_value"
  }},
  "notes": "brief explanation of any issues"
}}

EXTRACTED DATA:
{data}

ORIGINAL TEXT:
{text}"""


def _report_source_for_platform(platform: SourcePlatform) -> str:
    """Map source platform to OSAF report_source value."""
    return {
        SourcePlatform.YOUTUBE: "social_media",
        SourcePlatform.REDDIT: "social_media",
        SourcePlatform.TWITTER: "social_media",
        SourcePlatform.NEWS_RSS: "news_media",
        SourcePlatform.WEB_SCRAPE: "news_media",
    }.get(platform, "community")


def _report_platform_for_source(platform: SourcePlatform) -> str | None:
    """Map source platform to OSAF report_platform value."""
    return {
        SourcePlatform.YOUTUBE: "youtube",
        SourcePlatform.REDDIT: "reddit",
        SourcePlatform.TWITTER: "twitter",
    }.get(platform)


def _source_type_for_platform(platform: SourcePlatform) -> str:
    """Map source platform to incident_sources.source_type."""
    return {
        SourcePlatform.YOUTUBE: "video",
        SourcePlatform.REDDIT: "social_media",
        SourcePlatform.TWITTER: "social_media",
        SourcePlatform.NEWS_RSS: "news_article",
        SourcePlatform.WEB_SCRAPE: "news_article",
    }.get(platform, "other")


def _normalize_species(species_text: str | None) -> str | None:
    """Convert common shark names to scientific names."""
    if not species_text:
        return None
    lower = species_text.lower().strip()

    # Check common name mapping first (catches "Great White Shark" etc.)
    for common, scientific in COMMON_TO_SCIENTIFIC.items():
        if common in lower:
            return scientific

    # If two words, first uppercase, second lowercase — likely already scientific
    parts = species_text.strip().split()
    if len(parts) == 2 and parts[0][0].isupper() and parts[1][0].islower():
        return species_text.strip()

    # Return as-is if we can't map it
    return species_text


def _normalize_country(country: str | None) -> str | None:
    """Map common country-name variants to their canonical form."""
    if not country:
        return None
    stripped = country.strip()
    return COUNTRY_ALIASES.get(stripped.lower(), stripped)


def _validate_field(value: str | None, valid_options: list[str]) -> str | None:
    """Validate a field value against allowed options.

    Exact match wins first. Only then do we fall back to matching an option as
    a substring of a longer phrase (e.g. "severe injuries" -> "severe"). The
    reverse direction (value as substring of an option) is intentionally NOT
    used: it would mis-map "provoked" onto "unprovoked".
    """
    if not value:
        return None
    lower = value.lower().strip().replace(" ", "_")
    if lower in valid_options:
        return lower
    # Option appears as a substring of the (longer) value phrase.
    matches = [opt for opt in valid_options if opt in lower]
    if matches:
        # Prefer the most specific (longest) match when several apply, e.g.
        # "unprovoked_attack" contains both "provoked" and "unprovoked".
        return max(matches, key=len)
    return None


def _normalize_bool(value: object, default: bool = False) -> bool:
    """Normalize nullable/model-generated booleans without truthy-string bugs."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized == "true":
            return True
        if normalized == "false":
            return False
    if value in (0, 1):
        return bool(value)
    return default


def _parse_json_response(text: str) -> dict | None:
    """Extract JSON from Ollama response, handling markdown code blocks."""
    # Try direct parse first
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try extracting from markdown code block
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # Try finding first { to last }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass

    return None


async def _call_ollama(prompt: str) -> str | None:
    """Send a prompt to Ollama and return the response text."""
    headers: dict[str, str] = {}
    if settings.ollama_api_key:
        headers["Authorization"] = f"Bearer {settings.ollama_api_key}"

    async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
        try:
            resp = await client.post(
                f"{settings.ollama_url}/api/generate",
                headers=headers,
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    # Disable reasoning output: glm-5.2 and other thinking-capable
                    # models would otherwise spend the num_predict budget on
                    # <think> blocks and risk truncating/contaminating the JSON.
                    "think": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 2048,
                    },
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
        except httpx.HTTPError:
            logger.exception("ollama: request failed")
            return None


def _sanitize_for_prompt(text: str) -> str:
    """Escape curly braces in user content to prevent format string issues."""
    return text.replace("{", "{{").replace("}", "}}")


# Max characters sent to Ollama per call
MAX_EXTRACTION_CHARS = 4000
MAX_VERIFICATION_CHARS = 3000


async def extract_incident(raw: RawItem) -> ExtractedIncident | None:
    """Extract structured incident data from a raw item using Ollama."""
    safe_text = _sanitize_for_prompt(raw.content[:MAX_EXTRACTION_CHARS])
    today = date.today().isoformat()
    prompt = EXTRACTION_PROMPT.format(text=safe_text, today=today)
    response = await _call_ollama(prompt)

    if not response:
        logger.warning("extractor: no response from Ollama for %s", raw.source_url)
        return None

    data = _parse_json_response(response)
    if not data:
        logger.warning("extractor: failed to parse JSON from Ollama response")
        return None

    # Check relevance
    if not data.get("is_relevant", False):
        logger.debug("extractor: item not relevant: %s", raw.title[:60])
        return None

    # Map and validate fields
    classification = _validate_field(
        data.get("classification"), VALID_CLASSIFICATIONS
    ) or "not_confirmed"

    severity = _validate_field(
        data.get("victim_injury_severity"), VALID_SEVERITIES
    )

    activity = _validate_field(
        data.get("victim_activity"), VALID_ACTIVITIES
    )

    species = _normalize_species(data.get("shark_species"))

    # Date extraction with fallback to source publication date
    incident_date = data.get("incident_date")
    if not incident_date and raw.published_at:
        incident_date = raw.published_at.date().isoformat()
        logger.debug("extractor: using published_at as fallback date for %s", raw.source_url)

    # Geocode location via Nominatim (accurate coastline coordinates)
    location_desc = data.get("location_description") or raw.title
    country = _normalize_country(data.get("country")) or "Unknown"
    state_province = data.get("state_province")
    body_of_water = data.get("body_of_water")

    coords = await geocode_incident(
        location_description=location_desc,
        country=country,
        state_province=state_province,
        body_of_water=body_of_water,
    )
    # Vague locations (just a country/region) geocode to inland centroids;
    # snap those to the nearest coast. Specific locations are never snapped.
    if coords and is_vague_location(location_desc, country, state_province):
        snapped = snap_if_inland(coords[0], coords[1])
        if snapped:
            logger.info(
                "extractor: snapped vague location %r %.0fkm inland -> coast",
                location_desc, snapped[2],
            )
            coords = (snapped[0], snapped[1])
    latitude = coords[0] if coords else None
    longitude = coords[1] if coords else None

    # Build extracted incident
    return ExtractedIncident(
        incident_date=incident_date,
        location_description=location_desc,
        country=country,
        state_province=state_province,
        body_of_water=body_of_water,
        classification=classification,
        report_source=_report_source_for_platform(raw.source_platform),
        report_platform=_report_platform_for_source(raw.source_platform),
        shark_species_suspected=species,
        victim_activity=activity,
        victim_injury_severity=severity,
        victim_name=data.get("victim_name"),
        victim_age=data.get("victim_age"),
        victim_sex=data.get("victim_sex"),
        fatal=_normalize_bool(data.get("fatal")),
        latitude=latitude,
        longitude=longitude,
        description=data.get("description"),
        source_url=raw.source_url,
        source_title=raw.title,
        source_publisher=raw.author,
        source_date=raw.published_at.date() if raw.published_at else None,
        source_type=_source_type_for_platform(raw.source_platform),
        confidence=data.get("confidence", 0.5),
        is_relevant=True,
        raw_item_key=raw.dedup_key,
    )


async def verify_incident(
    incident: ExtractedIncident, raw: RawItem
) -> VerificationResult:
    """Run a verification pass on extracted data using Ollama."""
    incident_dict = incident.model_dump(mode="json")
    safe_data = _sanitize_for_prompt(json.dumps(incident_dict, indent=2, default=str))
    safe_text = _sanitize_for_prompt(raw.content[:MAX_VERIFICATION_CHARS])
    prompt = VERIFICATION_PROMPT.format(data=safe_data, text=safe_text)

    response = await _call_ollama(prompt)
    if not response:
        logger.warning("verifier: no response from Ollama")
        return VerificationResult(is_valid=False, notes="Ollama verification failed")

    data = _parse_json_response(response)
    if not data:
        logger.warning("verifier: failed to parse verification response")
        return VerificationResult(is_valid=False, notes="Failed to parse verification")

    return VerificationResult(
        is_valid=data.get("is_valid", False),
        is_duplicate_likely=data.get("is_duplicate_likely", False),
        corrections=data.get("corrections", {}),
        notes=data.get("notes", ""),
        confidence=data.get("confidence", 0.0),
    )


_CORRECTABLE_FIELDS = frozenset({
    "incident_date", "location_description", "country", "state_province",
    "body_of_water", "fatal", "description", "victim_name", "victim_age", "victim_sex",
})


def apply_corrections(
    incident: ExtractedIncident, verification: VerificationResult
) -> ExtractedIncident:
    """Apply verified corrections to an extracted incident."""
    if not verification.corrections:
        return incident

    update_data = {}
    for field, value in verification.corrections.items():
        if field == "shark_species":
            update_data["shark_species_suspected"] = _normalize_species(value)
        elif field == "classification":
            corrected = _validate_field(value, VALID_CLASSIFICATIONS)
            if corrected:
                update_data["classification"] = corrected
        elif field == "victim_injury_severity":
            corrected = _validate_field(value, VALID_SEVERITIES)
            if corrected:
                update_data["victim_injury_severity"] = corrected
        elif field == "victim_activity":
            corrected = _validate_field(value, VALID_ACTIVITIES)
            if corrected:
                update_data["victim_activity"] = corrected
        elif field == "fatal":
            update_data["fatal"] = _normalize_bool(value, default=incident.fatal)
        elif field in _CORRECTABLE_FIELDS:
            update_data[field] = value
        else:
            logger.debug("extractor: ignoring correction for disallowed field %r", field)

    if update_data:
        return incident.model_copy(update=update_data)
    return incident
