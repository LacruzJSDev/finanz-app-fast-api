import uuid

from fastapi import APIRouter, status

from app.accounts.dependencies import (
    RequireAccountMembership,
    RequireAccountOwnerOrAdmin,
)
from app.payment_plans.commands import CreatePaymentPlanCommand
from app.payment_plans.dependencies import PaymentPlanServiceDep
from app.payment_plans.schemas import CreatePaymentPlanRequest, PaymentPlanRead
from app.shared.dependencies import CurrentUser
from app.shared.schemas import CollectionResponse

router = APIRouter(
    prefix="/accounts/{account_id}/payment-plans", tags=["payment-plans"]
)


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_payment_plan(
    payload: CreatePaymentPlanRequest,
    service: PaymentPlanServiceDep,
    user: CurrentUser,
    account_id: uuid.UUID,
    account: RequireAccountOwnerOrAdmin,
) -> PaymentPlanRead:
    command = CreatePaymentPlanCommand(
        account_id=account_id,
        group_id=account.group_id,
        type=payload.type,
        amount=payload.amount,
        category_id=payload.category_id,
        to_account_id=payload.to_account_id,
        description=payload.description,
        next_due_date=payload.next_due_date,
        end_date=payload.end_date,
        is_recurring=payload.is_recurring,
        frequency_interval=payload.frequency_interval,
        frequency_unit=payload.frequency_unit,
    )
    return service.create_payment_plan(user.id, command)


@router.get("/")
def get_payment_plans(
    service: PaymentPlanServiceDep,
    account_id: uuid.UUID,
    account: RequireAccountMembership,
) -> CollectionResponse[PaymentPlanRead]:
    result = service.get_payment_plans(account_id)
    return CollectionResponse[PaymentPlanRead](items=result)
