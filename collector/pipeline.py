"""Core pipeline: poll → filter → extract → verify → submit."""

import logging
import re
from typing import TYPE_CHECKING

from collector.extractor import apply_corrections, extract_incident, verify_incident
from collector.models import ExtractedIncident, RawItem
from collector.relevance import is_shark_relevant

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

# An item needs this much body text, beyond its own title, before it may become
# an incident. Google News RSS serves the headline as the body, and asked to
# build a dated, geocoded, classified incident from that the extractor guesses:
# retrospectives, follow-ups and policy pieces all come out as fresh attacks.
# Measured 2026-09-08, glm-5.3-flash turned "Three years after fatal shark
# attack, community cements teacher's legacy" into a NEW fatality at 0.80
# confidence, deriving a date by arithmetic. A stronger model made that failure
# more confident, so the control belongs on the input, not on the judgement.
MIN_PROMOTABLE_BODY_CHARS = 400

_HTML_TAG = re.compile(r"<[^>]+>")


def has_promotable_body(raw: RawItem) -> bool:
    """Whether an item carries enough real text to support an incident record.

    Three things are checked, and the character floor is the weakest of them.

    A poller that went looking for an article and came back empty says so in
    extra["has_article_body"], and that answer wins outright. Measured
    2026-09-08 against the live feeds, Google News search summaries are an HTML
    list of *related headlines* running 470-860 characters — long enough to
    clear any floor, and containing no article whatsoever. Pollers that carry
    their own text rather than a link (Reddit, YouTube, the tracker) set no flag
    and are judged on the text alone.

    Markup is then stripped, because tags are not prose, and the title is
    removed, because aggregator stubs are the headline repeated and counting raw
    length would let repetition clear the floor.

    Items that fail are still captured into Shark News — nothing is lost from
    the feed, they simply cannot become incidents.
    """
    if (raw.extra or {}).get("has_article_body") is False:
        return False

    content = _HTML_TAG.sub(" ", raw.content or "").strip()
    if not content:
        return False

    title = (raw.title or "").strip()
    if title:
        content = content.replace(title, " ")

    return len(" ".join(content.split())) >= MIN_PROMOTABLE_BODY_CHARS


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
    news_client: "NewsClient",
) -> dict:
    """Poll batch → capture all shark items → promote events to incidents."""
    stats = {
        "processed": 0,
        "captured_news": 0,
        "extracted": 0,
        "verified": 0,
        "submitted": 0,
        "candidates": 0,
        "promoted_attack": 0,
        "promoted_sighting": 0,
        "skipped_seen": 0,
        "skipped_not_shark": 0,
        "skipped_headline_only": 0,
        "skipped_irrelevant": 0,
        "skipped_low_confidence": 0,
        "skipped_duplicate": 0,
        "retryable_failures": 0,
        "errors": 0,
    }

    for raw in items:
        stats["processed"] += 1

        # Capture evidence and acquire a durable DB lease before doing any work.
        try:
            capture = await news_client.capture(raw)
        except Exception:
            logger.exception("pipeline: durable capture failed for %s", raw.source_url)
            capture = None
        if not capture:
            stats["errors"] += 1
            stats["retryable_failures"] += 1
            continue
        if not capture.get("should_process"):
            stats["skipped_seen"] += 1
            continue
        job_id = capture["job_id"]

        # GATE 1 — shark-relevant at all?
        if not is_shark_relevant(
            raw.title,
            raw.content,
            trusted_shark_source=bool(
                raw.extra and raw.extra.get("trusted_shark_source")
            ),
        ):
            stats["skipped_not_shark"] += 1
            await news_client.complete_without_incident(job_id, "not_relevant", "not_shark")
            continue

        # Capture into news_items first (resilient — survives extraction failure)
        try:
            news_id = await news_client.upsert(_news_payload(raw, event_type="news"))
            if news_id:
                stats["captured_news"] += 1
            else:
                logger.warning("pipeline: news capture returned no id for %s", raw.source_url)
        except Exception:
            logger.exception("pipeline: news capture failed for %s", raw.source_url)

        # GATE 1.5 — is there an article behind this, or just a headline?
        # Checked before extraction so a stub never reaches the model at all.
        if not has_promotable_body(raw):
            stats["skipped_headline_only"] += 1
            await news_client.complete_without_incident(job_id, "news", "headline_only")
            continue

        # GATE 2 — is it a promotable event?
        try:
            incident = await extract_incident(raw)
        except Exception:
            logger.exception("pipeline: extraction failed for %s", raw.source_url)
            stats["errors"] += 1
            stats["retryable_failures"] += 1
            await news_client.fail_job(job_id, "extraction_error")
            continue

        if not incident or not incident.is_relevant:
            # Shark-related but not an event — lives in the feed only.
            stats["skipped_irrelevant"] += 1
            await news_client.complete_without_incident(job_id, "news", "not_promotable")
            continue

        stats["extracted"] += 1

        if incident.confidence < MIN_EXTRACTION_CONFIDENCE:
            stats["skipped_low_confidence"] += 1
            await news_client.record_observation(
                job_id, incident, None, derive_event_type(incident)
            )
            continue

        try:
            verification = await verify_incident(incident, raw)
        except Exception:
            logger.exception("pipeline: verification failed for %s", raw.source_url)
            stats["errors"] += 1
            if incident.confidence >= 0.7:
                verification = None
            else:
                stats["retryable_failures"] += 1
                await news_client.fail_job(job_id, "verification_error")
                continue

        if verification:
            stats["verified"] += 1
            if verification.is_duplicate_likely:
                stats["skipped_duplicate"] += 1
                await news_client.record_observation(
                    job_id, incident, verification, derive_event_type(incident)
                )
                continue
            if not verification.is_valid:
                if verification.confidence >= 0.6:
                    stats["skipped_low_confidence"] += 1
                    await news_client.record_observation(
                        job_id, incident, verification, derive_event_type(incident)
                    )
                    continue
                logger.warning(
                    "pipeline: verifier uncertain (%.0f%%), downgrading report: %s",
                    verification.confidence * 100, verification.notes,
                )
                if incident.classification != "sighting":
                    incident = incident.model_copy(
                        update={"classification": "unverified_report"}
                    )
            incident = apply_corrections(incident, verification)

        event_type = derive_event_type(incident)

        # Classification is visible in the news feed, but canonical publication
        # now requires an explicit admin review of the evidence candidate.
        try:
            await news_client.upsert(_news_payload(
                raw, event_type=event_type, country=incident.country,
                ai_confidence=incident.confidence,
            ))
        except Exception:
            logger.exception("pipeline: news classification update failed for %s", raw.source_url)

        observation_id = await news_client.record_observation(
            job_id, incident, verification, event_type
        )
        if observation_id:
            stats["candidates"] += 1
            logger.info(
                "pipeline: candidate [%s] — %s, %s (%s)",
                event_type, incident.location_description,
                incident.country, raw.source_platform.value,
            )
        else:
            stats["errors"] += 1
            stats["retryable_failures"] += 1
            await news_client.fail_job(job_id, "observation_failed")

    return stats
