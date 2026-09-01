import uuid
from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.shared.commands import UNSET
from app.users.commands import UpdateUserCommand
from app.users.models import User


@dataclass
class UserRepository:
    """Acceso a datos del dominio user.

    Única capa que toca la sesión de SQLAlchemy. No hace commit ni rollback:
    la transacción la cierra get_db al terminar la petición.
    """

    db: Session

    def get_user_by_email(self, email: str) -> User | None:
        return self.db.execute(
            select(User).where(User.email == email)
        ).scalar_one_or_none()

    def create_user(self, email: str, name: str) -> User:
        user = User(email=email, name=name)
        self.db.add(user)
        self.db.flush()
        return user

    def get_user_by_id(self, user_id: uuid.UUID) -> User | None:
        return self.db.execute(
            select(User).where(User.id == user_id)
        ).scalar_one_or_none()

    def get_users_by_ids(self, user_ids: set[uuid.UUID]) -> list[User]:
        users = (
            self.db.execute(select(User).where(User.id.in_(user_ids))).scalars().all()
        )

        return list(users)

    def update_user(self, user_id: uuid.UUID, command: UpdateUserCommand) -> User:
        # Ninguno de los dos es vaciable (ambas columnas son NOT NULL), pero
        # la marca de ausencia es UNSET igual que en el resto de dominios.
        values: dict[str, str] = {}
        if command.name is not UNSET:
            values["name"] = command.name
        if command.email is not UNSET:
            values["email"] = command.email

        return self.db.execute(
            update(User).where(User.id == user_id).values(**values).returning(User)
        ).scalar_one()
