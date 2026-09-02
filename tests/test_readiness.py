from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import OperationalError

from app.main import app, readiness
from app.shared.exceptions import ServiceUnavailableError


def test_readiness_checks_postgresql_connection() -> None:
    connection = MagicMock()
    connection.__enter__.return_value = connection

    with patch("app.main.engine.connect", return_value=connection):
        assert readiness() == {"status": "ready"}

    connection.execute.assert_called_once()


def test_readiness_returns_service_unavailable_when_database_is_down() -> None:
    with patch(
        "app.main.engine.connect",
        side_effect=OperationalError("SELECT 1", {}, Exception("down")),
    ):
        with pytest.raises(
            ServiceUnavailableError, match="Base de datos no disponible"
        ):
            readiness()


def test_readiness_documents_service_unavailable_response() -> None:
    assert "503" in app.openapi()["paths"]["/ready"]["get"]["responses"]
