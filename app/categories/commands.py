import uuid
from dataclasses import dataclass

from app.shared.commands import UNSET, UnsetType


@dataclass
class CategoryCommand:
    group_id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    color: str | None
    icon: str | None


@dataclass
class UpdateCategoryCommand:
    """UNSET es "no lo mandó"; None es "mándalo a null", y esto último
    solo lo admiten parent_id, color e icon (ARCHITECTURE.md §5.5)."""

    name: str | UnsetType = UNSET
    parent_id: uuid.UUID | None | UnsetType = UNSET
    color: str | None | UnsetType = UNSET
    icon: str | None | UnsetType = UNSET
    is_active: bool | UnsetType = UNSET
