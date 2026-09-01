import uuid
from datetime import date as date_
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SetBudgetRequest(BaseModel):
    """Cuerpo de PUT /budgets/{category_id} — category_id viaja en la ruta,
    no aquí."""

    amount: int = Field(gt=0)
    valid_from: date_ | None = Field(default=None)


class BudgetRead(BaseModel):
    """Representación pública de un periodo de presupuesto."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    category_id: uuid.UUID
    amount: int
    valid_from: date_
    valid_to: date_ | None
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class BudgetProgressRead(BaseModel):
    """Presupuesto vigente en un mes junto al gasto real de ese mes."""

    category_id: uuid.UUID
    category_name: str
    parent_id: uuid.UUID | None
    amount: int
    spent: int
    remaining: int
    percentage: int
