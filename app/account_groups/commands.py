import uuid
from dataclasses import dataclass
from datetime import datetime

from app.account_groups.models import AccountGroupMemberRoleEnum


@dataclass
class AccountGroupCommand:
    name: str
    color: str | None
    icon: str | None


@dataclass
class UpdateAccountGroupCommand:
    name: str | None
    color: str | None
    icon: str | None
    is_active: bool | None


@dataclass
class AccountGroupMemberCommand:
    group_id: uuid.UUID
    user_id: uuid.UUID
    role: AccountGroupMemberRoleEnum


@dataclass
class InvitationCommand:
    group_id: uuid.UUID
    invited_by: uuid.UUID
    role: AccountGroupMemberRoleEnum
    code: str
    expires_at: datetime
