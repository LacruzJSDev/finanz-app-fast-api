import uuid
from datetime import date as date_
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.transactions.models import TransactionTypeEnum


class CreateTransactionRequest(BaseModel):
    type: TransactionTypeEnum
    amount: int = Field(gt=0)
    category_id: uuid.UUID | None = Field(default=None)
    to_account_id: uuid.UUID | None = Field(default=None)
    date: date_
    notes: str | None = Field(default=None)

    @model_validator(mode="after")
    def check_type_consistency(self) -> Self:
        if self.type == TransactionTypeEnum.TRANSFER:
            if self.to_account_id is None:
                raise ValueError("Una transferencia necesita to_account_id")
            if self.category_id is not None:
                raise ValueError("Una transferencia no admite category_id")
        elif self.to_account_id is not None:
            raise ValueError("to_account_id solo es válido para transferencias")
        return self


class UpdateTransactionRequest(BaseModel):
    amount: int | None = Field(default=None, gt=0)
    type: TransactionTypeEnum | None = Field(default=None)
    category_id: uuid.UUID | None = Field(default=None)
    date: date_ | None = Field(default=None)
    notes: str | None = Field(default=None)

    @model_validator(mode="after")
    def check_type_not_transfer(self) -> Self:
        if self.type == TransactionTypeEnum.TRANSFER:
            raise ValueError("No se puede cambiar el tipo a transferencia")
        return self


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    to_account_id: uuid.UUID | None
    category_id: uuid.UUID | None
    transfer_group_id: uuid.UUID | None
    amount: int
    type: TransactionTypeEnum
    date: date_
    notes: str | None
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
