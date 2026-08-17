from typing import Annotated

from fastapi import Depends

from app.categories.repository import CategoryRepository
from app.categories.service import CategoryService
from app.shared.dependencies import DbSession


def get_category_repository(db: DbSession) -> CategoryRepository:
    return CategoryRepository(db)


def get_category_service(
    category_repo: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> CategoryService:
    return CategoryService(category_repo)


CategoryServiceDep = Annotated[CategoryService, Depends(get_category_service)]
