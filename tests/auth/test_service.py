import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest
from sqlalchemy.exc import IntegrityError

from app.auth.models import AuthProvider, AuthProviderEnum, UserSession
from app.auth.repository import AuthRepository
from app.auth.service import AuthService
from app.shared.bcrypt import hash_password, verify_password
from app.shared.exceptions import ConflictError, UnauthorizedError
from app.shared.hashing import hash_token
from app.users.models import User
from app.users.repository import UserRepository


def make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "email": "user@test.com",
        "name": "Test User",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return User(**defaults)  # pyright: ignore[reportArgumentType]


def make_local_provider(
    user_id: uuid.UUID, password: str, **overrides: object
) -> AuthProvider:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "provider": AuthProviderEnum.LOCAL,
        "password_hash": hash_password(password),
        "provider_user_id": None,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return AuthProvider(**defaults)  # pyright: ignore[reportArgumentType]


def make_session(
    user_id: uuid.UUID,
    refresh_token: str,
    *,
    revoked: bool = False,
    expires_delta: timedelta = timedelta(days=7),
    **overrides: object,
) -> UserSession:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "user_id": user_id,
        "refresh_token_hash": hash_token(refresh_token),
        "revoked": revoked,
        "expires_at": datetime.now(timezone.utc) + expires_delta,
        "created_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return UserSession(**defaults)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def auth_repo() -> MagicMock:
    return MagicMock(spec=AuthRepository)


@pytest.fixture
def user_repo() -> MagicMock:
    return MagicMock(spec=UserRepository)


@pytest.fixture
def service(auth_repo: MagicMock, user_repo: MagicMock) -> AuthService:
    return AuthService(auth_repo, user_repo)


class TestLogin:
    def test_raises_unauthorized_when_user_not_found(
        self, service: AuthService, user_repo: MagicMock
    ):
        user_repo.get_user_by_email.return_value = None

        with pytest.raises(UnauthorizedError):
            service.login("nobody@test.com", "whatever")

    def test_raises_unauthorized_when_no_local_provider(
        self, service: AuthService, user_repo: MagicMock, auth_repo: MagicMock
    ):
        user = make_user()
        user_repo.get_user_by_email.return_value = user
        auth_repo.get_local_provider.return_value = None

        with pytest.raises(UnauthorizedError):
            service.login(user.email, "whatever")

    def test_raises_unauthorized_when_password_wrong(
        self, service: AuthService, user_repo: MagicMock, auth_repo: MagicMock
    ):
        user = make_user()
        user_repo.get_user_by_email.return_value = user
        auth_repo.get_local_provider.return_value = make_local_provider(
            user.id, "correct-password"
        )

        with pytest.raises(UnauthorizedError):
            service.login(user.email, "wrong-password")

    def test_issues_tokens_and_creates_session_on_success(
        self, service: AuthService, user_repo: MagicMock, auth_repo: MagicMock
    ):
        user = make_user()
        user_repo.get_user_by_email.return_value = user
        auth_repo.get_local_provider.return_value = make_local_provider(
            user.id, "correct-password"
        )

        result = service.login(user.email, "correct-password")

        assert result.user.id == user.id
        assert result.access_token
        assert result.refresh_token
        auth_repo.create_session.assert_called_once()
        call_kwargs = auth_repo.create_session.call_args.kwargs
        assert call_kwargs["user_id"] == user.id
        assert call_kwargs["refresh_token_hash"] == hash_token(result.refresh_token)


class TestRegister:
    def test_raises_conflict_when_email_already_registered(
        self, service: AuthService, user_repo: MagicMock
    ):
        user_repo.get_user_by_email.return_value = make_user()

        with pytest.raises(ConflictError):
            service.register("dup@test.com", "Name", "Password123!")

        user_repo.create_user.assert_not_called()

    def test_raises_conflict_on_integrity_error_race(
        self, service: AuthService, user_repo: MagicMock
    ):
        user_repo.get_user_by_email.return_value = None
        user_repo.create_user.side_effect = IntegrityError(
            "INSERT", {}, Exception("duplicate key")
        )

        with pytest.raises(ConflictError):
            service.register("race@test.com", "Name", "Password123!")

    def test_creates_user_local_provider_and_session_on_success(
        self, service: AuthService, user_repo: MagicMock, auth_repo: MagicMock
    ):
        user_repo.get_user_by_email.return_value = None
        user = make_user(email="new@test.com", name="New User")
        user_repo.create_user.return_value = user

        result = service.register("new@test.com", "New User", "Password123!")

        assert result.user.email == "new@test.com"
        user_repo.create_user.assert_called_once_with("new@test.com", "New User")
        auth_repo.create_local_provider.assert_called_once()
        password_hash = auth_repo.create_local_provider.call_args.args[1]
        assert verify_password("Password123!", password_hash)
        auth_repo.create_session.assert_called_once()


class TestLogout:
    def test_revokes_session_by_refresh_token_hash(
        self, service: AuthService, auth_repo: MagicMock
    ):
        service.logout("some-refresh-token")

        auth_repo.revoke_session_by_refresh_token_hash.assert_called_once_with(
            hash_token("some-refresh-token")
        )


class TestRefresh:
    def test_raises_unauthorized_when_session_not_found(
        self, service: AuthService, auth_repo: MagicMock
    ):
        auth_repo.get_session_by_refresh_token_hash.return_value = None

        with pytest.raises(UnauthorizedError):
            service.refresh("unknown-token")

    def test_raises_unauthorized_when_session_revoked(
        self, service: AuthService, auth_repo: MagicMock
    ):
        user_id = uuid.uuid4()
        auth_repo.get_session_by_refresh_token_hash.return_value = make_session(
            user_id, "token", revoked=True
        )

        with pytest.raises(UnauthorizedError):
            service.refresh("token")

    def test_raises_unauthorized_when_session_expired(
        self, service: AuthService, auth_repo: MagicMock
    ):
        user_id = uuid.uuid4()
        auth_repo.get_session_by_refresh_token_hash.return_value = make_session(
            user_id, "token", expires_delta=timedelta(days=-1)
        )

        with pytest.raises(UnauthorizedError):
            service.refresh("token")

    def test_raises_unauthorized_when_user_missing(
        self, service: AuthService, auth_repo: MagicMock, user_repo: MagicMock
    ):
        user_id = uuid.uuid4()
        auth_repo.get_session_by_refresh_token_hash.return_value = make_session(
            user_id, "token"
        )
        user_repo.get_user_by_id.return_value = None

        with pytest.raises(UnauthorizedError):
            service.refresh("token")

    def test_rotates_tokens_and_revokes_old_session_on_success(
        self, service: AuthService, auth_repo: MagicMock, user_repo: MagicMock
    ):
        user = make_user()
        auth_repo.get_session_by_refresh_token_hash.return_value = make_session(
            user.id, "old-token"
        )
        user_repo.get_user_by_id.return_value = user

        result = service.refresh("old-token")

        assert result.user.id == user.id
        auth_repo.revoke_session_by_refresh_token_hash.assert_called_once_with(
            hash_token("old-token")
        )
        auth_repo.create_session.assert_called_once()


class TestChangePassword:
    def test_raises_unauthorized_when_current_password_wrong(
        self, service: AuthService, auth_repo: MagicMock
    ):
        user = make_user()
        auth_repo.get_local_provider.return_value = make_local_provider(
            user.id, "correct-password"
        )

        with pytest.raises(UnauthorizedError):
            service.change_password(user, "wrong-password", "NewPassword123!")

        auth_repo.change_password_hash.assert_not_called()

    def test_updates_password_hash_on_success(
        self, service: AuthService, auth_repo: MagicMock
    ):
        user = make_user()
        auth_repo.get_local_provider.return_value = make_local_provider(
            user.id, "correct-password"
        )

        service.change_password(user, "correct-password", "NewPassword123!")

        auth_repo.change_password_hash.assert_called_once()
        call_args = auth_repo.change_password_hash.call_args.args
        assert call_args[0] == user.id
        assert verify_password("NewPassword123!", call_args[1])
