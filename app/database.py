import enum
from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


def enum_values(enum_class: type[enum.Enum]) -> list[str]:
    """Devuelve los VALORES de una enumeración, para `Enum(values_callable=...)`.

    Por defecto SQLAlchemy guardaría en Postgres los NOMBRES de los miembros
    ('LOCAL'), no sus valores ('local').

    Función con nombre y no lambda: `values_callable` recibe su parámetro como
    Any, y los parámetros de una lambda no se pueden anotar.
    """
    return [str(member.value) for member in enum_class]


# Plantillas de nombre para índices y restricciones. Sin esto, Postgres asigna
# nombres automáticos que Alembic no sabe reproducir, y un `downgrade` que
# necesite borrar una restricción no encuentra cómo referirse a ella.
naming_convention = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

engine = create_engine(
    settings.DATABASE_URL,
    # Comprueba que la conexión sigue viva antes de reutilizarla del pool. En
    # Docker la base puede reiniciarse por debajo y dejar conexiones muertas en
    # el pool; sin esto, la siguiente petición fallaría con un error de socket.
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    # declarative_base() (la función clásica) no tiene tipado propio: pyright
    # la ve como Any, y con ella cualquier modelo que herede de Base —
    # User, AccountGroup...— arrastra ese Any, silenciando comprobaciones
    # como pasar un Modelo | None donde se espera un Modelo. DeclarativeBase
    # es la clase tipada equivalente desde SQLAlchemy 2.0.
    metadata = MetaData(naming_convention=naming_convention)


def get_db() -> Generator[Session, None, None]:
    """Sesión de base de datos con alcance de una petición HTTP.

    Se usa como dependencia de FastAPI:

        @router.get("/items")
        def read_items(db: Session = Depends(get_db)):
            ...

    El `commit` ocurre una sola vez, al terminar la petición sin errores;
    cualquier excepción no controlada revierte todos los cambios de esa
    petición. Por eso la capa de repositorio nunca hace commit por su cuenta:
    la unidad de trabajo es la petición completa (ver ARCHITECTURE.md §3).
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
