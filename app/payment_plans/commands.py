import uuid
from dataclasses import dataclass
from datetime import date as date_

from app.payment_plans.models import FrequencyUnitEnum
from app.transactions.models import TransactionTypeEnum


@dataclass
class CreatePaymentPlanCommand:
    account_id: uuid.UUID
    group_id: uuid.UUID
    type: TransactionTypeEnum
    amount: int
    category_id: uuid.UUID | None
    to_account_id: uuid.UUID | None
    description: str | None
    next_due_date: date_
    end_date: date_ | None
    is_recurring: bool
    frequency_interval: int | None
    frequency_unit: FrequencyUnitEnum | None


@dataclass
class UpdatePaymentPlanCommand:
    amount: int | None
    type: TransactionTypeEnum | None
    category_id: uuid.UUID | None
    description: str | None
    next_due_date: date_ | None
    end_date: date_ | None
    is_recurring: bool | None
    frequency_interval: int | None
    frequency_unit: FrequencyUnitEnum | None
    is_active: bool | None
