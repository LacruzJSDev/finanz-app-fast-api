from collections.abc import Generator

from sqlalchemy import MetaData, create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

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
Base = declarative_base(metadata=MetaData(naming_convention=naming_convention))


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
