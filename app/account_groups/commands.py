import uuid
from dataclasses import dataclass
from datetime import datetime

from app.account_groups.models import AccountGroupMemberRoleEnum
from app.shared.commands import UNSET, UnsetType


@dataclass
class AccountGroupCommand:
    name: str
    color: str | None
    icon: str | None


@dataclass
class UpdateAccountGroupCommand:
    """UNSET es "no lo mandó"; None es "mándalo a null", y esto último
    solo lo admiten color e icon (ARCHITECTURE.md §5.5)."""

    name: str | UnsetType = UNSET
    color: str | None | UnsetType = UNSET
    icon: str | None | UnsetType = UNSET
    is_active: bool | UnsetType = UNSET


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
