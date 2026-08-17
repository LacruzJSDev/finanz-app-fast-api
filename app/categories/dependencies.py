import uuid
from typing import Annotated, Callable

from fastapi import Depends

from app.account_groups.dependencies import check_group_role
from app.account_groups.models import AccountGroupMemberRoleEnum
from app.account_groups.repository import AccountGroupMemberRepository
from app.categories.models import Category
from app.categories.repository import CategoryRepository
from app.categories.service import CategoryService
from app.shared.dependencies import CurrentUser, DbSession
from app.shared.exceptions import ForbiddenError
from app.users.models import User


def get_category_repository(db: DbSession) -> CategoryRepository:
    return CategoryRepository(db)


def get_category_service(
    category_repo: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> CategoryService:
    return CategoryService(category_repo)


CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]


def require_category_role(
    *allowed_roles: AccountGroupMemberRoleEnum,
) -> Callable[[uuid.UUID, User, DbSession], Category]:
    """categories.md §4: para endpoints con {category_id} en la ruta, resuelve
    la pertenencia a partir de la propia categoría — mismo patrón que
    require_account_role en accounts/dependencies.py, reutilizando el mismo
    check_group_role. Reemplaza a la verify_category_access original, que
    solo comprobaba pertenencia sin distinguir rol: PATCH necesita
    owner/admin, no cualquier miembro.
    """

    def verify_category_access(
        category_id: uuid.UUID,
        user: CurrentUser,
        db: DbSession,
    ) -> Category:
        category_repo = CategoryRepository(db)
        category = category_repo.get_category_by_id(category_id)
        if category is None:
            raise ForbiddenError("No perteneces al grupo de esta categoría")

        member_repo = AccountGroupMemberRepository(db)
        membership = member_repo.get_membership(category.group_id, user.id)
        check_group_role(membership, *allowed_roles)
        return category

    return verify_category_access


RequireCategoryMembership = Annotated[
    Category, Depends(require_category_role())  # sin roles = solo exige pertenencia
]

RequireCategoryOwnerOrAdmin = Annotated[
    Category,
    Depends(
        require_category_role(
            AccountGroupMemberRoleEnum.OWNER, AccountGroupMemberRoleEnum.ADMIN
        )
    ),
]
