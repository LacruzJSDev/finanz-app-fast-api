import logging

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.types import ExceptionHandler

from app.shared.exceptions import AppError
from app.shared.schemas import ErrorBody, ErrorDetail, ErrorResponse

logger = logging.getLogger(__name__)

# Códigos para los errores que no genera la aplicación, sino el framework:
# rutas inexistentes, métodos no permitidos, cuerpos malformados.
_CODES_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    415: "unsupported_media_type",
    422: "validation_error",
    500: "internal_error",
    501: "not_implemented",
}


def _error_response(status_code: int, body: ErrorBody) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=body).model_dump(exclude_none=True),
    )


async def app_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Excepciones de negocio lanzadas por la capa de servicio."""
    assert isinstance(exc, AppError)
    return _error_response(
        exc.status_code, ErrorBody(code=exc.code, message=exc.message)
    )


async def validation_error_handler(_: Request, exc: Exception) -> JSONResponse:
    """Cuerpo, query o path que no pasan la validación de Pydantic."""
    assert isinstance(exc, RequestValidationError)
    details = [
        ErrorDetail(
            # loc viene como ("body", "email"); se aplana a "body.email"
            field=".".join(str(part) for part in error["loc"]),
            message=error["msg"],
        )
        for error in exc.errors()
    ]
    return _error_response(
        422,
        ErrorBody(
            code="validation_error",
            message="Los datos enviados no son válidos",
            details=details,
        ),
    )


async def http_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Errores del propio framework: ruta inexistente, método no permitido."""
    assert isinstance(exc, StarletteHTTPException)
    code = _CODES_BY_STATUS.get(exc.status_code, "error")
    return _error_response(
        exc.status_code, ErrorBody(code=code, message=str(exc.detail))
    )


async def unhandled_exception_handler(_: Request, exc: Exception) -> JSONResponse:
    """Cualquier excepción no prevista."""
    # El traceback va al log, nunca a la respuesta: filtrarlo expondría rutas
    # de ficheros y detalles internos a cualquiera que provoque un fallo.
    logger.exception("Excepción no controlada", exc_info=exc)
    return _error_response(
        500, ErrorBody(code="internal_error", message="Error interno del servidor")
    )


# Qué manejador atiende a qué excepción. Mantener el mapa junto a los
# manejadores evita tener que tocar dos ficheros al añadir uno nuevo.
#
# La anotación es necesaria: las claves son clases de excepción distintas
# (type[AppError], type[RequestValidationError]...) y sin un tipo explícito
# el checker no siempre sintetiza un tipo común limpio para un dict literal
# así, así que las claves aparecen como Unknown en vez de type[Exception].
# ExceptionHandler es el mismo tipo que exige Starlette.add_exception_handler.
ERROR_HANDLERS: dict[type[Exception], ExceptionHandler] = {
    AppError: app_error_handler,
    RequestValidationError: validation_error_handler,
    StarletteHTTPException: http_exception_handler,
    Exception: unhandled_exception_handler,
}


def register_error_handlers(app: FastAPI) -> None:
    """Deja toda la API devolviendo la misma forma de error.

    Sin esto FastAPI responde de tres maneras distintas: `detail` como lista en
    los 422, `detail` como cadena en los 404, y texto plano sin JSON en los 500.
    """
    for exception, handler in ERROR_HANDLERS.items():
        app.add_exception_handler(exception, handler)
