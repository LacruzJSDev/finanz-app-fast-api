import uuid
from datetime import datetime
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from app.account_groups.models import AccountGroupMemberRoleEnum


class CreateGroupRequest(BaseModel):
    """Cuerpo de POST /account-groups"""

    name: str = Field(min_length=8, max_length=100)
    color: str | None = Field(default=None, min_length=4, max_length=7)
    icon: str | None = Field(default=None, max_length=50)


class UpdateGroupRequest(BaseModel):
    """Cuerpo de PATCH /account-groups"""

    name: str | None = Field(default=None, min_length=8, max_length=100)
    color: str | None = Field(default=None, min_length=4, max_length=7)
    icon: str | None = Field(default=None, max_length=50)
    is_active: bool | None = Field(default=None)


class GroupMemberRead(BaseModel):
    """Representación pública de un miembro grupo en las respuestas de la API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    email: str
    user_id: uuid.UUID
    role: AccountGroupMemberRoleEnum
    created_at: datetime
    updated_at: datetime


class GroupRead(BaseModel):
    """Representación pública de un grupo en las respuestas de la API."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    color: str | None
    icon: str | None
    is_active: bool
    created_at: datetime
    updated_at: datetime
    members: list[GroupMemberRead] = Field(
        default_factory=lambda: cast(list[GroupMemberRead], [])
    )
