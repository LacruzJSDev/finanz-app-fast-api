from typing import Annotated

from fastapi import Depends

from app.budgets.repository import BudgetRepository
from app.budgets.service import BudgetService
from app.categories.dependencies import get_category_repository
from app.categories.repository import CategoryRepository
from app.shared.dependencies import DbSession


def get_budget_repository(db: DbSession) -> BudgetRepository:
    return BudgetRepository(db)


def get_budget_service(
    budget_repo: Annotated[BudgetRepository, Depends(get_budget_repository)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> BudgetService:
    return BudgetService(budget_repo, category_repo)


BudgetServiceDep = Annotated[BudgetService, Depends(get_budget_service)]
