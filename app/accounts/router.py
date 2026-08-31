import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.account_groups.dependencies import RequireMembership, RequireOwnerOrAdmin
from app.accounts.commands import AccountCommand, UpdateAccountCommand
from app.accounts.dependencies import (
    AccountServiceDep,
    RequireAccountMembership,
    RequireAccountOwnerOrAdmin,
)
from app.accounts.schemas import (
    AccountRead,
    CreateAccountRequest,
    GroupBalanceRead,
    UpdateAccountRequest,
)
from app.shared.commands import UNSET
from app.shared.dependencies import CurrentUser
from app.shared.openapi_responses import (
    BAD_REQUEST,
    CONFLICT,
    FORBIDDEN,
    UNAUTHORIZED,
    responses,
)
from app.shared.schemas import CollectionResponse

router = APIRouter(prefix="/accounts", tags=["accounts"])

# accounts.md §4: group_id va en la query string, no en el body ni como
# segmento de la ruta — así RequireOwnerOrAdmin lo resuelve sin código de
# autorización propio de este dominio (ver dependencies.py de account_groups).
GroupIdQuery = Annotated[
    uuid.UUID, Query(description="Grupo al que pertenece la cuenta")
]


@router.post(
    "/",
    status_code=status.HTTP_201_CREATED,
    responses=responses(UNAUTHORIZED, FORBIDDEN, CONFLICT),
)
def create_account(
    payload: CreateAccountRequest,
    service: AccountServiceDep,
    user: CurrentUser,
    group_id: GroupIdQuery,
    membership: RequireOwnerOrAdmin,
) -> AccountRead:
    account_command = AccountCommand(
        group_id=group_id,
        name=payload.name,
        type=payload.type,
        opening_balance=payload.opening_balance,
        currency=payload.currency,
        color=payload.color,
        icon=payload.icon,
    )
    return service.create_account(user.id, account_command)


@router.get("/", responses=responses(UNAUTHORIZED, FORBIDDEN))
def get_accounts(
    service: AccountServiceDep, group_id: GroupIdQuery, membership: RequireMembership
) -> CollectionResponse[AccountRead]:
    result = service.get_accounts(group_id)
    collection_response = CollectionResponse[AccountRead](items=result)
    return collection_response


# accounts.md §4: debe ir declarada antes que GET /{account_id}, o FastAPI
# resuelve "balance" como un account_id y responde un 422 de UUID inválido.
@router.get("/balance", responses=responses(UNAUTHORIZED, FORBIDDEN))
def get_group_balance(
    service: AccountServiceDep, group_id: GroupIdQuery, membership: RequireMembership
) -> GroupBalanceRead:
    return service.get_group_balance(group_id)


@router.get("/{account_id}", responses=responses(UNAUTHORIZED, FORBIDDEN))
def get_account(
    service: AccountServiceDep,
    account_id: uuid.UUID,
    account: RequireAccountMembership,
) -> AccountRead:
    return service.get_account(account_id)


@router.patch(
    "/{account_id}", responses=responses(UNAUTHORIZED, FORBIDDEN, BAD_REQUEST)
)
def update_account(
    payload: UpdateAccountRequest,
    service: AccountServiceDep,
    account_id: uuid.UUID,
    account: RequireAccountOwnerOrAdmin,
) -> AccountRead:

    fields_set = payload.model_fields_set
    update_account_command = UpdateAccountCommand(
        name=payload.name if payload.name is not None else UNSET,
        type=payload.type if payload.type is not None else UNSET,
        color=payload.color if "color" in fields_set else UNSET,
        icon=payload.icon if "icon" in fields_set else UNSET,
        is_active=payload.is_active if payload.is_active is not None else UNSET,
    )
    return service.update_account(account_id, update_account_command)
