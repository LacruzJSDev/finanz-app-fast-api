from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError

from app.auth.repository import AuthRepository
from app.shared.bcrypt import hash_password, verify_password
from app.shared.exceptions import ConflictError, UnauthorizedError
from app.shared.hashing import hash_token
from app.shared.jwt import (
    ACCESS_TOKEN_TYPE,
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
_NO_SESSION_MESSAGE = "Session no encontrada"
_NO_USER_MESSAGE = "Usuario no encontrado"


@dataclass
class AuthResult:
    """Lo que produce login/register puertas adentro del servicio.

    No es un schema de FastAPI ni viaja tal cual al cliente: el router lee
    los tokens de aquí para ponerlos en cookies httpOnly, y solo devuelve
    `user` en el cuerpo de la respuesta. Los `*_expires_at` salen de
    decodificar cada token recién emitido, no de recalcularlos a partir de
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES / JWT_REFRESH_TOKEN_EXPIRE_DAYS: así hay
    una sola fuente de verdad (app/shared/jwt.py) para cuánto dura cada uno,
    y el Max-Age de la cookie nunca puede desincronizarse del token real.
    """

    user: UserRead
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime


@dataclass
class AuthService:
    """Lógica de negocio del dominio auth.

    No importa nada de FastAPI ni sabe qué código HTTP acabará devolviendo el
    router: se puede instanciar con un repositorio falso y probar sin levantar
    la API ni tocar Postgres.
    """

    auth_repo: AuthRepository
    user_repo: UserRepository

    def _issue_tokens(self, user: User) -> AuthResult:
        access_token = create_access_token(user.id)
        refresh_token = create_refresh_token(user.id)

        access_payload = decode_token(access_token, ACCESS_TOKEN_TYPE)
        refresh_payload = decode_token(refresh_token, REFRESH_TOKEN_TYPE)

        self.auth_repo.create_session(
            user_id=user.id,
            refresh_token_hash=hash_token(refresh_token),
            expires_at=refresh_payload.expires_at,
        )

        return AuthResult(
            user=UserRead.model_validate(user),
            access_token=access_token,
            access_expires_at=access_payload.expires_at,
            refresh_token=refresh_token,
            refresh_expires_at=refresh_payload.expires_at,
        )

    def login(self, email: str, password: str) -> AuthResult:
        user = self.user_repo.get_user_by_email(email)
        if not user:
            raise UnauthorizedError(_INVALID_CREDENTIALS_MESSAGE)

        local_provider = self.auth_repo.get_local_provider(user.id)
        if not local_provider or not local_provider.password_hash:
            raise UnauthorizedError(_INVALID_CREDENTIALS_MESSAGE)

        if not verify_password(password, local_provider.password_hash):
            raise UnauthorizedError(_INVALID_CREDENTIALS_MESSAGE)

        return self._issue_tokens(user)

    def register(self, email: str, name: str, password: str) -> AuthResult:
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

    def logout(self, refresh_token: str) -> None:
        refresh_token_hash = hash_token(refresh_token)
        self.auth_repo.revoke_session_by_refresh_token_hash(refresh_token_hash)

    def refresh(self, refresh_token: str) -> AuthResult:
        refresh_token_hash = hash_token(refresh_token)
        existing_session = self.auth_repo.get_session_by_refresh_token_hash(
            refresh_token_hash
        )
        if not existing_session:
            raise UnauthorizedError(_NO_SESSION_MESSAGE)
        if existing_session.revoked:
            raise UnauthorizedError(_NO_SESSION_MESSAGE)
        if existing_session.expires_at < datetime.now(timezone.utc):
            raise UnauthorizedError(_NO_SESSION_MESSAGE)

        user = self.user_repo.get_user_by_id(existing_session.user_id)
        if not user:
            raise UnauthorizedError(_NO_USER_MESSAGE)

        self.auth_repo.revoke_session_by_refresh_token_hash(refresh_token_hash)

        return self._issue_tokens(user)
