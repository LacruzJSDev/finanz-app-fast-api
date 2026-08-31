import enum


class UnsetType(enum.Enum):
    """Marca "el cliente no envió este campo" en una actualización parcial.

    `None` no sirve para eso: en un `PATCH`, `null` es un valor legítimo para
    cualquier columna nullable, y significa "vacía este campo"
    (`ARCHITECTURE.md` §5.5). Usar `None` para las dos cosas hace imposible
    distinguirlas, y el campo acaba sin poder vaciarse nunca.

    Se declara como enum de un solo miembro, y no como una instancia suelta,
    porque así el análisis de tipos estrecha correctamente en las
    comparaciones `is UNSET` / `is not UNSET`.
    """

    UNSET = "unset"


UNSET = UnsetType.UNSET
