"""Platform-admin panel: gated by PLATFORM_ADMIN_EMAIL, must never leak to
tenants and must validate its own inputs (a typo'd status silently unblocking
a suspended tenant was one of the security-review findings)."""
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.models.network import Network
from app.models.subscription import Subscription
from tests.conftest import register_network, auth_headers


async def test_matching_admin_email_gets_access(client: AsyncClient, monkeypatch):
    reg = await register_network(client)
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAIL", reg["email"])

    resp = await client.get("/platform/admin", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
    assert reg["slug"] in resp.text


async def test_non_admin_email_still_gets_404_even_when_feature_enabled(client: AsyncClient, monkeypatch):
    reg = await register_network(client)
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAIL", "someone-else@example.com")

    resp = await client.get("/platform/admin", headers=auth_headers(reg["token"]))
    assert resp.status_code == 404


async def test_admin_can_update_subscription_plan_and_status(client: AsyncClient, db, monkeypatch):
    reg = await register_network(client)
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAIL", reg["email"])

    network = (await db.execute(select(Network).where(Network.slug == reg["slug"]))).scalar_one()

    resp = await client.post(
        f"/platform/admin/subscription/{network.id}",
        data={"plan": "pro", "status": "active"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code in (200, 303)

    await db.refresh(network)
    sub = (await db.execute(select(Subscription).where(Subscription.network_id == network.id))).scalar_one()
    assert sub.plan == "pro"
    assert sub.status == "active"


async def test_admin_rejects_invalid_plan_or_status(client: AsyncClient, db, monkeypatch):
    reg = await register_network(client)
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAIL", reg["email"])
    network = (await db.execute(select(Network).where(Network.slug == reg["slug"]))).scalar_one()

    resp = await client.post(
        f"/platform/admin/subscription/{network.id}",
        data={"plan": "pro", "status": "acctive"},  # typo — must not silently unblock a tenant
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 400
