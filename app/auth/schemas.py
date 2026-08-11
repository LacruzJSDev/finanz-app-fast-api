from pydantic import BaseModel, Field

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


class ChangePasswordRequest(BaseModel):
    """Cuerpo de PATCH /auth/change_password"""

    current_password: str
    new_password: str = Field(min_length=8, max_length=72)
