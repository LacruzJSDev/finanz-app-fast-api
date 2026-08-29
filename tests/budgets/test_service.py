import uuid
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import pytest

from app.budgets.commands import SetBudgetCommand
from app.budgets.models import Budget
from app.budgets.repository import BudgetProgressRow, BudgetRepository
from app.budgets.service import BudgetService
from app.categories.models import Category
from app.categories.repository import CategoryRepository
from app.shared.exceptions import ConflictError, NotFoundError


def make_budget(**overrides: object) -> Budget:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "category_id": uuid.uuid4(),
        "amount": 40000,
        "valid_from": date(2026, 8, 1),
        "valid_to": None,
        "created_by": None,
        "updated_by": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return Budget(**defaults)  # pyright: ignore[reportArgumentType]


def make_category(**overrides: object) -> Category:
    defaults: dict[str, object] = {
        "id": uuid.uuid4(),
        "group_id": uuid.uuid4(),
        "parent_id": None,
        "name": "Comida",
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


def make_progress_row(**overrides: object) -> BudgetProgressRow:
    defaults: dict[str, object] = {
        "category_id": uuid.uuid4(),
        "category_name": "Comida",
        "parent_id": None,
        "amount": 40000,
        "spent": 0,
    }
    defaults.update(overrides)
    return BudgetProgressRow(**defaults)  # pyright: ignore[reportArgumentType]


@pytest.fixture
def budget_repo() -> MagicMock:
    return MagicMock(spec=BudgetRepository)


@pytest.fixture
def category_repo() -> MagicMock:
    return MagicMock(spec=CategoryRepository)


@pytest.fixture
def service(budget_repo: MagicMock, category_repo: MagicMock) -> BudgetService:
    return BudgetService(budget_repo, category_repo)


class TestSetBudget:
    """budgets.md §4: las cuatro ramas de la tabla de efectos del PUT."""

    def test_creates_budget_when_category_has_none(
        self,
        service: BudgetService,
        budget_repo: MagicMock,
        category_repo: MagicMock,
    ):
        category = make_category()
        category_repo.get_category_by_id.return_value = category
        budget_repo.get_current_budget.return_value = None
        created = make_budget(category_id=category.id, valid_from=date(2026, 8, 1))
        budget_repo.create_budget.return_value = created

        command = SetBudgetCommand(
            category_id=category.id, amount=40000, valid_from=date(2026, 8, 1)
        )
        result = service.set_budget(uuid.uuid4(), command)

        assert result.valid_to is None
        budget_repo.update_amount.assert_not_called()
        budget_repo.close_budget.assert_not_called()

    def test_defaults_valid_from_to_first_day_of_current_month(
        self,
        service: BudgetService,
        budget_repo: MagicMock,
        category_repo: MagicMock,
    ):
        category = make_category()
        category_repo.get_category_by_id.return_value = category
        budget_repo.get_current_budget.return_value = None
        budget_repo.create_budget.return_value = make_budget(category_id=category.id)

        command = SetBudgetCommand(
            category_id=category.id, amount=40000, valid_from=None
        )
        service.set_budget(uuid.uuid4(), command)

        period = budget_repo.create_budget.call_args.args[1]
        assert period.valid_from == date.today().replace(day=1)

    def test_updates_in_place_when_valid_from_is_the_same(
        self,
        service: BudgetService,
        budget_repo: MagicMock,
        category_repo: MagicMock,
    ):
        category = make_category()
        category_repo.get_category_by_id.return_value = category
        current = make_budget(category_id=category.id, valid_from=date(2026, 8, 1))
        budget_repo.get_current_budget.return_value = current
        budget_repo.update_amount.return_value = make_budget(
            id=current.id, category_id=category.id, amount=50000
        )

        user_id = uuid.uuid4()
        command = SetBudgetCommand(
            category_id=category.id, amount=50000, valid_from=date(2026, 8, 1)
        )
        result = service.set_budget(user_id, command)

        assert result.amount == 50000
        assert budget_repo.update_amount.call_args.args == (current.id, 50000, user_id)
        budget_repo.create_budget.assert_not_called()
        budget_repo.close_budget.assert_not_called()

    def test_closes_current_and_creates_new_when_valid_from_is_later(
        self,
        service: BudgetService,
        budget_repo: MagicMock,
        category_repo: MagicMock,
    ):
        category = make_category()
        category_repo.get_category_by_id.return_value = category
        current = make_budget(category_id=category.id, valid_from=date(2026, 8, 1))
        budget_repo.get_current_budget.return_value = current
        budget_repo.create_budget.return_value = make_budget(
            category_id=category.id, amount=50000, valid_from=date(2026, 9, 1)
        )

        user_id = uuid.uuid4()
        command = SetBudgetCommand(
            category_id=category.id, amount=50000, valid_from=date(2026, 9, 1)
        )
        service.set_budget(user_id, command)

        # El intervalo es semiabierto: el valid_to de la vieja es exactamente
        # el valid_from de la nueva, ni un día antes ni uno después.
        closed_id, closed_valid_to, closed_by = budget_repo.close_budget.call_args.args
        period = budget_repo.create_budget.call_args.args[1]
        assert closed_id == current.id
        assert closed_by == user_id
        assert closed_valid_to == date(2026, 9, 1)
        assert closed_valid_to == period.valid_from

    def test_raises_conflict_when_valid_from_is_earlier(
        self,
        service: BudgetService,
        budget_repo: MagicMock,
        category_repo: MagicMock,
    ):
        category = make_category()
        category_repo.get_category_by_id.return_value = category
        budget_repo.get_current_budget.return_value = make_budget(
            category_id=category.id, valid_from=date(2026, 8, 1)
        )

        command = SetBudgetCommand(
            category_id=category.id, amount=50000, valid_from=date(2026, 7, 1)
        )
        with pytest.raises(ConflictError):
            service.set_budget(uuid.uuid4(), command)

        budget_repo.create_budget.assert_not_called()
        budget_repo.update_amount.assert_not_called()
        budget_repo.close_budget.assert_not_called()

    def test_raises_conflict_when_category_is_archived(
        self,
        service: BudgetService,
        budget_repo: MagicMock,
        category_repo: MagicMock,
    ):
        category = make_category(is_active=False)
        category_repo.get_category_by_id.return_value = category

        command = SetBudgetCommand(
            category_id=category.id, amount=40000, valid_from=None
        )
        with pytest.raises(ConflictError):
            service.set_budget(uuid.uuid4(), command)

        budget_repo.get_current_budget.assert_not_called()
        budget_repo.create_budget.assert_not_called()

    def test_raises_not_found_when_category_does_not_exist(
        self,
        service: BudgetService,
        budget_repo: MagicMock,
        category_repo: MagicMock,
    ):
        category_repo.get_category_by_id.return_value = None

        command = SetBudgetCommand(
            category_id=uuid.uuid4(), amount=40000, valid_from=None
        )
        with pytest.raises(NotFoundError):
            service.set_budget(uuid.uuid4(), command)

        budget_repo.create_budget.assert_not_called()


class TestDeleteBudget:
    def test_closes_current_budget_with_today(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        current = make_budget(valid_from=date(2020, 1, 1))
        budget_repo.get_current_budget.return_value = current

        user_id = uuid.uuid4()
        service.delete_budget(user_id, current.category_id)

        assert budget_repo.close_budget.call_args.args == (
            current.id,
            date.today(),
            user_id,
        )

    def test_raises_not_found_when_there_is_no_current_budget(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        budget_repo.get_current_budget.return_value = None

        with pytest.raises(NotFoundError):
            service.delete_budget(uuid.uuid4(), uuid.uuid4())

        budget_repo.close_budget.assert_not_called()

    def test_raises_conflict_when_current_budget_starts_today_or_later(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        # Cerrarlo con valid_to = hoy dejaría un periodo de longitud cero o
        # negativa, que ck_budgets_period rechaza.
        current = make_budget(valid_from=date.today())
        budget_repo.get_current_budget.return_value = current

        with pytest.raises(ConflictError):
            service.delete_budget(uuid.uuid4(), current.category_id)

        budget_repo.close_budget.assert_not_called()


class TestGetBudgetHistory:
    def test_returns_every_period_of_the_category(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        category_id = uuid.uuid4()
        budget_repo.get_budgets_by_category_id.return_value = [
            make_budget(category_id=category_id, valid_from=date(2026, 9, 1)),
            make_budget(
                category_id=category_id,
                valid_from=date(2026, 1, 1),
                valid_to=date(2026, 9, 1),
            ),
        ]

        result = service.get_budget_history(category_id)

        assert len(result) == 2
        assert result[0].valid_to is None
        assert result[1].valid_to == date(2026, 9, 1)
        assert budget_repo.get_budgets_by_category_id.call_args.args == (category_id,)


class TestGetBudgetProgress:
    def test_derives_remaining_and_percentage(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        budget_repo.get_budget_progress.return_value = [
            make_progress_row(amount=40000, spent=34000)
        ]

        result = service.get_budget_progress(uuid.uuid4(), date(2026, 8, 14))

        assert result[0].remaining == 6000
        assert result[0].percentage == 85

    def test_reports_zero_and_not_null_without_any_expense(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        budget_repo.get_budget_progress.return_value = [
            make_progress_row(amount=40000, spent=0)
        ]

        result = service.get_budget_progress(uuid.uuid4(), date(2026, 8, 14))

        assert result[0].spent == 0
        assert result[0].percentage == 0
        assert result[0].remaining == 40000

    def test_allows_going_over_budget(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        budget_repo.get_budget_progress.return_value = [
            make_progress_row(amount=40000, spent=50000)
        ]

        result = service.get_budget_progress(uuid.uuid4(), date(2026, 8, 14))

        assert result[0].remaining == -10000
        assert result[0].percentage == 125

    def test_asks_the_repository_for_the_whole_month_of_the_given_date(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        budget_repo.get_budget_progress.return_value = []
        group_id = uuid.uuid4()

        service.get_budget_progress(group_id, date(2026, 8, 14))

        command = budget_repo.get_budget_progress.call_args.args[0]
        assert command.group_id == group_id
        assert command.month_start == date(2026, 8, 1)
        assert command.next_month_start == date(2026, 9, 1)

    def test_rolls_the_month_window_over_the_end_of_the_year(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        budget_repo.get_budget_progress.return_value = []

        service.get_budget_progress(uuid.uuid4(), date(2026, 12, 31))

        command = budget_repo.get_budget_progress.call_args.args[0]
        assert command.month_start == date(2026, 12, 1)
        assert command.next_month_start == date(2027, 1, 1)

    def test_defaults_to_the_current_month(
        self, service: BudgetService, budget_repo: MagicMock
    ):
        budget_repo.get_budget_progress.return_value = []

        service.get_budget_progress(uuid.uuid4(), None)

        command = budget_repo.get_budget_progress.call_args.args[0]
        assert command.month_start == date.today().replace(day=1)
