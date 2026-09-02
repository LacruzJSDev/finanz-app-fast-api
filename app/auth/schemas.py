from pydantic import BaseModel, Field, field_validator

from app.shared.bcrypt import MAX_PASSWORD_BYTES
from app.users.schemas import NormalizedEmail

# No hay un LoginResponse aquí: login y register devuelven UserRead
# directamente (ver app/auth/router.py). Los tokens no viajan en el cuerpo de
# la respuesta, sino en cookies httpOnly — un esquema que los incluyera como
# campos normales invitaría a leerlos desde el cliente, que es justo lo que
# httpOnly existe para impedir.


class LoginRequest(BaseModel):
    """Cuerpo de POST /auth/login."""

    email: NormalizedEmail
    password: str


class RegisterRequest(BaseModel):
    """Cuerpo de POST /auth/register."""

    email: NormalizedEmail
    name: str
    password: str = Field(min_length=8, max_length=72)

    @field_validator("password")
    @classmethod
    def password_fits_bcrypt(cls, password: str) -> str:
        if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"La contraseña no puede superar {MAX_PASSWORD_BYTES} bytes UTF-8"
            )
        return password


class ChangePasswordRequest(BaseModel):
    """Cuerpo de PATCH /auth/change_password"""

    current_password: str
    new_password: str = Field(min_length=8, max_length=72)

    @field_validator("new_password")
    @classmethod
    def new_password_fits_bcrypt(cls, password: str) -> str:
        if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
            raise ValueError(
                f"La contraseña no puede superar {MAX_PASSWORD_BYTES} bytes UTF-8"
            )
        return password
