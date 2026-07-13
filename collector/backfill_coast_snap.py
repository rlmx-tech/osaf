"""One-shot backfill: snap vague-location incidents to the nearest coast.

Vague-location incidents (location == country/region) were geocoded to inland
country centroids. This re-evaluates each incident's STORED coordinates against
the coastline snap rule (collector.coastline) — no Nominatim calls, so it is
instant and not rate-limited — and moves the obvious inland errors to the coast.

Specific-location incidents are never touched, so genuine inland river/lake
incidents are preserved.

Usage (from the production deployment directory):
    docker compose exec collector python -m collector.backfill_coast_snap [--dry-run] [--limit N]
"""

import argparse
import asyncio
import logging
import os

import httpx

from collector.coastline import is_vague_location, snap_if_inland

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger(__name__)


async def _fetch_all_incidents(client: httpx.AsyncClient, headers: dict) -> list[dict]:
    incidents: list[dict] = []
    page = 1
    while True:
        resp = await client.get(
            "/incidents", params={"page": page, "per_page": 100}, headers=headers,
        )
        resp.raise_for_status()
        body = resp.json()
        batch = body.get("data", [])
        if not batch:
            break
        incidents.extend(batch)
        if page >= body.get("meta", {}).get("pages", 1):
            break
        page += 1
    return incidents


async def main(dry_run: bool = False, limit: int | None = None) -> None:
    api_url = "http://backend:8000/api/v1"

    async with httpx.AsyncClient(base_url=api_url, timeout=30) as client:
        username = os.environ.get("COLLECTOR_OSAF_USERNAME", "collector")
        password = os.environ.get("COLLECTOR_OSAF_PASSWORD", "")
        resp = await client.post(
            "/auth/login",
            data={"username": username, "password": password},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        resp.raise_for_status()
        headers = {"Authorization": f"Bearer {resp.json()['access_token']}"}

        incidents = await _fetch_all_incidents(client, headers)
        geocoded = [i for i in incidents if i.get("latitude") is not None]
        logger.info("Fetched %d incidents, %d geocoded", len(incidents), len(geocoded))
        if limit:
            geocoded = geocoded[:limit]

        updated = skipped = failed = 0

        for incident in geocoded:
            try:
                location = incident.get("location_description", "")
                country = incident.get("country", "")
                state = incident.get("state_province", "")

                # Gate 1: only vague-location incidents are eligible.
                if not is_vague_location(location, country, state):
                    skipped += 1
                    continue

                # Gate 2 + 3: on land and clearly inland -> snap stored coords.
                snapped = snap_if_inland(incident["latitude"], incident["longitude"])
                if not snapped:
                    skipped += 1
                    continue

                new_lat, new_lon, moved_km = snapped
                case = incident.get("case_number", "?")

                if dry_run:
                    logger.info(
                        "%s: %r WOULD snap %.0fkm (%.3f,%.3f) -> (%.3f,%.3f)",
                        case, location, moved_km,
                        incident["latitude"], incident["longitude"], new_lat, new_lon,
                    )
                    updated += 1
                    continue

                update = await client.put(
                    f"/incidents/{incident['id']}",
                    json={"coordinates": {"latitude": new_lat, "longitude": new_lon}},
                    headers=headers,
                )
                if update.status_code == 200:
                    logger.info(
                        "%s: %r snapped %.0fkm -> (%.3f,%.3f)",
                        case, location, moved_km, new_lat, new_lon,
                    )
                    updated += 1
                else:
                    logger.warning("%s: update failed (%d)", case, update.status_code)
                    failed += 1
            except Exception:
                logger.exception("backfill: error on incident %s", incident.get("id"))
                failed += 1

        logger.info("Done. Updated: %d, Skipped: %d, Failed: %d", updated, skipped, failed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Snap vague-location incidents to coast")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, limit=args.limit))
