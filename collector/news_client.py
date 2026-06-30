"""OSAF API client for the news_items capture store."""

import logging

import httpx

from collector.config import settings

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
            self._token = resp.json().get("access_token")
            return bool(self._token)
        except httpx.HTTPError:
            logger.exception("news_client: authentication failed")
            return False

    async def upsert(self, payload: dict) -> str | None:
        """Upsert a news item. Returns the row id or None."""
        if not self._token and not await self.authenticate():
            return None
        try:
            resp = await self._client.post(
                "/news", json=payload, headers={"Authorization": f"Bearer {self._token}"}
            )
            if resp.status_code == 401:
                if await self.authenticate():
                    resp = await self._client.post(
                        "/news", json=payload, headers={"Authorization": f"Bearer {self._token}"}
                    )
                else:
                    return None
            resp.raise_for_status()
            return resp.json().get("id")
        except httpx.HTTPError:
            logger.exception("news_client: upsert failed for %s", payload.get("source_url"))
            return None

    async def close(self) -> None:
        await self._client.aclose()
