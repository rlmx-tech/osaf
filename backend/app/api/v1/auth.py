from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import AuthService, create_access_token

router = APIRouter()


@router.post("/login")
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    user = await service.authenticate(form_data.username, form_data.password)
    token = create_access_token(user.id, user.role)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
    }


@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    data: UserCreate,
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    user = await service.register(
        email=data.email,
        username=data.username,
        password=data.password,
        display_name=data.display_name,
    )
    return user
