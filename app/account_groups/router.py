import uuid

from fastapi import APIRouter, status

from app.account_groups.commands import AccountGroupCommand, UpdateAccountGroupCommand
from app.account_groups.dependencies import (
    AccountGroupServiceDep,
    GroupOverviewServiceDep,
    RequireMembership,
    RequireOwner,
    RequireOwnerOrAdmin,
)
from app.account_groups.schemas import (
    ChangeGroupMemberRoleRequest,
    CreateGroupRequest,
    CreateInvitationRequest,
    GroupMemberRead,
    GroupOverviewRead,
    GroupRead,
    InvitationDetailRead,
    InvitationRead,
    UpdateGroupRequest,
)
from app.shared.dependencies import CurrentUser
from app.shared.openapi_responses import (
    BAD_REQUEST,
    CONFLICT,
    FORBIDDEN,
    NOT_FOUND,
    UNAUTHORIZED,
    responses,
)
from app.shared.schemas import CollectionResponse

router = APIRouter(prefix="/account-groups", tags=["account-groups"])


@router.post(
    "/", status_code=status.HTTP_201_CREATED, responses=responses(UNAUTHORIZED)
)
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


@router.get("/", responses=responses(UNAUTHORIZED))
def groups(
    service: AccountGroupServiceDep,
    user: CurrentUser,
) -> CollectionResponse[GroupRead]:
    """Creacion de un nuevo grupo y su propietario"""

    result = service.get_groups(user.id)
    collection_response = CollectionResponse[GroupRead](items=result)
    return collection_response


@router.patch(
    "/{group_id}",
    responses=responses(UNAUTHORIZED, FORBIDDEN, BAD_REQUEST),
)
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


@router.get("/{group_id}/members", responses=responses(UNAUTHORIZED, FORBIDDEN))
def get_group_members(
    service: AccountGroupServiceDep, group_id: uuid.UUID, membership: RequireMembership
) -> CollectionResponse[GroupMemberRead]:
    """Obtiene los miembros de un grupo de cuentas"""
    result = service.get_group_members(group_id)
    collection_response = CollectionResponse[GroupMemberRead](items=result)
    return collection_response


@router.patch(
    "/{group_id}/members/{user_id}",
    responses=responses(UNAUTHORIZED, FORBIDDEN, CONFLICT),
)
def change_group_member_role(
    payload: ChangeGroupMemberRoleRequest,
    service: AccountGroupServiceDep,
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    membership: RequireOwner,
) -> GroupMemberRead:
    return service.change_group_member_role(group_id, user_id, payload.role)


@router.delete(
    "/{group_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=responses(UNAUTHORIZED, FORBIDDEN, CONFLICT),
)
def expel_group_member(
    service: AccountGroupServiceDep,
    group_id: uuid.UUID,
    user_id: uuid.UUID,
    user: CurrentUser,
    membership: RequireMembership,
) -> None:
    service.expel_group_member(group_id, user_id, user.id)
    return


@router.post(
    "/{group_id}/invitations",
    status_code=status.HTTP_201_CREATED,
    responses=responses(UNAUTHORIZED, FORBIDDEN),
)
def create_invitation(
    payload: CreateInvitationRequest,
    service: AccountGroupServiceDep,
    group_id: uuid.UUID,
    membership: RequireOwnerOrAdmin,
) -> InvitationRead:
    result = service.create_invitation(group_id, membership.user_id, payload.role)
    return result


@router.get(
    "/{group_id}/invitations",
    responses=responses(UNAUTHORIZED, FORBIDDEN),
)
def get_group_invitations(
    service: AccountGroupServiceDep,
    group_id: uuid.UUID,
    membership: RequireOwnerOrAdmin,
) -> CollectionResponse[InvitationRead]:
    """Invitaciones del grupo en cualquier estado, con su código"""
    result = service.get_group_invitations(group_id)
    collection_response = CollectionResponse[InvitationRead](items=result)
    return collection_response


@router.delete(
    "/{group_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT),
)
def revoke_invitation(
    service: AccountGroupServiceDep,
    group_id: uuid.UUID,
    invitation_id: uuid.UUID,
    membership: RequireOwnerOrAdmin,
) -> None:
    """Revoca una invitación no aceptada"""
    service.revoke_invitation(group_id, invitation_id)
    return


@router.get(
    "/invitations/{code}",
    # Sin CONFLICT: account_groups.md §4 dice que una invitación aceptada o
    # caducada no es un error aquí, se devuelve con su status real.
    responses=responses(UNAUTHORIZED, NOT_FOUND),
)
def get_invitation(
    service: AccountGroupServiceDep, code: str, user: CurrentUser
) -> InvitationDetailRead:
    result = service.get_invitation(code)
    return result


@router.post(
    "/{group_id}/invitations/{invitation_id}/accept",
    responses=responses(UNAUTHORIZED, NOT_FOUND, CONFLICT),
)
def accept_invitation(
    service: AccountGroupServiceDep,
    group_id: uuid.UUID,
    invitation_id: uuid.UUID,
    user: CurrentUser,
) -> InvitationRead:
    result = service.accept_invitation(group_id, user.id, invitation_id)
    return result


@router.get("/{group_id}/overview", responses=responses(UNAUTHORIZED, FORBIDDEN))
def get_group_overview(
    service: GroupOverviewServiceDep,
    group_id: uuid.UUID,
    membership: RequireMembership,
) -> GroupOverviewRead:
    """Resumen del grupo: saldo, gasto de hoy y previsión hasta el cobro"""
    result = service.get_group_overview(group_id)
    return result
