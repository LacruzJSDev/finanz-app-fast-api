import uuid
from typing import Annotated

from fastapi import Depends, Request
from jose import JWTError
from sqlalchemy.orm import Session

from app.database import get_db
from app.shared.exceptions import UnauthorizedError
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


def get_current_user(request: Request, db: DbSession) -> User:
    """Resuelve el usuario autenticado a partir de la cookie `access_token`.

    Vive en shared y no en auth/: es la dependencia base de cualquier
    endpoint protegido de cualquier dominio (ARCHITECTURE.md §7.2).

    Construye su propio UserRepository(db) en vez de reutilizar
    get_user_repository: importarlo desde aquí crearía un ciclo, ya que
    users/dependencies.py necesita DbSession, definida en este mismo módulo.
    """
    user_repo = UserRepository(db)
    access_token = request.cookies.get(ACCESS_TOKEN_COOKIE)
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
