import uuid
from dataclasses import dataclass
from datetime import date as date_

from app.payment_plans.models import FrequencyUnitEnum
from app.shared.commands import UNSET, UnsetType
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
    """UNSET es "no lo mandó"; None es "mándalo a null", y esto último
    solo lo admiten category_id, description, end_date,
    frequency_interval y frequency_unit (ARCHITECTURE.md §5.5)."""

    amount: int | UnsetType = UNSET
    type: TransactionTypeEnum | UnsetType = UNSET
    category_id: uuid.UUID | None | UnsetType = UNSET
    description: str | None | UnsetType = UNSET
    next_due_date: date_ | UnsetType = UNSET
    end_date: date_ | None | UnsetType = UNSET
    is_recurring: bool | UnsetType = UNSET
    frequency_interval: int | None | UnsetType = UNSET
    frequency_unit: FrequencyUnitEnum | None | UnsetType = UNSET
    is_active: bool | UnsetType = UNSET
