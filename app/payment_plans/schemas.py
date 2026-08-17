import uuid
from datetime import date as date_
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.payment_plans.models import FrequencyUnitEnum
from app.transactions.models import TransactionTypeEnum


class CreatePaymentPlanRequest(BaseModel):
    type: TransactionTypeEnum
    amount: int = Field(gt=0)
    category_id: uuid.UUID | None = Field(default=None)
    to_account_id: uuid.UUID | None = Field(default=None)
    description: str | None = Field(default=None)
    next_due_date: date_
    end_date: date_ | None = Field(default=None)
    is_recurring: bool = Field(default=False)
    frequency_interval: int | None = Field(default=None, gt=0)
    frequency_unit: FrequencyUnitEnum | None = Field(default=None)

    @model_validator(mode="after")
    def check_consistency(self) -> Self:
        if self.type == TransactionTypeEnum.TRANSFER:
            if self.to_account_id is None:
                raise ValueError("Una transferencia necesita to_account_id")
            if self.category_id is not None:
                raise ValueError("Una transferencia no admite category_id")
        elif self.to_account_id is not None:
            raise ValueError("to_account_id solo es válido para transferencias")

        if self.is_recurring:
            if self.frequency_interval is None or self.frequency_unit is None:
                raise ValueError(
                    "Un plan recurrente necesita frequency_interval y frequency_unit"
                )
        elif (
            self.frequency_interval is not None
            or self.frequency_unit is not None
            or self.end_date is not None
        ):
            raise ValueError(
                "frequency_interval, frequency_unit y end_date solo son válidos "
                "en un plan recurrente"
            )

        if self.end_date is not None and self.end_date < self.next_due_date:
            raise ValueError("end_date no puede ser anterior a next_due_date")

        return self


class UpdatePaymentPlanRequest(BaseModel):
    amount: int | None = Field(default=None, gt=0)
    type: TransactionTypeEnum | None = Field(default=None)
    category_id: uuid.UUID | None = Field(default=None)
    description: str | None = Field(default=None)
    next_due_date: date_ | None = Field(default=None)
    end_date: date_ | None = Field(default=None)
    is_recurring: bool | None = Field(default=None)
    frequency_interval: int | None = Field(default=None, gt=0)
    frequency_unit: FrequencyUnitEnum | None = Field(default=None)
    is_active: bool | None = Field(default=None)

    @model_validator(mode="after")
    def check_consistency(self) -> Self:
        if self.type == TransactionTypeEnum.TRANSFER:
            raise ValueError("No se puede cambiar el tipo a transferencia")

        if self.is_recurring is True:
            if self.frequency_interval is None or self.frequency_unit is None:
                raise ValueError(
                    "Activar is_recurring necesita frequency_interval y "
                    "frequency_unit en la misma petición"
                )
        elif self.is_recurring is False:
            if (
                self.frequency_interval is not None
                or self.frequency_unit is not None
                or self.end_date is not None
            ):
                raise ValueError(
                    "Desactivar is_recurring no admite frequency_interval, "
                    "frequency_unit ni end_date en la misma petición"
                )

        if (
            self.end_date is not None
            and self.next_due_date is not None
            and self.end_date < self.next_due_date
        ):
            raise ValueError("end_date no puede ser anterior a next_due_date")

        return self


class PaymentPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    account_id: uuid.UUID
    to_account_id: uuid.UUID | None
    category_id: uuid.UUID | None
    type: TransactionTypeEnum
    amount: int
    description: str | None
    next_due_date: date_
    end_date: date_ | None
    is_recurring: bool
    is_active: bool
    frequency_interval: int | None
    frequency_unit: FrequencyUnitEnum | None
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
