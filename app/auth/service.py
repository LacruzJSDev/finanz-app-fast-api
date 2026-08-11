from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.auth.repository import AuthRepository
from app.auth.schemas import LoginResponse
from app.shared.bcrypt import hash_password, verify_password
from app.shared.exceptions import ConflictError, UnauthorizedError
from app.shared.hashing import hash_token
from app.shared.jwt import (
    REFRESH_TOKEN_TYPE,
    create_access_token,
    create_refresh_token,
    decode_token,
)
from app.users.models import User
from app.users.repository import UserRepository
from app.users.schemas import UserRead

# Mismo código y mismo mensaje tanto si el email no existe como si la
# contraseña no coincide: docs/domains/auth.md lo exige explícitamente, para
# no confirmar desde la respuesta qué emails están registrados.
_INVALID_CREDENTIALS_MESSAGE = "Email o contraseña incorrectos"


@dataclass
class AuthService:
    """Lógica de negocio del dominio auth.

    No importa nada de FastAPI ni sabe qué código HTTP acabará devolviendo el
    router: se puede instanciar con un repositorio falso y probar sin levantar
    la API ni tocar Postgres.
    """

    auth_repo: AuthRepository
    user_repo: UserRepository

    def _issue_tokens(self, user: User) -> LoginResponse:
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)

        # expires_at sale de decodificar el propio token recién emitido, no de
        # recalcularlo aquí a partir de JWT_REFRESH_TOKEN_EXPIRE_DAYS: así hay
        # una sola fuente de verdad para la duración (app/shared/jwt.py), y la
        # fila de `sessions` no puede desincronizarse del token que describe.
        refresh_payload = decode_token(refresh_token, REFRESH_TOKEN_TYPE)
        self.auth_repo.create_session(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            expires_at=refresh_payload.expires_at,
        )

        return LoginResponse(
            user=UserRead.model_validate(user),
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def login(self, email: str, password: str) -> LoginResponse:
        user = self.user_repo.get_user_by_email(email)
        if not user:
            raise UnauthorizedError(_INVALID_CREDENTIALS_MESSAGE)

        local_provider = self.auth_repo.get_local_provider(user.id)
        if not local_provider or not local_provider.password_hash:
            raise UnauthorizedError(_INVALID_CREDENTIALS_MESSAGE)

        if not verify_password(password, local_provider.password_hash):
            raise UnauthorizedError(_INVALID_CREDENTIALS_MESSAGE)

        return self._issue_tokens(user)

    def register(self, email: str, name: str, password: str) -> LoginResponse:
        existing_user = self.user_repo.get_user_by_email(email)

        if existing_user:
            raise ConflictError("El usuario ya está registrado con ese correo")

        try:
            user = self.user_repo.create_user(email, name)
        except IntegrityError:
            raise ConflictError(
                "El usuario ya está registrado con ese correo"
            ) from None

        password_hash = hash_password(password)
        self.auth_repo.create_local_provider(user.id, password_hash)

        return self._issue_tokens(user)
