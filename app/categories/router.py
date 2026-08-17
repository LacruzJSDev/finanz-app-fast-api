import uuid
from typing import Annotated

from fastapi import APIRouter, Query, status

from app.account_groups.dependencies import RequireMembership, RequireOwnerOrAdmin
from app.categories.commands import CategoryCommand, UpdateCategoryCommand
from app.categories.dependencies import (
    CategoryServiceDep,
    RequireCategoryMembership,
    RequireCategoryOwnerOrAdmin,
)
from app.categories.schemas import (
    CategoryRead,
    CreateCategoryRequest,
    UpdateCategoryRequest,
)
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


@router.get("/{category_id}")
def get_category(
    service: CategoryServiceDep,
    category_id: uuid.UUID,
    category: RequireCategoryMembership,
) -> CategoryRead:
    return service.get_category(category_id)


@router.patch("/{category_id}")
def update_category(
    payload: UpdateCategoryRequest,
    service: CategoryServiceDep,
    category_id: uuid.UUID,
    category: RequireCategoryOwnerOrAdmin,
) -> CategoryRead:
    fields_set = payload.model_fields_set
    update_category_command = UpdateCategoryCommand(
        name=payload.name if "name" in fields_set else None,
        parent_id=payload.parent_id if "parent_id" in fields_set else None,
        color=payload.color if "color" in fields_set else None,
        icon=payload.icon if "icon" in fields_set else None,
        is_active=payload.is_active if "is_active" in fields_set else None,
    )
    return service.update_category(category_id, update_category_command)
