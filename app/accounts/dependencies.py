import uuid
from typing import Annotated

from fastapi import Depends

from app.account_groups.repository import AccountGroupMemberRepository
from app.accounts.models import Account
from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.shared.dependencies import CurrentUser, DbSession
from app.shared.exceptions import ForbiddenError


def get_account_repository(db: DbSession) -> AccountRepository:
    return AccountRepository(db)


def get_account_service(
    account_repo: Annotated[AccountRepository, Depends(get_account_repository)],
) -> AccountService:
    return AccountService(account_repo)


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]


def verify_account_access(
    account_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> Account:
    """accounts.md §2: para endpoints con {account_id} en la ruta, resuelve
    la pertenencia a partir de la propia cuenta, en vez de pedirle group_id
    al cliente por separado. 403 tanto si la cuenta no existe como si el
    usuario no pertenece a su grupo — nunca 404, mismo criterio que el
    resto de la autorización del proyecto: un fallo de autorización no se
    distingue de un recurso inexistente.
    """
    account_repo = AccountRepository(db)
    account = account_repo.get_account_by_id(account_id)
    if account is None:
        raise ForbiddenError("No perteneces al grupo de esta cuenta")

    member_repo = AccountGroupMemberRepository(db)
    membership = member_repo.get_membership(account.group_id, user.id)
    if membership is None:
        raise ForbiddenError("No perteneces al grupo de esta cuenta")

    return account


VerifyAccountAccess = Annotated[Account, Depends(verify_account_access)]
