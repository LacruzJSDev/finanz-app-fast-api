from typing import Annotated

from fastapi import Depends

from app.accounts.dependencies import get_account_repository
from app.accounts.repository import AccountRepository
from app.categories.dependencies import get_category_repository
from app.categories.repository import CategoryRepository
from app.shared.dependencies import DbSession
from app.transactions.repository import TransactionRepository
from app.transactions.service import TransactionService


def get_transaction_repository(db: DbSession) -> TransactionRepository:
    return TransactionRepository(db)


def get_transaction_service(
    transaction_repo: Annotated[
        TransactionRepository, Depends(get_transaction_repository)
    ],
    account_repo: Annotated[AccountRepository, Depends(get_account_repository)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> TransactionService:
    return TransactionService(transaction_repo, account_repo, category_repo)


TransactionServiceDep = Annotated[TransactionService, Depends(get_transaction_service)]
