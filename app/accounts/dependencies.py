from typing import Annotated

from fastapi import Depends

from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.shared.dependencies import DbSession


def get_account_repository(db: DbSession) -> AccountRepository:
    return AccountRepository(db)


def get_account_service(
    account_repo: Annotated[AccountRepository, Depends(get_account_repository)],
) -> AccountService:
    return AccountService(account_repo)


AccountServiceDep = Annotated[AccountService, Depends(get_account_service)]
