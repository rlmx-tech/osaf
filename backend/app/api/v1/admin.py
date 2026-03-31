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


@router.get("/users")
async def list_users(
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    admin: User = Depends(require_role("admin")),
    db: AsyncSession = Depends(get_db),
):
    from sqlalchemy import func, select
    count_q = select(func.count()).select_from(User)
    total = (await db.execute(count_q)).scalar()

    q = select(User).order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(q)
    users = result.scalars().all()

    return {
        "data": [
            {
                "id": str(u.id),
                "username": u.username,
                "email": u.email,
                "display_name": u.display_name,
                "role": u.role,
                "is_active": u.is_active,
                "created_at": u.created_at.isoformat() if u.created_at else None,
                "last_login": u.last_login.isoformat() if u.last_login else None,
            }
            for u in users
        ],
        "meta": {"total": total, "page": page, "per_page": per_page},
    }


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
