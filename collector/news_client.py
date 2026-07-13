"""OSAF API client for durable evidence ingestion and the public news feed."""

import hashlib
import json
import logging

import httpx

from collector.config import settings
from collector.models import ExtractedIncident, RawItem, VerificationResult

logger = logging.getLogger(__name__)


class NewsClient:
    """Authenticates with the OSAF API and upserts news items."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(base_url=settings.osaf_api_url, timeout=30)
        self._token: str | None = None

    async def authenticate(self) -> bool:
        try:
            resp = await self._client.post(
                "/auth/login",
                data={"username": settings.osaf_username, "password": settings.osaf_password},
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            # JWT is issued as an httpOnly cookie (web app flow); fall back to body.
            self._token = resp.cookies.get("access_token") or resp.json().get("access_token")
            return bool(self._token)
        except httpx.HTTPError:
            logger.exception("news_client: authentication failed")
            return False

    async def upsert(self, payload: dict) -> str | None:
        """Upsert a news item. Returns the row id or None."""
        response = await self._post_authenticated("/news", payload)
        return response.json().get("id") if response else None

    async def _post_authenticated(self, path: str, payload: dict) -> httpx.Response | None:
        if not self._token and not await self.authenticate():
            return None
        try:
            response = await self._client.post(
                path, json=payload, headers={"Authorization": f"Bearer {self._token}"}
            )
            if response.status_code == 401:
                if not await self.authenticate():
                    return None
                response = await self._client.post(
                    path, json=payload, headers={"Authorization": f"Bearer {self._token}"}
                )
            response.raise_for_status()
            return response
        except httpx.HTTPError:
            logger.exception("news_client: request failed for %s", path)
            return None

    async def capture(self, raw: RawItem) -> dict | None:
        """Persist immutable source evidence and lease its durable extraction job."""
        content = raw.content or ""
        payload = {
            "dedup_key": raw.dedup_key,
            "source_platform": raw.source_platform.value,
            "source_name": raw.source_name,
            "source_url": raw.source_url,
            "title": raw.title,
            "body_excerpt": content[:12000] or None,
            "author": raw.author,
            "published_at": raw.published_at.isoformat() if raw.published_at else None,
            "content_sha256": hashlib.sha256(content.encode()).hexdigest(),
            "raw_metadata": json.loads(json.dumps(raw.extra, default=str)),
        }
        response = await self._post_authenticated("/ingestion/sources", payload)
        return response.json() if response else None

    async def record_observation(
        self,
        job_id: str,
        incident: ExtractedIncident,
        verification: VerificationResult | None,
        event_type: str,
        case_number: str | None = None,
    ) -> str | None:
        payload = {
            "extractor_name": "osaf-collector",
            "model_name": settings.ollama_model,
            "prompt_version": "extract-v3+verify-v2",
            "schema_version": "1",
            "event_type": event_type,
            "confidence": incident.confidence,
            "verification_confidence": verification.confidence if verification else None,
            "payload": incident.model_dump(mode="json"),
            "verification": verification.model_dump(mode="json") if verification else {},
            "validation_errors": [],
            "promoted_case_number": case_number,
        }
        response = await self._post_authenticated(
            f"/ingestion/jobs/{job_id}/observation", payload
        )
        return response.json().get("observation_id") if response else None

    async def complete_without_incident(
        self, job_id: str, event_type: str, outcome: str
    ) -> str | None:
        payload = {
            "extractor_name": "osaf-collector",
            "model_name": settings.ollama_model,
            "prompt_version": "extract-v3",
            "schema_version": "1",
            "event_type": event_type,
            "confidence": None,
            "payload": {"outcome": outcome},
            "verification": {},
            "validation_errors": [],
        }
        response = await self._post_authenticated(
            f"/ingestion/jobs/{job_id}/observation", payload
        )
        return response.json().get("observation_id") if response else None

    async def fail_job(self, job_id: str, reason: str) -> bool:
        response = await self._post_authenticated(
            f"/ingestion/jobs/{job_id}/fail", {"error": reason, "retryable": True}
        )
        return response is not None

    async def close(self) -> None:
        await self._client.aclose()
