import pytest
from unittest.mock import AsyncMock

from collector.models import ExtractedIncident, RawItem, SourcePlatform, VerificationResult
import collector.pipeline as pipeline


class FakeNews:
    def __init__(self):
        self.calls = []
        self.captures = []
        self.observations = []
        self.failures = []
    async def capture(self, raw):
        self.captures.append(raw)
        return {"job_id": f"job-{len(self.captures)}", "should_process": True}
    async def upsert(self, payload):
        self.calls.append(payload)
        return "id1"
    async def record_observation(self, job_id, incident, verification, event_type, case_number=None):
        self.observations.append({
            "job_id": job_id, "incident": incident, "verification": verification,
            "event_type": event_type, "case_number": case_number,
        })
        return "observation-1"
    async def complete_without_incident(self, job_id, event_type, outcome):
        self.observations.append({"job_id": job_id, "event_type": event_type, "outcome": outcome})
        return "observation-1"
    async def fail_job(self, job_id, reason):
        self.failures.append({"job_id": job_id, "reason": reason})


def _raw(url, title, content):
    return RawItem(source_platform=SourcePlatform.YOUTUBE, source_name="C",
                   source_url=url, title=title, content=content)


@pytest.mark.asyncio
async def test_non_shark_skipped_no_capture(monkeypatch):
    news = FakeNews()
    items = [_raw("https://u/1", "City council meeting", "budget")]
    stats = await pipeline.process_items(items, news)
    assert stats["skipped_not_shark"] == 1
    assert len(news.captures) == 1
    assert news.calls == []
    assert news.observations[0]["event_type"] == "not_relevant"


@pytest.mark.asyncio
async def test_shark_news_only_captured_not_promoted(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=None))
    news = FakeNews()
    items = [_raw("https://u/2", "New shark documentary released", "about great white shark")]
    stats = await pipeline.process_items(items, news)
    assert stats["captured_news"] == 1
    assert len(news.calls) == 1 and news.calls[0]["event_type"] == "news"
    assert news.observations[0]["event_type"] == "news"


@pytest.mark.asyncio
async def test_trusted_shark_source_context_reaches_capture_gate(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=None))
    news = FakeNews()
    raw = _raw(
        "https://u/context",
        "Matawan River Attacks Revisited - Jaws",
        "",
    )
    raw.extra["trusted_shark_source"] = True

    stats = await pipeline.process_items([raw], news)

    assert stats["captured_news"] == 1
    assert stats["skipped_not_shark"] == 0


@pytest.mark.asyncio
async def test_sighting_becomes_candidate_without_auto_publish(monkeypatch):
    inc = ExtractedIncident(location_description="Bondi", country="Australia",
                            classification="sighting", source_url="https://u/3",
                            source_title="t", confidence=0.9)
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=inc))
    monkeypatch.setattr(pipeline, "verify_incident",
                        AsyncMock(return_value=VerificationResult(is_valid=True, confidence=0.9)))
    news = FakeNews()
    items = [_raw("https://u/3", "Great white shark spotted", "drone footage")]
    stats = await pipeline.process_items(items, news)
    assert stats["candidates"] == 1
    assert stats["submitted"] == 0
    # two upserts: initial news capture + extracted event classification
    assert len(news.calls) == 2
    promo = news.calls[-1]
    assert promo["event_type"] == "sighting"
    assert promo["promoted_case_number"] is None
    assert news.observations[0]["case_number"] is None


@pytest.mark.asyncio
async def test_candidate_recording_failure_remains_retryable(monkeypatch):
    inc = ExtractedIncident(location_description="Bondi", country="Australia",
                            classification="sighting", source_url="https://u/4",
                            source_title="t", confidence=0.9)
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=inc))
    monkeypatch.setattr(pipeline, "verify_incident",
                        AsyncMock(return_value=VerificationResult(is_valid=True, confidence=0.9)))
    news = FakeNews()
    news.record_observation = AsyncMock(return_value=None)

    stats = await pipeline.process_items(
        [_raw("https://u/4", "Great white shark spotted", "drone footage")],
        news,
    )

    assert stats["retryable_failures"] == 1
    assert stats["errors"] == 1
    assert news.failures == [{"job_id": "job-1", "reason": "observation_failed"}]


@pytest.mark.asyncio
async def test_durable_completed_job_is_not_reprocessed():
    news = FakeNews()
    async def already_done(raw):
        return {"job_id": "job-existing", "should_process": False}
    news.capture = already_done

    stats = await pipeline.process_items(
        [_raw("https://u/done", "Shark bite reported", "shark bite")],
        news,
    )

    assert stats["skipped_seen"] == 1


@pytest.mark.asyncio
async def test_news_capture_without_id_is_not_counted(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=None))
    news = FakeNews()
    news.upsert = AsyncMock(return_value=None)

    stats = await pipeline.process_items(
        [_raw("https://u/5", "New shark documentary", "great white shark")],
        news,
    )

    assert stats["captured_news"] == 0


@pytest.mark.asyncio
async def test_uncertain_attack_is_downgraded_before_candidate_recording(monkeypatch):
    inc = ExtractedIncident(
        location_description="Jones Beach",
        country="United States",
        classification="unprovoked",
        source_url="https://u/6",
        source_title="t",
        confidence=0.9,
    )
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=inc))
    monkeypatch.setattr(
        pipeline,
        "verify_incident",
        AsyncMock(return_value=VerificationResult(is_valid=False, confidence=0.3)),
    )
    news = FakeNews()

    stats = await pipeline.process_items(
        [_raw("https://u/6", "Swimmer reports shark bite", "headline only")],
        news,
    )

    assert stats["candidates"] == 1
    observed_incident = news.observations[0]["incident"]
    assert observed_incident.classification == "unverified_report"


@pytest.mark.asyncio
async def test_capture_failure_is_retryable():
    news = FakeNews()
    news.capture = AsyncMock(return_value=None)

    stats = await pipeline.process_items(
        [_raw("https://u/capture-error", "Shark report", "shark")], news
    )

    assert stats["errors"] == 1
    assert stats["retryable_failures"] == 1


@pytest.mark.asyncio
async def test_extraction_exception_fails_durable_job(monkeypatch):
    monkeypatch.setattr(
        pipeline, "extract_incident", AsyncMock(side_effect=RuntimeError("model down"))
    )
    news = FakeNews()

    stats = await pipeline.process_items(
        [_raw("https://u/extract-error", "Shark bite report", "shark bite")], news
    )

    assert stats["retryable_failures"] == 1
    assert news.failures == [{"job_id": "job-1", "reason": "extraction_error"}]


@pytest.mark.asyncio
async def test_verification_exception_on_uncertain_extraction_retries(monkeypatch):
    incident = ExtractedIncident(
        location_description="Test Beach", country="Australia",
        classification="sighting", source_url="https://u/verify-error",
        source_title="t", confidence=0.6,
    )
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=incident))
    monkeypatch.setattr(
        pipeline, "verify_incident", AsyncMock(side_effect=RuntimeError("verifier down"))
    )
    news = FakeNews()

    stats = await pipeline.process_items(
        [_raw("https://u/verify-error", "Shark sighting", "shark spotted")], news
    )

    assert stats["retryable_failures"] == 1
    assert news.failures == [{"job_id": "job-1", "reason": "verification_error"}]


@pytest.mark.asyncio
async def test_verifier_likely_duplicate_stays_reviewable(monkeypatch):
    incident = ExtractedIncident(
        location_description="Test Beach", country="Australia",
        classification="sighting", source_url="https://u/dupe",
        source_title="t", confidence=0.9,
    )
    verification = VerificationResult(
        is_valid=True, is_duplicate_likely=True, confidence=0.9
    )
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=incident))
    monkeypatch.setattr(pipeline, "verify_incident", AsyncMock(return_value=verification))
    news = FakeNews()

    stats = await pipeline.process_items(
        [_raw("https://u/dupe", "Shark sighting", "shark spotted")], news
    )

    assert stats["skipped_duplicate"] == 1
    assert news.observations[0]["verification"].is_duplicate_likely is True
