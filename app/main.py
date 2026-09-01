from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.account_groups.router import router as account_groups_router
from app.accounts.router import router as accounts_router
from app.auth.router import router as auth_router
from app.budgets.router import router as budgets_router
from app.categories.router import router as categories_router
from app.config import settings
from app.payment_plans.router import group_router as payment_plans_group_router
from app.payment_plans.router import router as payment_plans_router
from app.shared.error_handlers import register_error_handlers
from app.shared.openapi_responses import VALIDATION_ERROR
from app.transactions.router import query_router as transactions_query_router
from app.transactions.router import router as transactions_router
from app.users.router import router as users_router

# /docs, /redoc y /openapi.json solo en desarrollo: exponerlos en producción
# publica la forma completa de la API (rutas, modelos, nombres de campos) a
# cualquiera en internet. El frontend genera sus tipos a partir de ellos en
# tiempo de build, no los necesita en caliente contra producción.
_docs_enabled = settings.ENVIRONMENT != "production"
app = FastAPI(
    title="FinanzApp API",
    version="0.1.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

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
app.include_router(users_router, prefix="/api/v1", responses=VALIDATION_ERROR)

# Routers de consulta y agregados (ARCHITECTURE.md §8.3). Van aparte de los de
# CRUD porque un APIRouter solo admite un prefijo, y estos cuelgan del grupo,
# no de la cuenta.
app.include_router(
    transactions_query_router, prefix="/api/v1", responses=VALIDATION_ERROR
)
app.include_router(
    payment_plans_group_router, prefix="/api/v1", responses=VALIDATION_ERROR
)
app.include_router(budgets_router, prefix="/api/v1", responses=VALIDATION_ERROR)


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    """Comprobación de disponibilidad, sin autenticación ni lógica de negocio.

    La usa el healthcheck de Docker para saber si el contenedor está listo
    (ver ARCHITECTURE.md §5.8). No consulta la base de datos a propósito: mide
    si el proceso responde, no si sus dependencias están sanas.
    """
    return {"status": "ok"}
