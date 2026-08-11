from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from app.database import get_db

# Sesión de base de datos con alcance de una petición. La usan los módulos
# `dependencies.py` de cada dominio para construir sus repositorios; ningún
# router debería declararla directamente.
DbSession = Annotated[Session, Depends(get_db)]
