import uuid
from dataclasses import dataclass
from datetime import date as date_

from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session

from app.accounts.models import Account
from app.budgets.commands import BudgetPeriodCommand, BudgetProgressCommand
from app.budgets.models import Budget
from app.categories.models import Category
from app.transactions.models import Transaction, TransactionTypeEnum


@dataclass
class BudgetProgressRow:
    """Fila cruda de la consulta de progreso, antes de derivar remaining y
    percentage."""

    category_id: uuid.UUID
    category_name: str
    parent_id: uuid.UUID | None
    amount: int
    spent: int


@dataclass
class BudgetRepository:
    """Acceso a datos del dominio budgets."""

    db: Session

    def create_budget(
        self, user_id: uuid.UUID, period: BudgetPeriodCommand
    ) -> Budget:
        budget = Budget(
            category_id=period.category_id,
            amount=period.amount,
            valid_from=period.valid_from,
            created_by=user_id,
            updated_by=user_id,
        )
        self.db.add(budget)
        self.db.flush()
        return budget

    def get_current_budget(self, category_id: uuid.UUID) -> Budget | None:
        """El periodo abierto de la categoría. excl_budget_overlap garantiza
        que como mucho hay uno: un rango abierto solapa con cualquier otro."""
        return self.db.execute(
            select(Budget).where(
                Budget.category_id == category_id, Budget.valid_to.is_(None)
            )
        ).scalar_one_or_none()

    def get_budgets_by_category_id(self, category_id: uuid.UUID) -> list[Budget]:
        budgets = (
            self.db.execute(
                select(Budget)
                .where(Budget.category_id == category_id)
                .order_by(Budget.valid_from.desc())
            )
            .scalars()
            .all()
        )
        return list(budgets)

    def update_amount(
        self, budget_id: uuid.UUID, amount: int, user_id: uuid.UUID
    ) -> Budget:
        return self.db.execute(
            update(Budget)
            .where(Budget.id == budget_id)
            .values(amount=amount, updated_by=user_id)
            .returning(Budget)
        ).scalar_one()

    def close_budget(
        self, budget_id: uuid.UUID, valid_to: date_, user_id: uuid.UUID
    ) -> Budget:
        return self.db.execute(
            update(Budget)
            .where(Budget.id == budget_id)
            .values(valid_to=valid_to, updated_by=user_id)
            .returning(Budget)
        ).scalar_one()

    def get_budget_progress(
        self, command: BudgetProgressCommand
    ) -> list[BudgetProgressRow]:
        """budgets.md §5: el gasto se agrupa por la categoría PROPIA de cada
        transacción y se une por dos ramas —la categoría del presupuesto o su
        padre—. Agrupar ya por la raíz dejaría a cero cualquier presupuesto
        puesto sobre una subcategoría, porque su id no sería clave de ningún
        grupo. El precio conocido es que el gasto de una hija cuenta a la vez
        en su presupuesto y en el de su padre, si ambos existen.
        """
        spent = (
            select(
                Transaction.category_id.label("category_id"),
                Category.parent_id.label("parent_id"),
                func.sum(Transaction.amount).label("spent"),
            )
            .join(Account, Account.id == Transaction.account_id)
            .join(Category, Category.id == Transaction.category_id)
            .where(
                Account.group_id == command.group_id,
                Transaction.deleted_at.is_(None),
                Transaction.type == TransactionTypeEnum.EXPENSE,
                Transaction.date >= command.month_start,
                Transaction.date < command.next_month_start,
            )
            .group_by(Transaction.category_id, Category.parent_id)
            .subquery()
        )

        rows = self.db.execute(
            select(
                Category.id,
                Category.name,
                Category.parent_id,
                Budget.amount,
                func.coalesce(func.sum(spent.c.spent), 0),
            )
            .select_from(Budget)
            .join(Category, Category.id == Budget.category_id)
            .outerjoin(
                spent,
                or_(
                    spent.c.category_id == Budget.category_id,
                    spent.c.parent_id == Budget.category_id,
                ),
            )
            .where(
                Category.group_id == command.group_id,
                Budget.valid_from <= command.month_start,
                or_(
                    Budget.valid_to.is_(None),
                    Budget.valid_to > command.month_start,
                ),
            )
            .group_by(
                Budget.id,
                Budget.amount,
                Category.id,
                Category.name,
                Category.parent_id,
            )
            .order_by(Category.name)
        ).all()

        # SUM sobre BIGINT devuelve NUMERIC, que psycopg entrega como Decimal.
        # Los gastos se guardan en negativo y spent es la magnitud.
        return [
            BudgetProgressRow(
                category_id=row[0],
                category_name=row[1],
                parent_id=row[2],
                amount=int(row[3]),
                spent=abs(int(row[4])),
            )
            for row in rows
        ]
