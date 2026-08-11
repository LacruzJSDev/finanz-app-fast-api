from fastapi import APIRouter

from app.auth.dependencies import AuthServiceDep
from app.auth.schemas import LoginRequest, LoginResponse, RegisterRequest

# El prefijo aquí es solo el del dominio. La versión (/api/v1) la pone main.py
# al montar el router, para que cambiarla sea tocar una línea y no doce.
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login")
def login(payload: LoginRequest, service: AuthServiceDep) -> LoginResponse:
    """Inicio de sesión con credenciales locales."""
    return service.login(payload.email, payload.password)


@router.post("/register")
def register(payload: RegisterRequest, service: AuthServiceDep) -> LoginResponse:
    """Registro de un nuevo usuario local."""
    return service.register(payload.email, payload.name, payload.password)
