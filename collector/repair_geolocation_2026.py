"""Repair verified 2026 geolocation errors and clear unsupported guesses.

Coordinates below were reviewed against the incident's source material and a
named-place Nominatim result. Records whose source does not identify a specific
place are cleared rather than assigned an arbitrary state-centroid coastline.

Dry-run is the default. Use ``--apply`` after reviewing the printed changes.
"""

import argparse
import asyncio
from dataclasses import dataclass
import logging

import httpx

from collector.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


def _auth_headers(login: httpx.Response) -> dict[str, str]:
    """Promote the secure login cookie for internal HTTP API requests."""
    token = login.cookies.get("access_token")
    if not token:
        raise RuntimeError("login response did not include an access token")
    return {"Authorization": f"Bearer {token}"}


@dataclass(frozen=True)
class Correction:
    latitude: float | None
    longitude: float | None
    location_description: str | None = None
    state_province: str | None = None

    def payload(self) -> dict:
        data: dict = {
            "coordinates": (
                {"latitude": self.latitude, "longitude": self.longitude}
                if self.latitude is not None and self.longitude is not None
                else None
            ),
            "location_precision": (
                "approximate" if self.latitude is not None else "unknown"
            ),
        }
        if self.location_description:
            data["location_description"] = self.location_description
        if self.state_province:
            data["state_province"] = self.state_province
        return data


CORRECTIONS = {
    # Named Australian locations verified from GSAF/news source material.
    "OSAF-2026-0056": Correction(
        -31.31491, 152.97542, "Point Plomer, north of Port Macquarie", "New South Wales"
    ),
    "OSAF-2026-0055": Correction(
        -41.04760, 145.86670, "Cooee Beach, west of Burnie", "Tasmania"
    ),
    "OSAF-2026-0030": Correction(
        -24.113146, 152.715024, "Lady Elliot Island", "Queensland"
    ),
    # Named US coastal locations that previously resolved to inland namesakes.
    "OSAF-2026-6620": Correction(
        31.80105, -81.09455, "near Ossabaw Island, Georgia", "Georgia"
    ),
    "OSAF-2026-6586": Correction(
        40.59455, -73.50290, "Jones Beach, Long Island, New York", "New York"
    ),
    "OSAF-2026-6611": Correction(
        43.164093, -70.618381, "Long Sands Beach, York", "Maine"
    ),
    # Syndicated coverage of the 35th Street Newport Beach sighting.
    **{
        case: Correction(
            33.616523, -117.933667, "35th Street, Newport Beach", "California"
        )
        for case in (
            "OSAF-2026-6422",
            "OSAF-2026-6424",
            "OSAF-2026-6425",
            "OSAF-2026-6443",
            "OSAF-2026-6456",
        )
    },
    # Coverage and follow-ups for the Big River Beach, Mendocino attack.
    **{
        case: Correction(
            39.303083, -123.794289, "Big River Beach, Mendocino", "California"
        )
        for case in (
            "OSAF-2026-0006",
            "OSAF-2026-0013",
            "OSAF-2026-1117",
            "OSAF-2026-6392",
            "OSAF-2026-6400",
            "OSAF-2026-6401",
        )
    },
    # Source text is regional/aggregate and cannot support a point location.
    "OSAF-2026-0001": Correction(None, None),
    "OSAF-2026-0060": Correction(None, None),
    "OSAF-2026-6391": Correction(None, None),
    "OSAF-2026-6455": Correction(None, None),
}


async def _incident_index(client: httpx.AsyncClient) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    page = 1
    while True:
        response = await client.get(
            "/incidents", params={"page": page, "per_page": 200}
        )
        response.raise_for_status()
        body = response.json()
        rows.update({item["case_number"]: item for item in body["data"]})
        if page >= body["meta"]["pages"]:
            return rows
        page += 1


async def main(*, apply: bool = False) -> None:
    async with httpx.AsyncClient(base_url=settings.osaf_api_url, timeout=30) as client:
        login = await client.post(
            "/auth/login",
            data={
                "username": settings.osaf_username,
                "password": settings.osaf_password,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        login.raise_for_status()
        headers = _auth_headers(login)
        incidents = await _incident_index(client)

        updated = missing = failed = 0
        for case_number, correction in CORRECTIONS.items():
            incident = incidents.get(case_number)
            if not incident:
                logger.warning("%s not found", case_number)
                missing += 1
                continue
            action = "clear unsupported coordinates" if correction.latitude is None else (
                f"move to ({correction.latitude:.6f}, {correction.longitude:.6f})"
            )
            if not apply:
                logger.info("%s WOULD %s", case_number, action)
                continue
            response = await client.put(
                f"/incidents/{incident['id']}",
                json=correction.payload(),
                headers=headers,
            )
            if response.status_code == 200:
                logger.info("%s: %s", case_number, action)
                updated += 1
            else:
                logger.error(
                    "%s update failed (%d): %s",
                    case_number,
                    response.status_code,
                    response.text[:500],
                )
                failed += 1

        logger.info(
            "Done. Planned: %d, Updated: %d, Missing: %d, Failed: %d",
            len(CORRECTIONS), updated, missing, failed,
        )
        if failed:
            raise RuntimeError(f"{failed} geolocation repairs failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    asyncio.run(main(apply=args.apply))
