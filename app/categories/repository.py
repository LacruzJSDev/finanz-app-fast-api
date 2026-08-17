import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.categories.commands import CategoryCommand
from app.categories.models import Category


@dataclass
class CategoryRepository:
    """Acceso a datos del dominio categories."""

    db: Session

    def create_category(
        self, user_id: uuid.UUID, new_category: CategoryCommand
    ) -> Category:
        values: dict[str, uuid.UUID | str] = {}
        if new_category.parent_id is not None:
            values["parent_id"] = new_category.parent_id
        if new_category.color is not None:
            values["color"] = new_category.color
        if new_category.icon is not None:
            values["icon"] = new_category.icon

        category = Category(
            group_id=new_category.group_id,
            name=new_category.name,
            **values,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(category)
        self.db.flush()
        return category

    def get_categories_by_group_id(self, group_id: uuid.UUID) -> list[Category]:
        categories = (
            self.db.execute(select(Category).where(Category.group_id == group_id))
            .scalars()
            .all()
        )
        return list(categories)

    def get_category_by_id(self, category_id: uuid.UUID) -> Category | None:
        return self.db.execute(
            select(Category).where(Category.id == category_id)
        ).scalar_one_or_none()
