import uuid
from dataclasses import dataclass

from app.accounts.models import AccountTypeEnum
from app.shared.commands import UNSET, UnsetType


@dataclass
class AccountCommand:
    group_id: uuid.UUID
    name: str
    type: AccountTypeEnum | None
    opening_balance: int | None
    currency: str | None
    color: str | None
    icon: str | None


@dataclass
class UpdateAccountCommand:
    """UNSET es "no lo mandó"; None es "mándalo a null", y solo lo admiten
    color e icon (ARCHITECTURE.md §5.5)."""

    name: str | UnsetType = UNSET
    type: AccountTypeEnum | UnsetType = UNSET
    color: str | None | UnsetType = UNSET
    icon: str | None | UnsetType = UNSET
    is_active: bool | UnsetType = UNSET
