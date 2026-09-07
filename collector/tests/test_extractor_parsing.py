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
