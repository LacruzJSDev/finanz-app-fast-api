import uuid
from datetime import date as date_
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.account_groups.dependencies import RequireMembership
from app.budgets.commands import SetBudgetCommand
from app.budgets.dependencies import BudgetServiceDep
from app.budgets.schemas import BudgetProgressRead, BudgetRead, SetBudgetRequest
from app.categories.dependencies import (
    RequireCategoryMembership,
    RequireCategoryOwnerOrAdmin,
)
from app.shared.dependencies import CurrentUser
from app.shared.openapi_responses import (
    CONFLICT,
    FORBIDDEN,
    NOT_FOUND,
    UNAUTHORIZED,
    responses,
)
from app.shared.schemas import CollectionResponse

router = APIRouter(prefix="/budgets", tags=["budgets"])

# budgets.md §4: el listado se hace por grupo y las escrituras por categoría.
# Con category_id en la ruta, la autorización es la de categories tal cual.
GroupIdQuery = Annotated[
    uuid.UUID, Query(description="Grupo al que pertenecen los presupuestos")
]
MonthQuery = Annotated[
    date_ | None, Query(description="Cualquier fecha del mes consultado")
]


@router.get("/", responses=responses(UNAUTHORIZED, FORBIDDEN))
def get_budgets(
    service: BudgetServiceDep,
    group_id: GroupIdQuery,
    membership: RequireMembership,
    month: MonthQuery = None,
) -> CollectionResponse[BudgetProgressRead]:
    result = service.get_budget_progress(group_id, month)
    return CollectionResponse[BudgetProgressRead](items=result)


@router.put(
    "/{category_id}",
    responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT),
)
def set_budget(
    payload: SetBudgetRequest,
    service: BudgetServiceDep,
    user: CurrentUser,
    category_id: uuid.UUID,
    category: RequireCategoryOwnerOrAdmin,
) -> BudgetRead:
    set_budget_command = SetBudgetCommand(
        category_id=category_id,
        amount=payload.amount,
        valid_from=payload.valid_from,
    )
    return service.set_budget(user.id, set_budget_command)


@router.delete(
    "/{category_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=responses(UNAUTHORIZED, FORBIDDEN, NOT_FOUND, CONFLICT),
)
def delete_budget(
    service: BudgetServiceDep,
    user: CurrentUser,
    category_id: uuid.UUID,
    category: RequireCategoryOwnerOrAdmin,
) -> None:
    service.delete_budget(user.id, category_id)
    return


@router.get("/{category_id}/history", responses=responses(UNAUTHORIZED, FORBIDDEN))
def get_budget_history(
    service: BudgetServiceDep,
    category_id: uuid.UUID,
    category: RequireCategoryMembership,
) -> CollectionResponse[BudgetRead]:
    result = service.get_budget_history(category_id)
    return CollectionResponse[BudgetRead](items=result)
