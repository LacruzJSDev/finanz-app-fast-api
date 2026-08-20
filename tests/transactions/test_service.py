import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.accounts.models import Account, AccountTypeEnum
from app.accounts.repository import AccountRepository
from app.categories.models import Category
from app.categories.repository import CategoryRepository
from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError
from app.transactions.commands import (
    CreateTransactionCommand,
    UpdateTransactionCommand,
)
from app.transactions.models import Transaction, TransactionTypeEnum
from app.transactions.repository import TransactionRepository
from app.transactions.service import TransactionService


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


def make_category(**overrides: object) -> Category:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "group_id": uuid.uuid4(),
        "parent_id": None,
        "name": "Test Category",
        "color": None,
        "icon": None,
        "is_active": True,
        "created_by": None,
        "updated_by": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Category(**defaults)  # pyright: ignore[reportArgumentType]


def make_transaction(**overrides: object) -> Transaction:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "to_account_id": None,
        "category_id": None,
        "transfer_group_id": None,
        "payment_plan_id": None,
        "amount": 1000,
        "type": TransactionTypeEnum.INCOME,
        "date": date(2026, 1, 1),
        "notes": None,
        "ocr_receipt_ref": None,
        "deleted_at": None,
        "created_by": None,
        "updated_by": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Transaction(**defaults)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def transaction_repo() -> MagicMock:
    return MagicMock(spec=TransactionRepository)


@pytest.fixture
def account_repo() -> MagicMock:
    return MagicMock(spec=AccountRepository)


@pytest.fixture
def category_repo() -> MagicMock:
    return MagicMock(spec=CategoryRepository)


@pytest.fixture
def service(
    transaction_repo: MagicMock, account_repo: MagicMock, category_repo: MagicMock
) -> TransactionService:
    return TransactionService(transaction_repo, account_repo, category_repo)


class TestCreateTransactionIncomeExpense:
    def test_income_stores_positive_amount(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        created = make_transaction(account_id=account_id, amount=1000)
        transaction_repo.create_transaction.return_value = created
        command = CreateTransactionCommand(
            account_id=account_id,
            group_id=uuid.uuid4(),
            type=TransactionTypeEnum.INCOME,
            amount=1000,
            category_id=None,
            to_account_id=None,
            date=date(2026, 1, 1),
            notes=None,
        )

        service.create_transaction(uuid.uuid4(), command)

        row = transaction_repo.create_transaction.call_args.args[1]
        assert row.amount == 1000
        assert row.transfer_group_id is None

    def test_expense_stores_negative_amount_from_positive_input(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction_repo.create_transaction.return_value = make_transaction(
            account_id=account_id, amount=-500
        )
        command = CreateTransactionCommand(
            account_id=account_id,
            group_id=uuid.uuid4(),
            type=TransactionTypeEnum.EXPENSE,
            amount=500,
            category_id=None,
            to_account_id=None,
            date=date(2026, 1, 1),
            notes=None,
        )

        service.create_transaction(uuid.uuid4(), command)

        row = transaction_repo.create_transaction.call_args.args[1]
        assert row.amount == -500

    def test_raises_conflict_when_category_belongs_to_another_group(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        category_repo: MagicMock,
    ):
        category_repo.get_category_by_id.return_value = make_category(
            group_id=uuid.uuid4()
        )
        command = CreateTransactionCommand(
            account_id=uuid.uuid4(),
            group_id=uuid.uuid4(),
            type=TransactionTypeEnum.EXPENSE,
            amount=500,
            category_id=uuid.uuid4(),
            to_account_id=None,
            date=date(2026, 1, 1),
            notes=None,
        )

        with pytest.raises(ConflictError):
            service.create_transaction(uuid.uuid4(), command)

        transaction_repo.create_transaction.assert_not_called()

    def test_allows_none_user_id_for_system_generated_transactions(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction_repo.create_transaction.return_value = make_transaction(
            account_id=account_id, created_by=None
        )
        command = CreateTransactionCommand(
            account_id=account_id,
            group_id=uuid.uuid4(),
            type=TransactionTypeEnum.INCOME,
            amount=1000,
            category_id=None,
            to_account_id=None,
            date=date(2026, 1, 1),
            notes=None,
            payment_plan_id=uuid.uuid4(),
        )

        service.create_transaction(None, command)

        transaction_repo.create_transaction.assert_called_once_with(
            None, transaction_repo.create_transaction.call_args.args[1]
        )


class TestCreateTransfer:
    def test_creates_two_rows_with_opposite_signs_and_shared_group_id(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        origin_id = uuid.uuid4()
        destination_id = uuid.uuid4()
        account_repo.get_account_by_id.return_value = make_account(
            id=destination_id, group_id=group_id
        )
        origin_row_result = make_transaction(account_id=origin_id, amount=-300)
        transaction_repo.create_transaction.return_value = origin_row_result

        command = CreateTransactionCommand(
            account_id=origin_id,
            group_id=group_id,
            type=TransactionTypeEnum.TRANSFER,
            amount=300,
            category_id=None,
            to_account_id=destination_id,
            date=date(2026, 1, 1),
            notes=None,
        )
        result = service.create_transaction(uuid.uuid4(), command)

        assert transaction_repo.create_transaction.call_count == 2
        origin_row = transaction_repo.create_transaction.call_args_list[0].args[1]
        destination_row = transaction_repo.create_transaction.call_args_list[1].args[1]

        assert origin_row.account_id == origin_id
        assert origin_row.to_account_id == destination_id
        assert origin_row.amount == -300
        assert destination_row.account_id == destination_id
        assert destination_row.to_account_id == origin_id
        assert destination_row.amount == 300
        assert origin_row.transfer_group_id == destination_row.transfer_group_id
        assert origin_row.transfer_group_id is not None
        assert result.amount == -300

    def test_raises_conflict_when_destination_equals_origin(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        command = CreateTransactionCommand(
            account_id=account_id,
            group_id=uuid.uuid4(),
            type=TransactionTypeEnum.TRANSFER,
            amount=300,
            category_id=None,
            to_account_id=account_id,
            date=date(2026, 1, 1),
            notes=None,
        )

        with pytest.raises(ConflictError):
            service.create_transaction(uuid.uuid4(), command)

        transaction_repo.create_transaction.assert_not_called()

    def test_raises_conflict_when_destination_missing(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
    ):
        account_repo.get_account_by_id.return_value = None
        command = CreateTransactionCommand(
            account_id=uuid.uuid4(),
            group_id=uuid.uuid4(),
            type=TransactionTypeEnum.TRANSFER,
            amount=300,
            category_id=None,
            to_account_id=uuid.uuid4(),
            date=date(2026, 1, 1),
            notes=None,
        )

        with pytest.raises(ConflictError):
            service.create_transaction(uuid.uuid4(), command)

    def test_raises_conflict_when_destination_in_another_group(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
    ):
        account_repo.get_account_by_id.return_value = make_account(
            group_id=uuid.uuid4()
        )
        command = CreateTransactionCommand(
            account_id=uuid.uuid4(),
            group_id=uuid.uuid4(),
            type=TransactionTypeEnum.TRANSFER,
            amount=300,
            category_id=None,
            to_account_id=uuid.uuid4(),
            date=date(2026, 1, 1),
            notes=None,
        )

        with pytest.raises(ConflictError):
            service.create_transaction(uuid.uuid4(), command)

        transaction_repo.create_transaction.assert_not_called()


class TestGetTransactions:
    def test_returns_paginated_items_and_total(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction_repo.get_transactions_by_account_id.return_value = (
            [make_transaction(account_id=account_id)],
            5,
        )

        result = service.get_transactions(account_id, limit=1, offset=0)

        assert len(result.items) == 1
        assert result.total == 5


class TestGetTransaction:
    def test_returns_transaction_when_it_belongs_to_account(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(account_id=account_id)
        transaction_repo.get_transaction_by_id.return_value = transaction

        result = service.get_transaction(account_id, transaction.id)

        assert result.id == transaction.id

    def test_raises_not_found_when_missing(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        transaction_repo.get_transaction_by_id.return_value = None

        with pytest.raises(NotFoundError):
            service.get_transaction(uuid.uuid4(), uuid.uuid4())

    def test_raises_not_found_when_belongs_to_different_account(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        transaction = make_transaction(account_id=uuid.uuid4())
        transaction_repo.get_transaction_by_id.return_value = transaction

        with pytest.raises(NotFoundError):
            service.get_transaction(uuid.uuid4(), transaction.id)

    def test_raises_not_found_when_deleted(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, deleted_at=datetime.now(timezone.utc)
        )
        transaction_repo.get_transaction_by_id.return_value = transaction

        with pytest.raises(NotFoundError):
            service.get_transaction(account_id, transaction.id)


class TestUpdateTransaction:
    def test_raises_bad_request_when_no_fields(self, service: TransactionService):
        command = UpdateTransactionCommand(
            amount=None, type=None, category_id=None, date=None, notes=None
        )

        with pytest.raises(BadRequestError):
            service.update_transaction(uuid.uuid4(), uuid.uuid4(), command)

    def test_raises_not_found_when_transaction_missing(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        transaction_repo.get_transaction_by_id.return_value = None
        command = UpdateTransactionCommand(
            amount=100, type=None, category_id=None, date=None, notes=None
        )

        with pytest.raises(NotFoundError):
            service.update_transaction(uuid.uuid4(), uuid.uuid4(), command)

    def test_editing_amount_preserves_expense_sign(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, amount=-500, type=TransactionTypeEnum.EXPENSE
        )
        transaction_repo.get_transaction_by_id.return_value = transaction
        transaction_repo.update_transaction.return_value = make_transaction(
            account_id=account_id, amount=-800
        )
        command = UpdateTransactionCommand(
            amount=800, type=None, category_id=None, date=None, notes=None
        )

        service.update_transaction(account_id, transaction.id, command)

        applied_command = transaction_repo.update_transaction.call_args.args[1]
        assert applied_command.amount == -800

    def test_editing_amount_preserves_transfer_leg_sign(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id,
            amount=-300,
            type=TransactionTypeEnum.TRANSFER,
            transfer_group_id=uuid.uuid4(),
            to_account_id=uuid.uuid4(),
        )
        transaction_repo.get_transaction_by_id.return_value = transaction
        transaction_repo.update_transaction.return_value = transaction
        command = UpdateTransactionCommand(
            amount=450, type=None, category_id=None, date=None, notes=None
        )

        service.update_transaction(account_id, transaction.id, command)

        applied_command = transaction_repo.update_transaction.call_args.args[1]
        assert applied_command.amount == -450

    def test_changing_type_from_expense_to_income_flips_sign_without_amount(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, amount=-500, type=TransactionTypeEnum.EXPENSE
        )
        transaction_repo.get_transaction_by_id.return_value = transaction
        transaction_repo.update_transaction.return_value = transaction
        command = UpdateTransactionCommand(
            amount=None,
            type=TransactionTypeEnum.INCOME,
            category_id=None,
            date=None,
            notes=None,
        )

        service.update_transaction(account_id, transaction.id, command)

        applied_command = transaction_repo.update_transaction.call_args.args[1]
        assert applied_command.amount == 500

    def test_raises_conflict_changing_type_of_existing_transfer(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, type=TransactionTypeEnum.TRANSFER
        )
        transaction_repo.get_transaction_by_id.return_value = transaction
        command = UpdateTransactionCommand(
            amount=None,
            type=TransactionTypeEnum.INCOME,
            category_id=None,
            date=None,
            notes=None,
        )

        with pytest.raises(ConflictError):
            service.update_transaction(account_id, transaction.id, command)

        transaction_repo.update_transaction.assert_not_called()

    def test_raises_conflict_setting_category_on_transfer(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, type=TransactionTypeEnum.TRANSFER
        )
        transaction_repo.get_transaction_by_id.return_value = transaction
        command = UpdateTransactionCommand(
            amount=None,
            type=None,
            category_id=uuid.uuid4(),
            date=None,
            notes=None,
        )

        with pytest.raises(ConflictError):
            service.update_transaction(account_id, transaction.id, command)

    def test_raises_conflict_when_new_category_from_another_group(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
        category_repo: MagicMock,
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, type=TransactionTypeEnum.EXPENSE
        )
        transaction_repo.get_transaction_by_id.return_value = transaction
        account_repo.get_account_by_id.return_value = make_account(
            id=account_id, group_id=uuid.uuid4()
        )
        category_repo.get_category_by_id.return_value = make_category(
            group_id=uuid.uuid4()
        )
        command = UpdateTransactionCommand(
            amount=None,
            type=None,
            category_id=uuid.uuid4(),
            date=None,
            notes=None,
        )

        with pytest.raises(ConflictError):
            service.update_transaction(account_id, transaction.id, command)


class TestDeleteTransaction:
    def test_deletes_when_transaction_belongs_to_account(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(account_id=account_id)
        transaction_repo.get_transaction_by_id.return_value = transaction

        service.delete_transaction(account_id, transaction.id)

        transaction_repo.delete_transaction.assert_called_once_with(transaction.id)

    def test_raises_not_found_when_already_deleted(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, deleted_at=datetime.now(timezone.utc)
        )
        transaction_repo.get_transaction_by_id.return_value = transaction

        with pytest.raises(NotFoundError):
            service.delete_transaction(account_id, transaction.id)

        transaction_repo.delete_transaction.assert_not_called()

    def test_raises_not_found_when_belongs_to_different_account(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        transaction = make_transaction(account_id=uuid.uuid4())
        transaction_repo.get_transaction_by_id.return_value = transaction

        with pytest.raises(NotFoundError):
            service.delete_transaction(uuid.uuid4(), transaction.id)
