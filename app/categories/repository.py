import uuid
from dataclasses import dataclass

from sqlalchemy import exists, select, update
from sqlalchemy.orm import Session

from app.categories.commands import CategoryCommand, UpdateCategoryCommand
from app.categories.models import Category
from app.shared.commands import UNSET


@dataclass
class CategoryRepository:
    """Acceso a datos del dominio categories."""

    db: Session

    def create_category(
        self, user_id: uuid.UUID, new_category: CategoryCommand
    ) -> Category:
        # Aquí no interviene UNSET: en una creación, None significa "usa el
        # default de la columna", así que se omite del constructor.
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

    def has_children(self, category_id: uuid.UUID) -> bool:
        return bool(
            self.db.execute(
                select(exists().where(Category.parent_id == category_id))
            ).scalar_one()
        )

    def update_category(
        self,
        category_id: uuid.UUID,
        category: UpdateCategoryCommand,
        user_id: uuid.UUID,
    ) -> Category:
        # UNSET es la marca de ausencia; un None que llega aquí es un null
        # explícito del cliente y sí se escribe (ARCHITECTURE.md §5.5).
        values: dict[str, uuid.UUID | str | bool | None] = {}
        if category.name is not UNSET:
            values["name"] = category.name
        if category.parent_id is not UNSET:
            values["parent_id"] = category.parent_id
        if category.color is not UNSET:
            values["color"] = category.color
        if category.icon is not UNSET:
            values["icon"] = category.icon
        if category.is_active is not UNSET:
            values["is_active"] = category.is_active
        values["updated_by"] = user_id

        return self.db.execute(
            update(Category)
            .where(Category.id == category_id)
            .values(**values)
            .returning(Category)
        ).scalar_one()
