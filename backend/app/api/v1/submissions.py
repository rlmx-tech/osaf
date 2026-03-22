from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.user import User
from app.schemas.incident import IncidentCreate, IncidentResponse
from app.services.auth_service import require_authenticated
from app.services.submission_service import SubmissionService

router = APIRouter()


@router.post("", response_model=IncidentResponse, status_code=201)
async def submit_incident(
    data: IncidentCreate,
    user: User = Depends(require_authenticated),
    db: AsyncSession = Depends(get_db),
):
    """Submit a new incident. Verified contributors auto-publish; others go to review queue."""
    service = SubmissionService(db)
    return await service.submit_incident(data, user)
