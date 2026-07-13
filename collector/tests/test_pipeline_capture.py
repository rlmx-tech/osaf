import pytest
from unittest.mock import AsyncMock

from collector.models import ExtractedIncident, RawItem, SourcePlatform, VerificationResult
import collector.pipeline as pipeline


class FakeState:
    def __init__(self): self.seen = {}
    def is_seen(self, k): return k in self.seen
    def mark_seen(self, k, case_number=None): self.seen[k] = case_number
    def mark_skipped(self, k, reason): self.seen[k] = f"skip:{reason}"
    def mark_retryable(self, k, reason): self.seen[k] = f"retry:{reason}"


class FakeNews:
    def __init__(self): self.calls = []
    async def upsert(self, payload):
        self.calls.append(payload)
        return "id1"


def _raw(url, title, content):
    return RawItem(source_platform=SourcePlatform.YOUTUBE, source_name="C",
                   source_url=url, title=title, content=content)


@pytest.mark.asyncio
async def test_non_shark_skipped_no_capture(monkeypatch):
    news = FakeNews()
    submitter = AsyncMock()
    items = [_raw("https://u/1", "City council meeting", "budget")]
    stats = await pipeline.process_items(items, FakeState(), submitter, news)
    assert stats["skipped_not_shark"] == 1
    assert news.calls == []
    submitter.submit.assert_not_called()


@pytest.mark.asyncio
async def test_shark_news_only_captured_not_promoted(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=None))
    news = FakeNews()
    submitter = AsyncMock()
    items = [_raw("https://u/2", "New shark documentary released", "about great white shark")]
    stats = await pipeline.process_items(items, FakeState(), submitter, news)
    assert stats["captured_news"] == 1
    assert len(news.calls) == 1 and news.calls[0]["event_type"] == "news"
    submitter.submit.assert_not_called()


@pytest.mark.asyncio
async def test_sighting_captured_and_promoted(monkeypatch):
    inc = ExtractedIncident(location_description="Bondi", country="Australia",
                            classification="sighting", source_url="https://u/3",
                            source_title="t", confidence=0.9)
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=inc))
    monkeypatch.setattr(pipeline, "verify_incident",
                        AsyncMock(return_value=VerificationResult(is_valid=True, confidence=0.9)))
    news = FakeNews()
    submitter = AsyncMock()
    submitter.submit = AsyncMock(return_value="OSAF-2026-0007")
    items = [_raw("https://u/3", "Great white shark spotted", "drone footage")]
    stats = await pipeline.process_items(items, FakeState(), submitter, news)
    assert stats["promoted_sighting"] == 1
    assert stats["submitted"] == 1
    # two upserts: initial news capture + promotion link
    assert len(news.calls) == 2
    promo = news.calls[-1]
    assert promo["event_type"] == "sighting"
    assert promo["promoted_case_number"] == "OSAF-2026-0007"


@pytest.mark.asyncio
async def test_submission_failure_remains_retryable(monkeypatch):
    inc = ExtractedIncident(location_description="Bondi", country="Australia",
                            classification="sighting", source_url="https://u/4",
                            source_title="t", confidence=0.9)
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=inc))
    monkeypatch.setattr(pipeline, "verify_incident",
                        AsyncMock(return_value=VerificationResult(is_valid=True, confidence=0.9)))
    state = FakeState()
    submitter = AsyncMock()
    submitter.submit = AsyncMock(return_value=None)

    stats = await pipeline.process_items(
        [_raw("https://u/4", "Great white shark spotted", "drone footage")],
        state,
        submitter,
        FakeNews(),
    )

    assert stats["retryable_failures"] == 1
    assert stats["errors"] == 1
    assert state.seen["youtube:https://u/4"] == "retry:submission_failed"


@pytest.mark.asyncio
async def test_news_capture_without_id_is_not_counted(monkeypatch):
    monkeypatch.setattr(pipeline, "extract_incident", AsyncMock(return_value=None))
    news = FakeNews()
    news.upsert = AsyncMock(return_value=None)

    stats = await pipeline.process_items(
        [_raw("https://u/5", "New shark documentary", "great white shark")],
        FakeState(),
        AsyncMock(),
        news,
    )

    assert stats["captured_news"] == 0


@pytest.mark.asyncio
async def test_uncertain_attack_is_downgraded_before_submission(monkeypatch):
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
    submitter = AsyncMock()
    submitter.submit = AsyncMock(return_value="OSAF-2026-0008")

    stats = await pipeline.process_items(
        [_raw("https://u/6", "Swimmer reports shark bite", "headline only")],
        FakeState(),
        submitter,
        FakeNews(),
    )

    assert stats["submitted"] == 1
    submitted_incident = submitter.submit.await_args.args[0]
    assert submitted_incident.classification == "unverified_report"
