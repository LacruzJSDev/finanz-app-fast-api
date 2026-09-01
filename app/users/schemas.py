import uuid
from datetime import datetime
from typing import Annotated, Self

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, model_validator

from app.shared.schemas import reject_explicit_nulls


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


def normalize_email(value: str) -> str:
    return value.strip().lower()


NormalizedEmail = Annotated[str, BeforeValidator(normalize_email)]


class UpdateUserRequest(BaseModel):
    """Cuerpo de PATCH /me"""

    name: str | None = Field(default=None)
    email: NormalizedEmail | None = Field(default=None)

    @model_validator(mode="after")
    def check_nulls(self) -> Self:
        # Ninguno es vaciable: ambas columnas son NOT NULL.
        reject_explicit_nulls(self, "name", "email")
        return self
