import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    """Representación pública de un usuario en las respuestas de la API.

    No es el modelo de SQLAlchemy: un modelo ORM no es un tipo válido de
    Pydantic (FastAPI no puede generar su esquema para /docs), y aunque lo
    fuera, exponer el modelo de persistencia directamente acopla el contrato
    HTTP a las columnas de la tabla. Hoy User no tiene campos sensibles, pero
    la capa de todos modos debe estar separada desde el principio.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    name: str
    created_at: datetime
    updated_at: datetime
