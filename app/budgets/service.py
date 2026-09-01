import uuid
from dataclasses import dataclass
from datetime import date as date_

from app.budgets.commands import (
    BudgetPeriodCommand,
    BudgetProgressCommand,
    SetBudgetCommand,
)
from app.budgets.repository import BudgetRepository
from app.budgets.schemas import BudgetProgressRead, BudgetRead
from app.categories.repository import CategoryRepository
from app.shared.exceptions import ConflictError, NotFoundError


def _month_start(day: date_) -> date_:
    return day.replace(day=1)


def _next_month_start(month_start: date_) -> date_:
    if month_start.month == 12:
        return date_(month_start.year + 1, 1, 1)
    return date_(month_start.year, month_start.month + 1, 1)


@dataclass
class BudgetService:
    """Lógica de negocio del dominio budgets."""

    budget_repo: BudgetRepository
    category_repo: CategoryRepository

    def set_budget(self, user_id: uuid.UUID, command: SetBudgetCommand) -> BudgetRead:
        """budgets.md §4: las cuatro ramas de la tabla de efectos. Cerrar la
        fila vigente antes de insertar la nueva deja a excl_budget_overlap
        como red de seguridad ante una carrera, no como camino habitual.
        """
        category = self.category_repo.get_category_by_id(command.category_id)
        if category is None:
            raise NotFoundError("La categoría no existe")
        if not category.is_active:
            raise ConflictError("No se puede presupuestar una categoría archivada")

        valid_from = command.valid_from or _month_start(date_.today())
        period = BudgetPeriodCommand(
            category_id=command.category_id,
            amount=command.amount,
            valid_from=valid_from,
        )

        current = self.budget_repo.get_current_budget(command.category_id)
        if current is None:
            budget = self.budget_repo.create_budget(user_id, period)
        elif current.valid_from == valid_from:
            # Sin fila nueva: abrirla dejaría un periodo de longitud cero.
            budget = self.budget_repo.update_amount(current.id, command.amount, user_id)
        elif valid_from > current.valid_from:
            # El valid_to de la vieja es el valid_from de la nueva: el
            # intervalo es semiabierto, así no hay solape ni hueco.
            self.budget_repo.close_budget(current.id, valid_from, user_id)
            budget = self.budget_repo.create_budget(user_id, period)
        else:
            raise ConflictError(
                "No se puede retrodatar un presupuesto por delante del vigente"
            )

        return BudgetRead.model_validate(budget)

    def delete_budget(self, user_id: uuid.UUID, category_id: uuid.UUID) -> None:
        current = self.budget_repo.get_current_budget(category_id)
        if current is None:
            raise NotFoundError("La categoría no tiene ningún presupuesto vigente")

        today = date_.today()
        # El SPEC no cubre este caso: cerrar hoy un periodo que empieza hoy o
        # más adelante violaría ck_budgets_period (valid_to > valid_from) y
        # saldría como 500. Se corta aquí como conflicto de estado.
        if today <= current.valid_from:
            raise ConflictError(
                "El presupuesto vigente empieza hoy o más adelante y no se "
                "puede cerrar con fecha de hoy"
            )

        self.budget_repo.close_budget(current.id, today, user_id)

    def get_budget_history(self, category_id: uuid.UUID) -> list[BudgetRead]:
        budgets = self.budget_repo.get_budgets_by_category_id(category_id)
        return [BudgetRead.model_validate(budget) for budget in budgets]

    def get_budget_progress(
        self, group_id: uuid.UUID, month: date_ | None
    ) -> list[BudgetProgressRead]:
        month_start = _month_start(month or date_.today())
        command = BudgetProgressCommand(
            group_id=group_id,
            month_start=month_start,
            next_month_start=_next_month_start(month_start),
        )
        rows = self.budget_repo.get_budget_progress(command)
        return [
            BudgetProgressRead(
                category_id=row.category_id,
                category_name=row.category_name,
                parent_id=row.parent_id,
                amount=row.amount,
                spent=row.spent,
                remaining=row.amount - row.spent,
                # amount > 0 lo garantiza ck_budgets_amount_positive, así que
                # la división es segura. Entero, sin decimales (budgets.md §5).
                percentage=row.spent * 100 // row.amount,
            )
            for row in rows
        ]
