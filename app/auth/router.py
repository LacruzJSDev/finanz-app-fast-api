from fastapi import APIRouter, Request, Response, status

from app.auth.dependencies import AuthServiceDep
from app.auth.schemas import ChangePasswordRequest, LoginRequest, RegisterRequest
from app.auth.service import AuthResult
from app.config import settings
from app.shared.dependencies import (
    ACCESS_TOKEN_COOKIE,
    REFRESH_TOKEN_COOKIE,
    CurrentUser,
)
from app.shared.exceptions import UnauthorizedError
from app.users.schemas import UserRead

# El prefijo aquí es solo el del dominio. La versión (/api/v1) la pone main.py
# al montar el router, para que cambiarla sea tocar una línea y no doce.
router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, result: AuthResult) -> None:
    """Pone los dos tokens como cookies httpOnly, nunca en el cuerpo JSON.

    refresh_token se restringe a /api/v1/auth: solo lo necesitan /refresh y
    /logout, no hace falta que viaje en cada petición a la API.
    """
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        result.access_token,
        expires=result.access_expires_at,
        path="/",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        result.refresh_token,
        expires=result.refresh_expires_at,
        path="/api/v1/auth",
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
    )


def _delete_auth_cookies(response: Response):
    response.delete_cookie(ACCESS_TOKEN_COOKIE)
    response.delete_cookie(REFRESH_TOKEN_COOKIE, path="/api/v1/auth")


@router.post("/login")
def login(
    payload: LoginRequest, service: AuthServiceDep, response: Response
) -> UserRead:
    """Inicio de sesión con credenciales locales."""
    result = service.login(payload.email, payload.password)
    _set_auth_cookies(response, result)
    return result.user


@router.post("/register")
def register(
    payload: RegisterRequest, service: AuthServiceDep, response: Response
) -> UserRead:
    """Registro de un nuevo usuario local."""
    result = service.register(payload.email, payload.name, payload.password)
    _set_auth_cookies(response, result)
    return result.user


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(service: AuthServiceDep, request: Request, response: Response):
    """Cierra la sesión actual del usuario."""
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if refresh_token is None:
        raise UnauthorizedError("Refresh token no presente en la petición")
    service.logout(refresh_token)
    _delete_auth_cookies(response)
    return


@router.post("/refresh")
def refresh(service: AuthServiceDep, request: Request, response: Response) -> UserRead:
    """Refresca el token y lo rota."""
    refresh_token = request.cookies.get(REFRESH_TOKEN_COOKIE)
    if refresh_token is None:
        raise UnauthorizedError("Refresh token no presente en la petición")
    result = service.refresh(refresh_token)
    _set_auth_cookies(response, result)
    return result.user


@router.patch("/change_password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    service: AuthServiceDep, payload: ChangePasswordRequest, user: CurrentUser
):
    """Cambia la contraseña del método local. Requiere autenticación."""
    service.change_password(user, payload.current_password, payload.new_password)
    return
