"""Shared OSAF API authentication for collector-side scripts.

The API issues the JWT as an HttpOnly cookie named `access_token` (see
app/api/v1/auth.py and app/services/auth_service.COOKIE_NAME); the JSON body
carries no token. Scripts that POST /auth/login must read the cookie — reading
`resp.json()["access_token"]` predates the auth rework and silently yields None.

Usage:
    from collector.osaf_auth import login

    async with httpx.AsyncClient(base_url=settings.osaf_api_url, timeout=30) as client:
        token = await login(client)
        if token is None:
            raise SystemExit("authentication failed")
        headers = {"Authorization": f"Bearer {token}"}
"""

import logging

import httpx

from collector.config import settings

logger = logging.getLogger(__name__)


async def login(client: httpx.AsyncClient) -> str | None:
    """Authenticate with settings.osaf_username/osaf_password; return the JWT or None."""
    try:
        resp = await client.post(
            "/auth/login",
            data={"username": settings.osaf_username, "password": settings.osaf_password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        token = resp.cookies.get("access_token") or resp.json().get("access_token")
        if token:
            logger.info("Authenticated as %s", settings.osaf_username)
            return token
        logger.error("Login returned 200 but no access_token cookie — API contract changed?")
        return None
    except httpx.HTTPError:
        logger.exception("Authentication failed")
        return None
