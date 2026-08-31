from dataclasses import dataclass

from app.shared.commands import UNSET, UnsetType


@dataclass
class UpdateUserCommand:
    """UNSET es "no lo mandó". Ninguno de los dos campos es vaciable: ambas
    columnas son NOT NULL (ARCHITECTURE.md §5.5)."""

    name: str | UnsetType = UNSET
    email: str | UnsetType = UNSET
