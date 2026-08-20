from typing import Any

from app.config import settings

# En producción, Grafana Alloy recoge el stdout de cada contenedor y lo manda
# a Loki tal cual (ver entramaes-infra/monitoring/alloy/config.alloy) — no
# hace ningún parseo. Loguear JSON aquí es lo que permite filtrar por campo
# (status_code, logger, mensaje...) en Grafana con `| json`, en vez de solo
# buscar texto suelto. En desarrollo se mantiene el formato coloreado de
# Uvicorn, más legible en la terminal.
_JSON_FORMATTER: dict[str, Any] = {
    "()": "pythonjsonlogger.json.JsonFormatter",
    "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
}
_TEXT_FORMATTER: dict[str, Any] = {
    "()": "uvicorn.logging.DefaultFormatter",
    "fmt": "%(levelprefix)s %(message)s",
}


def build_log_config() -> dict[str, Any]:
    formatter = (
        _JSON_FORMATTER if settings.ENVIRONMENT == "production" else _TEXT_FORMATTER
    )
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {"default": formatter},
        "handlers": {
            "default": {
                "class": "logging.StreamHandler",
                "formatter": "default",
                "stream": "ext://sys.stdout",
            }
        },
        "loggers": {
            "uvicorn": {"handlers": ["default"], "level": "INFO", "propagate": False},
            "uvicorn.error": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "uvicorn.access": {
                "handlers": ["default"],
                "level": "INFO",
                "propagate": False,
            },
            "app": {"handlers": ["default"], "level": "INFO", "propagate": False},
        },
        "root": {"handlers": ["default"], "level": "INFO"},
    }
