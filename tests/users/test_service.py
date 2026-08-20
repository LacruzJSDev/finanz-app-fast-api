import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError
from app.users.commands import UpdateUserCommand
from app.users.models import User
from app.users.repository import UserRepository
from app.users.service import UserService


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


@pytest.fixture
def user_repo() -> MagicMock:
    return MagicMock(spec=UserRepository)


@pytest.fixture
def service(user_repo: MagicMock) -> UserService:
    return UserService(user_repo)


class TestGetUser:
    def test_returns_user_when_found(self, service: UserService, user_repo: MagicMock):
        user = make_user()
        user_repo.get_user_by_id.return_value = user

        result = service.get_user(user.id)

        assert result.id == user.id
        assert result.email == user.email
        user_repo.get_user_by_id.assert_called_once_with(user.id)

    def test_raises_not_found_when_missing(
        self, service: UserService, user_repo: MagicMock
    ):
        user_repo.get_user_by_id.return_value = None

        with pytest.raises(NotFoundError):
            service.get_user(uuid.uuid4())


class TestUpdateUser:
    def test_raises_bad_request_when_no_fields(
        self, service: UserService, user_repo: MagicMock
    ):
        command = UpdateUserCommand(name=None, email=None)

        with pytest.raises(BadRequestError):
            service.update_user(uuid.uuid4(), command)

        user_repo.update_user.assert_not_called()

    def test_updates_name_only_without_checking_email(
        self, service: UserService, user_repo: MagicMock
    ):
        user_id = uuid.uuid4()
        updated = make_user(id=user_id, name="New Name")
        user_repo.update_user.return_value = updated
        command = UpdateUserCommand(name="New Name", email=None)

        result = service.update_user(user_id, command)

        assert result.name == "New Name"
        user_repo.get_user_by_email.assert_not_called()
        user_repo.update_user.assert_called_once_with(user_id, command)

    def test_updates_email_when_not_taken(
        self, service: UserService, user_repo: MagicMock
    ):
        user_id = uuid.uuid4()
        user_repo.get_user_by_email.return_value = None
        updated = make_user(id=user_id, email="new@test.com")
        user_repo.update_user.return_value = updated
        command = UpdateUserCommand(name=None, email="new@test.com")

        result = service.update_user(user_id, command)

        assert result.email == "new@test.com"

    def test_allows_email_already_belonging_to_self(
        self, service: UserService, user_repo: MagicMock
    ):
        user_id = uuid.uuid4()
        self_user = make_user(id=user_id, email="same@test.com")
        user_repo.get_user_by_email.return_value = self_user
        user_repo.update_user.return_value = self_user
        command = UpdateUserCommand(name=None, email="same@test.com")

        result = service.update_user(user_id, command)

        assert result.email == "same@test.com"
        user_repo.update_user.assert_called_once()

    def test_raises_conflict_when_email_belongs_to_another_user(
        self, service: UserService, user_repo: MagicMock
    ):
        user_id = uuid.uuid4()
        other_user = make_user(id=uuid.uuid4(), email="taken@test.com")
        user_repo.get_user_by_email.return_value = other_user
        command = UpdateUserCommand(name=None, email="taken@test.com")

        with pytest.raises(ConflictError):
            service.update_user(user_id, command)

        user_repo.update_user.assert_not_called()
