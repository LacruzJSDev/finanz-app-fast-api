from pydantic import BaseModel

from app.users.schemas import UserRead


class LoginRequest(BaseModel):
    """Cuerpo de POST /auth/login."""

    email: str
    password: str


class LoginResponse(BaseModel):
    """Respuesta de los endpoints que abren sesión: login, register, refresh."""

    user: UserRead
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
