import uuid
from dataclasses import dataclass


@dataclass
class CategoryCommand:
    group_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    color: str | None
    icon: str | None


@dataclass
class UpdateCategoryCommand:
    name: str | None
    parent_id: uuid.UUID | None
    color: str | None
    icon: str | None
    is_active: bool | None
