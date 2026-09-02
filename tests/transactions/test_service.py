import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.accounts.models import Account, AccountTypeEnum
from app.accounts.repository import AccountRepository
from app.categories.models import Category
from app.categories.repository import CategoryRepository
from app.shared.commands import UNSET
from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError
from app.transactions.commands import (
    CreateTransactionCommand,
    DailySpendCommand,
    TransactionFilterCommand,
    UpdateTransactionCommand,
)
from app.transactions.models import Transaction, TransactionTypeEnum
from app.transactions.repository import CategorySummaryRow, TransactionRepository
from app.transactions.schemas import TransactionFilterQuery, UpdateTransactionRequest
from app.transactions.service import TransactionService

ACTOR_ID = uuid.uuid4()


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
        command = UpdateTransactionCommand()

        with pytest.raises(BadRequestError):
            service.update_transaction(uuid.uuid4(), uuid.uuid4(), command, ACTOR_ID)

    def test_raises_not_found_when_transaction_missing(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        transaction_repo.get_transaction_by_id.return_value = None
        command = UpdateTransactionCommand(amount=100)

        with pytest.raises(NotFoundError):
            service.update_transaction(uuid.uuid4(), uuid.uuid4(), command, ACTOR_ID)

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
        command = UpdateTransactionCommand(amount=800)

        service.update_transaction(account_id, transaction.id, command, ACTOR_ID)

        applied_command = transaction_repo.update_transaction.call_args.args[1]
        assert applied_command.amount == -800
        assert transaction_repo.update_transaction.call_args.args[2] == ACTOR_ID

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
        command = UpdateTransactionCommand(amount=450)

        service.update_transaction(account_id, transaction.id, command, ACTOR_ID)

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
        command = UpdateTransactionCommand(type=TransactionTypeEnum.INCOME)

        service.update_transaction(account_id, transaction.id, command, ACTOR_ID)

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
        command = UpdateTransactionCommand(type=TransactionTypeEnum.INCOME)

        with pytest.raises(ConflictError):
            service.update_transaction(account_id, transaction.id, command, ACTOR_ID)

        transaction_repo.update_transaction.assert_not_called()

    def test_raises_conflict_setting_category_on_transfer(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, type=TransactionTypeEnum.TRANSFER
        )
        transaction_repo.get_transaction_by_id.return_value = transaction
        command = UpdateTransactionCommand(category_id=uuid.uuid4())

        with pytest.raises(ConflictError):
            service.update_transaction(account_id, transaction.id, command, ACTOR_ID)

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
        command = UpdateTransactionCommand(category_id=uuid.uuid4())

        with pytest.raises(ConflictError):
            service.update_transaction(account_id, transaction.id, command, ACTOR_ID)


class TestUpdateTransactionClearingFields:
    """ARCHITECTURE.md §5.5: un campo ausente no se toca, pero uno enviado como
    null sí se aplica cuando la columna lo admite. Antes ambos llegaban como
    None y era imposible vaciar nada."""

    def test_explicit_null_category_reaches_the_repository(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(account_id=account_id, category_id=uuid.uuid4())
        transaction_repo.get_transaction_by_id.return_value = transaction
        transaction_repo.update_transaction.return_value = make_transaction(
            account_id=account_id, category_id=None
        )
        command = UpdateTransactionCommand(category_id=None)

        service.update_transaction(account_id, transaction.id, command, ACTOR_ID)

        applied = transaction_repo.update_transaction.call_args.args[1]
        assert applied.category_id is None

    def test_explicit_null_notes_reaches_the_repository(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(account_id=account_id, notes="Cena")
        transaction_repo.get_transaction_by_id.return_value = transaction
        transaction_repo.update_transaction.return_value = make_transaction(
            account_id=account_id, notes=None
        )
        command = UpdateTransactionCommand(notes=None)

        service.update_transaction(account_id, transaction.id, command, ACTOR_ID)

        applied = transaction_repo.update_transaction.call_args.args[1]
        assert applied.notes is None

    def test_clearing_the_category_skips_the_group_check(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        category_repo: MagicMock,
    ):
        # Vaciar no asigna ninguna categoría, así que no hay grupo que validar.
        account_id = uuid.uuid4()
        transaction = make_transaction(account_id=account_id, category_id=uuid.uuid4())
        transaction_repo.get_transaction_by_id.return_value = transaction
        transaction_repo.update_transaction.return_value = make_transaction(
            account_id=account_id, category_id=None
        )

        service.update_transaction(
            account_id,
            transaction.id,
            UpdateTransactionCommand(category_id=None),
            ACTOR_ID,
        )

        category_repo.get_category_by_id.assert_not_called()

    def test_absent_fields_stay_unset(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, category_id=uuid.uuid4(), notes="Cena"
        )
        transaction_repo.get_transaction_by_id.return_value = transaction
        transaction_repo.update_transaction.return_value = transaction

        service.update_transaction(
            account_id,
            transaction.id,
            UpdateTransactionCommand(notes="Otra cosa"),
            ACTOR_ID,
        )

        applied = transaction_repo.update_transaction.call_args.args[1]
        assert applied.notes == "Otra cosa"
        # category_id no viajó: el repositorio no debe tocarlo.
        assert applied.category_id is UNSET
        assert applied.date is UNSET


class TestUpdateTransactionRequestNulls:
    def test_rejects_explicit_null_on_not_null_columns(self):
        # amount, type y date no son vaciables: null ahí no es "vacíalo", es un
        # valor imposible que acabaría en un error de integridad.
        for field in ("amount", "type", "date"):
            with pytest.raises(ValidationError):
                UpdateTransactionRequest.model_validate({field: None})

    def test_accepts_explicit_null_on_nullable_columns(self):
        payload = UpdateTransactionRequest.model_validate(
            {"category_id": None, "notes": None}
        )

        assert payload.category_id is None
        assert payload.notes is None
        assert "category_id" in payload.model_fields_set
        assert "notes" in payload.model_fields_set


class TestDeleteTransaction:
    def test_deletes_when_transaction_belongs_to_account(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(account_id=account_id)
        transaction_repo.get_transaction_by_id.return_value = transaction

        service.delete_transaction(account_id, transaction.id, ACTOR_ID)

        transaction_repo.delete_transaction.assert_called_once_with(
            transaction.id, ACTOR_ID
        )

    def test_raises_not_found_when_already_deleted(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        transaction = make_transaction(
            account_id=account_id, deleted_at=datetime.now(timezone.utc)
        )
        transaction_repo.get_transaction_by_id.return_value = transaction

        with pytest.raises(NotFoundError):
            service.delete_transaction(account_id, transaction.id, ACTOR_ID)

        transaction_repo.delete_transaction.assert_not_called()

    def test_raises_not_found_when_belongs_to_different_account(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        transaction = make_transaction(account_id=uuid.uuid4())
        transaction_repo.get_transaction_by_id.return_value = transaction

        with pytest.raises(NotFoundError):
            service.delete_transaction(uuid.uuid4(), transaction.id, ACTOR_ID)


def make_filters(**overrides: object) -> TransactionFilterCommand:
    defaults: dict[str, object] = {
        "group_id": uuid.uuid4(),
        "account_id": None,
        "category_id": None,
        "uncategorized": False,
        "type": None,
        "date_from": None,
        "date_to": None,
        "q": None,
    }
    defaults.update(overrides)
    return TransactionFilterCommand(**defaults)  # pyright: ignore[reportArgumentType]


class TestTransactionFilterQuery:
    """Las contradicciones entre filtros se rechazan en el schema de entrada
    (422), no en el service (transactions.md §5)."""

    def test_rejects_uncategorized_together_with_category_id(self):
        with pytest.raises(ValidationError):
            TransactionFilterQuery(category_id=uuid.uuid4(), uncategorized=True)

    def test_rejects_date_from_after_date_to(self):
        with pytest.raises(ValidationError):
            TransactionFilterQuery(date_from=date(2026, 2, 1), date_to=date(2026, 1, 1))

    def test_accepts_same_day_range(self):
        filters = TransactionFilterQuery(
            date_from=date(2026, 1, 1), date_to=date(2026, 1, 1)
        )

        assert filters.date_from == filters.date_to

    def test_accepts_uncategorized_without_category_id(self):
        filters = TransactionFilterQuery(uncategorized=True)

        assert filters.category_id is None


class TestGetFilteredTransactions:
    def test_passes_every_filter_through_to_the_repository(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        category_repo: MagicMock,
    ):
        filters = make_filters(
            category_id=uuid.uuid4(),
            type=TransactionTypeEnum.EXPENSE,
            date_from=date(2026, 1, 1),
            date_to=date(2026, 1, 31),
            q="merca",
        )
        category_repo.get_category_by_id.return_value = make_category(
            id=filters.category_id, group_id=filters.group_id
        )
        transaction_repo.get_filtered_transactions.return_value = ([], 0)

        service.get_filtered_transactions(filters, limit=20, offset=40)

        args = transaction_repo.get_filtered_transactions.call_args.args
        assert args == (filters, 20, 40)

    def test_returns_items_and_total_of_the_filtered_rows(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        transaction_repo.get_filtered_transactions.return_value = (
            [make_transaction()],
            3,
        )

        result = service.get_filtered_transactions(make_filters(), limit=20, offset=0)

        assert len(result.items) == 1
        assert result.total == 3

    def test_raises_conflict_when_account_belongs_to_another_group(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
    ):
        account_repo.get_account_by_id.return_value = make_account(
            group_id=uuid.uuid4()
        )
        filters = make_filters(account_id=uuid.uuid4())

        with pytest.raises(ConflictError):
            service.get_filtered_transactions(filters, limit=20, offset=0)

        transaction_repo.get_filtered_transactions.assert_not_called()

    def test_raises_conflict_when_account_does_not_exist(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
    ):
        account_repo.get_account_by_id.return_value = None
        filters = make_filters(account_id=uuid.uuid4())

        with pytest.raises(ConflictError):
            service.get_filtered_transactions(filters, limit=20, offset=0)

        transaction_repo.get_filtered_transactions.assert_not_called()

    def test_raises_conflict_when_category_belongs_to_another_group(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        category_repo: MagicMock,
    ):
        category_repo.get_category_by_id.return_value = make_category(
            group_id=uuid.uuid4()
        )
        filters = make_filters(category_id=uuid.uuid4())

        with pytest.raises(ConflictError):
            service.get_filtered_transactions(filters, limit=20, offset=0)

        transaction_repo.get_filtered_transactions.assert_not_called()

    def test_does_not_check_scope_when_no_account_or_category_filter(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
        category_repo: MagicMock,
    ):
        transaction_repo.get_filtered_transactions.return_value = ([], 0)

        service.get_filtered_transactions(make_filters(), limit=20, offset=0)

        account_repo.get_account_by_id.assert_not_called()
        category_repo.get_category_by_id.assert_not_called()


class TestGetCategorySummary:
    def test_queries_with_the_same_filters_as_the_listing(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
    ):
        filters = make_filters(
            account_id=uuid.uuid4(),
            type=TransactionTypeEnum.EXPENSE,
            q="merca",
        )
        transaction_repo.get_filtered_transactions.return_value = ([], 0)
        transaction_repo.get_category_summary.return_value = []
        account_repo.get_account_by_id.return_value = make_account(
            id=filters.account_id, group_id=filters.group_id
        )

        service.get_filtered_transactions(filters, limit=20, offset=0)
        service.get_category_summary(filters)

        assert (
            transaction_repo.get_category_summary.call_args.args[0]
            == transaction_repo.get_filtered_transactions.call_args.args[0]
        )

    def test_maps_rows_including_the_uncategorized_one(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        root_id = uuid.uuid4()
        transaction_repo.get_category_summary.return_value = [
            CategorySummaryRow(
                root_category_id=root_id,
                root_category_name="Comida",
                income=0,
                expense=-2600,
                transaction_count=2,
            ),
            CategorySummaryRow(
                root_category_id=None,
                root_category_name=None,
                income=1000,
                expense=0,
                transaction_count=1,
            ),
        ]

        result = service.get_category_summary(make_filters())

        assert [row.root_category_id for row in result] == [root_id, None]
        assert result[0].expense == -2600
        assert result[1].root_category_name is None

    def test_raises_conflict_when_account_belongs_to_another_group(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
    ):
        account_repo.get_account_by_id.return_value = make_account(
            group_id=uuid.uuid4()
        )
        filters = make_filters(account_id=uuid.uuid4())

        with pytest.raises(ConflictError):
            service.get_category_summary(filters)

        transaction_repo.get_category_summary.assert_not_called()


class TestGetDailySpend:
    def test_queries_a_single_day_of_expenses(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        transaction_repo.get_spent_on_date.return_value = (2600, 2)
        command = DailySpendCommand(group_id=uuid.uuid4(), date=date(2026, 1, 5))

        service.get_daily_spend(command)

        filters = transaction_repo.get_spent_on_date.call_args.args[0]
        assert filters.group_id == command.group_id
        assert filters.type == TransactionTypeEnum.EXPENSE
        assert filters.date_from == command.date
        assert filters.date_to == command.date

    def test_returns_what_the_repository_aggregated(
        self, service: TransactionService, transaction_repo: MagicMock
    ):
        transaction_repo.get_spent_on_date.return_value = (2600, 2)
        command = DailySpendCommand(group_id=uuid.uuid4(), date=date(2026, 1, 5))

        result = service.get_daily_spend(command)

        assert result.date == date(2026, 1, 5)
        assert result.spent == 2600
        assert result.transaction_count == 2

    def test_keeps_the_account_filter(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        account_id = uuid.uuid4()
        account_repo.get_account_by_id.return_value = make_account(
            id=account_id, group_id=group_id
        )
        transaction_repo.get_spent_on_date.return_value = (0, 0)
        command = DailySpendCommand(
            group_id=group_id, date=date(2026, 1, 5), account_id=account_id
        )

        service.get_daily_spend(command)

        filters = transaction_repo.get_spent_on_date.call_args.args[0]
        assert filters.account_id == account_id

    def test_raises_conflict_when_account_belongs_to_another_group(
        self,
        service: TransactionService,
        transaction_repo: MagicMock,
        account_repo: MagicMock,
    ):
        account_repo.get_account_by_id.return_value = make_account(
            group_id=uuid.uuid4()
        )
        command = DailySpendCommand(
            group_id=uuid.uuid4(), date=date(2026, 1, 5), account_id=uuid.uuid4()
        )

        with pytest.raises(ConflictError):
            service.get_daily_spend(command)

        transaction_repo.get_spent_on_date.assert_not_called()
