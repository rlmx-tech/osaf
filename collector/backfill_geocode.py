"""One-time backfill: re-geocode incidents with clearly wrong coordinates.

Only fixes incidents where Nominatim returns a valid result within the expected
state/region. Skips incidents where the current coordinates are reasonable.

Usage (from the production deployment directory):
    docker compose exec collector python -m collector.backfill_geocode [--dry-run] [--limit N]
"""

import argparse
import asyncio
import logging
import os

import httpx

from collector.geocoder import geocode_incident, haversine_km, _in_state_bounds

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)

# Maximum distance (km) a Nominatim correction can move a point.
# 100km is generous for refinement but blocks clearly wrong matches
# (e.g., "Pinellas County coast" moving 191km to Lee County).
MAX_CORRECTION_KM = 100


async def main(dry_run: bool = False, limit: int | None = None) -> None:
    api_url = "http://backend:8000/api/v1"

    async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
        # Authenticate
        username = os.environ.get("COLLECTOR_OSAF_USERNAME", "collector")
        password = os.environ.get("COLLECTOR_OSAF_PASSWORD", "")

        resp = await client.post(
            "/auth/login",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Fetch all incidents (paginated)
        all_incidents: list[dict] = []
        page = 1
        per_page = 100

        while True:
            resp = await client.get(
                "/incidents",
                params={"page": page, "per_page": per_page},
                headers=headers,
            )
            resp.raise_for_status()
            body = resp.json()
            incidents = body.get("data", [])
            if not incidents:
                break
            all_incidents.extend(incidents)
            meta = body.get("meta", {})
            if page >= meta.get("pages", 1):
                break
            page += 1

        # Filter to incidents with coordinates
        geocoded = [i for i in all_incidents if i.get("latitude") is not None]
        logger.info(
            "Fetched %d incidents, %d geocoded", len(all_incidents), len(geocoded),
        )

        if limit:
            geocoded = geocoded[:limit]

        updated = 0
        skipped = 0
        failed = 0

        for i, incident in enumerate(geocoded):
            old_lat = incident["latitude"]
            old_lng = incident["longitude"]
            location = incident.get("location_description", "")
            case_number = incident.get("case_number", "?")
            incident_id = incident["id"]
            country = incident.get("country", "")
            state_prov = incident.get("state_province", "")
            body_water = incident.get("body_of_water", "")

            if not location:
                skipped += 1
                continue

            # Geocode via Nominatim (with state bounds validation)
            result = await geocode_incident(
                location_description=location,
                country=country,
                state_province=state_prov,
                body_of_water=body_water,
            )

            if not result:
                failed += 1
                continue

            new_lat, new_lng = result

            # Skip if coordinates barely changed (< 1km)
            dist = haversine_km(old_lat, old_lng, new_lat, new_lng)
            if dist < 1.0:
                skipped += 1
                continue

            # Safety check: don't move points more than MAX_CORRECTION_KM
            if dist > MAX_CORRECTION_KM:
                logger.debug(
                    "[%d/%d] %s: %r — Nominatim wants %.0fkm move, skipping (too far)",
                    i + 1, len(geocoded), case_number, location, dist,
                )
                skipped += 1
                continue

            if dry_run:
                logger.info(
                    "[%d/%d] %s: %r WOULD move %.1fkm (%.4f,%.4f) -> (%.4f,%.4f)",
                    i + 1, len(geocoded), case_number, location, dist,
                    old_lat, old_lng, new_lat, new_lng,
                )
                updated += 1
                continue

            # Update via PUT API
            update_resp = await client.put(
                f"/incidents/{incident_id}",
                json={"coordinates": {"latitude": new_lat, "longitude": new_lng}},
                headers=headers,
            )

            if update_resp.status_code == 200:
                logger.info(
                    "[%d/%d] %s: %r moved %.1fkm (%.4f,%.4f) -> (%.4f,%.4f)",
                    i + 1, len(geocoded), case_number, location, dist,
                    old_lat, old_lng, new_lat, new_lng,
                )
                updated += 1
            else:
                logger.warning(
                    "[%d/%d] %s: update failed (%d)",
                    i + 1, len(geocoded), case_number, update_resp.status_code,
                )
                failed += 1

        logger.info(
            "Done. Updated: %d, Skipped: %d, Failed: %d", updated, skipped, failed,
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Re-geocode incidents via Nominatim")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, limit=args.limit))
