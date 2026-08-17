import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.accounts.dependencies import RequireAccountMembership
from app.shared.dependencies import CurrentUser
from app.shared.openapi_responses import (
    BAD_REQUEST,
    CONFLICT,
    FORBIDDEN,
    NOT_FOUND,
    UNAUTHORIZED,
    responses,
)
from app.shared.schemas import PaginatedResponse
from app.transactions.commands import CreateTransactionCommand, UpdateTransactionCommand
from app.transactions.dependencies import TransactionServiceDep
from app.transactions.schemas import (
    CreateTransactionRequest,
    TransactionRead,
    UpdateTransactionRequest,
)

LimitQuery = Annotated[int, Query(gt=0, le=100)]
OffsetQuery = Annotated[int, Query(ge=0)]

router = APIRouter(prefix="/accounts/{account_id}/transactions", tags=["transactions"])


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses=responses(UNAUTHORIZED, FORBIDDEN, CONFLICT),
)
def create_transaction(
    payload: CreateTransactionRequest,
    service: TransactionServiceDep,
    user: CurrentUser,
    account_id: uuid.UUID,
    account: RequireAccountMembership,
) -> TransactionRead:
    command = CreateTransactionCommand(
        account_id=account_id,
        group_id=account.group_id,
        type=payload.type,
        amount=payload.amount,
        category_id=payload.category_id,
        to_account_id=payload.to_account_id,
        date=payload.date,
        notes=payload.notes,
    )
    return service.create_transaction(user.id, command)


@router.get("/", responses=responses(UNAUTHORIZED, FORBIDDEN))
def get_transactions(
    service: TransactionServiceDep,
    account_id: uuid.UUID,
    account: RequireAccountMembership,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> PaginatedResponse[TransactionRead]:
    result = service.get_transactions(account_id, limit, offset)
    return PaginatedResponse[TransactionRead](
        items=result.items, total=result.total, limit=limit, offset=offset
    )


@router.get(
    "/{transaction_id}", responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND)
)
def get_transaction(
    service: TransactionServiceDep,
    account_id: uuid.UUID,
    transaction_id: uuid.UUID,
    account: RequireAccountMembership,
) -> TransactionRead:
    return service.get_transaction(account_id, transaction_id)


@router.patch(
    "/{transaction_id}",
    responses=responses(UNAUTHORIZED, FORBIDDEN, BAD_REQUEST, NOT_FOUND, CONFLICT),
)
def update_transaction(
    payload: UpdateTransactionRequest,
    service: TransactionServiceDep,
    account_id: uuid.UUID,
    transaction_id: uuid.UUID,
    account: RequireAccountMembership,
) -> TransactionRead:
    fields_set = payload.model_fields_set
    command = UpdateTransactionCommand(
        amount=payload.amount if "amount" in fields_set else None,
        type=payload.type if "type" in fields_set else None,
        category_id=payload.category_id if "category_id" in fields_set else None,
        date=payload.date if "date" in fields_set else None,
        notes=payload.notes if "notes" in fields_set else None,
    )
    return service.update_transaction(account_id, transaction_id, command)


@router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND),
)
def delete_transaction(
    service: TransactionServiceDep,
    account_id: uuid.UUID,
    transaction_id: uuid.UUID,
    account: RequireAccountMembership,
) -> None:
    service.delete_transaction(account_id, transaction_id)
    return
