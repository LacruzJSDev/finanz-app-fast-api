import uuid
from typing import Annotated

from fastapi import Depends

from app.account_groups.dependencies import check_group_role
from app.account_groups.repository import AccountGroupMemberRepository
from app.categories.models import Category
from app.categories.repository import CategoryRepository
from app.categories.service import CategoryService
from app.shared.dependencies import CurrentUser, DbSession
from app.shared.exceptions import ForbiddenError


def get_category_repository(db: DbSession) -> CategoryRepository:
    return CategoryRepository(db)


def get_category_service(
    category_repo: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> CategoryService:
    return CategoryService(category_repo)


CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]


def verify_category_access(
    category_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
) -> Category:
    """categories.md §4: para endpoints con {category_id} en la ruta, resuelve
    la pertenencia a partir de la propia categoría, en vez de pedirle
    group_id al cliente por separado — mismo patrón que verify_account_access
    en accounts/dependencies.py.
    """
    category_repo = CategoryRepository(db)
    category = category_repo.get_category_by_id(category_id)
    if category is None:
        raise ForbiddenError("No perteneces al grupo de esta categoría")

    member_repo = AccountGroupMemberRepository(db)
    membership = member_repo.get_membership(category.group_id, user.id)
    check_group_role(membership)
    return category


RequireCategoryAccess = Annotated[Category, Depends(verify_category_access)]
