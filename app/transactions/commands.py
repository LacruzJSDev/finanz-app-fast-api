import uuid
from dataclasses import dataclass
from datetime import date as date_

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
