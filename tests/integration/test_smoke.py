"""Comprobaciones mínimas del camino real aplicación + migraciones + Postgres."""

import asyncio

import pytest
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from httpx import ASGITransport, AsyncClient, Response
from sqlalchemy.engine import Engine

from app.main import app

pytestmark = pytest.mark.integration


async def _request_health() -> Response:
    """Llama a la aplicación ASGI sin abrir un puerto de red local."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        return await client.get("/health")


def test_database_is_at_alembic_head(migrated_database: Engine) -> None:
    """El entorno de integración se crea exclusivamente desde migraciones."""
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    with migrated_database.connect() as connection:
        current_revision = MigrationContext.configure(connection).get_current_revision()

    assert current_revision == script.get_current_head()


def test_health_endpoint_responds(migrated_database: Engine) -> None:
    """La aplicación importada con la configuración de pruebas responde por HTTP."""
    response = asyncio.run(_request_health())

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
