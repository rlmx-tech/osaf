"""Integration tests for the durable collector ingestion workflow."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.ingestion import CollectionJob, IncidentCandidate, SourceDocument
from tests.conftest import auth_header


SOURCE = {
    "dedup_key": "youtube:https://example.test/watch/1",
    "source_platform": "youtube",
    "source_name": "Shark Reports",
    "source_url": "https://example.test/watch/1",
    "title": "Shark bite reported at Test Beach",
    "body_excerpt": "A swimmer was bitten near Test Beach on July 12.",
    "published_at": "2026-07-12T12:00:00Z",
    "content_sha256": "a" * 64,
    "raw_metadata": {"poller": "youtube"},
}


@pytest.mark.asyncio
async def test_capture_is_idempotent_and_leases_one_durable_job(client, verified_user, db):
    headers = auth_header(verified_user)

    first = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)
    second = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)

    assert first.status_code == 201
    assert first.json()["should_process"] is True
    assert first.json()["job_status"] == "leased"
    assert second.status_code == 200
    assert second.json()["source_document_id"] == first.json()["source_document_id"]
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["should_process"] is False
    assert len((await db.execute(select(SourceDocument))).scalars().all()) == 1
    assert len((await db.execute(select(CollectionJob))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_expired_lease_can_be_reclaimed(client, verified_user, db):
    headers = auth_header(verified_user)
    first = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)
    job = await db.get(CollectionJob, first.json()["job_id"])
    job.leased_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()

    retried = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)

    assert retried.status_code == 200
    assert retried.json()["should_process"] is True
    assert retried.json()["attempts"] == 2


@pytest.mark.asyncio
async def test_record_observation_completes_job_and_creates_reviewable_candidate(
    client, verified_user, db
):
    headers = auth_header(verified_user)
    captured = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)
    job_id = captured.json()["job_id"]
    observation = {
        "extractor_name": "osaf-collector",
        "model_name": "test-model",
        "prompt_version": "extract-v3",
        "schema_version": "1",
        "event_type": "attack",
        "confidence": 0.91,
        "verification_confidence": 0.88,
        "payload": {
            "incident_date": "2026-07-12",
            "country": "United States",
            "location_description": "Test Beach",
            "classification": "unprovoked",
        },
        "verification": {"is_valid": True, "notes": "Supported by source"},
        "promoted_case_number": None,
    }

    response = await client.post(
        f"/api/v1/ingestion/jobs/{job_id}/observation", json=observation, headers=headers
    )

    assert response.status_code == 201
    assert response.json()["job_status"] == "completed"
    assert response.json()["candidate_status"] == "needs_review"
    candidate = await db.get(IncidentCandidate, response.json()["candidate_id"])
    assert candidate.canonical_incident_id is None
    assert candidate.match_key == "2026-07-12|united states|test beach|unprovoked"


@pytest.mark.asyncio
async def test_record_observation_links_published_candidate(client, verified_user, sample_incident):
    headers = auth_header(verified_user)
    captured = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)
    response = await client.post(
        f"/api/v1/ingestion/jobs/{captured.json()['job_id']}/observation",
        json={
            "extractor_name": "osaf-collector",
            "model_name": "test-model",
            "prompt_version": "extract-v3",
            "event_type": "attack",
            "confidence": 0.9,
            "payload": {"country": "United States", "classification": "unprovoked"},
            "promoted_case_number": sample_incident.case_number,
        },
        headers=headers,
    )

    assert response.status_code == 201
    assert response.json()["candidate_status"] == "published"
    assert response.json()["canonical_incident_id"] == str(sample_incident.id)


@pytest.mark.asyncio
async def test_fail_job_schedules_retry_with_backoff(client, verified_user, db):
    headers = auth_header(verified_user)
    captured = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)
    response = await client.post(
        f"/api/v1/ingestion/jobs/{captured.json()['job_id']}/fail",
        json={"error": "model timeout", "retryable": True},
        headers=headers,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "retrying"
    job = await db.get(CollectionJob, captured.json()["job_id"])
    assert job.available_at > datetime.now(timezone.utc)
    assert job.last_error == "model timeout"


@pytest.mark.asyncio
async def test_admin_can_list_candidates_but_public_cannot(client, verified_user, admin_user):
    headers = auth_header(verified_user)
    captured = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)
    await client.post(
        f"/api/v1/ingestion/jobs/{captured.json()['job_id']}/observation",
        json={
            "extractor_name": "osaf-collector",
            "model_name": "test-model",
            "prompt_version": "extract-v3",
            "event_type": "attack",
            "confidence": 0.9,
            "payload": {"country": "United States", "classification": "unprovoked"},
        },
        headers=headers,
    )

    unauthorized = await client.get("/api/v1/admin/candidates")
    listed = await client.get(
        "/api/v1/admin/candidates?status=needs_review", headers=auth_header(admin_user)
    )

    assert unauthorized.status_code == 401
    assert listed.status_code == 200
    assert listed.json()["meta"]["total"] == 1
    assert listed.json()["data"][0]["source"]["source_url"] == SOURCE["source_url"]


@pytest.mark.asyncio
async def test_admin_can_publish_candidate_from_evidence(
    client, verified_user, admin_user, db
):
    headers = auth_header(verified_user)
    captured = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)
    await client.post(
        "/api/v1/news",
        json={
            "dedup_key": SOURCE["dedup_key"],
            "source_platform": SOURCE["source_platform"],
            "source_name": SOURCE["source_name"],
            "source_url": SOURCE["source_url"],
            "title": SOURCE["title"],
            "event_type": "attack",
        },
        headers=headers,
    )
    observation = await client.post(
        f"/api/v1/ingestion/jobs/{captured.json()['job_id']}/observation",
        json={
            "extractor_name": "osaf-collector",
            "model_name": "test-model",
            "prompt_version": "extract-v3",
            "event_type": "attack",
            "confidence": 0.9,
            "payload": {
                "incident_date": "2026-07-12",
                "country": "United States",
                "location_description": "Test Beach",
                "classification": "unprovoked",
                "fatal": False,
                "source_type": "news_article",
                "source_url": SOURCE["source_url"],
                "source_title": SOURCE["title"],
                "latitude": 29.0,
                "longitude": -80.9,
            },
        },
        headers=headers,
    )
    candidate_id = observation.json()["candidate_id"]

    published = await client.put(
        f"/api/v1/admin/candidates/{candidate_id}/publish",
        json={"notes": "Source checked"},
        headers=auth_header(admin_user),
    )

    assert published.status_code == 200
    assert published.json()["status"] == "published"
    assert published.json()["case_number"].startswith("OSAF-2026-")
    from app.models.news import NewsItem
    news = (await db.execute(select(NewsItem))).scalar_one()
    assert news.promoted_incident_id is not None


@pytest.mark.asyncio
async def test_admin_can_reject_candidate(client, verified_user, admin_user):
    headers = auth_header(verified_user)
    captured = await client.post("/api/v1/ingestion/sources", json=SOURCE, headers=headers)
    observation = await client.post(
        f"/api/v1/ingestion/jobs/{captured.json()['job_id']}/observation",
        json={
            "extractor_name": "osaf-collector",
            "model_name": "test-model",
            "prompt_version": "extract-v3",
            "event_type": "sighting",
            "confidence": 0.5,
            "payload": {"country": "United States", "classification": "sighting"},
        },
        headers=headers,
    )

    rejected = await client.put(
        f"/api/v1/admin/candidates/{observation.json()['candidate_id']}/reject",
        json={"notes": "Roundup, not a discrete event"},
        headers=auth_header(admin_user),
    )

    assert rejected.status_code == 200
    assert rejected.json()["status"] == "rejected"


@pytest.mark.asyncio
async def test_ingestion_health_is_admin_only(client, verified_user, admin_user):
    await client.post(
        "/api/v1/ingestion/sources", json=SOURCE, headers=auth_header(verified_user)
    )

    public_health = await client.get("/health")
    unauthorized = await client.get("/api/v1/admin/ingestion-health")
    response = await client.get(
        "/api/v1/admin/ingestion-health", headers=auth_header(admin_user)
    )

    assert public_health.json() == {"status": "ok"}
    assert unauthorized.status_code == 401
    assert response.status_code == 200
    assert response.json()["leased"] == 1
    assert response.json()["last_source_captured_at"] is not None
