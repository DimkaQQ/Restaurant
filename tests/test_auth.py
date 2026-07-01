import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.subscription import Subscription
from app.models.network import Network
from tests.conftest import register_network, auth_headers


async def test_register_creates_network_and_trial_subscription(client: AsyncClient, db):
    reg = await register_network(client)

    network = (await db.execute(select(Network).where(Network.slug == reg["slug"]))).scalar_one()
    sub = (await db.execute(
        select(Subscription).where(Subscription.network_id == network.id)
    )).scalar_one()

    assert sub.status == "trial"
    assert sub.plan == "starter"
    assert sub.trial_ends_at is not None


async def test_register_rejects_short_password(client: AsyncClient):
    resp = await client.post("/auth/register", json={
        "name": "Short PW",
        "slug": "short-pw-test",
        "email": "shortpw@example.com",
        "password": "abc123",
    })
    assert resp.status_code == 422


async def test_login_with_wrong_password_fails(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.post("/auth/login", json={
        "email": reg["email"],
        "password": "wrong-password",
    })
    assert resp.status_code == 401


async def test_login_with_correct_password_succeeds(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.post("/auth/login", json={
        "email": reg["email"],
        "password": "supersecret123",
    })
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_dashboard_requires_auth(client: AsyncClient):
    resp = await client.get("/dashboard")
    assert resp.status_code in (401, 307)


async def test_dashboard_accessible_with_token(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.get("/dashboard", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
