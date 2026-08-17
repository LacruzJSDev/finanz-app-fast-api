import uuid
from dataclasses import dataclass

from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError
from app.users.commands import UpdateUserCommand
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

    def update_user(self, user_id: uuid.UUID, command: UpdateUserCommand) -> UserRead:
        if command.name is None and command.email is None:
            raise BadRequestError("Debes incluir al menos un campo para actualizar")

        if command.email is not None:
            existing_user = self.user_repo.get_user_by_email(command.email)
            if existing_user is not None and existing_user.id != user_id:
                raise ConflictError("El email ya está en uso")

        updated_user = self.user_repo.update_user(user_id, command)
        return UserRead.model_validate(updated_user)
