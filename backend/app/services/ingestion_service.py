import hashlib
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.incident import Incident
from app.models.news import NewsItem
from app.models.ingestion import (
    CollectionJob,
    ExtractedObservation,
    IncidentCandidate,
    SourceDocument,
)
from app.schemas.ingestion import JobFailure, ObservationCreate, SourceDocumentCreate
from app.schemas.incident import IncidentCreate
from app.models.user import User

LEASE_DURATION = timedelta(minutes=15)
INITIAL_RETRY_DELAY = timedelta(minutes=5)
MAX_RETRY_DELAY = timedelta(hours=6)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_match_part(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def build_match_key(payload: dict[str, Any]) -> str | None:
    """Build a conservative deterministic key; incomplete reports stay ungrouped."""
    parts = [
        payload.get("incident_date"),
        payload.get("country"),
        payload.get("location_description"),
        payload.get("classification"),
    ]
    if not all(parts):
        return None
    return "|".join(_normalize_match_part(part) for part in parts)


class IngestionService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def capture_source(
        self, data: SourceDocumentCreate, worker: str
    ) -> tuple[SourceDocument, CollectionJob, bool, bool]:
        """Idempotently capture evidence and atomically lease its extraction job."""
        now = _utcnow()
        source_id = uuid.uuid4()
        inserted_id = (
            await self.db.execute(
                pg_insert(SourceDocument)
                .values(
                    id=source_id,
                    dedup_key=data.dedup_key,
                    source_platform=data.source_platform,
                    source_name=data.source_name,
                    source_url=data.source_url,
                    title=data.title,
                    body_excerpt=data.body_excerpt,
                    author=data.author,
                    published_at=data.published_at,
                    content_sha256=data.content_sha256,
                    raw_metadata=data.raw_metadata,
                    last_seen_at=now,
                )
                .on_conflict_do_nothing(index_elements=["dedup_key"])
                .returning(SourceDocument.id)
            )
        ).scalar_one_or_none()
        created = inserted_id is not None
        result = await self.db.execute(
            select(SourceDocument)
            .where(SourceDocument.dedup_key == data.dedup_key)
            .with_for_update()
        )
        source = result.scalar_one()
        if not created:
            # Evidence content is immutable; only record that the source was observed again.
            source.last_seen_at = now

        job_result = await self.db.execute(
            select(CollectionJob)
            .where(
                CollectionJob.source_document_id == source.id,
                CollectionJob.job_type == "extract",
            )
            .with_for_update()
        )
        job = job_result.scalar_one_or_none()
        if job is None:
            job = CollectionJob(
                source_document_id=source.id,
                job_type="extract",
                status="leased",
                attempts=1,
                leased_by=worker,
                leased_until=now + LEASE_DURATION,
                available_at=now,
            )
            self.db.add(job)
            should_process = True
        else:
            lease_expired = job.status == "leased" and (
                job.leased_until is None or job.leased_until <= now
            )
            retry_due = job.status in {"queued", "retrying"} and job.available_at <= now
            should_process = lease_expired or retry_due
            if should_process:
                job.status = "leased"
                job.attempts += 1
                job.leased_by = worker
                job.leased_until = now + LEASE_DURATION
                job.last_error = None

        await self.db.commit()
        await self.db.refresh(source)
        await self.db.refresh(job)
        return source, job, should_process, created

    async def record_observation(
        self, job_id: uuid.UUID, data: ObservationCreate
    ) -> tuple[ExtractedObservation, IncidentCandidate | None, CollectionJob]:
        job = (
            await self.db.execute(
                select(CollectionJob)
                .where(CollectionJob.id == job_id)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="Collection job not found")
        if job.status == "dead_letter":
            raise HTTPException(status_code=409, detail="Collection job is dead-lettered")

        canonical_id = None
        if data.promoted_case_number:
            canonical_id = (
                await self.db.execute(
                    select(Incident.id).where(Incident.case_number == data.promoted_case_number)
                )
            ).scalar_one_or_none()
            if canonical_id is None:
                raise HTTPException(status_code=422, detail="Promoted incident was not found")

        payload_json = json.dumps(data.payload, sort_keys=True, separators=(",", ":"), default=str)
        payload_sha256 = hashlib.sha256(payload_json.encode()).hexdigest()
        existing = (
            await self.db.execute(
                select(ExtractedObservation).where(
                    ExtractedObservation.source_document_id == job.source_document_id,
                    ExtractedObservation.extractor_name == data.extractor_name,
                    ExtractedObservation.prompt_version == data.prompt_version,
                    ExtractedObservation.payload_sha256 == payload_sha256,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            candidate = await self.db.get(IncidentCandidate, existing.candidate_id)
            return existing, candidate, job
        if job.status != "leased":
            raise HTTPException(status_code=409, detail="Collection job is not actively leased")

        candidate = None
        if data.event_type in {"attack", "sighting"}:
            match_key = build_match_key(data.payload)
            if match_key:
                candidate = (
                    await self.db.execute(
                        select(IncidentCandidate)
                        .where(
                            IncidentCandidate.match_key == match_key,
                            IncidentCandidate.status.in_(("needs_review", "published")),
                        )
                        .order_by(IncidentCandidate.created_at)
                        .with_for_update()
                    )
                ).scalars().first()
            if candidate is None:
                candidate = IncidentCandidate(
                    status="published" if canonical_id else "needs_review",
                    match_key=match_key,
                    match_score=1.0 if match_key else None,
                    match_rationale=(
                        "Exact normalized date, country, location, and classification"
                        if match_key else "Insufficient deterministic fields; manual review required"
                    ),
                    canonical_incident_id=canonical_id,
                )
                self.db.add(candidate)
                await self.db.flush()
            elif canonical_id and candidate.canonical_incident_id is None:
                candidate.canonical_incident_id = canonical_id
                candidate.status = "published"

        observation = ExtractedObservation(
            source_document_id=job.source_document_id,
            candidate_id=candidate.id if candidate else None,
            extractor_name=data.extractor_name,
            model_name=data.model_name,
            prompt_version=data.prompt_version,
            schema_version=data.schema_version,
            payload=data.payload,
            payload_sha256=payload_sha256,
            event_type=data.event_type,
            confidence=data.confidence,
            verification_confidence=data.verification_confidence,
            verification=data.verification,
            validation_errors=data.validation_errors,
        )
        self.db.add(observation)
        now = _utcnow()
        job.status = "completed"
        job.completed_at = now
        job.leased_until = None
        job.result = {
            "outcome": "published" if canonical_id else data.event_type,
            "candidate_id": str(candidate.id) if candidate else None,
            "canonical_incident_id": str(canonical_id) if canonical_id else None,
        }
        await self.db.commit()
        await self.db.refresh(observation)
        return observation, candidate, job

    async def fail_job(self, job_id: uuid.UUID, data: JobFailure) -> CollectionJob:
        job = (
            await self.db.execute(
                select(CollectionJob).where(CollectionJob.id == job_id).with_for_update()
            )
        ).scalar_one_or_none()
        if job is None:
            raise HTTPException(status_code=404, detail="Collection job not found")
        now = _utcnow()
        terminal = not data.retryable or job.attempts >= job.max_attempts
        delay_seconds = min(
            INITIAL_RETRY_DELAY.total_seconds() * (2 ** max(job.attempts - 1, 0)),
            MAX_RETRY_DELAY.total_seconds(),
        )
        job.status = "dead_letter" if terminal else "retrying"
        job.last_error = data.error
        job.available_at = now if terminal else now + timedelta(seconds=delay_seconds)
        job.leased_until = None
        await self.db.commit()
        await self.db.refresh(job)
        return job

    async def list_candidates(
        self, status: str | None, page: int, per_page: int
    ) -> dict[str, Any]:
        filters = [IncidentCandidate.status == status] if status else []
        total = (
            await self.db.execute(
                select(func.count()).select_from(IncidentCandidate).where(*filters)
            )
        ).scalar_one()
        candidates = (
            await self.db.execute(
                select(IncidentCandidate)
                .where(*filters)
                .options(
                    selectinload(IncidentCandidate.observations).selectinload(
                        ExtractedObservation.source_document
                    )
                )
                .order_by(IncidentCandidate.created_at.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
            )
        ).scalars().all()

        rows = []
        for candidate in candidates:
            observation = (
                max(candidate.observations, key=lambda item: item.created_at)
                if candidate.observations else None
            )
            source = observation.source_document if observation else None
            rows.append({
                "id": str(candidate.id),
                "status": candidate.status,
                "match_key": candidate.match_key,
                "match_score": candidate.match_score,
                "match_rationale": candidate.match_rationale,
                "canonical_incident_id": (
                    str(candidate.canonical_incident_id) if candidate.canonical_incident_id else None
                ),
                "created_at": candidate.created_at.isoformat(),
                "observation": {
                    "id": str(observation.id),
                    "event_type": observation.event_type,
                    "confidence": observation.confidence,
                    "verification_confidence": observation.verification_confidence,
                    "payload": observation.payload,
                    "model_name": observation.model_name,
                    "prompt_version": observation.prompt_version,
                } if observation else None,
                "source": {
                    "id": str(source.id),
                    "source_url": source.source_url,
                    "title": source.title,
                    "source_name": source.source_name,
                    "captured_at": source.captured_at.isoformat(),
                } if source else None,
                "observation_count": len(candidate.observations),
            })
        return {"data": rows, "meta": {"total": total, "page": page, "per_page": per_page}}

    async def review_candidate(
        self, candidate_id: uuid.UUID, action: str, admin: User, notes: str | None
    ) -> dict[str, Any]:
        candidate = (
            await self.db.execute(
                select(IncidentCandidate)
                .where(IncidentCandidate.id == candidate_id)
                .options(
                    selectinload(IncidentCandidate.observations).selectinload(
                        ExtractedObservation.source_document
                    )
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        if candidate is None:
            raise HTTPException(status_code=404, detail="Incident candidate not found")
        if candidate.status != "needs_review":
            raise HTTPException(status_code=409, detail="Candidate has already been reviewed")

        now = _utcnow()
        if action == "reject":
            candidate.status = "rejected"
            candidate.review_notes = notes
            candidate.reviewed_by = admin.id
            candidate.reviewed_at = now
            await self.db.commit()
            return {"id": str(candidate.id), "status": candidate.status, "case_number": None}

        if not candidate.observations:
            raise HTTPException(status_code=422, detail="Candidate has no supporting observation")
        observation = max(candidate.observations, key=lambda item: item.created_at)
        source = observation.source_document
        payload = dict(observation.payload)
        incident_fields = set(IncidentCreate.model_fields) - {"sources", "coordinates"}
        incident_data = {key: payload[key] for key in incident_fields if payload.get(key) is not None}
        latitude = payload.get("latitude")
        longitude = payload.get("longitude")
        if latitude is not None and longitude is not None:
            incident_data["coordinates"] = {"latitude": latitude, "longitude": longitude}
        incident_data["sources"] = [{
            "source_type": payload.get("source_type") or "other",
            "source_url": payload.get("source_url") or source.source_url,
            "source_title": payload.get("source_title") or source.title,
            "source_publisher": payload.get("source_publisher") or source.source_name,
            "source_date": payload.get("source_date"),
            "source_notes": "Published from reviewed ingestion evidence",
        }]
        try:
            submission = IncidentCreate.model_validate(incident_data)
        except ValidationError as exc:
            raise HTTPException(
                status_code=422,
                detail={"message": "Candidate data is not publishable", "errors": exc.errors()},
            ) from exc

        # Import here to avoid a module cycle during application startup.
        from app.services.submission_service import SubmissionService

        incident = await SubmissionService(self.db).submit_incident(submission, admin)
        candidate.status = "published"
        candidate.canonical_incident_id = incident.id
        candidate.review_notes = notes
        candidate.reviewed_by = admin.id
        candidate.reviewed_at = now
        source_ids = {item.source_document_id for item in candidate.observations}
        await self.db.execute(
            update(NewsItem)
            .where(NewsItem.source_document_id.in_(source_ids))
            .values(
                promoted_incident_id=incident.id,
                event_type=observation.event_type,
                country=payload.get("country"),
            )
        )
        await self.db.commit()
        return {
            "id": str(candidate.id),
            "status": candidate.status,
            "case_number": incident.case_number,
            "canonical_incident_id": str(incident.id),
        }

    async def health_summary(self) -> dict[str, Any]:
        counts = dict((await self.db.execute(
            select(CollectionJob.status, func.count()).group_by(CollectionJob.status)
        )).all())
        last_capture = (await self.db.execute(select(func.max(SourceDocument.captured_at)))).scalar()
        last_completion = (await self.db.execute(select(func.max(CollectionJob.completed_at)))).scalar()
        return {
            "queued": counts.get("queued", 0),
            "leased": counts.get("leased", 0),
            "retrying": counts.get("retrying", 0),
            "dead_letter": counts.get("dead_letter", 0),
            "completed": counts.get("completed", 0),
            "last_source_captured_at": last_capture.isoformat() if last_capture else None,
            "last_job_completed_at": last_completion.isoformat() if last_completion else None,
        }
