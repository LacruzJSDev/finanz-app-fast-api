import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt

from app.config import settings

ACCESS_TOKEN_TYPE = "access"
REFRESH_TOKEN_TYPE = "refresh"


class InvalidTokenError(JWTError):
    """Token con firma y expiración válidas, pero del tipo equivocado.

    Por ejemplo, un refresh token presentado donde se esperaba un access
    token. Hereda de JWTError para que el caller pueda capturar solo
    `JWTError` y cubrir cualquier motivo de invalidez sin distinguir casos.
    """


@dataclass
class TokenPayload:
    subject: str
    expires_at: datetime
    token_type: str
    token_id: str


def _create_token(
    subject: uuid.UUID | str, expires_delta: timedelta, token_type: str
) -> str:
    expires_at = datetime.now(timezone.utc) + expires_delta
    claims = {  # pyright: ignore[reportUnknownVariableType]
        "sub": str(subject),
        "exp": expires_at,
        "type": token_type,
        # jti (JWT ID) de RFC 7519: un identificador único por token. Sin
        # esto, dos tokens emitidos para el mismo usuario dentro del mismo
        # segundo son bytes idénticos —`exp` solo tiene resolución de
        # segundo—, lo que colisiona contra el UNIQUE de
        # sessions.refresh_token_hash en cuanto se hashean igual.
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(claims, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)  # pyright: ignore[reportUnknownArgumentType]


def create_access_token(subject: uuid.UUID | str) -> str:
    """Token de acceso. Vida corta: JWT_ACCESS_TOKEN_EXPIRE_MINUTES."""
    delta = timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES)
    return _create_token(subject, delta, ACCESS_TOKEN_TYPE)


def create_refresh_token(subject: uuid.UUID | str) -> str:
    """Token de refresco. Vida larga: JWT_REFRESH_TOKEN_EXPIRE_DAYS."""
    delta = timedelta(days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS)
    return _create_token(subject, delta, REFRESH_TOKEN_TYPE)


def decode_token(token: str, expected_type: str) -> TokenPayload:
    """Decodifica y valida un JWT: firma, expiración y tipo.

    Lanza `jose.JWTError` (o `InvalidTokenError`, subclase suya) si el token
    no es válido por cualquier motivo: firma incorrecta, expirado, con
    reclamaciones incompletas, o del tipo equivocado. El caller decide cómo
    traducir eso a una respuesta HTTP — este módulo no conoce AppError ni
    ningún código de estado, igual que shared/bcrypt.py no conoce HTTP.
    """
    claims = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])

    subject = claims.get("sub")
    token_type = claims.get("type")
    token_id = claims.get("jti")
    if subject is None or token_type is None or token_id is None:
        raise InvalidTokenError("El token no contiene las reclamaciones esperadas")
    if token_type != expected_type:
        raise InvalidTokenError(f"Se esperaba un token de tipo '{expected_type}'")

    return TokenPayload(
        subject=subject,
        expires_at=datetime.fromtimestamp(claims["exp"], tz=timezone.utc),
        token_type=token_type,
        token_id=token_id,
    )
