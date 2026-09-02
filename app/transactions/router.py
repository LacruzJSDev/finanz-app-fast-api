import uuid
from datetime import date as date_
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.account_groups.dependencies import RequireMembership
from app.accounts.dependencies import RequireAccountMembership
from app.shared.commands import UNSET
from app.shared.dependencies import CurrentUser
from app.shared.openapi_responses import (
    BAD_REQUEST,
    CONFLICT,
    FORBIDDEN,
    NOT_FOUND,
    UNAUTHORIZED,
    responses,
)
from app.shared.schemas import CollectionResponse, PaginatedResponse
from app.transactions.commands import (
    CreateTransactionCommand,
    DailySpendCommand,
    TransactionFilterCommand,
    UpdateTransactionCommand,
)
from app.transactions.dependencies import TransactionFiltersDep, TransactionServiceDep
from app.transactions.schemas import (
    CategorySummaryRead,
    CreateTransactionRequest,
    DailySpendRead,
    TransactionFilterQuery,
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
    user: CurrentUser,
    account_id: uuid.UUID,
    transaction_id: uuid.UUID,
    account: RequireAccountMembership,
) -> TransactionRead:
    fields_set = payload.model_fields_set
    # El else va a UNSET, no a None: si ambas ramas dieran None, un campo
    # enviado como null sería indistinguible de uno ausente y no habría forma
    # de vaciarlo (ARCHITECTURE.md §5.5).
    command = UpdateTransactionCommand(
        amount=payload.amount if payload.amount is not None else UNSET,
        type=payload.type if payload.type is not None else UNSET,
        category_id=payload.category_id if "category_id" in fields_set else UNSET,
        date=payload.date if payload.date is not None else UNSET,
        notes=payload.notes if "notes" in fields_set else UNSET,
    )
    return service.update_transaction(account_id, transaction_id, command, user.id)


@router.delete(
    "/{transaction_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND),
)
def delete_transaction(
    service: TransactionServiceDep,
    user: CurrentUser,
    account_id: uuid.UUID,
    transaction_id: uuid.UUID,
    account: RequireAccountMembership,
) -> None:
    service.delete_transaction(account_id, transaction_id, user.id)
    return


# Segundo router del dominio: consultar es una pregunta de grupo, no de
# cuenta, y un APIRouter solo admite un prefix (ADR-0002). El anidado de
# arriba queda intacto por ARCHITECTURE.md §5.1.
query_router = APIRouter(prefix="/transactions", tags=["transactions"])

GroupIdQuery = Annotated[uuid.UUID, Query(description="Grupo que se consulta")]
AccountIdQuery = Annotated[uuid.UUID | None, Query(description="Cuenta del grupo")]
DateQuery = Annotated[date_, Query(description="Día consultado")]


def _to_filter_command(
    group_id: uuid.UUID, filters: TransactionFilterQuery
) -> TransactionFilterCommand:
    return TransactionFilterCommand(
        group_id=group_id,
        account_id=filters.account_id,
        category_id=filters.category_id,
        uncategorized=filters.uncategorized,
        type=filters.type,
        date_from=filters.date_from,
        date_to=filters.date_to,
        q=filters.q,
    )


@query_router.get("/", responses=responses(UNAUTHORIZED, FORBIDDEN, CONFLICT))
def query_transactions(
    service: TransactionServiceDep,
    group_id: GroupIdQuery,
    membership: RequireMembership,
    filters: TransactionFiltersDep,
    limit: LimitQuery = 20,
    offset: OffsetQuery = 0,
) -> PaginatedResponse[TransactionRead]:
    result = service.get_filtered_transactions(
        _to_filter_command(group_id, filters), limit, offset
    )
    return PaginatedResponse[TransactionRead](
        items=result.items, total=result.total, limit=limit, offset=offset
    )


@query_router.get("/summary", responses=responses(UNAUTHORIZED, FORBIDDEN, CONFLICT))
def get_category_summary(
    service: TransactionServiceDep,
    group_id: GroupIdQuery,
    membership: RequireMembership,
    filters: TransactionFiltersDep,
) -> CollectionResponse[CategorySummaryRead]:
    items = service.get_category_summary(_to_filter_command(group_id, filters))
    return CollectionResponse[CategorySummaryRead](items=items)


@query_router.get("/daily", responses=responses(UNAUTHORIZED, FORBIDDEN, CONFLICT))
def get_daily_spend(
    service: TransactionServiceDep,
    group_id: GroupIdQuery,
    membership: RequireMembership,
    date: DateQuery,
    account_id: AccountIdQuery = None,
) -> DailySpendRead:
    command = DailySpendCommand(group_id=group_id, date=date, account_id=account_id)
    return service.get_daily_spend(command)
