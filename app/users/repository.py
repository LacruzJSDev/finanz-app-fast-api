from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

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
