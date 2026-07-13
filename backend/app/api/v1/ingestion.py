from uuid import UUID

from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.ingestion import (
    JobFailure,
    JobFailureResponse,
    ObservationCreate,
    ObservationResponse,
    SourceCaptureResponse,
    SourceDocumentCreate,
)
from app.services.auth_service import require_role
from app.services.ingestion_service import IngestionService

router = APIRouter()


@router.post("/sources", response_model=SourceCaptureResponse, status_code=201)
async def capture_source(
    data: SourceDocumentCreate,
    response: Response,
    user: User = Depends(require_role("admin", "verified_contributor")),
    db: AsyncSession = Depends(get_db),
):
    source, job, should_process, created = await IngestionService(db).capture_source(
        data, worker=f"api:{user.username}"
    )
    if not created:
        response.status_code = 200
    return SourceCaptureResponse(
        source_document_id=source.id,
        job_id=job.id,
        job_status=job.status,
        should_process=should_process,
        attempts=job.attempts,
    )


@router.post(
    "/jobs/{job_id}/observation", response_model=ObservationResponse, status_code=201
)
async def record_observation(
    job_id: UUID,
    data: ObservationCreate,
    user: User = Depends(require_role("admin", "verified_contributor")),
    db: AsyncSession = Depends(get_db),
):
    observation, candidate, job = await IngestionService(db).record_observation(job_id, data)
    return ObservationResponse(
        observation_id=observation.id,
        candidate_id=candidate.id if candidate else None,
        candidate_status=candidate.status if candidate else None,
        canonical_incident_id=candidate.canonical_incident_id if candidate else None,
        job_status=job.status,
    )


@router.post("/jobs/{job_id}/fail", response_model=JobFailureResponse)
async def fail_job(
    job_id: UUID,
    data: JobFailure,
    user: User = Depends(require_role("admin", "verified_contributor")),
    db: AsyncSession = Depends(get_db),
):
    job = await IngestionService(db).fail_job(job_id, data)
    return JobFailureResponse(
        id=job.id, status=job.status, attempts=job.attempts, available_at=job.available_at
    )
