from typing import Any

from app.shared.schemas import ErrorResponse

ResponsesDict = dict[int | str, dict[str, Any]]

BAD_REQUEST: ResponsesDict = {
    400: {"model": ErrorResponse, "description": "Petición incorrecta"},
}
UNAUTHORIZED: ResponsesDict = {
    401: {"model": ErrorResponse, "description": "No autenticado"},
}
FORBIDDEN: ResponsesDict = {
    403: {"model": ErrorResponse, "description": "Sin autorización sobre el recurso"},
}
NOT_FOUND: ResponsesDict = {
    404: {"model": ErrorResponse, "description": "Recurso no encontrado"},
}
CONFLICT: ResponsesDict = {
    409: {
        "model": ErrorResponse,
        "description": "Conflicto con el estado actual del recurso",
    },
}
SERVICE_UNAVAILABLE: ResponsesDict = {
    503: {"model": ErrorResponse, "description": "Dependencia no disponible"},
}
# Sobrescribe el HTTPValidationError que FastAPI documenta por defecto para
# el 422: la respuesta real la construye validation_error_handler con la
# misma forma que el resto de errores, no con la de FastAPI.
VALIDATION_ERROR: ResponsesDict = {
    422: {"model": ErrorResponse, "description": "Los datos enviados no son válidos"},
}


def responses(*groups: ResponsesDict) -> ResponsesDict:
    """Combina los grupos de respuestas que un endpoint concreto puede
    devolver de verdad, para pasarlos como `responses=` del decorador.
    """
    merged: ResponsesDict = {}
    for group in groups:
        merged.update(group)
    return merged
