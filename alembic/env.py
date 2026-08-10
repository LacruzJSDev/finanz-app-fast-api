from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

import app.db_registry
from alembic import context
from app.config import settings
from app.database import Base

# Importar db_registry hace que todos los modelos se registren en
# Base.metadata. Sin esto, --autogenerate solo vería los modelos que alguien
# haya importado por casualidad y propondría borrar el resto de tablas.
# El `assert` está solo para que ruff no marque el import como no usado.
assert app.db_registry

config = context.config

# La URL no vive en alembic.ini, sino en la configuración de la aplicación:
# así hay una única fuente de verdad y el fichero .ini no contiene la
# contraseña de la base de datos.
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

# compare_type y compare_server_default afectan a lo que --autogenerate es
# capaz de detectar. Por defecto Alembic solo ve tablas y columnas nuevas o
# eliminadas; estas dos añaden los cambios de tipo (VARCHAR(100) ->
# VARCHAR(200)) y de valor por defecto del servidor.
#
# Van escritas a mano en cada llamada en vez de en un dict con **kwargs: al
# desempaquetar un dict[str, bool], el type checker asume que cualquier
# parámetro de configure() podría recibir un bool y protesta por `connection`.


def run_migrations_offline() -> None:
    """Genera el SQL de las migraciones sin conectarse a la base de datos."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica las migraciones contra la base de datos."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
