import uuid
from dataclasses import dataclass
from datetime import date as date_


@dataclass
class SetBudgetCommand:
    """Lo que pide el router en PUT /budgets/{category_id}. valid_from llega
    sin resolver: el día 1 del mes en curso lo pone el service."""

    category_id: uuid.UUID
    amount: int
    valid_from: date_ | None


@dataclass
class BudgetPeriodCommand:
    """El periodo ya resuelto que se escribe en la base de datos."""

    category_id: uuid.UUID
    amount: int
    valid_from: date_


@dataclass
class BudgetProgressCommand:
    """Ventana de la consulta de progreso. month_start es a la vez el día
    de referencia de la vigencia y el primer día del rango de gasto
    (budgets.md §5)."""

    group_id: uuid.UUID
    month_start: date_
    next_month_start: date_
