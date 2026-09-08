"""Tests for LLM response parsing and Ollama configuration validation."""

import pytest

from collector.config import requires_ollama_api_key
from collector.extractor import _parse_json_response


class TestParseJsonResponse:
    """A model can return valid JSON that is not an object.

    Callers go straight to .get() on the result, so anything other than a dict
    (or None) reaches them as an AttributeError and silently drops the item.
    """

    def test_parses_plain_object(self):
        assert _parse_json_response('{"is_relevant": true}') == {"is_relevant": True}

    def test_parses_fenced_object(self):
        text = '```json\n{"is_relevant": false}\n```'
        assert _parse_json_response(text) == {"is_relevant": False}

    def test_parses_object_embedded_in_prose(self):
        text = 'Here is the result:\n{"is_relevant": true}\nHope that helps.'
        assert _parse_json_response(text) == {"is_relevant": True}

    @pytest.mark.parametrize(
        "payload",
        [
            '[{"is_relevant": true}]',   # array of results
            '["a", "b"]',                # array of strings
            '"just a string"',           # bare string
            "42",                        # bare number
            "true",                      # bare bool
            "null",                      # explicit null
        ],
    )
    def test_rejects_valid_json_that_is_not_an_object(self, payload):
        assert _parse_json_response(payload) is None

    @pytest.mark.parametrize(
        "payload",
        ['```json\n[{"a": 1}]\n```', "```\n[1, 2, 3]\n```"],
    )
    def test_rejects_non_object_inside_code_fence(self, payload):
        assert _parse_json_response(payload) is None

    @pytest.mark.parametrize("payload", ["", "   ", "not json at all", "{broken"])
    def test_rejects_unparseable_text(self, payload):
        assert _parse_json_response(payload) is None

    def test_result_is_always_safe_to_call_get_on(self):
        """The contract callers depend on: dict or None, never anything else."""
        for payload in ['[{"a": 1}]', '"str"', "7", '{"a": 1}', "garbage"]:
            result = _parse_json_response(payload)
            assert result is None or isinstance(result, dict)


class TestRequiresOllamaApiKey:
    @pytest.mark.parametrize(
        "url",
        [
            "https://ollama.com",
            "https://api.ollama.com",
            "http://198.51.100.10:11434",
        ],
    )
    def test_remote_endpoints_require_a_key(self, url):
        assert requires_ollama_api_key(url) is True

    @pytest.mark.parametrize(
        "url",
        [
            "http://localhost:11434",
            "http://127.0.0.1:11434",
            "http://ollama:11434",
            "http://host.docker.internal:11434",
        ],
    )
    def test_local_endpoints_do_not(self, url):
        assert requires_ollama_api_key(url) is False


class TestOllamaRequestShape:
    """The request body must not carry "think".

    Measured against glm-5.3-flash and glm-5.3: sending think=False makes the
    model write its reasoning out as prose ahead of the JSON (~8000 chars, and
    glm-5.3:cloud became unparseable), while omitting the key returns bare JSON
    in ~700 chars. This guards against someone reinstating it from the old
    glm-5.2 comment.
    """

    @pytest.mark.asyncio
    async def test_think_is_not_sent(self, monkeypatch):
        from collector import extractor

        captured = {}

        class _Resp:
            status_code = 200

            def raise_for_status(self): ...

            def json(self): return {"response": '{"is_relevant": false}'}

        class _Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, url, headers=None, json=None):
                captured.update(json)
                return _Resp()

        monkeypatch.setattr(extractor.httpx, "AsyncClient", lambda **kw: _Client())
        await extractor._call_ollama("hello")

        assert "think" not in captured
        assert captured["stream"] is False
        assert captured["options"]["temperature"] == 0.1


class TestCheckModelAvailable:
    """A retired or unknown model must stop startup, not degrade silently."""

    @staticmethod
    def _patch(monkeypatch, *, status=None, raises=None, body=""):
        from collector import extractor

        class _Resp:
            status_code = status
            text = body

        class _Client:
            async def __aenter__(self): return self
            async def __aexit__(self, *a): return False
            async def post(self, *a, **kw):
                if raises is not None:
                    raise raises
                return _Resp()

        monkeypatch.setattr(extractor.httpx, "AsyncClient", lambda **kw: _Client())
        return extractor

    @pytest.mark.parametrize("status", [401, 403, 404, 410])
    @pytest.mark.asyncio
    async def test_fatal_statuses_report_unusable(self, monkeypatch, status):
        ex = self._patch(monkeypatch, status=status, body="model was retired")
        usable, reason = await ex.check_model_available()
        assert usable is False
        assert str(status) in reason

    @pytest.mark.asyncio
    async def test_the_real_qwen_retirement_shape_is_caught(self, monkeypatch):
        """410 + retirement notice is the real shape of a retired model.

        qwen3-coder:480b was the shipped compose/.env.example default and was
        retired upstream on 2026-07-15. Production overrode it and so was never
        affected, but a fresh deploy would have hit exactly this.
        """
        ex = self._patch(
            monkeypatch, status=410,
            body="qwen3-coder:480b was retired at 2026-07-15 00:00:00 -0700 PDT",
        )
        usable, reason = await ex.check_model_available()
        assert usable is False
        assert "retired" in reason

    @pytest.mark.asyncio
    async def test_success_is_usable(self, monkeypatch):
        ex = self._patch(monkeypatch, status=200)
        assert await ex.check_model_available() == (True, "ok")

    @pytest.mark.asyncio
    async def test_network_blip_does_not_block_startup(self, monkeypatch):
        import httpx as _httpx
        ex = self._patch(monkeypatch, raises=_httpx.ConnectError("boom"))
        usable, reason = await ex.check_model_available()
        assert usable is True
        assert "continuing anyway" in reason

    @pytest.mark.asyncio
    async def test_transient_server_error_does_not_block_startup(self, monkeypatch):
        ex = self._patch(monkeypatch, status=503, body="upstream busy")
        usable, reason = await ex.check_model_available()
        assert usable is True
        assert "continuing anyway" in reason
