import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.account_groups.dependencies import RequireOwnerOrAdmin
from app.accounts.commands import AccountCommand
from app.accounts.dependencies import AccountServiceDep
from app.accounts.schemas import AccountRead, CreateAccountRequest
from app.shared.dependencies import CurrentUser

router = APIRouter(prefix="/accounts", tags=["accounts"])

# accounts.md §4: group_id va en la query string, no en el body ni como
# segmento de la ruta — así RequireOwnerOrAdmin lo resuelve sin código de
# autorización propio de este dominio (ver dependencies.py de account_groups).
GroupIdQuery = Annotated[
    uuid.UUID, Query(description="Grupo al que pertenece la cuenta")
]


@router.post("/", status_code=status.HTTP_201_CREATED)
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
