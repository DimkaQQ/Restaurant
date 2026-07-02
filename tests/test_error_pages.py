"""Branded 404/500 pages instead of raw framework JSON — previously an
unknown URL or an unhandled bug showed a bare {"detail": "Not Found"} even
to a browser, and there was no safety net for genuinely unexpected
exceptions at all (they'd have propagated as a raw 500 traceback)."""
from httpx import AsyncClient, ASGITransport
from fastapi import APIRouter

from app.main import app
from tests.conftest import register_network, auth_headers


async def test_unknown_html_route_shows_branded_404(client: AsyncClient):
    resp = await client.get("/this-page-does-not-exist", headers={"Accept": "text/html"})
    assert resp.status_code == 404
    assert "404" in resp.text
    assert "RestOS" in resp.text


async def test_unknown_api_route_returns_json_404(client: AsyncClient):
    resp = await client.get("/this-route-does-not-exist", headers={"Accept": "application/json"})
    assert resp.status_code == 404
    assert resp.json()["detail"]


async def test_existing_api_404_still_returns_expected_detail(client: AsyncClient):
    """A route-raised HTTPException(404, detail="...") must still carry its
    own message through unchanged — only truly-unhandled paths get the
    generic branded/JSON fallback."""
    reg = await register_network(client)
    import uuid
    resp = await client.get(f"/api/orders/{uuid.uuid4()}", headers=auth_headers(reg["token"]))
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Заказ не найден"


async def test_unhandled_exception_returns_json_for_api_clients():
    """Simulate a genuine bug (unhandled exception) in a route and confirm
    the global handler catches it instead of leaking a raw traceback.

    Uses a dedicated client with raise_app_exceptions=False: httpx's
    ASGITransport re-raises any exception that reaches the ASGI boundary by
    default (useful for catching bugs during testing) even after Starlette's
    ServerErrorMiddleware has already sent a response — real ASGI servers
    like uvicorn don't do this, they just use the response that was sent.
    """
    boom_router = APIRouter()

    @boom_router.get("/api/__test_boom")
    async def boom():
        raise RuntimeError("simulated unexpected failure")

    app.include_router(boom_router)
    try:
        transport = ASGITransport(app=app, raise_app_exceptions=False)
        async with AsyncClient(transport=transport, base_url="http://test") as boom_client:
            resp = await boom_client.get("/api/__test_boom", headers={"Accept": "application/json"})
        assert resp.status_code == 500
        assert resp.json()["detail"]
    finally:
        app.router.routes = [r for r in app.router.routes if getattr(r, "path", None) != "/api/__test_boom"]
