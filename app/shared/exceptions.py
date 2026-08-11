class AppError(Exception):
    """Base de los errores de negocio de la aplicación.

    Las capas de servicio lanzan estas excepciones, no HTTPException: así
    `service.py` no necesita saber nada de FastAPI ni de códigos HTTP. La
    traducción a respuesta HTTP la hace un único manejador registrado en
    `app/shared/error_handlers.py`.

    Cada dominio define sus propias subclases con un `code` específico, que es
    lo que el cliente usa para distinguir causas sin leer el mensaje:

        class InvalidCredentialsError(UnauthorizedError):
            code = "invalid_credentials"
            message = "Email o contraseña incorrectos"
    """

    status_code: int = 500
    code: str = "internal_error"
    message: str = "Error interno del servidor"

    def __init__(self, message: str | None = None) -> None:
        if message is not None:
            self.message = message
        super().__init__(self.message)


class BadRequestError(AppError):
    status_code = 400
    code = "bad_request"
    message = "Petición incorrecta"


class UnauthorizedError(AppError):
    """Autenticación ausente o inválida."""

    status_code = 401
    code = "unauthorized"
    message = "No autenticado"


class ForbiddenError(AppError):
    """Autenticado, pero sin autorización sobre el recurso.

    Nunca se enmascara como 404: ver ARCHITECTURE.md §5.6.
    """

    status_code = 403
    code = "forbidden"
    message = "Sin permiso sobre este recurso"


class NotFoundError(AppError):
    status_code = 404
    code = "not_found"
    message = "Recurso no encontrado"


class ConflictError(AppError):
    """Conflicto de unicidad o de estado (por ejemplo, email ya registrado)."""

    status_code = 409
    code = "conflict"
    message = "Conflicto con el estado actual del recurso"
