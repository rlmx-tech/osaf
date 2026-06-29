"""Core pipeline: poll → filter → extract → verify → submit."""

import logging
from typing import TYPE_CHECKING

from collector.extractor import apply_corrections, extract_incident, verify_incident
from collector.models import ExtractedIncident, RawItem
from collector.relevance import is_shark_relevant
from collector.state import StateManager
from collector.submitter import OsafSubmitter

if TYPE_CHECKING:
    from collector.news_client import NewsClient

logger = logging.getLogger(__name__)


def derive_event_type(incident: "ExtractedIncident | None") -> str:
    """Map an extraction result to a news_items.event_type value."""
    if incident is None:
        return "news"
    return "sighting" if incident.classification == "sighting" else "attack"


# Minimum confidence threshold to submit
MIN_EXTRACTION_CONFIDENCE = 0.4
MIN_VERIFICATION_CONFIDENCE = 0.5


def _news_payload(
    raw: RawItem,
    event_type: str = "news",
    country: str | None = None,
    ai_confidence: float | None = None,
    promoted_case_number: str | None = None,
) -> dict:
    return {
        "dedup_key": raw.dedup_key,
        "source_platform": raw.source_platform.value,
        "source_name": raw.source_name,
        "source_url": raw.source_url,
        "title": raw.title,
        "summary": raw.content[:2000] if raw.content else None,
        "author": raw.author,
        "image_url": raw.extra.get("image_url") if raw.extra else None,
        "published_at": raw.published_at.isoformat() if raw.published_at else None,
        "event_type": event_type,
        "country": country,
        "ai_confidence": ai_confidence,
        "promoted_case_number": promoted_case_number,
    }


async def process_items(
    items: list[RawItem],
    state: StateManager,
    submitter: OsafSubmitter,
    news_client: "NewsClient",
) -> dict:
    """Poll batch → capture all shark items → promote events to incidents."""
    stats = {
        "processed": 0,
        "captured_news": 0,
        "extracted": 0,
        "verified": 0,
        "submitted": 0,
        "promoted_attack": 0,
        "promoted_sighting": 0,
        "skipped_seen": 0,
        "skipped_not_shark": 0,
        "skipped_irrelevant": 0,
        "skipped_low_confidence": 0,
        "skipped_duplicate": 0,
        "errors": 0,
    }

    for raw in items:
        stats["processed"] += 1

        if state.is_seen(raw.dedup_key):
            stats["skipped_seen"] += 1
            continue

        # GATE 1 — shark-relevant at all?
        if not is_shark_relevant(raw.title, raw.content):
            stats["skipped_not_shark"] += 1
            state.mark_skipped(raw.dedup_key, "not_shark")
            continue

        # Capture into news_items first (resilient — survives extraction failure)
        try:
            await news_client.upsert(_news_payload(raw, event_type="news"))
            stats["captured_news"] += 1
        except Exception:
            logger.exception("pipeline: news capture failed for %s", raw.source_url)

        # GATE 2 — is it a promotable event?
        try:
            incident = await extract_incident(raw)
        except Exception:
            logger.exception("pipeline: extraction failed for %s", raw.source_url)
            stats["errors"] += 1
            state.mark_skipped(raw.dedup_key, "extraction_error")
            continue

        if not incident or not incident.is_relevant:
            # Shark-related but not an event — lives in the feed only.
            stats["skipped_irrelevant"] += 1
            state.mark_seen(raw.dedup_key)
            continue

        stats["extracted"] += 1

        if incident.confidence < MIN_EXTRACTION_CONFIDENCE:
            stats["skipped_low_confidence"] += 1
            state.mark_skipped(raw.dedup_key, f"low_extraction_confidence ({incident.confidence:.0%})")
            continue

        try:
            verification = await verify_incident(incident, raw)
        except Exception:
            logger.exception("pipeline: verification failed for %s", raw.source_url)
            stats["errors"] += 1
            if incident.confidence >= 0.7:
                verification = None
            else:
                state.mark_skipped(raw.dedup_key, "verification_error")
                continue

        if verification:
            stats["verified"] += 1
            if verification.is_duplicate_likely:
                stats["skipped_duplicate"] += 1
                state.mark_skipped(raw.dedup_key, "likely_duplicate")
                continue
            if not verification.is_valid:
                if verification.confidence >= 0.6:
                    stats["skipped_low_confidence"] += 1
                    state.mark_skipped(raw.dedup_key, f"verification_rejected: {verification.notes}")
                    continue
                logger.warning(
                    "pipeline: verifier uncertain (%.0f%%), submitting anyway: %s",
                    verification.confidence * 100, verification.notes,
                )
            incident = apply_corrections(incident, verification)

        event_type = derive_event_type(incident)

        try:
            case_number = await submitter.submit(incident)
        except Exception:
            logger.exception("pipeline: submission failed for %s", raw.source_url)
            stats["errors"] += 1
            continue

        if case_number:
            stats["submitted"] += 1
            if event_type == "sighting":
                stats["promoted_sighting"] += 1
            else:
                stats["promoted_attack"] += 1
            # Link the news item to the promoted incident.
            try:
                await news_client.upsert(_news_payload(
                    raw, event_type=event_type, country=incident.country,
                    ai_confidence=incident.confidence, promoted_case_number=case_number,
                ))
            except Exception:
                logger.exception("pipeline: news promotion-link failed for %s", raw.source_url)
            state.mark_seen(raw.dedup_key, case_number)
            logger.info(
                "pipeline: ✓ %s [%s] — %s, %s (%s)",
                case_number, event_type, incident.location_description,
                incident.country, raw.source_platform.value,
            )
        else:
            stats["errors"] += 1
            state.mark_skipped(raw.dedup_key, "submission_failed")

    return stats
