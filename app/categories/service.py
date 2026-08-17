import uuid
from dataclasses import dataclass

from app.categories.commands import CategoryCommand
from app.categories.repository import CategoryRepository
from app.categories.schemas import CategoryRead
from app.shared.exceptions import ConflictError


@dataclass
class CategoryService:
    """Lógica de negocio del dominio categories."""

    category_repo: CategoryRepository

    def _check_parent(self, parent_id: uuid.UUID, group_id: uuid.UUID) -> None:
        """categories.md §5: lo que el trigger trg_check_category_depth no
        cubre (parent de otro grupo) se valida aquí. El propio trigger sigue
        siendo la última barrera si esta validación tuviera un fallo.
        """
        parent = self.category_repo.get_category_by_id(parent_id)
        if parent is None:
            raise ConflictError("La categoría padre no existe")
        if parent.group_id != group_id:
            raise ConflictError("La categoría padre pertenece a otro grupo")
        if parent.parent_id is not None:
            raise ConflictError("La categoría padre ya es una subcategoría")

    def create_category(
        self, user_id: uuid.UUID, category_command: CategoryCommand
    ) -> CategoryRead:
        if category_command.parent_id is not None:
            self._check_parent(category_command.parent_id, category_command.group_id)
        category = self.category_repo.create_category(user_id, category_command)
        return CategoryRead.model_validate(category)
