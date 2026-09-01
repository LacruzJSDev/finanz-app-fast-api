import uuid
from datetime import date as date_
from typing import Annotated

from fastapi import Depends, Query
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError

from app.accounts.dependencies import get_account_repository
from app.accounts.repository import AccountRepository
from app.categories.dependencies import get_category_repository
from app.categories.repository import CategoryRepository
from app.shared.dependencies import DbSession
from app.transactions.models import TransactionTypeEnum
from app.transactions.repository import TransactionRepository
from app.transactions.schemas import TransactionFilterQuery
from app.transactions.service import TransactionService


def get_transaction_repository(db: DbSession) -> TransactionRepository:
    return TransactionRepository(db)


def get_transaction_service(
    transaction_repo: Annotated[
        TransactionRepository, Depends(get_transaction_repository)
    ],
    account_repo: Annotated[AccountRepository, Depends(get_account_repository)],
    category_repo: Annotated[CategoryRepository, Depends(get_category_repository)],
) -> TransactionService:
    return TransactionService(transaction_repo, account_repo, category_repo)


TransactionServiceDep = Annotated[TransactionService, Depends(get_transaction_service)]


def get_transaction_filters(
    account_id: Annotated[
        uuid.UUID | None, Query(description="Restringe a una cuenta del grupo")
    ] = None,
    category_id: Annotated[
        uuid.UUID | None,
        Query(description="Una categoría raíz incluye sus subcategorías"),
    ] = None,
    uncategorized: Annotated[
        bool, Query(description="Solo movimientos sin categoría")
    ] = False,
    type: Annotated[TransactionTypeEnum | None, Query()] = None,
    date_from: Annotated[date_ | None, Query(description="Inclusivo")] = None,
    date_to: Annotated[date_ | None, Query(description="Inclusivo")] = None,
    q: Annotated[str | None, Query(description="Subcadena a buscar en notes")] = None,
) -> TransactionFilterQuery:
    """Query params comunes al listado plano y a sus agregados.

    Los params se declaran uno a uno en vez de como `Annotated[Schema,
    Query()]`: FastAPI solo despliega un modelo de query en el OpenAPI cuando
    es el único param de query del endpoint, y aquí siempre conviven al menos
    con el `group_id` del ámbito, así que el schema saldría documentado como
    un parámetro suelto con un `$ref` — y de ahí generaría sus tipos el
    frontend (ARCHITECTURE.md §5.1). La validación cruzada sigue viviendo en
    el schema, y su fallo se traduce al 422 estándar de la API.
    """
    try:
        return TransactionFilterQuery(
            account_id=account_id,
            category_id=category_id,
            uncategorized=uncategorized,
            type=type,
            date_from=date_from,
            date_to=date_to,
            q=q,
        )
    except ValidationError as exc:
        raise RequestValidationError(
            [{**error, "loc": ("query", *error["loc"])} for error in exc.errors()]
        ) from exc


TransactionFiltersDep = Annotated[
    TransactionFilterQuery, Depends(get_transaction_filters)
]
