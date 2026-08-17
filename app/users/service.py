import uuid
from dataclasses import dataclass

from app.shared.exceptions import NotFoundError
from app.users.repository import UserRepository
from app.users.schemas import UserRead


@dataclass
class UserService:
    """Lógica de negocio del dominio users."""

    user_repo: UserRepository

    def get_user(self, user_id: uuid.UUID) -> UserRead:
        user = self.user_repo.get_user_by_id(user_id)
        if user is None:
            raise NotFoundError("El usuario no existe")
        return UserRead.model_validate(user)
