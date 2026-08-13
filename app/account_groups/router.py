from fastapi import APIRouter, status

from app.account_groups.commands import AccountGroupCommand
from app.account_groups.dependencies import AccountGroupServiceDep
from app.account_groups.schemas import CreateGroupRequest, GroupRead
from app.shared.dependencies import CurrentUser
from app.shared.schemas import CollectionResponse

router = APIRouter(prefix="/account-groups", tags=["account-groups"])


@router.post("/", status_code=status.HTTP_201_CREATED)
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


@router.get("/")
def groups(
    service: AccountGroupServiceDep,
    user: CurrentUser,
) -> CollectionResponse[GroupRead]:
    """Creacion de un nuevo grupo y su propietario"""

    result = service.get_groups(user.id)
    collection_response = CollectionResponse[GroupRead](items=result)
    return collection_response
