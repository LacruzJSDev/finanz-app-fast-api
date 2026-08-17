import uuid

from fastapi import APIRouter, status

from app.accounts.dependencies import (
    RequireAccountMembership,
    RequireAccountOwnerOrAdmin,
)
from app.payment_plans.commands import (
    CreatePaymentPlanCommand,
    UpdatePaymentPlanCommand,
)
from app.payment_plans.dependencies import PaymentPlanServiceDep
from app.payment_plans.schemas import (
    CreatePaymentPlanRequest,
    PaymentPlanRead,
    UpdatePaymentPlanRequest,
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

router = APIRouter(
    prefix="/accounts/{account_id}/payment-plans", tags=["payment-plans"]
)


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses=responses(UNAUTHORIZED, FORBIDDEN, CONFLICT),
)
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


@router.get("/", responses=responses(UNAUTHORIZED, FORBIDDEN))
def get_payment_plans(
    service: PaymentPlanServiceDep,
    account_id: uuid.UUID,
    account: RequireAccountMembership,
) -> CollectionResponse[PaymentPlanRead]:
    result = service.get_payment_plans(account_id)
    return CollectionResponse[PaymentPlanRead](items=result)


@router.get(
    "/{payment_plan_id}", responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND)
)
def get_payment_plan(
    service: PaymentPlanServiceDep,
    account_id: uuid.UUID,
    payment_plan_id: uuid.UUID,
    account: RequireAccountMembership,
) -> PaymentPlanRead:
    return service.get_payment_plan(account_id, payment_plan_id)


@router.patch(
    "/{payment_plan_id}",
    responses=responses(UNAUTHORIZED, FORBIDDEN, BAD_REQUEST, NOT_FOUND, CONFLICT),
)
def update_payment_plan(
    payload: UpdatePaymentPlanRequest,
    service: PaymentPlanServiceDep,
    account_id: uuid.UUID,
    payment_plan_id: uuid.UUID,
    account: RequireAccountOwnerOrAdmin,
) -> PaymentPlanRead:
    fields_set = payload.model_fields_set
    command = UpdatePaymentPlanCommand(
        amount=payload.amount if "amount" in fields_set else None,
        type=payload.type if "type" in fields_set else None,
        category_id=payload.category_id if "category_id" in fields_set else None,
        description=payload.description if "description" in fields_set else None,
        next_due_date=(
            payload.next_due_date if "next_due_date" in fields_set else None
        ),
        end_date=payload.end_date if "end_date" in fields_set else None,
        is_recurring=(payload.is_recurring if "is_recurring" in fields_set else None),
        frequency_interval=(
            payload.frequency_interval if "frequency_interval" in fields_set else None
        ),
        frequency_unit=(
            payload.frequency_unit if "frequency_unit" in fields_set else None
        ),
        is_active=payload.is_active if "is_active" in fields_set else None,
    )
    return service.update_payment_plan(account_id, payment_plan_id, command)
