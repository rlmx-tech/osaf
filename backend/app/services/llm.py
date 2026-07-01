"""Ollama Cloud client for backend batch jobs (LLM near-dupe adjudication)."""

import json
import logging
import re

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


async def _call_ollama(prompt: str) -> str | None:
    headers: dict[str, str] = {}
    if settings.ollama_api_key:
        headers["Authorization"] = f"Bearer {settings.ollama_api_key}"
    try:
        async with httpx.AsyncClient(timeout=settings.ollama_timeout) as client:
            resp = await client.post(
                f"{settings.ollama_url}/api/generate",
                headers=headers,
                json={
                    "model": settings.ollama_model,
                    "prompt": prompt,
                    "stream": False,
                    "think": False,
                    "options": {"temperature": 0.1, "num_predict": 2048},
                },
            )
            resp.raise_for_status()
            return resp.json().get("response", "")
    except httpx.HTTPError:
        logger.exception("llm: ollama request failed")
        return None


def _parse_json_response(text: str) -> dict | None:
    """Extract a JSON object from an LLM response (plain, fenced, or embedded)."""
    text = (text or "").strip()
    try:
        val = json.loads(text)
        return val if isinstance(val, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            val = json.loads(m.group(1).strip())
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            val = json.loads(text[start : end + 1])
            return val if isinstance(val, dict) else None
        except json.JSONDecodeError:
            pass
    return None
