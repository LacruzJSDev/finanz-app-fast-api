import uuid
from datetime import datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.shared.schemas import reject_explicit_nulls


class CreateCategoryRequest(BaseModel):
    """Cuerpo de POST /categories?group_id=... — group_id viaja en la query
    string, no aquí, mismo motivo que en accounts (ver accounts/schemas.py)."""

    name: str
    parent_id: uuid.UUID | None = Field(default=None)
    color: str | None = Field(default=None, min_length=4, max_length=7)
    icon: str | None = Field(default=None, max_length=50)


class UpdateCategoryRequest(BaseModel):
    """Cuerpo de PATCH /categories/{category_id}"""

    name: str | None = Field(default=None)
    parent_id: uuid.UUID | None = Field(default=None)
    color: str | None = Field(default=None, min_length=4, max_length=7)
    icon: str | None = Field(default=None, max_length=50)
    is_active: bool | None = Field(default=None)

    @model_validator(mode="after")
    def check_nulls(self) -> Self:
        # Solo parent_id, color e icon admiten vaciarse.
        reject_explicit_nulls(self, "name", "is_active")
        return self


class CategoryRead(BaseModel):
    """Representación pública de una categoría"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    group_id: uuid.UUID
    parent_id: uuid.UUID | None
    name: str
    color: str | None
    icon: str | None
    is_active: bool
    created_by: uuid.UUID | None
    updated_by: uuid.UUID | None
    created_at: datetime
    updated_at: datetime
