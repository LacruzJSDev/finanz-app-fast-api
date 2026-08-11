from typing import Annotated

from fastapi import Depends

from app.auth.repository import AuthRepository
from app.auth.service import AuthService
from app.shared.dependencies import DbSession
from app.users.dependencies import get_user_repository
from app.users.repository import UserRepository

# get_user_repository no se define aquí: UserRepository es del dominio users,
# y get_current_user (app/shared/dependencies.py) también lo necesita.


def get_auth_repository(db: DbSession) -> AuthRepository:
    return AuthRepository(db)


def get_auth_service(
    auth_repo: Annotated[AuthRepository, Depends(get_auth_repository)],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> AuthService:
    return AuthService(auth_repo, user_repo)


AuthServiceDep = Annotated[AuthService, Depends(get_auth_service)]
