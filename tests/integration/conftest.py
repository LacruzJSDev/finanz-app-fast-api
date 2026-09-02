"""Infraestructura común para pruebas de integración con PostgreSQL."""

import os
from collections.abc import Generator

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection, Engine, make_url

from alembic import command
from app import db_registry
from app.config import settings
from app.database import Base


def _test_database_url() -> str:
    """Devuelve una URL segura para pruebas o salta la suite de integración.

    `TEST_DATABASE_URL` es intencionadamente distinta de la variable normal
    de la aplicación. Así ejecutar `pytest` no puede truncar por accidente la
    base de desarrollo: además de requerir esa señal explícita, el nombre de
    la base debe acabar en `_test` y coincidir con `DATABASE_URL`.
    """
    database_url = os.getenv("TEST_DATABASE_URL")
    if database_url is None:
        pytest.skip("falta TEST_DATABASE_URL; se omiten las pruebas de integración")

    test_url = make_url(database_url)
    configured_url = make_url(settings.DATABASE_URL)
    if test_url.get_backend_name() != "postgresql":
        raise pytest.UsageError("TEST_DATABASE_URL debe usar PostgreSQL")
    if test_url.database is None or not test_url.database.endswith("_test"):
        raise pytest.UsageError(
            "TEST_DATABASE_URL debe apuntar a una base acabada en _test"
        )
    if test_url != configured_url:
        raise pytest.UsageError(
            "DATABASE_URL y TEST_DATABASE_URL deben apuntar a la misma base aislada"
        )

    return database_url


def _truncate_all_tables(connection: Connection) -> None:
    """Vacía las tablas entre pruebas sin depender de su orden de claves foráneas."""
    # Importar db_registry registra todos los modelos antes de construir esta
    # lista. Los nombres proceden del propio metadata, no de datos de prueba.
    assert db_registry
    table_names = ", ".join(
        connection.dialect.identifier_preparer.quote(table.name)
        for table in Base.metadata.sorted_tables
    )
    connection.execute(text(f"TRUNCATE TABLE {table_names} RESTART IDENTITY CASCADE"))


@pytest.fixture(scope="session")
def migrated_database() -> Generator[Engine]:
    """Aplica todas las migraciones una vez y expone el motor de pruebas."""
    database_url = _test_database_url()
    command.upgrade(Config("alembic.ini"), "head")

    engine = create_engine(database_url, pool_pre_ping=True)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(migrated_database: Engine) -> Generator[None]:
    """Aísla cada caso de prueba y deja limpia la base al terminar."""
    with migrated_database.begin() as connection:
        _truncate_all_tables(connection)

    yield

    with migrated_database.begin() as connection:
        _truncate_all_tables(connection)
