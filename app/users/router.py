from fastapi import APIRouter

from app.shared.commands import UNSET
from app.shared.dependencies import CurrentUser
from app.shared.openapi_responses import (
    BAD_REQUEST,
    CONFLICT,
    UNAUTHORIZED,
    responses,
)
from app.users.commands import UpdateUserCommand
from app.users.dependencies import UserServiceDep
from app.users.schemas import UpdateUserRequest, UserRead

router = APIRouter(tags=["users"])


@router.get("/me", responses=responses(UNAUTHORIZED))
def get_me(service: UserServiceDep, user: CurrentUser) -> UserRead:
    return service.get_user(user.id)


@router.patch("/me", responses=responses(UNAUTHORIZED, BAD_REQUEST, CONFLICT))
def update_me(
    payload: UpdateUserRequest, service: UserServiceDep, user: CurrentUser
) -> UserRead:
    command = UpdateUserCommand(
        name=payload.name if payload.name is not None else UNSET,
        email=payload.email if payload.email is not None else UNSET,
    )
    return service.update_user(user.id, command)
