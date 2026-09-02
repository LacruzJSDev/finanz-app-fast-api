import asyncio
import json
from typing import cast

import pytest
from sqlalchemy.exc import IntegrityError
from starlette.requests import Request

from app.shared.error_handlers import integrity_error_handler


class DatabaseError(Exception):
    def __init__(self, sqlstate: str):
        self.sqlstate = sqlstate


def _integrity_error(sqlstate: str) -> IntegrityError:
    return IntegrityError("INSERT", {}, DatabaseError(sqlstate))


@pytest.mark.parametrize("sqlstate", ["23503", "23505", "23514", "23P01"])
def test_known_database_constraint_violations_use_the_conflict_contract(
    sqlstate: str,
) -> None:
    response = asyncio.run(
        integrity_error_handler(cast(Request, None), _integrity_error(sqlstate))
    )

    assert response.status_code == 409
    assert json.loads(bytes(response.body)) == {
        "error": {
            "code": "conflict",
            "message": "La operación entra en conflicto con el estado actual",
        }
    }


def test_unknown_database_error_is_not_misclassified_as_a_conflict() -> None:
    error = _integrity_error("22001")

    with pytest.raises(IntegrityError) as raised:
        asyncio.run(integrity_error_handler(cast(Request, None), error))

    assert raised.value is error
