import uuid
from dataclasses import dataclass


@dataclass
class CategoryCommand:
    group_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    color: str | None
    icon: str | None
