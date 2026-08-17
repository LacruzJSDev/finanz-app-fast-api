from fastapi import APIRouter

from app.shared.dependencies import CurrentUser
from app.shared.openapi_responses import UNAUTHORIZED, responses
from app.users.dependencies import UserServiceDep
from app.users.schemas import UserRead

router = APIRouter(tags=["users"])


@router.get("/me", responses=responses(UNAUTHORIZED))
def get_me(service: UserServiceDep, user: CurrentUser) -> UserRead:
    return service.get_user(user.id)
