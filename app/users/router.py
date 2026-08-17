from fastapi import APIRouter

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
    fields_set = payload.model_fields_set
    command = UpdateUserCommand(
        name=payload.name if "name" in fields_set else None,
        email=payload.email if "email" in fields_set else None,
    )
    return service.update_user(user.id, command)
