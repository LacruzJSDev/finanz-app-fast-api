from typing import cast

import pytest
from starlette.requests import Request
from starlette.types import Scope

from app.config import settings
from app.shared.dependencies import ACCESS_TOKEN_COOKIE, require_trusted_origin
from app.shared.exceptions import ForbiddenError


def make_request(
    method: str, *, cookie: bool = False, origin: str | None = None
) -> Request:
    headers: list[tuple[bytes, bytes]] = []
    if cookie:
        headers.append((b"cookie", f"{ACCESS_TOKEN_COOKIE}=token".encode()))
    if origin is not None:
        headers.append((b"origin", origin.encode()))

    scope = cast(
        Scope,
        {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.3"},
            "http_version": "1.1",
            "method": method,
            "scheme": "https",
            "path": "/",
            "raw_path": b"/",
            "query_string": b"",
            "root_path": "",
            "headers": headers,
            "client": None,
            "server": None,
            "extensions": {},
            "state": {},
        },
    )
    return Request(scope)


@pytest.fixture(autouse=True)
def allowed_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        settings, "CORS_ALLOWED_ORIGINS", "https://finanzapp.entramaes.com"
    )


def test_allows_unsafe_request_without_authentication_cookie() -> None:
    require_trusted_origin(make_request("POST"))


def test_allows_safe_request_with_authentication_cookie() -> None:
    require_trusted_origin(make_request("GET", cookie=True))


def test_allows_authenticated_mutation_from_allowed_origin() -> None:
    require_trusted_origin(
        make_request("PATCH", cookie=True, origin="https://finanzapp.entramaes.com")
    )


@pytest.mark.parametrize("origin", [None, "https://attacker.example"])
def test_rejects_authenticated_mutation_without_trusted_origin(
    origin: str | None,
) -> None:
    with pytest.raises(ForbiddenError, match="Origen no permitido"):
        require_trusted_origin(make_request("DELETE", cookie=True, origin=origin))
