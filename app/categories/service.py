import uuid
from dataclasses import dataclass

from app.categories.commands import CategoryCommand, UpdateCategoryCommand
from app.categories.repository import CategoryRepository
from app.categories.schemas import CategoryRead
from app.shared.commands import UNSET
from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError


@dataclass
class CategoryService:
    """Lógica de negocio del dominio categories."""

    category_repo: CategoryRepository

    def _check_parent(
        self,
        parent_id: uuid.UUID,
        group_id: uuid.UUID,
        category_id: uuid.UUID | None,
    ) -> None:
        """categories.md §5: lo que el trigger trg_check_category_depth no
        cubre (parent de otro grupo, o convertir en subcategoría a una fila
        que ya tiene hijos propios) se valida aquí. El propio trigger sigue
        siendo la última barrera si esta validación tuviera un fallo.
        """
        if parent_id == category_id:
            raise ConflictError("Una categoría no puede ser su propio padre")

        parent = self.category_repo.get_category_by_id(parent_id)
        if parent is None:
            raise ConflictError("La categoría padre no existe")
        if parent.group_id != group_id:
            raise ConflictError("La categoría padre pertenece a otro grupo")
        if parent.parent_id is not None:
            raise ConflictError("La categoría padre ya es una subcategoría")

        if category_id is not None and self.category_repo.has_children(category_id):
            raise ConflictError(
                "La categoría ya tiene subcategorías propias, no puede pasar a "
                "ser ella misma una subcategoría"
            )

    def create_category(
        self, user_id: uuid.UUID, category_command: CategoryCommand
    ) -> CategoryRead:
        if category_command.parent_id is not None:
            self._check_parent(
                category_command.parent_id, category_command.group_id, None
            )
        category = self.category_repo.create_category(user_id, category_command)
        return CategoryRead.model_validate(category)

    def get_categories(self, group_id: uuid.UUID) -> list[CategoryRead]:
        categories = self.category_repo.get_categories_by_group_id(group_id)
        return [CategoryRead.model_validate(category) for category in categories]

    def get_category(self, category_id: uuid.UUID) -> CategoryRead:
        category = self.category_repo.get_category_by_id(category_id)
        if category is None:
            raise NotFoundError("La categoría no existe")
        return CategoryRead.model_validate(category)

    def update_category(
        self,
        category_id: uuid.UUID,
        category: UpdateCategoryCommand,
        user_id: uuid.UUID,
    ) -> CategoryRead:
        fields = (
            category.name,
            category.parent_id,
            category.color,
            category.icon,
            category.is_active,
        )
        if all(field is UNSET for field in fields):
            raise BadRequestError("Debes incluir al menos un campo para actualizar")

        # Vaciar parent_id (null explícito) promueve la categoría a raíz y no
        # necesita validarse; solo se comprueba cuando se asigna un padre.
        if category.parent_id is not UNSET and category.parent_id is not None:
            current = self.category_repo.get_category_by_id(category_id)
            if current is None:
                raise NotFoundError("La categoría no existe")
            self._check_parent(category.parent_id, current.group_id, category_id)

        updated_category = self.category_repo.update_category(
            category_id, category, user_id
        )
        return CategoryRead.model_validate(updated_category)
