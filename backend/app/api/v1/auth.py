from fastapi import APIRouter, Depends, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.schemas.user import UserCreate, UserResponse
from app.services.auth_service import COOKIE_NAME, AuthService, create_access_token

router = APIRouter()

_COOKIE_MAX_AGE = settings.jwt_expiration_hours * 3600


@router.post("/login")
async def login(
    response: Response,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db),
):
    service = AuthService(db)
    user = await service.authenticate(form_data.username, form_data.password)
    token = create_access_token(user.id, user.role)

    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.app_env != "development",
        samesite="lax",
        max_age=_COOKIE_MAX_AGE,
    )

    return {
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "username": user.username,
            "email": user.email,
            "display_name": user.display_name,
            "role": user.role,
        },
    }


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, httponly=True, samesite="lax")
    return {"message": "Logged out"}


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
