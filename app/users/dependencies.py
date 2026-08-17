from typing import Annotated

from fastapi import Depends

from app.shared.dependencies import DbSession
from app.users.repository import UserRepository
from app.users.service import UserService


def get_user_repository(db: DbSession) -> UserRepository:
    return UserRepository(db)


def get_user_service(
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
) -> UserService:
    return UserService(user_repo)


UserServiceDep = Annotated[UserService, Depends(get_user_service)]
