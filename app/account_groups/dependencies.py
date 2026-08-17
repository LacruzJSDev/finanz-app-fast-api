import uuid
from typing import Annotated, Callable

from fastapi import Depends

from app.account_groups.models import AccountGroupMember, AccountGroupMemberRoleEnum
from app.account_groups.repository import (
    AccountGroupMemberRepository,
    AccountGroupsRepository,
    InvitationRepository,
)
from app.account_groups.service import AccountGroupService
from app.shared.dependencies import CurrentUser, DbSession
from app.shared.exceptions import ForbiddenError
from app.users.dependencies import get_user_repository
from app.users.models import User
from app.users.repository import UserRepository


def get_account_group_repository(db: DbSession) -> AccountGroupsRepository:
    return AccountGroupsRepository(db)


def get_account_group_member_repository(db: DbSession) -> AccountGroupMemberRepository:
    return AccountGroupMemberRepository(db)


def get_invitation_repository(db: DbSession) -> InvitationRepository:
    return InvitationRepository(db)


def get_account_group_service(
    account_group_repo: Annotated[
        AccountGroupsRepository, Depends(get_account_group_repository)
    ],
    account_group_member_repo: Annotated[
        AccountGroupMemberRepository, Depends(get_account_group_member_repository)
    ],
    user_repo: Annotated[UserRepository, Depends(get_user_repository)],
    invitation_repo: Annotated[
        InvitationRepository, Depends(get_invitation_repository)
    ],
) -> AccountGroupService:
    return AccountGroupService(
        account_group_repo, account_group_member_repo, user_repo, invitation_repo
    )


AccountGroupServiceDep = Annotated[
    AccountGroupService, Depends(get_account_group_service)
]


def check_group_role(
    membership: AccountGroupMember | None,
    *allowed_roles: AccountGroupMemberRoleEnum,
) -> AccountGroupMember:
    """Parte de la comprobación que no depende de cómo se llegó al
    group_id — la reutiliza cualquier dominio que necesite autorizar por
    rol de pertenencia a un grupo (ver accounts/dependencies.py, que
    resuelve el group_id desde una cuenta en vez de leerlo directo de la
    ruta/query).
    """
    if membership is None:
        raise ForbiddenError("No perteneces a este grupo")
    if allowed_roles and membership.role not in allowed_roles:
        raise ForbiddenError("No tienes permiso suficiente")
    return membership


def require_group_role(
    *allowed_roles: AccountGroupMemberRoleEnum,
) -> Callable[[uuid.UUID, User, DbSession], AccountGroupMember]:
    def verify_group_membership(
        group_id: uuid.UUID,
        user: CurrentUser,
        db: DbSession,
    ) -> AccountGroupMember:
        member_repo = AccountGroupMemberRepository(db)
        membership = member_repo.get_membership(group_id, user.id)
        return check_group_role(membership, *allowed_roles)

    return verify_group_membership


RequireOwner = Annotated[
    AccountGroupMember,
    Depends(
        require_group_role(
            AccountGroupMemberRoleEnum.OWNER,
        )
    ),
]

RequireOwnerOrAdmin = Annotated[
    AccountGroupMember,
    Depends(
        require_group_role(
            AccountGroupMemberRoleEnum.OWNER, AccountGroupMemberRoleEnum.ADMIN
        )
    ),
]

RequireMembership = Annotated[
    AccountGroupMember,
    Depends(require_group_role()),  # sin roles = solo exige pertenencia
]
