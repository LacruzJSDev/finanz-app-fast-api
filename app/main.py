from fastapi import FastAPI

from app.auth.router import router as auth_router
from app.shared.error_handlers import register_error_handlers

app = FastAPI(title="FinanzApp API", version="0.1.0")

# Unifica la forma de TODAS las respuestas de error (ver ARCHITECTURE.md §5.6).
register_error_handlers(app)

# Todas las rutas de negocio cuelgan de /api/v1. El prefijo se pone aquí, una
# sola vez, y no dentro de cada router (ver ARCHITECTURE.md §5.1).
app.include_router(auth_router, prefix="/api/v1")


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Comprobación de disponibilidad, sin autenticación ni lógica de negocio.

    La usa el healthcheck de Docker para saber si el contenedor está listo
    (ver ARCHITECTURE.md §5.8). No consulta la base de datos a propósito: mide
    si el proceso responde, no si sus dependencias están sanas.
    """
    return {"status": "ok"}
