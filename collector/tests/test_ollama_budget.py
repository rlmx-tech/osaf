"""The token budget shared by thinking and answer, and what happens when it runs out.

glm-5.3-flash reasons before it answers, and `num_predict` caps reasoning and
answer together. Measured 2026-09-08 against the live verification prompt, the
model spent 5,392-9,354 characters thinking; on the long runs the 2048-token
budget was exhausted before it wrote any JSON, so the API returned HTTP 200 with
an empty `response` and `done_reason: "length"`. Four of eight calls came back
empty that way.

The pipeline read that as "no response from Ollama", marked the incident invalid,
and downgraded it to 0% confidence — which fails in the safe direction but
silently suppresses real incidents, and reads in the log exactly like an outage.
"""

import httpx
import pytest

from collector.config import settings
from collector.extractor import _call_ollama


def _patch_ollama(monkeypatch, handler):
    """Route the extractor's own AsyncClient through a mock transport.

    The real class is bound before patching: `collector.extractor.httpx` is the
    httpx module itself, so a factory that called `httpx.AsyncClient` after the
    patch would call itself.
    """
    real_client = httpx.AsyncClient

    def factory(**kwargs):
        kwargs.pop("transport", None)
        return real_client(transport=httpx.MockTransport(handler), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _responder(payload, *, capture=None):
    def handler(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            import json as _json
            capture.update(_json.loads(request.content))
        return httpx.Response(200, json=payload)

    return handler


class TestNormalCompletion:
    @pytest.mark.asyncio
    async def test_returns_the_response_text(self, monkeypatch):
        _patch_ollama(monkeypatch, _responder(
            {"response": '{"is_valid": true}', "done_reason": "stop"}
        ))
        assert await _call_ollama("hello") == '{"is_valid": true}'


class TestTruncationIsDistinguishable:
    @pytest.mark.asyncio
    async def test_truncated_response_is_falsy(self, monkeypatch):
        """Every caller branches on `if not response`, so falsy is the contract."""
        _patch_ollama(monkeypatch, _responder(
            {"response": "", "done_reason": "length", "eval_count": 2048}
        ))
        assert not await _call_ollama("hello")

    @pytest.mark.asyncio
    async def test_truncation_is_named_in_the_log(self, monkeypatch, caplog):
        """An operator must be able to tell a budget overrun from an outage."""
        _patch_ollama(monkeypatch, _responder(
            {"response": "", "done_reason": "length", "eval_count": 2048}
        ))
        with caplog.at_level("WARNING"):
            await _call_ollama("hello")

        assert any(
            "num_predict" in r.message or "truncat" in r.message.lower()
            for r in caplog.records
        ), f"no truncation warning in {[r.message for r in caplog.records]}"

    @pytest.mark.asyncio
    async def test_a_short_answer_that_hit_the_cap_is_still_returned(self, monkeypatch):
        """Truncated but non-empty is the parser's problem, not a dropped call."""
        _patch_ollama(monkeypatch, _responder(
            {"response": '{"is_val', "done_reason": "length"}
        ))
        assert await _call_ollama("hello") == '{"is_val'

    @pytest.mark.asyncio
    async def test_empty_response_without_length_is_not_called_truncation(
        self, monkeypatch, caplog
    ):
        """A model that simply declined should not be reported as out of budget."""
        _patch_ollama(monkeypatch, _responder(
            {"response": "", "done_reason": "stop"}
        ))
        with caplog.at_level("WARNING"):
            result = await _call_ollama("hello")

        assert not result
        assert not any("num_predict" in r.message for r in caplog.records)


class TestBudgetIsConfigurable:
    @pytest.mark.asyncio
    async def test_request_carries_the_configured_budget(self, monkeypatch):
        sent: dict = {}
        _patch_ollama(monkeypatch, _responder({"response": "ok"}, capture=sent))
        monkeypatch.setattr(settings, "ollama_num_predict", 4096)

        await _call_ollama("hello")

        assert sent["options"]["num_predict"] == 4096

    @pytest.mark.asyncio
    async def test_budget_default_leaves_room_for_the_reasoning_measured(self):
        """9,354 characters of thinking is roughly 2,340 tokens. 2048 cannot fit it."""
        assert settings.ollama_num_predict >= 4096
