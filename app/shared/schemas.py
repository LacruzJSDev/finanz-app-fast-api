from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


def reject_explicit_nulls(model: BaseModel, *fields: str) -> None:
    """Rechaza un `null` explícito en campos que la tabla declara NOT NULL.

    En un `PATCH`, `null` significa "vacía este campo" (`ARCHITECTURE.md`
    §5.5), y eso solo tiene sentido donde la columna lo admite. En el resto no
    es un valor a aplicar sino uno imposible, así que se corta aquí con un 422
    en vez de dejar que llegue a la base y salga como un 500.

    Se llama desde un `model_validator(mode="after")` del schema de entrada.
    """
    for field in fields:
        if field in model.model_fields_set and getattr(model, field) is None:
            raise ValueError(f"{field} no admite null")


class CollectionResponse(BaseModel, Generic[T]):
    """Colección sin paginar. La usan todos los endpoints de lista salvo
    transactions.

    Se envuelve en lugar de devolver un array plano para que el cliente lea
    siempre `.items`, sin recordar cuál pagina y cuál no, y para poder añadir
    metadatos más adelante sin romper el contrato.
    """

    items: list[T]


class PaginatedResponse(CollectionResponse[T], Generic[T]):
    """Colección paginada por desplazamiento. Solo transactions, por ahora."""

    total: int
    limit: int
    offset: int


class ErrorDetail(BaseModel):
    """Un error concreto de un campo, dentro de un error de validación."""

    field: str
    message: str


class ErrorBody(BaseModel):
    code: str
    message: str
    details: list[ErrorDetail] | None = None


class ErrorResponse(BaseModel):
    """Forma ÚNICA de todas las respuestas de error de la API.

    Cualquier fallo —validación, autorización, recurso inexistente o error
    interno— sale con esta estructura, para que el cliente pueda escribir un
    solo manejador.
    """

    error: ErrorBody
