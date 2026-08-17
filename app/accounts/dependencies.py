import uuid
from typing import Annotated, Callable

from fastapi import Depends

from app.account_groups.dependencies import check_group_role
from app.account_groups.models import AccountGroupMemberRoleEnum
from app.account_groups.repository import AccountGroupMemberRepository
from app.accounts.models import Account
from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.shared.dependencies import CurrentUser, DbSession
from app.shared.exceptions import ForbiddenError
from app.users.models import User


def get_account_repository(db: DbSession) -> AccountRepository:
    return AccountRepository(db)


def get_account_service(
    account_repo: Annotated[AccountRepository, Depends(get_account_repository)],
) -> AccountService:
    return AccountService(account_repo)


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]


def require_account_role(
    *allowed_roles: AccountGroupMemberRoleEnum,
) -> Callable[[uuid.UUID, User, DbSession], Account]:
    """accounts.md §2: para endpoints con {account_id} en la ruta, resuelve
    la pertenencia a partir de la propia cuenta, en vez de pedirle group_id
    al cliente por separado — la comprobación de rol en sí (check_group_role)
    es la misma que usa require_group_role en account_groups, solo cambia
    cómo se llega al group_id.
    """

    def verify_account_access(
        account_id: uuid.UUID,
        user: CurrentUser,
        db: DbSession,
    ) -> Account:
        account_repo = AccountRepository(db)
        account = account_repo.get_account_by_id(account_id)
        # 403 aquí también, no solo cuando falla el rol: una cuenta
        # inexistente nunca se distingue de una a la que no tienes acceso.
        if account is None:
            raise ForbiddenError("No perteneces al grupo de esta cuenta")

        member_repo = AccountGroupMemberRepository(db)
        membership = member_repo.get_membership(account.group_id, user.id)
        check_group_role(membership, *allowed_roles)
        return account

    return verify_account_access


RequireAccountMembership = Annotated[
    Account, Depends(require_account_role())  # sin roles = solo exige pertenencia
]

RequireAccountOwnerOrAdmin = Annotated[
    Account,
    Depends(
        require_account_role(
            AccountGroupMemberRoleEnum.OWNER, AccountGroupMemberRoleEnum.ADMIN
        )
    ),
]
