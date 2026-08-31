import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest
from pydantic import ValidationError

from app.accounts.models import Account, AccountTypeEnum
from app.accounts.repository import AccountRepository
from app.categories.models import Category
from app.categories.repository import CategoryRepository
from app.payment_plans.commands import (
    CreatePaymentPlanCommand,
    UpdatePaymentPlanCommand,
)
from app.payment_plans.models import FrequencyUnitEnum, PaymentPlan
from app.payment_plans.repository import PaymentPlanRepository
from app.payment_plans.schemas import UpdatePaymentPlanRequest
from app.payment_plans.service import PaymentPlanService
from app.shared.commands import UNSET
from app.shared.exceptions import BadRequestError, ConflictError, NotFoundError
from app.transactions.models import TransactionTypeEnum


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


def make_plan(**overrides: object) -> PaymentPlan:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "account_id": uuid.uuid4(),
        "to_account_id": None,
        "category_id": None,
        "type": TransactionTypeEnum.EXPENSE,
        "amount": 1000,
        "description": None,
        "next_due_date": date(2026, 1, 1),
        "end_date": None,
        "is_recurring": False,
        "is_active": True,
        "frequency_interval": None,
        "frequency_unit": None,
        "created_by": None,
        "updated_by": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return PaymentPlan(**defaults)  # pyright: ignore[reportArgumentType]


def make_create_command(**overrides: object) -> CreatePaymentPlanCommand:
    defaults: dict[str, object] = {
        "account_id": uuid.uuid4(),
        "group_id": uuid.uuid4(),
        "type": TransactionTypeEnum.EXPENSE,
        "amount": 1000,
        "category_id": None,
        "to_account_id": None,
        "description": None,
        "next_due_date": date(2026, 1, 1),
        "end_date": None,
        "is_recurring": False,
        "frequency_interval": None,
        "frequency_unit": None,
    }
    defaults.update(overrides)
    return CreatePaymentPlanCommand(**defaults)  # pyright: ignore[reportArgumentType]


def make_update_command(**overrides: object) -> UpdatePaymentPlanCommand:
    # Por defecto, nada enviado: UNSET, no None. None significaría "vacía este
    # campo" (ARCHITECTURE.md §5.5).
    defaults: dict[str, object] = {
        "amount": UNSET,
        "type": UNSET,
        "category_id": UNSET,
        "description": UNSET,
        "next_due_date": UNSET,
        "end_date": UNSET,
        "is_recurring": UNSET,
        "frequency_interval": UNSET,
        "frequency_unit": UNSET,
        "is_active": UNSET,
    }
    defaults.update(overrides)
    return UpdatePaymentPlanCommand(**defaults)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def payment_plan_repo() -> MagicMock:
    return MagicMock(spec=PaymentPlanRepository)


@pytest.fixture
def account_repo() -> MagicMock:
    return MagicMock(spec=AccountRepository)


@pytest.fixture
def category_repo() -> MagicMock:
    return MagicMock(spec=CategoryRepository)


@pytest.fixture
def service(
    payment_plan_repo: MagicMock, account_repo: MagicMock, category_repo: MagicMock
) -> PaymentPlanService:
    return PaymentPlanService(payment_plan_repo, account_repo, category_repo)


class TestCreatePaymentPlan:
    def test_creates_one_off_plan(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        payment_plan_repo.create_payment_plan.return_value = make_plan()
        command = make_create_command()

        result = service.create_payment_plan(uuid.uuid4(), command)

        assert result.is_recurring is False

    def test_raises_conflict_when_category_from_another_group(
        self, service: PaymentPlanService, category_repo: MagicMock
    ):
        category_repo.get_category_by_id.return_value = make_category(
            group_id=uuid.uuid4()
        )
        command = make_create_command(category_id=uuid.uuid4())

        with pytest.raises(ConflictError):
            service.create_payment_plan(uuid.uuid4(), command)

    def test_raises_conflict_when_transfer_destination_equals_origin(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        command = make_create_command(
            account_id=account_id,
            type=TransactionTypeEnum.TRANSFER,
            to_account_id=account_id,
        )

        with pytest.raises(ConflictError):
            service.create_payment_plan(uuid.uuid4(), command)

        payment_plan_repo.create_payment_plan.assert_not_called()

    def test_raises_conflict_when_transfer_destination_missing(
        self,
        service: PaymentPlanService,
        account_repo: MagicMock,
    ):
        account_repo.get_account_by_id.return_value = None
        command = make_create_command(
            type=TransactionTypeEnum.TRANSFER, to_account_id=uuid.uuid4()
        )

        with pytest.raises(ConflictError):
            service.create_payment_plan(uuid.uuid4(), command)

    def test_raises_conflict_when_transfer_destination_in_another_group(
        self, service: PaymentPlanService, account_repo: MagicMock
    ):
        account_repo.get_account_by_id.return_value = make_account(
            group_id=uuid.uuid4()
        )
        command = make_create_command(
            type=TransactionTypeEnum.TRANSFER, to_account_id=uuid.uuid4()
        )

        with pytest.raises(ConflictError):
            service.create_payment_plan(uuid.uuid4(), command)

    def test_creates_valid_transfer_plan(
        self,
        service: PaymentPlanService,
        payment_plan_repo: MagicMock,
        account_repo: MagicMock,
    ):
        group_id = uuid.uuid4()
        destination_id = uuid.uuid4()
        account_repo.get_account_by_id.return_value = make_account(
            id=destination_id, group_id=group_id
        )
        payment_plan_repo.create_payment_plan.return_value = make_plan(
            type=TransactionTypeEnum.TRANSFER, to_account_id=destination_id
        )
        command = make_create_command(
            group_id=group_id,
            type=TransactionTypeEnum.TRANSFER,
            to_account_id=destination_id,
        )

        result = service.create_payment_plan(uuid.uuid4(), command)

        assert result.to_account_id == destination_id


class TestGetPaymentPlans:
    def test_returns_all_plans_for_account(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        payment_plan_repo.get_payment_plans_by_account_id.return_value = [
            make_plan(account_id=account_id),
            make_plan(account_id=account_id, is_active=False),
        ]

        result = service.get_payment_plans(account_id)

        assert len(result) == 2


class TestGetUpcomingPaymentPlans:
    def test_returns_plans_from_every_account_of_the_group(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        payment_plan_repo.get_upcoming_by_group.return_value = [
            make_plan(account_id=uuid.uuid4(), next_due_date=date(2026, 3, 1)),
            make_plan(account_id=uuid.uuid4(), next_due_date=date(2026, 3, 5)),
        ]

        result = service.get_upcoming_payment_plans(uuid.uuid4(), date(2026, 3, 31))

        assert len(result) == 2

    def test_passes_group_and_until_to_the_repository(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        until = date(2026, 3, 31)
        payment_plan_repo.get_upcoming_by_group.return_value = []

        service.get_upcoming_payment_plans(group_id, until)

        payment_plan_repo.get_upcoming_by_group.assert_called_once_with(group_id, until)

    def test_returns_empty_list_when_nothing_is_due(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        payment_plan_repo.get_upcoming_by_group.return_value = []

        result = service.get_upcoming_payment_plans(uuid.uuid4(), date(2026, 3, 31))

        assert result == []


class TestGetPaydayPlan:
    def test_returns_none_when_group_has_no_recurring_income(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        payment_plan_repo.get_payday_plan.return_value = None

        result = service.get_payday_plan(uuid.uuid4())

        assert result is None

    def test_returns_the_anchor_plan(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        plan = make_plan(
            type=TransactionTypeEnum.INCOME,
            amount=180000,
            next_due_date=date(2026, 3, 5),
            is_recurring=True,
            frequency_interval=1,
            frequency_unit=FrequencyUnitEnum.MONTH,
        )
        payment_plan_repo.get_payday_plan.return_value = plan

        result = service.get_payday_plan(uuid.uuid4())

        assert result is not None
        assert result.id == plan.id
        assert result.next_due_date == date(2026, 3, 5)

    def test_passes_group_to_the_repository(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        group_id = uuid.uuid4()
        payment_plan_repo.get_payday_plan.return_value = None

        service.get_payday_plan(group_id)

        payment_plan_repo.get_payday_plan.assert_called_once_with(group_id)


class TestGetPaymentPlan:
    def test_returns_plan_when_it_belongs_to_account(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(account_id=account_id)
        payment_plan_repo.get_payment_plan_by_id.return_value = plan

        result = service.get_payment_plan(account_id, plan.id)

        assert result.id == plan.id

    def test_raises_not_found_when_missing(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        payment_plan_repo.get_payment_plan_by_id.return_value = None

        with pytest.raises(NotFoundError):
            service.get_payment_plan(uuid.uuid4(), uuid.uuid4())

    def test_raises_not_found_when_belongs_to_different_account(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        plan = make_plan(account_id=uuid.uuid4())
        payment_plan_repo.get_payment_plan_by_id.return_value = plan

        with pytest.raises(NotFoundError):
            service.get_payment_plan(uuid.uuid4(), plan.id)


class TestUpdatePaymentPlan:
    def test_raises_bad_request_when_no_fields(self, service: PaymentPlanService):
        command = make_update_command()

        with pytest.raises(BadRequestError):
            service.update_payment_plan(uuid.uuid4(), uuid.uuid4(), command)

    def test_raises_not_found_when_plan_missing(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        payment_plan_repo.get_payment_plan_by_id.return_value = None
        command = make_update_command(amount=500)

        with pytest.raises(NotFoundError):
            service.update_payment_plan(uuid.uuid4(), uuid.uuid4(), command)

    def test_raises_conflict_changing_type_of_existing_transfer(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(account_id=account_id, type=TransactionTypeEnum.TRANSFER)
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        command = make_update_command(type=TransactionTypeEnum.INCOME)

        with pytest.raises(ConflictError):
            service.update_payment_plan(account_id, plan.id, command)

        payment_plan_repo.update_payment_plan.assert_not_called()

    def test_raises_conflict_setting_category_on_transfer(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(account_id=account_id, type=TransactionTypeEnum.TRANSFER)
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        command = make_update_command(category_id=uuid.uuid4())

        with pytest.raises(ConflictError):
            service.update_payment_plan(account_id, plan.id, command)

    def test_raises_conflict_when_category_from_another_group(
        self,
        service: PaymentPlanService,
        payment_plan_repo: MagicMock,
        account_repo: MagicMock,
        category_repo: MagicMock,
    ):
        account_id = uuid.uuid4()
        plan = make_plan(account_id=account_id, type=TransactionTypeEnum.EXPENSE)
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        account_repo.get_account_by_id.return_value = make_account(
            id=account_id, group_id=uuid.uuid4()
        )
        category_repo.get_category_by_id.return_value = make_category(
            group_id=uuid.uuid4()
        )
        command = make_update_command(category_id=uuid.uuid4())

        with pytest.raises(ConflictError):
            service.update_payment_plan(account_id, plan.id, command)

    def test_turning_off_recurring_clears_frequency_fields(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(
            account_id=account_id,
            is_recurring=True,
            frequency_interval=1,
            frequency_unit=FrequencyUnitEnum.MONTH,
        )
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        payment_plan_repo.update_payment_plan.return_value = make_plan(
            account_id=account_id, is_recurring=False
        )
        command = make_update_command(is_recurring=False)

        service.update_payment_plan(account_id, plan.id, command)

        payment_plan_repo.update_payment_plan.assert_called_once_with(plan.id, command)

    def test_turning_on_recurring_without_frequency_fields_raises_conflict(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(account_id=account_id, is_recurring=False)
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        command = make_update_command(is_recurring=True)

        with pytest.raises(ConflictError):
            service.update_payment_plan(account_id, plan.id, command)

        payment_plan_repo.update_payment_plan.assert_not_called()

    def test_turning_on_recurring_with_frequency_fields_succeeds(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(account_id=account_id, is_recurring=False)
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        payment_plan_repo.update_payment_plan.return_value = make_plan(
            account_id=account_id,
            is_recurring=True,
            frequency_interval=2,
            frequency_unit=FrequencyUnitEnum.WEEK,
        )
        command = make_update_command(
            is_recurring=True,
            frequency_interval=2,
            frequency_unit=FrequencyUnitEnum.WEEK,
        )

        result = service.update_payment_plan(account_id, plan.id, command)

        assert result.is_recurring is True
        assert result.frequency_interval == 2

    def test_editing_frequency_interval_alone_keeps_existing_recurring_state(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(
            account_id=account_id,
            is_recurring=True,
            frequency_interval=1,
            frequency_unit=FrequencyUnitEnum.MONTH,
        )
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        payment_plan_repo.update_payment_plan.return_value = make_plan(
            account_id=account_id,
            is_recurring=True,
            frequency_interval=3,
            frequency_unit=FrequencyUnitEnum.MONTH,
        )
        command = make_update_command(frequency_interval=3)

        result = service.update_payment_plan(account_id, plan.id, command)

        assert result.frequency_interval == 3

    def test_raises_conflict_when_new_end_date_before_existing_next_due_date(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(
            account_id=account_id,
            is_recurring=True,
            frequency_interval=1,
            frequency_unit=FrequencyUnitEnum.MONTH,
            next_due_date=date(2026, 6, 1),
        )
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        command = make_update_command(end_date=date(2026, 1, 1))

        with pytest.raises(ConflictError):
            service.update_payment_plan(account_id, plan.id, command)

    def test_raises_conflict_when_new_next_due_date_after_existing_end_date(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(
            account_id=account_id,
            is_recurring=True,
            frequency_interval=1,
            frequency_unit=FrequencyUnitEnum.MONTH,
            end_date=date(2026, 3, 1),
        )
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        command = make_update_command(next_due_date=date(2026, 6, 1))

        with pytest.raises(ConflictError):
            service.update_payment_plan(account_id, plan.id, command)

    def test_archiving_is_a_valid_sole_field(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(account_id=account_id)
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        payment_plan_repo.update_payment_plan.return_value = make_plan(
            account_id=account_id, is_active=False
        )
        command = make_update_command(is_active=False)

        result = service.update_payment_plan(account_id, plan.id, command)

        assert result.is_active is False


class TestUpdatePaymentPlanClearingFields:
    """ARCHITECTURE.md §5.5: null explícito vacía; ausente no toca nada."""

    def test_explicit_null_description_reaches_the_repository(
        self, service: PaymentPlanService, payment_plan_repo: MagicMock
    ):
        account_id = uuid.uuid4()
        plan = make_plan(account_id=account_id, description="Alquiler")
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        payment_plan_repo.update_payment_plan.return_value = make_plan(
            account_id=account_id, description=None
        )

        service.update_payment_plan(
            account_id, plan.id, make_update_command(description=None)
        )

        applied = payment_plan_repo.update_payment_plan.call_args.args[1]
        assert applied.description is None
        assert applied.amount is UNSET

    def test_explicit_null_category_skips_the_group_check(
        self,
        service: PaymentPlanService,
        payment_plan_repo: MagicMock,
        category_repo: MagicMock,
    ):
        account_id = uuid.uuid4()
        plan = make_plan(account_id=account_id, category_id=uuid.uuid4())
        payment_plan_repo.get_payment_plan_by_id.return_value = plan
        payment_plan_repo.update_payment_plan.return_value = make_plan(
            account_id=account_id, category_id=None
        )

        service.update_payment_plan(
            account_id, plan.id, make_update_command(category_id=None)
        )

        applied = payment_plan_repo.update_payment_plan.call_args.args[1]
        assert applied.category_id is None
        category_repo.get_category_by_id.assert_not_called()

    def test_rejects_explicit_null_on_not_null_columns(self):
        for field in ("amount", "type", "next_due_date", "is_recurring", "is_active"):
            with pytest.raises(ValidationError):
                UpdatePaymentPlanRequest.model_validate({field: None})
