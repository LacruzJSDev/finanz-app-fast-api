import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import APIKeyCookie
from jose import JWTError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.shared.exceptions import ForbiddenError, UnauthorizedError
from app.shared.jwt import ACCESS_TOKEN_TYPE, decode_token
from app.users.models import User
from app.users.repository import UserRepository

# La usan los `dependencies.py` de cada dominio para construir sus
# repositorios; ningún router debería declararla directamente.
DbSession = Annotated[Session, Depends(get_db)]

# Aquí y no en auth/router.py: quien pone las cookies y quien las lee
# (get_current_user) necesitan el mismo nombre.
ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"

# auto_error=False: el 401 lo lanzamos nosotros como UnauthorizedError, con
# la forma de error única del proyecto.
_access_token_scheme = APIKeyCookie(
    name=ACCESS_TOKEN_COOKIE, scheme_name="AccessTokenCookie", auto_error=False
)


def get_current_user(
    db: DbSession,
    access_token: Annotated[str | None, Depends(_access_token_scheme)],
) -> User:
    """Resuelve el usuario autenticado a partir de la cookie `access_token`.

    Vive en shared y no en auth/: es la dependencia base de cualquier
    endpoint protegido de cualquier dominio (ARCHITECTURE.md §7.2).

    Construye su propio UserRepository(db) en vez de reutilizar
    get_user_repository: importarlo desde aquí crearía un ciclo, ya que
    users/dependencies.py necesita DbSession, definida en este mismo módulo.
    """
    user_repo = UserRepository(db)
    if access_token is None:
        raise UnauthorizedError("No autenticado")

    try:
        payload = decode_token(access_token, ACCESS_TOKEN_TYPE)
        user_id = uuid.UUID(payload.subject)
    except (JWTError, ValueError):
        # ValueError: un token forjado con un `sub` que no es un UUID.
        raise UnauthorizedError("No autenticado") from None

    user = user_repo.get_user_by_id(user_id)
    if user is None:
        raise UnauthorizedError("No autenticado")

    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

# scheme_name propio: sin él, las dos instancias de APIKeyCookie comparten el
# mismo nombre de esquema por defecto, y /docs acaba diciendo que
# /auth/refresh necesita la cookie access_token en vez de refresh_token.
_refresh_token_scheme = APIKeyCookie(
    name=REFRESH_TOKEN_COOKIE, scheme_name="RefreshTokenCookie", auto_error=False
)

RefreshToken = Annotated[str | None, Depends(_refresh_token_scheme)]


def require_trusted_origin(request: Request) -> None:
    """Bloquea mutaciones con cookies si no proceden de un origen permitido.

    Las cookies httpOnly no pueden llevar un token anti-CSRF leído por
    JavaScript. La protección elegida para la API es exigir `Origin` en toda
    mutación que incluya una cookie de autenticación y compararlo con la lista
    explícita de CORS. Los endpoints públicos (registro y login) no llevan
    todavía una cookie y no quedan bloqueados; GET/HEAD/OPTIONS son seguros.
    """
    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    auth_cookie_names = {ACCESS_TOKEN_COOKIE, REFRESH_TOKEN_COOKIE}
    if not auth_cookie_names.intersection(request.cookies):
        return

    origin = request.headers.get("origin")
    if origin not in settings.cors_allowed_origins:
        raise ForbiddenError("Origen no permitido")
