from typing import Annotated

from fastapi import Depends

from app.auth.repository import AuthRepository
from app.auth.service import AuthService
from app.shared.dependencies import DbSession
from app.users.repository import UserRepository

# Cableado del dominio: el único módulo que conoce a la vez FastAPI y las
# clases de las capas. Existe para que service.py y repository.py se queden sin
# importaciones de FastAPI, como exige ARCHITECTURE.md §2.2.


def get_auth_repository(db: DbSession) -> AuthRepository:
    return AuthRepository(db)


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


def get_auth_service(
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    return AuthService(auth_repo, user_repo)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
