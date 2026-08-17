import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.account_groups.dependencies import RequireMembership, RequireOwnerOrAdmin
from app.categories.commands import CategoryCommand
from app.categories.dependencies import CategoryServiceDep
from app.categories.schemas import CategoryRead, CreateCategoryRequest
from app.shared.dependencies import CurrentUser
from app.shared.schemas import CollectionResponse

router = APIRouter(prefix="/categories", tags=["categories"])

# categories.md §4: group_id va en la query string, mismo motivo que en
# accounts (ver accounts/router.py).
GroupIdQuery = Annotated[
    uuid.UUID, Query(description="Grupo al que pertenece la categoría")
]


@router.post("/", status_code=status.HTTP_201_CREATED)
def create_category(
    payload: CreateCategoryRequest,
    service: CategoryServiceDep,
    user: CurrentUser,
    group_id: GroupIdQuery,
    membership: RequireOwnerOrAdmin,
) -> CategoryRead:
    category_command = CategoryCommand(
        group_id=group_id,
        name=payload.name,
        parent_id=payload.parent_id,
        color=payload.color,
        icon=payload.icon,
    )
    return service.create_category(user.id, category_command)


@router.get("/")
def get_categories(
    service: CategoryServiceDep, group_id: GroupIdQuery, membership: RequireMembership
) -> CollectionResponse[CategoryRead]:
    result = service.get_categories(group_id)
    return CollectionResponse[CategoryRead](items=result)
