"""OSAF API client — authenticates and submits extracted incidents."""

import logging

import httpx

from collector.config import settings
from collector.models import ExtractedIncident

logger = logging.getLogger(__name__)


class OsafSubmitter:
    """Authenticates with the OSAF API and submits incidents."""

    def __init__(self) -> None:
        self._client = httpx.AsyncClient(
            base_url=settings.osaf_api_url,
            timeout=30,
        )
        self._token: str | None = None

    async def authenticate(self) -> bool:
        """Login to the OSAF API and store the JWT token."""
        try:
            resp = await self._client.post(
                "/auth/login",
                data={
                    "username": settings.osaf_username,
                    "password": settings.osaf_password,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            resp.raise_for_status()
            self._token = resp.json().get("access_token")
            if self._token:
                logger.info("submitter: authenticated as %s", settings.osaf_username)
                return True
            logger.error("submitter: no token in login response")
            return False
        except httpx.HTTPError:
            logger.exception("submitter: authentication failed")
            return False

    async def submit(self, incident: ExtractedIncident) -> str | None:
        """Submit an incident to the OSAF API. Returns the case number or None."""
        if not self._token:
            if not await self.authenticate():
                return None

        effective_date = incident.incident_date or incident.source_date
        payload = {
            "incident_date": str(effective_date) if effective_date else None,
            "location_description": incident.location_description,
            "country": incident.country,
            "state_province": incident.state_province,
            "body_of_water": incident.body_of_water,
            "classification": incident.classification,
            "report_source": incident.report_source,
            "report_platform": incident.report_platform,
            "shark_species_suspected": incident.shark_species_suspected,
            "victim_activity": incident.victim_activity,
            "victim_injury_severity": incident.victim_injury_severity,
            "victim_name": incident.victim_name,
            "victim_age": incident.victim_age,
            "victim_sex": incident.victim_sex,
            "fatal": incident.fatal,
            "description": incident.description,
            "coordinates": (
                {"latitude": incident.latitude, "longitude": incident.longitude}
                if incident.latitude is not None and incident.longitude is not None
                else None
            ),
            "location_precision": "approximate",
            "sources": [
                {
                    "source_type": incident.source_type,
                    "source_url": incident.source_url,
                    "source_title": incident.source_title,
                    "source_publisher": incident.source_publisher,
                    "source_date": str(incident.source_date) if incident.source_date else None,
                    "source_notes": f"Auto-collected by OSAF Collector (confidence: {incident.confidence:.0%})",
                }
            ],
        }

        try:
            resp = await self._client.post(
                "/submissions",
                json=payload,
                headers={"Authorization": f"Bearer {self._token}"},
            )

            # Handle token expiry
            if resp.status_code == 401:
                logger.info("submitter: token expired, re-authenticating")
                if await self.authenticate():
                    resp = await self._client.post(
                        "/submissions",
                        json=payload,
                        headers={"Authorization": f"Bearer {self._token}"},
                    )
                else:
                    return None

            resp.raise_for_status()
            data = resp.json()
            case_number = data.get("case_number", "")
            logger.info(
                "submitter: submitted %s — %s (%s)",
                case_number,
                incident.location_description,
                incident.classification,
            )
            return case_number

        except httpx.HTTPStatusError as exc:
            detail = ""
            try:
                detail = exc.response.json().get("detail", "")
            except Exception:
                pass
            logger.error(
                "submitter: submission failed (%d): %s",
                exc.response.status_code,
                detail,
            )
            return None
        except httpx.HTTPError:
            logger.exception("submitter: submission request failed")
            return None

    async def close(self) -> None:
        await self._client.aclose()
