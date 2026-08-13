import uuid

from fastapi import APIRouter, status

from app.account_groups.commands import AccountGroupCommand, UpdateAccountGroupCommand
from app.account_groups.dependencies import (
    AccountGroupServiceDep,
    RequireMembership,
    RequireOwnerOrAdmin,
)
from app.account_groups.schemas import (
    CreateGroupRequest,
    GroupMemberRead,
    GroupRead,
    UpdateGroupRequest,
)
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


@router.patch("/{group_id}")
def update_group(
    payload: UpdateGroupRequest,
    service: AccountGroupServiceDep,
    membership: RequireOwnerOrAdmin,
) -> GroupRead:
    """Edición de un grupo"""

    fields_set = payload.model_fields_set
    update_group_command = UpdateAccountGroupCommand(
        name=payload.name if "name" in fields_set else None,
        color=payload.color if "color" in fields_set else None,
        icon=payload.icon if "icon" in fields_set else None,
        is_active=payload.is_active if "is_active" in fields_set else None,
    )
    return service.update_group(membership, update_group_command)


@router.get("/{group_id}/members")
def get_group_members(
    service: AccountGroupServiceDep, group_id: uuid.UUID, membership: RequireMembership
) -> CollectionResponse[GroupMemberRead]:
    """Obtiene los miembros de un grupo de cuentas"""
    result = service.get_group_members(group_id)
    collection_response = CollectionResponse[GroupMemberRead](items=result)
    return collection_response
