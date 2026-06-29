"""Core pipeline: poll → filter → extract → verify → submit."""

import logging

from collector.extractor import apply_corrections, extract_incident, verify_incident
from collector.models import ExtractedIncident, RawItem
from collector.state import StateManager
from collector.submitter import OsafSubmitter

logger = logging.getLogger(__name__)


def derive_event_type(incident: "ExtractedIncident | None") -> str:
    """Map an extraction result to a news_items.event_type value."""
    if incident is None:
        return "news"
    return "sighting" if incident.classification == "sighting" else "attack"


# Minimum confidence threshold to submit
MIN_EXTRACTION_CONFIDENCE = 0.4
MIN_VERIFICATION_CONFIDENCE = 0.5


async def process_items(
    items: list[RawItem],
    state: StateManager,
    submitter: OsafSubmitter,
) -> dict:
    """Process a batch of raw items through the full pipeline.

    Returns stats: {processed, extracted, verified, submitted, skipped, errors}
    """
    stats = {
        "processed": 0,
        "extracted": 0,
        "verified": 0,
        "submitted": 0,
        "skipped_seen": 0,
        "skipped_irrelevant": 0,
        "skipped_low_confidence": 0,
        "skipped_duplicate": 0,
        "errors": 0,
    }

    for raw in items:
        stats["processed"] += 1

        # 1. Dedup check
        if state.is_seen(raw.dedup_key):
            stats["skipped_seen"] += 1
            continue

        # 2. Extract structured data via Ollama
        try:
            incident = await extract_incident(raw)
        except Exception:
            logger.exception("pipeline: extraction failed for %s", raw.source_url)
            stats["errors"] += 1
            state.mark_skipped(raw.dedup_key, "extraction_error")
            continue

        if not incident or not incident.is_relevant:
            stats["skipped_irrelevant"] += 1
            state.mark_skipped(raw.dedup_key, "not_relevant")
            continue

        stats["extracted"] += 1

        # 3. Check extraction confidence
        if incident.confidence < MIN_EXTRACTION_CONFIDENCE:
            stats["skipped_low_confidence"] += 1
            state.mark_skipped(
                raw.dedup_key,
                f"low_extraction_confidence ({incident.confidence:.0%})",
            )
            continue

        # 4. Verify via Ollama
        try:
            verification = await verify_incident(incident, raw)
        except Exception:
            logger.exception("pipeline: verification failed for %s", raw.source_url)
            stats["errors"] += 1
            # Still submit if extraction was confident enough
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
                    # Verifier is confident this data is bad — reject
                    stats["skipped_low_confidence"] += 1
                    state.mark_skipped(raw.dedup_key, f"verification_rejected: {verification.notes}")
                    continue
                # Low-confidence rejection — proceed but log warning
                logger.warning(
                    "pipeline: verifier uncertain (%.0f%%), submitting anyway: %s",
                    verification.confidence * 100,
                    verification.notes,
                )

            # Apply corrections from verification
            incident = apply_corrections(incident, verification)

        # 5. Submit to OSAF API
        try:
            case_number = await submitter.submit(incident)
        except Exception:
            logger.exception("pipeline: submission failed for %s", raw.source_url)
            stats["errors"] += 1
            continue

        if case_number:
            stats["submitted"] += 1
            state.mark_seen(raw.dedup_key, case_number)
            logger.info(
                "pipeline: ✓ %s — %s, %s (%s)",
                case_number,
                incident.location_description,
                incident.country,
                raw.source_platform.value,
            )
        else:
            stats["errors"] += 1
            state.mark_skipped(raw.dedup_key, "submission_failed")

    return stats
