import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.accounts.commands import AccountCommand, UpdateAccountCommand
from app.accounts.models import Account, AccountTypeEnum
from app.accounts.repository import AccountRepository
from app.accounts.service import AccountService
from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError


def make_account(**overrides: object) -> Account:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "group_id": uuid.uuid4(),
        "name": "Test Account",
        "type": AccountTypeEnum.BANK,
        "opening_balance": 0,
        "balance": 0,
        "currency": "EUR",
        "color": None,
        "icon": None,
        "is_active": True,
        "created_by": None,
        "updated_by": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Account(**defaults)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def account_repo() -> MagicMock:
    return MagicMock(spec=AccountRepository)


@pytest.fixture
def service(account_repo: MagicMock) -> AccountService:
    return AccountService(account_repo)


class TestCreateAccount:
    def test_creates_first_account_in_group_with_any_currency(
        self, service: AccountService, account_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        account_repo.get_accounts_by_group_id.return_value = []
        created = make_account(group_id=group_id, currency="USD")
        account_repo.create_account.return_value = created
        command = AccountCommand(
            group_id=group_id,
            name="First",
            type=None,
            opening_balance=None,
            currency="USD",
            color=None,
            icon=None,
        )

        result = service.create_account(uuid.uuid4(), command)

        assert result.currency == "USD"

    def test_creates_account_without_currency_defaults_to_eur(
        self, service: AccountService, account_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        account_repo.get_accounts_by_group_id.return_value = [
            make_account(group_id=group_id, currency="EUR", is_active=True)
        ]
        created = make_account(group_id=group_id, currency="EUR")
        account_repo.create_account.return_value = created
        command = AccountCommand(
            group_id=group_id,
            name="Second",
            type=None,
            opening_balance=None,
            currency=None,
            color=None,
            icon=None,
        )

        result = service.create_account(uuid.uuid4(), command)

        assert result.currency == "EUR"

    def test_raises_conflict_when_currency_does_not_match_group(
        self, service: AccountService, account_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        account_repo.get_accounts_by_group_id.return_value = [
            make_account(group_id=group_id, currency="EUR", is_active=True)
        ]
        command = AccountCommand(
            group_id=group_id,
            name="Mismatch",
            type=None,
            opening_balance=None,
            currency="USD",
            color=None,
            icon=None,
        )

        with pytest.raises(ConflictError):
            service.create_account(uuid.uuid4(), command)

        account_repo.create_account.assert_not_called()

    def test_ignores_archived_accounts_when_checking_currency(
        self, service: AccountService, account_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        account_repo.get_accounts_by_group_id.return_value = [
            make_account(group_id=group_id, currency="USD", is_active=False)
        ]
        created = make_account(group_id=group_id, currency="EUR")
        account_repo.create_account.return_value = created
        command = AccountCommand(
            group_id=group_id,
            name="New currency",
            type=None,
            opening_balance=None,
            currency="EUR",
            color=None,
            icon=None,
        )

        result = service.create_account(uuid.uuid4(), command)

        assert result.currency == "EUR"


class TestGetAccounts:
    def test_returns_all_accounts_in_group(
        self, service: AccountService, account_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        account_repo.get_accounts_by_group_id.return_value = [
            make_account(group_id=group_id),
            make_account(group_id=group_id, is_active=False),
        ]

        result = service.get_accounts(group_id)

        assert len(result) == 2


class TestGetAccount:
    def test_returns_account_when_found(
        self, service: AccountService, account_repo: MagicMock
    ):
        account = make_account()
        account_repo.get_account_by_id.return_value = account

        result = service.get_account(account.id)

        assert result.id == account.id

    def test_raises_not_found_when_missing(
        self, service: AccountService, account_repo: MagicMock
    ):
        account_repo.get_account_by_id.return_value = None

        with pytest.raises(NotFoundError):
            service.get_account(uuid.uuid4())


class TestUpdateAccount:
    def test_raises_bad_request_when_no_fields(self, service: AccountService):
        command = UpdateAccountCommand(
            name=None, type=None, color=None, icon=None, is_active=None
        )

        with pytest.raises(BadRequestError):
            service.update_account(uuid.uuid4(), command)

    def test_updates_when_at_least_one_field(
        self, service: AccountService, account_repo: MagicMock
    ):
        updated = make_account(name="Renamed")
        account_repo.update_account.return_value = updated
        command = UpdateAccountCommand(
            name="Renamed", type=None, color=None, icon=None, is_active=None
        )

        result = service.update_account(uuid.uuid4(), command)

        assert result.name == "Renamed"

    def test_archiving_is_a_valid_sole_field(
        self, service: AccountService, account_repo: MagicMock
    ):
        updated = make_account(is_active=False)
        account_repo.update_account.return_value = updated
        command = UpdateAccountCommand(
            name=None, type=None, color=None, icon=None, is_active=False
        )

        result = service.update_account(uuid.uuid4(), command)

        assert result.is_active is False
