from uuid import UUID

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.services.auth_service import require_role
from app.services.submission_service import SubmissionService

router = APIRouter()


class ReviewAction(BaseModel):
    notes: str | None = None


class RoleUpdate(BaseModel):
    role: str


@router.get("/submissions")
async def list_pending_submissions(
    page: int = Query(1, ge=1),
    per_page: int = Query(25, ge=1, le=100),
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    service = SubmissionService(db)
    return await service.list_pending(page=page, per_page=per_page)


@router.put("/submissions/{incident_id}/verify")
async def verify_submission(
    incident_id: UUID,
    body: ReviewAction = ReviewAction(),
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    service = SubmissionService(db)
    return await service.verify_submission(incident_id, admin, body.notes)


@router.put("/submissions/{incident_id}/reject")
async def reject_submission(
    incident_id: UUID,
    body: ReviewAction = ReviewAction(),
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    service = SubmissionService(db)
    return await service.reject_submission(incident_id, admin, body.notes)


@router.put("/users/{user_id}/role")
async def update_user_role(
    user_id: UUID,
    body: RoleUpdate,
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    service = SubmissionService(db)
    return await service.update_user_role(user_id, body.role, admin)


@router.get("/audit-log")
async def list_audit_log(
    incident_id: UUID | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    service = SubmissionService(db)
    return await service.list_audit_log(
        incident_id=incident_id, page=page, per_page=per_page
    )
