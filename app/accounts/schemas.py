import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.accounts.models import AccountTypeEnum


class CreateAccountRequest(BaseModel):
    """Cuerpo de POST /accounts?group_id=... — group_id viaja en la query
    string, no aquí, porque lo necesita la dependencia de autorización antes
    de que el body llegue a construirse (ver accounts/dependencies.py)."""

    name: str
    type: AccountTypeEnum | None = Field(default=None)
    opening_balance: int | None = Field(default=None)
    currency: str | None = Field(default=None)
    color: str | None = Field(default=None)
    icon: str | None = Field(default=None)


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
