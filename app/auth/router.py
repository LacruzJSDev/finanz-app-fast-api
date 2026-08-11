from fastapi import APIRouter, Request, Response, status

from app.auth.dependencies import AuthServiceDep
from app.auth.schemas import LoginRequest, RegisterRequest
from app.auth.service import AuthResult
from app.config import settings
from app.shared.exceptions import UnauthorizedError
from app.users.schemas import UserRead

# El prefijo aquí es solo el del dominio. La versión (/api/v1) la pone main.py
# al montar el router, para que cambiarla sea tocar una línea y no doce.
router = APIRouter(prefix="/auth", tags=["auth"])

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"


def _set_auth_cookies(response: Response, result: AuthResult) -> None:
    """Pone los dos tokens como cookies httpOnly, nunca en el cuerpo JSON.

    httpOnly impide que cualquier JavaScript (el tuyo o el de un XSS colado)
    lea el valor de la cookie — el navegador la adjunta solo, la aplicación
    cliente nunca la toca.

    El refresh token se restringe a /api/v1/auth con `path`: el navegador
    solo lo adjunta en peticiones bajo ese prefijo, así que no viaja en cada
    llamada a la API como sí hace el access token — no lo necesita para nada
    salvo /refresh y /logout.

    secure/samesite salen de Settings (dev vs producción, ver app/config.py):
    en producción front y back son dominios distintos de verdad, y eso exige
    SameSite=None + Secure; en local, con todo bajo localhost, Lax basta y
    permite probar sin HTTPS.
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
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token is None:
        raise UnauthorizedError("Refresh token no presente en la petición")
    service.logout(refresh_token)
    _delete_auth_cookies(response)
    return


@router.post("/refresh")
def refresh(service: AuthServiceDep, request: Request, response: Response):
    """Refresca el token y lo rota."""
    refresh_token = request.cookies.get("refresh_token")
    if refresh_token is None:
        raise UnauthorizedError("Refresh token no presente en la petición")
    result = service.refresh(refresh_token)
    _set_auth_cookies(response, result)
    return result.user
