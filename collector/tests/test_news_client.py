import pytest
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
