import uuid
from dataclasses import dataclass

from app.accounts.models import AccountTypeEnum


@dataclass
class AccountCommand:
    group_id: uuid.UUID
    name: str
    type: AccountTypeEnum | None
    opening_balance: int | None
    currency: str | None
    color: str | None
    icon: str | None
