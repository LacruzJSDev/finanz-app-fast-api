import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class CreateCategoryRequest(BaseModel):
    """Cuerpo de POST /categories?group_id=... — group_id viaja en la query
    string, no aquí, mismo motivo que en accounts (ver accounts/schemas.py)."""

    name: str
    parent_id: uuid.UUID | None = Field(default=None)
    color: str | None = Field(default=None, min_length=4, max_length=7)
    icon: str | None = Field(default=None, max_length=50)


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
