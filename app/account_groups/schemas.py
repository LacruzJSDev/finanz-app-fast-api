import uuid
from datetime import date as date_
from datetime import datetime
from typing import cast

from pydantic import BaseModel, ConfigDict, Field

from app.account_groups.models import AccountGroupMemberRoleEnum, InvitationStatusEnum


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


class ChangeGroupMemberRoleRequest(BaseModel):
    """Cuerpo de PATCH /account-groups/{group_id}/members/{user_id}"""

    role: AccountGroupMemberRoleEnum


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


class CreateInvitationRequest(BaseModel):
    """Cuerpo de POST /{group_id}/invitations"""

    role: AccountGroupMemberRoleEnum


class InvitedByRead(BaseModel):
    name: str
    email: str


class InvitationRead(BaseModel):
    """Representación pública de una invitación a un grupo"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    invited_by: InvitedByRead | None
    role: AccountGroupMemberRoleEnum
    code: str
    status: InvitationStatusEnum
    accepted_by: uuid.UUID | None
    accepted_at: datetime | None
    expires_at: datetime
    created_at: datetime


class PaydayRead(BaseModel):
    """Ancla de cobro del grupo: cuándo entra el próximo ingreso recurrente y
    cuánto (payment_plans.md §5)."""

    date: date_
    amount: int


class PendingFixedExpenseRead(BaseModel):
    """Gasto fijo que todavía tiene que salir antes del cobro."""

    payment_plan_id: uuid.UUID
    description: str | None
    amount: int
    due_date: date_


class ProjectionPointRead(BaseModel):
    """Un punto de la curva de saldo previsto, en céntimos."""

    date: date_
    balance: int


class GroupOverviewRead(BaseModel):
    """Resumen del grupo (account_groups.md §4). Los cuatro campos que
    dependen del ancla de cobro son null cuando el grupo no tiene ninguna."""

    net_worth: int
    available: int
    account_count: int
    spent_today: int
    transaction_count_today: int
    payday: PaydayRead | None
    pending_fixed_expenses: list[PendingFixedExpenseRead]
    pending_fixed_expenses_total: int
    real_balance: int
    days_remaining: int | None
    daily_safe_spend: int | None
    projection: list[ProjectionPointRead] | None
