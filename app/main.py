from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.account_groups.router import router as account_groups_router
from app.accounts.router import router as accounts_router
from app.auth.router import router as auth_router
from app.categories.router import router as categories_router
from app.config import settings
from app.payment_plans.router import router as payment_plans_router
from app.shared.error_handlers import register_error_handlers
from app.shared.openapi_responses import VALIDATION_ERROR
from app.transactions.router import router as transactions_router

app = FastAPI(title="FinanzApp API", version="0.1.0")

# Unifica la forma de TODAS las respuestas de error (ver ARCHITECTURE.md §5.6).
register_error_handlers(app)

# Frontend y backend viven en dominios distintos: sin esto, el navegador
# bloquea toda petición hecha con fetch/XHR antes de que llegue aquí.
# allow_credentials=True es lo que permite que las cookies de sesión viajen
# en peticiones cross-site — exige un origen explícito en allow_origins, "*"
# no vale en cuanto se permiten credenciales (ver ARCHITECTURE.md §5.7).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Todas las rutas de negocio cuelgan de /api/v1. El prefijo se pone aquí, una
# sola vez, y no dentro de cada router (ver ARCHITECTURE.md §5.1).
#
# responses=VALIDATION_ERROR aquí, una sola vez para todos los routers en vez
# de en cada endpoint (ver openapi_responses.py).
app.include_router(auth_router, prefix="/api/v1", responses=VALIDATION_ERROR)
app.include_router(account_groups_router, prefix="/api/v1", responses=VALIDATION_ERROR)
app.include_router(accounts_router, prefix="/api/v1", responses=VALIDATION_ERROR)
app.include_router(categories_router, prefix="/api/v1", responses=VALIDATION_ERROR)
app.include_router(transactions_router, prefix="/api/v1", responses=VALIDATION_ERROR)
app.include_router(payment_plans_router, prefix="/api/v1", responses=VALIDATION_ERROR)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Comprobación de disponibilidad, sin autenticación ni lógica de negocio.

    La usa el healthcheck de Docker para saber si el contenedor está listo
    (ver ARCHITECTURE.md §5.8). No consulta la base de datos a propósito: mide
    si el proceso responde, no si sus dependencias están sanas.
    """
    return {"status": "ok"}
