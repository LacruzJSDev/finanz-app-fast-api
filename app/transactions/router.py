import uuid

from fastapi import APIRouter, status

from app.accounts.dependencies import RequireAccountMembership
from app.shared.dependencies import CurrentUser
from app.transactions.commands import CreateTransactionCommand
from app.transactions.dependencies import TransactionServiceDep
from app.transactions.schemas import CreateTransactionRequest, TransactionRead

router = APIRouter(prefix="/accounts/{account_id}/transactions", tags=["transactions"])


@router.post("/", status_code=status.HTTP_201_CREATED)
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
