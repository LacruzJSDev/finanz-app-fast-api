import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.accounts.models import AccountTypeEnum
from app.shared.schemas import reject_explicit_nulls


class CreateAccountRequest(BaseModel):
    """Cuerpo de POST /accounts?group_id=... — group_id viaja en la query
    string, no aquí, porque lo necesita la dependencia de autorización antes
    de que el body llegue a construirse (ver accounts/dependencies.py)."""

    name: str
    type: AccountTypeEnum | None = Field(default=None)
    opening_balance: int | None = Field(default=None)
    currency: str | None = Field(default=None)
    color: str | None = Field(default=None, min_length=4, max_length=7)
    icon: str | None = Field(default=None, max_length=50)


class UpdateAccountRequest(BaseModel):
    """Cuerpo de PATCH /accounts"""

    # Todos opcionales, incluido name: un PATCH que solo cambia el color no
    # tiene por qué reenviar el nombre (ARCHITECTURE.md §5.5).
    name: str | None = Field(default=None)
    type: AccountTypeEnum | None = Field(default=None)
    color: str | None = Field(default=None, min_length=4, max_length=7)
    icon: str | None = Field(default=None, max_length=50)
    is_active: bool | None = Field(default=None)

    @model_validator(mode="after")
    def check_nulls(self) -> Self:
        # Solo color e icon son vaciables.
        reject_explicit_nulls(self, "name", "type", "is_active")
        return self


class GroupBalanceRead(BaseModel):
    """Saldo agregado de un grupo, en céntimos. Un grupo sin cuentas activas
    devuelve ceros y la divisa por defecto, nunca null (accounts.md §7)."""

    net_worth: int
    available: int
    account_count: int
    spendable_account_count: int
    currency: str


class AccountRead(BaseModel):
    """Representación pública de una cuenta"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    name: str
    type: AccountTypeEnum
    opening_balance: int
    balance: int
    currency: str
    color: str | None
    icon: str | None
    is_active: bool
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
