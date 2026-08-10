from sqlalchemy import Column, DateTime, String, func, text
from sqlalchemy.dialects.postgresql import UUID

from app.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )
    email = Column(String(255), unique=True, index=True, nullable=False)
    name = Column(String(100), nullable=False)
    created_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    # La mantiene el trigger trg_users_set_updated_at en cada UPDATE, no el
    # ORM. Tras modificar una fila hay que hacer db.refresh(obj) si se
    # necesita leer el valor nuevo en la misma petición.
    updated_at = Column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
