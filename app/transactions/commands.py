import uuid
from dataclasses import dataclass
from datetime import date as date_

from app.shared.commands import UNSET, UnsetType
from app.transactions.models import TransactionTypeEnum


@dataclass
class CreateTransactionCommand:
    account_id: uuid.UUID
    group_id: uuid.UUID
    type: TransactionTypeEnum
    amount: int
    category_id: uuid.UUID | None
    to_account_id: uuid.UUID | None
    date: date_
    notes: str | None
    payment_plan_id: uuid.UUID | None = None
    payment_plan_occurrence_id: uuid.UUID | None = None


@dataclass
class TransactionRowCommand:
    account_id: uuid.UUID
    to_account_id: uuid.UUID | None
    category_id: uuid.UUID | None
    transfer_group_id: uuid.UUID | None
    amount: int
    type: TransactionTypeEnum
    date: date_
    notes: str | None
    payment_plan_id: uuid.UUID | None = None
    payment_plan_occurrence_id: uuid.UUID | None = None


@dataclass
class TransactionFilterCommand:
    """Criterios de una consulta plana. group_id es el ámbito, no un filtro
    (ARCHITECTURE.md §8.3); el resto restringe solo si viene informado."""

    group_id: uuid.UUID
    account_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None
    uncategorized: bool = False
    type: TransactionTypeEnum | None = None
    date_from: date_ | None = None
    date_to: date_ | None = None
    q: str | None = None


@dataclass
class DailySpendCommand:
    group_id: uuid.UUID
    date: date_
    account_id: uuid.UUID | None = None


@dataclass
class UpdateTransactionCommand:
    """Cambios pedidos en un PATCH. UNSET es "no lo mandó"; None es "mándalo a
    null", y solo lo admiten los campos que la tabla declara nullable
    (ARCHITECTURE.md §5.5)."""

    amount: int | UnsetType = UNSET
    type: TransactionTypeEnum | UnsetType = UNSET
    category_id: uuid.UUID | None | UnsetType = UNSET
    date: date_ | UnsetType = UNSET
    notes: str | None | UnsetType = UNSET
