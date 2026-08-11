import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.auth.models import AuthProvider, AuthProviderEnum, UserSession


@dataclass
class AuthRepository:
    """Acceso a datos del dominio auth.

    No incluye búsquedas de User: esa tabla la posee el dominio users (ver
    ARCHITECTURE.md §2.1), y AuthService ya recibe UserRepository para eso.

    Única capa que toca la sesión de SQLAlchemy. No hace commit ni rollback:
    la transacción la cierra get_db al terminar la petición.
    """

    db: Session

    def get_local_provider(self, user_id: uuid.UUID) -> AuthProvider | None:
        """Método de autenticación por contraseña de un usuario, si lo tiene."""
        return self.db.execute(
            select(AuthProvider).where(
                AuthProvider.user_id == user_id,
                AuthProvider.provider == AuthProviderEnum.LOCAL,
            )
        ).scalar_one_or_none()

    def create_local_provider(
        self, user_id: uuid.UUID, password_hash: str
    ) -> AuthProvider:
        """Método de creación de un nuevo auth_provider local para un usuario"""
        auth_provider_local = AuthProvider(
            user_id=user_id,
            provider=AuthProviderEnum.LOCAL,
            password_hash=password_hash,
        )
        self.db.add(auth_provider_local)
        return auth_provider_local

    def change_password_hash(self, user_id: uuid.UUID, password_hash: str) -> None:
        """Método para cambiar la contraseña del auth_provider local"""
        self.db.execute(
            update(AuthProvider)
            .where(
                AuthProvider.user_id == user_id,
                AuthProvider.provider == AuthProviderEnum.LOCAL,
            )
            .values(password_hash=password_hash)
        )

    def create_session(
        self, user_id: uuid.UUID, refresh_token_hash: str, expires_at: datetime
    ) -> UserSession:
        """Registra una sesión activa a partir del refresh token emitido.

        Nunca recibe el token en claro, solo su hash (ver el comentario de
        `sessions.refresh_token_hash` en el modelo): quien llame a esto ya
        tiene que haberlo hasheado con `app.shared.hashing.hash_token`.
        """
        session = UserSession(
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
        )
        self.db.add(session)
        return session

    def revoke_session_by_refresh_token_hash(self, refresh_token_hash: str) -> None:
        """Revoca una sesión buscando por el hash del refresh_token"""
        self.db.execute(
            update(UserSession)
            .where(UserSession.refresh_token_hash == refresh_token_hash)
            .values(revoked=True)
        )

    def get_session_by_refresh_token_hash(
        self, refresh_token_hash: str
    ) -> UserSession | None:
        return self.db.execute(
            select(UserSession).where(
                UserSession.refresh_token_hash == refresh_token_hash
            )
        ).scalar_one_or_none()
