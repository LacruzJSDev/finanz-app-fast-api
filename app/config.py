from typing import Literal

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
    ENVIRONMENT: str = "development"

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

        Frontend y backend viven en dominios distintos (no solo puertos
        distintos de localhost), así que en producción la cookie es
        cross-site de verdad, y los navegadores exigen `Secure` en cuanto
        `SameSite=None` — sin HTTPS, el navegador la descarta en silencio.
        """
        return self.ENVIRONMENT == "production"

    @property
    def cookie_samesite(self) -> Literal["lax", "none"]:
        """`none` en producción (cross-site real); `lax` en desarrollo.

        "Site" no es lo mismo que "origen": dos servicios en `localhost` con
        puertos distintos (típico en desarrollo: Vite en :5173, la API en
        :8000) siguen siendo el MISMO site, así que `lax` ya deja pasar la
        cookie en peticiones fetch/XHR sin necesitar `Secure` ni HTTPS local.
        En producción, con dominios registrables distintos de verdad,
        `SameSite=Lax` bloquearía la cookie y hace falta `none` (+ Secure).
        """
        return "none" if self.ENVIRONMENT == "production" else "lax"


# type: ignore silencia un falso positivo conocido de pydantic-settings: el
# type checker ve que DATABASE_URL y SECRET_KEY son obligatorios y exige
# pasarlos como argumentos, sin saber que BaseSettings los rellena desde el
# entorno y el .env en tiempo de ejecución. Si de verdad faltan, el error
# salta igual al arrancar (ValidationError), que es justo lo que queremos.
settings = Settings()  # type: ignore[call-arg]
