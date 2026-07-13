import pytest
from collector.models import ExtractedIncident, RawItem, SourcePlatform, VerificationResult
from collector.news_client import NewsClient


@pytest.mark.asyncio
async def test_upsert_posts_and_returns_id(monkeypatch):
    client = NewsClient()
    client._token = "tok"  # skip auth

    calls = {}

    class FakeResp:
        status_code = 201
        def raise_for_status(self): pass
        def json(self): return {"id": "abc-123"}

    async def fake_post(path, json=None, headers=None):
        calls["path"] = path
        calls["json"] = json
        return FakeResp()

    monkeypatch.setattr(client._client, "post", fake_post)
    result = await client.upsert({"dedup_key": "k", "title": "shark"})
    assert result == "abc-123"
    assert calls["path"] == "/news"
    assert calls["json"]["dedup_key"] == "k"
    await client.close()


@pytest.mark.asyncio
async def test_capture_posts_hash_and_evidence(monkeypatch):
    client = NewsClient()
    client._token = "tok"
    calls = {}

    class FakeResp:
        status_code = 201
        def raise_for_status(self): pass
        def json(self):
            return {"source_document_id": "source-1", "job_id": "job-1", "should_process": True}

    async def fake_post(path, json=None, headers=None):
        calls.update(path=path, json=json)
        return FakeResp()

    monkeypatch.setattr(client._client, "post", fake_post)
    raw = RawItem(
        source_platform=SourcePlatform.YOUTUBE,
        source_name="Channel",
        source_url="https://example.test/1",
        title="Shark report",
        content="source body",
        extra={"image_url": "https://example.test/image.jpg"},
    )

    result = await client.capture(raw)

    assert result["job_id"] == "job-1"
    assert calls["path"] == "/ingestion/sources"
    assert calls["json"]["body_excerpt"] == "source body"
    assert len(calls["json"]["content_sha256"]) == 64
    assert calls["json"]["raw_metadata"]["image_url"].endswith("image.jpg")
    await client.close()


@pytest.mark.asyncio
async def test_record_observation_posts_model_and_prompt_provenance(monkeypatch):
    client = NewsClient()
    client._token = "tok"
    calls = {}

    class FakeResp:
        status_code = 201
        def raise_for_status(self): pass
        def json(self): return {"observation_id": "observation-1"}

    async def fake_post(path, json=None, headers=None):
        calls.update(path=path, json=json)
        return FakeResp()

    monkeypatch.setattr(client._client, "post", fake_post)
    incident = ExtractedIncident(
        location_description="Test Beach", country="United States",
        classification="unprovoked", source_url="https://example.test/1",
        source_title="Shark report", confidence=0.9,
    )
    verification = VerificationResult(is_valid=True, confidence=0.8, notes="supported")

    result = await client.record_observation(
        "job-1", incident, verification, "attack", "OSAF-2026-0001"
    )

    assert result == "observation-1"
    assert calls["path"] == "/ingestion/jobs/job-1/observation"
    assert calls["json"]["model_name"]
    assert calls["json"]["prompt_version"] == "extract-v3+verify-v2"
    assert calls["json"]["promoted_case_number"] == "OSAF-2026-0001"
    await client.close()


@pytest.mark.asyncio
async def test_authenticate_reads_cookie_token(monkeypatch):
    client = NewsClient()

    class FakeResp:
        cookies = {"access_token": "cookie-token"}
        def raise_for_status(self): pass
        def json(self): return {}

    async def fake_post(*args, **kwargs):
        return FakeResp()

    monkeypatch.setattr(client._client, "post", fake_post)
    assert await client.authenticate() is True
    assert client._token == "cookie-token"
    await client.close()


@pytest.mark.asyncio
async def test_authenticated_post_reauthenticates_once_on_401(monkeypatch):
    client = NewsClient()
    client._token = "expired"
    statuses = [401, 201]

    class FakeResp:
        def __init__(self, status): self.status_code = status
        def raise_for_status(self):
            if self.status_code >= 400:
                raise AssertionError("the retried response should succeed")
        def json(self): return {"id": "news-1"}

    async def fake_post(*args, **kwargs):
        return FakeResp(statuses.pop(0))

    async def fake_authenticate():
        client._token = "fresh"
        return True

    monkeypatch.setattr(client._client, "post", fake_post)
    monkeypatch.setattr(client, "authenticate", fake_authenticate)
    assert await client.upsert({"dedup_key": "k"}) == "news-1"
    assert statuses == []
    await client.close()


@pytest.mark.asyncio
async def test_complete_and_fail_job_use_durable_endpoints(monkeypatch):
    client = NewsClient()
    client._token = "tok"
    calls = []

    class FakeResp:
        status_code = 201
        def raise_for_status(self): pass
        def json(self): return {"observation_id": "obs-1", "status": "retrying"}

    async def fake_post(path, json=None, headers=None):
        calls.append((path, json))
        return FakeResp()

    monkeypatch.setattr(client._client, "post", fake_post)
    assert await client.complete_without_incident("job-1", "news", "not_promotable") == "obs-1"
    assert await client.fail_job("job-2", "model_timeout") is True
    assert calls[0][0] == "/ingestion/jobs/job-1/observation"
    assert calls[1] == (
        "/ingestion/jobs/job-2/fail", {"error": "model_timeout", "retryable": True}
    )
    await client.close()
