import asyncio

from httpx import ASGITransport, AsyncClient, Response

from app.main import app


async def post_logout_with_refresh_cookie() -> Response:
    """Llama a una mutación protegida sin necesitar una base de datos."""
    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://testserver",
        cookies={"refresh_token": "x"},
    ) as client:
        return await client.post("/api/v1/auth/logout")


def test_router_rejects_cookie_mutation_without_origin() -> None:
    response = asyncio.run(post_logout_with_refresh_cookie())

    assert response.status_code == 403
    assert response.json() == {
        "error": {"code": "forbidden", "message": "Origen no permitido"}
    }
