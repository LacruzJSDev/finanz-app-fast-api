import uuid
from dataclasses import dataclass

from app.account_groups.models import AccountGroupMemberRoleEnum


@dataclass
class AccountGroupCommand:
    name: str
    color: str | None
    icon: str | None


@dataclass
class AccountGroupMemberCommand:
    group_id: uuid.UUID
    user_id: uuid.UUID
    role: AccountGroupMemberRoleEnum
