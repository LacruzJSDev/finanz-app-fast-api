import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base, enum_values


class AuthProviderEnum(str, enum.Enum):
    """Métodos de autenticación admitidos.

    Solo estos dos: añadir un valor a un ENUM de Postgres es una línea, pero
    quitarlo obliga a recrear el tipo y reescribir las columnas que lo usan.
    """

    LOCAL = "local"
    GOOGLE = "google"


class AuthProvider(Base):
    """Método de autenticación vinculado a un usuario.

    Un usuario puede tener varios: registrarse con Google y añadir contraseña
    más tarde, o al revés.
    """

    __tablename__ = "auth_providers"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    # values_callable es obligatorio: por defecto SQLAlchemy guardaría los
    # nombres de los miembros ('LOCAL'), y el CHECK de abajo compara con
    # 'local'. Sin esto ninguna fila pasaría la restricción.
    provider: Mapped[AuthProviderEnum] = mapped_column(
        Enum(
            AuthProviderEnum,
            name="auth_provider_enum",
            values_callable=enum_values,
        )
    )
    # Ambas opcionales a propósito: cuál es obligatoria depende de `provider`,
    # y eso lo impone el CHECK, no un NOT NULL de columna.
    provider_user_id: Mapped[str | None] = mapped_column(String(255))
    password_hash: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        CheckConstraint(
            "(provider = 'local'  AND password_hash IS NOT NULL "
            "AND provider_user_id IS NULL) OR "
            "(provider <> 'local' AND provider_user_id IS NOT NULL "
            "AND password_hash IS NULL)",
            name="provider_fields",
        ),
        UniqueConstraint("provider", "provider_user_id", name="uq_provider_identity"),
        # No es redundante con el UNIQUE de arriba: provider_user_id es NULL en
        # las filas 'local' y Postgres no considera que dos NULL choquen, así
        # que nada impediría dos contraseñas para el mismo usuario.
        Index(
            "uq_auth_providers_local_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("provider = 'local'"),
        ),
    )


class UserSession(Base):
    """Sesión de autenticación activa, revocable.

    UserSession y no Session para no chocar con sqlalchemy.orm.Session, que en
    los repositorios se escribe constantemente.
    """

    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    # El hash del refresh token, nunca el valor en claro: quien acceda a la
    # base de datos no debe poder robar sesiones activas leyendo una columna.
    refresh_token_hash: Mapped[str] = mapped_column(
        String(255), unique=True, index=True
    )
    revoked: Mapped[bool] = mapped_column(server_default=text("false"))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
