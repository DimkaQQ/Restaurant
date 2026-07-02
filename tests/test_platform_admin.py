"""Platform-admin panel: gated by PLATFORM_ADMIN_EMAIL, must never leak to
tenants and must validate its own inputs (a typo'd status silently unblocking
a suspended tenant was one of the security-review findings)."""
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.models.audit_log import AdminAuditLog
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


async def test_subscription_update_is_written_to_audit_log(client: AsyncClient, db, monkeypatch):
    reg = await register_network(client)
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAIL", reg["email"])
    network = (await db.execute(select(Network).where(Network.slug == reg["slug"]))).scalar_one()

    resp = await client.post(
        f"/platform/admin/subscription/{network.id}",
        data={"plan": "pro", "status": "suspended", "reason": "chargeback"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code in (200, 303)

    entries = (await db.execute(
        select(AdminAuditLog).where(AdminAuditLog.network_id == network.id)
    )).scalars().all()
    assert len(entries) == 1
    assert entries[0].action == "subscription_update"
    assert entries[0].admin_email == reg["email"]
    assert "chargeback" in entries[0].detail


async def test_impersonate_logs_in_as_network_owner(client: AsyncClient, db, monkeypatch):
    admin_reg = await register_network(client, name="Admin Net")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAIL", admin_reg["email"])
    target_reg = await register_network(client, name="Target Restaurant")
    network = (await db.execute(select(Network).where(Network.slug == target_reg["slug"]))).scalar_one()

    resp = await client.post(
        f"/platform/admin/impersonate/{network.id}",
        headers=auth_headers(admin_reg["token"]),
        follow_redirects=False,
    )
    assert resp.status_code == 303
    assert "access_token" in resp.cookies

    entries = (await db.execute(
        select(AdminAuditLog).where(AdminAuditLog.network_id == network.id, AdminAuditLog.action == "impersonate")
    )).scalars().all()
    assert len(entries) == 1
    assert target_reg["email"] in entries[0].detail


async def test_audit_log_page_requires_admin(client: AsyncClient, monkeypatch):
    reg = await register_network(client)
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAIL", "someone-else@example.com")
    resp = await client.get("/platform/admin/audit", headers=auth_headers(reg["token"]))
    assert resp.status_code == 404
