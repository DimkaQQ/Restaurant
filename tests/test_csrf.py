"""CSRF defense: cookie-authenticated (no Authorization header) unsafe
requests must present an Origin/Referer matching this deployment. Disabled
globally in conftest.py (httpx's test client doesn't simulate a browser's
automatic Origin header), so it's flipped back on just here."""
import pytest
from httpx import AsyncClient, ASGITransport

from app.config import settings
from app.main import app
from tests.conftest import register_network


@pytest.fixture(autouse=True)
def _enable_csrf():
    settings.CSRF_ENABLED = True
    yield
    settings.CSRF_ENABLED = False


async def _cookie_client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def test_cookie_authenticated_mutation_without_origin_is_rejected():
    async with await _cookie_client() as client:
        reg_resp = await client.post("/auth/register", json={
            "name": "CSRF Test", "slug": "csrf-test-1", "email": "csrf1@example.com", "password": "supersecret123",
        })
        assert reg_resp.status_code == 200
        # No Authorization header, no Origin/Referer — cookie jar carries
        # access_token automatically, simulating a forged cross-site request.
        resp = await client.post("/api/venues/", json={"name": "Forged Venue"})
        assert resp.status_code == 403


async def test_cookie_authenticated_mutation_with_matching_origin_succeeds():
    async with await _cookie_client() as client:
        await client.post("/auth/register", json={
            "name": "CSRF Test 2", "slug": "csrf-test-2", "email": "csrf2@example.com", "password": "supersecret123",
        })
        resp = await client.post(
            "/api/venues/", json={"name": "Legit Venue"}, headers={"Origin": settings.PUBLIC_URL}
        )
        assert resp.status_code == 200


async def test_bearer_authenticated_mutation_skips_origin_check():
    """Authorization-header auth can't be forged cross-site (a remote page
    can't read our httpOnly cookie or another origin's localStorage), so it's
    exempt from the Origin check even with no Origin header at all."""
    from tests.conftest import auth_headers
    async with await _cookie_client() as client:
        reg = await register_network(client, name="CSRF Bearer")
        resp = await client.post("/api/venues/", json={"name": "Bearer Venue"}, headers=auth_headers(reg["token"]))
        assert resp.status_code == 200

async def test_origin_matching_request_host_succeeds_even_if_public_url_differs():
    """The bug that hit real deployments: PUBLIC_URL left at its default
    (localhost:8000) while the site is opened via IP/domain. Same-origin is
    now judged against the request's own Host too, so a browser POST with
    Origin == Host must pass regardless of PUBLIC_URL."""
    async with await _cookie_client() as client:
        await client.post("/auth/register", json={
            "name": "CSRF Test 3", "slug": "csrf-test-3", "email": "csrf3@example.com", "password": "supersecret123",
        })
        # base_url is http://test → Host: test; PUBLIC_URL stays localhost:8000
        resp = await client.post(
            "/api/venues/", json={"name": "Host Venue"}, headers={"Origin": "http://test"}
        )
        assert resp.status_code == 200


async def test_cross_site_origin_still_rejected():
    async with await _cookie_client() as client:
        await client.post("/auth/register", json={
            "name": "CSRF Test 4", "slug": "csrf-test-4", "email": "csrf4@example.com", "password": "supersecret123",
        })
        resp = await client.post(
            "/api/venues/", json={"name": "Evil Venue"}, headers={"Origin": "http://evil.example.com"}
        )
        assert resp.status_code == 403
