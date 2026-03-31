import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, field_validator


class UserCreate(BaseModel):
    email: EmailStr
    username: str
    password: str
    display_name: str | None = None

    @field_validator("password", mode="before")
    @classmethod
    def validate_password_complexity(cls, v: str) -> str:
        errors: list[str] = []
        if len(v) < 8:
            errors.append("at least 8 characters")
        if not re.search(r"[A-Z]", v):
            errors.append("an uppercase letter")
        if not re.search(r"[a-z]", v):
            errors.append("a lowercase letter")
        if not re.search(r"\d", v):
            errors.append("a digit")
        if not re.search(r"[!@#$%^&*()\-_=+\[\]{};:'\",.<>?/\\|`~]", v):
            errors.append("a special character")
        if errors:
            raise ValueError("Password must contain: " + ", ".join(errors))
        return v


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    display_name: str | None = None
    role: str
    bio: str | None = None
    created_at: datetime
    is_active: bool
