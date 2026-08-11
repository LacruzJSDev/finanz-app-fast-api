from pydantic import BaseModel, Field

from app.users.schemas import NormalizedEmail, UserRead


class LoginRequest(BaseModel):
    """Cuerpo de POST /auth/login."""

    email: NormalizedEmail
    password: str


class LoginResponse(BaseModel):
    """Respuesta de los endpoints que abren sesión: login, register, refresh."""

    user: UserRead
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RegisterRequest(BaseModel):
    """Cuerpo de POST /auth/register"""

    email: NormalizedEmail
    name: str
    password: str = Field(min_length=8, max_length=72)
