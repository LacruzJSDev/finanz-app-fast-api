from typing import Annotated

from fastapi import Depends

from app.accounts.dependencies import get_account_repository
from app.accounts.repository import AccountRepository
from app.categories.dependencies import get_category_repository
from app.categories.repository import CategoryRepository
from app.payment_plans.repository import PaymentPlanRepository
from app.payment_plans.service import PaymentPlanService
from app.shared.dependencies import DbSession


def get_payment_plan_repository(db: DbSession) -> PaymentPlanRepository:
    return PaymentPlanRepository(db)


def get_payment_plan_service(
    payment_plan_repo: Annotated[
        PaymentPlanRepository, Depends(get_payment_plan_repository)
    ],
    account_repo: Annotated[AccountRepository, Depends(get_account_repository)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> PaymentPlanService:
    return PaymentPlanService(payment_plan_repo, account_repo, category_repo)


PaymentPlanServiceDep = Annotated[PaymentPlanService, Depends(get_payment_plan_service)]
