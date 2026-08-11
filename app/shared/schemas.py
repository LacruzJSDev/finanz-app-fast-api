from typing import Generic, TypeVar

from pydantic import BaseModel

T = TypeVar("T")


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
