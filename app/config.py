from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configuración de la aplicación, leída del entorno al arrancar.

    Los campos sin valor por defecto son obligatorios: si falta uno, Pydantic
    lanza un error explícito durante el import y el proceso no llega a
    levantar. Es lo que queremos (ver ARCHITECTURE.md §4) — un default vacío
    dejaría, por ejemplo, firmar JWTs con SECRET_KEY="" sin que nadie se
    entere.
    """

    # Obligatorias.
    DATABASE_URL: str
    SECRET_KEY: str

    # Opcionales: tienen un valor por defecto razonable.
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    GOOGLE_CLIENT_ID: str = ""
    GOOGLE_CLIENT_SECRET: str = ""
    CORS_ALLOWED_ORIGINS: str = ""
    ENVIRONMENT: Literal["development", "production"] = "development"

    model_config = SettingsConfigDict(
        # Fuera de Docker, las variables se leen del .env. Dentro, las inyecta
        # Compose como variables de entorno reales, que tienen prioridad sobre
        # el fichero.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @property
    def cors_allowed_origins(self) -> list[str]:
        """CORS_ALLOWED_ORIGINS troceada por comas, lista para CORSMiddleware."""
        return [
            origin.strip()
            for origin in self.CORS_ALLOWED_ORIGINS.split(",")
            if origin.strip()
        ]

    @property
    def cookie_secure(self) -> bool:
        """Si las cookies de sesión exigen HTTPS.

        En producción todo el tráfico de la aplicación llega por HTTPS, así
        que una cookie de sesión no debe poder viajar por HTTP.
        """
        return self.ENVIRONMENT == "production"

    @property
    def cookie_samesite(self) -> Literal["lax"]:
        """Las cookies usan `Lax` porque frontend y API comparten site.

        "Site" no es lo mismo que "origen": en producción
        finanzapp.entramaes.com y api.finanzapp.entramaes.com comparten el
        dominio registrable y HTTPS; en desarrollo los puertos de localhost
        tampoco cambian el site. `Lax` permite las peticiones fetch/XHR entre
        esos orígenes y evita enviar las cookies en un contexto cross-site.
        """
        return "lax"

    @model_validator(mode="after")
    def validate_production_security(self) -> Self:
        """Impide arrancar producción con una sesión o CORS inseguros."""
        if self.ENVIRONMENT != "production":
            return self

        if len(self.SECRET_KEY) < 32:
            raise ValueError(
                "SECRET_KEY debe tener al menos 32 caracteres en producción"
            )

        origins = self.cors_allowed_origins
        if not origins:
            raise ValueError("CORS_ALLOWED_ORIGINS es obligatorio en producción")
        if len(origins) != len(set(origins)):
            raise ValueError(
                "CORS_ALLOWED_ORIGINS no puede contener orígenes repetidos"
            )

        for origin in origins:
            parsed = urlsplit(origin)
            if (
                parsed.scheme != "https"
                or not parsed.netloc
                or parsed.path
                or parsed.query
                or parsed.fragment
                or parsed.username is not None
                or parsed.password is not None
            ):
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS debe contener orígenes HTTPS exactos"
                )

        return self


# type: ignore silencia un falso positivo conocido de pydantic-settings: el
# type checker ve que DATABASE_URL y SECRET_KEY son obligatorios y exige
# pasarlos como argumentos, sin saber que BaseSettings los rellena desde el
# entorno y el .env en tiempo de ejecución. Si de verdad faltan, el error
# salta igual al arrancar (ValidationError), que es justo lo que queremos.
settings = Settings()  # type: ignore[call-arg]
