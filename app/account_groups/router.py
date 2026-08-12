from fastapi import APIRouter

from app.account_groups.commands import AccountGroupCommand
from app.account_groups.dependencies import AccountGroupServiceDep
from app.account_groups.schemas import CreateGroupRequest, GroupRead
from app.shared.dependencies import CurrentUser

router = APIRouter(prefix="/account-groups", tags=["account-groups"])


@router.post("/")
def create_group(
    payload: CreateGroupRequest,
    service: AccountGroupServiceDep,
    user: CurrentUser,
) -> GroupRead:
    """Creacion de un nuevo grupo y su propietario"""
    group_command = AccountGroupCommand(
        name=payload.name, color=payload.color, icon=payload.icon
    )
    result = service.create_group(user.id, group_command)
    return result
