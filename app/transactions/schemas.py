import uuid
from datetime import date as date_
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.schemas import reject_explicit_nulls
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
        # Solo category_id y notes admiten vaciarse.
        reject_explicit_nulls(self, "amount", "type", "date")
        return self


class TransactionFilterQuery(BaseModel):
    """Query params comunes al listado plano y a sus agregados.

    Un único schema para los tres endpoints: es lo que garantiza que un
    agregado describa exactamente las mismas filas que devolvería el listado
    con esos parámetros (transactions.md §4.B).
    """

    account_id: uuid.UUID | None = Field(default=None)
    category_id: uuid.UUID | None = Field(default=None)
    uncategorized: bool = Field(default=False)
    type: TransactionTypeEnum | None = Field(default=None)
    date_from: date_ | None = Field(default=None)
    date_to: date_ | None = Field(default=None)
    q: str | None = Field(default=None)

    @model_validator(mode="after")
    def check_filter_consistency(self) -> Self:
        # transactions.md §5: contradicciones entre params de la misma
        # petición, así que 422 desde aquí y no 409 desde el service.
        if self.uncategorized and self.category_id is not None:
            raise ValueError("uncategorized no admite category_id a la vez")
        if (
            self.date_from is not None
            and self.date_to is not None
            and self.date_from > self.date_to
        ):
            raise ValueError("date_from no puede ser posterior a date_to")
        return self


class CategorySummaryRead(BaseModel):
    """Fila del desglose por categoría raíz, en céntimos.

    `root_category_id`/`root_category_name` van a nulo en la fila que agrupa
    lo no categorizado. `expense` conserva el signo almacenado (negativo):
    `daily` es el único punto del dominio que devuelve magnitud
    (transactions.md §5).
    """

    root_category_id: uuid.UUID | None
    root_category_name: str | None
    income: int
    expense: int
    transaction_count: int


class DailySpendRead(BaseModel):
    date: date_
    spent: int
    transaction_count: int


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    to_account_id: uuid.UUID | None
    category_id: uuid.UUID | None
    transfer_group_id: uuid.UUID | None
    payment_plan_id: uuid.UUID | None
    amount: int
    type: TransactionTypeEnum
    date: date_
    notes: str | None
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
