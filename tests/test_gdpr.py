"""GDPR-style data portability (owner self-service export) and tenant
deletion (platform-admin, typed-confirmation gated) — the privacy policy
promises both; this is the actual implementation."""
from httpx import AsyncClient
from sqlalchemy import select

from app.config import settings
from app.models.network import Network
from app.models.venue import Venue
from tests.conftest import register_network, auth_headers


async def test_owner_can_export_network_data(client: AsyncClient):
    reg = await register_network(client)
    await client.post("/api/venues/", json={"name": "Main Hall"}, headers=auth_headers(reg["token"]))

    resp = await client.get("/settings/api/export", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
    data = resp.json()
    assert data["network"]["slug"] == reg["slug"]
    assert len(data["venues"]) == 1
    assert data["venues"][0]["name"] == "Main Hall"


async def test_non_owner_cannot_export_network_data(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.post(
        "/settings/users",
        json={"email": "manager1@example.com", "password": "somesecurepass", "role": "manager"},
        headers=auth_headers(reg["token"]),
    )
    manager_login = await client.post("/auth/login", json={"email": "manager1@example.com", "password": "somesecurepass"})
    manager_token = manager_login.json()["access_token"]

    resp = await client.get("/settings/api/export", headers=auth_headers(manager_token))
    assert resp.status_code == 403


async def test_delete_network_requires_matching_slug(client: AsyncClient, db, monkeypatch):
    admin_reg = await register_network(client, name="Admin Net")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAIL", admin_reg["email"])
    target_reg = await register_network(client, name="Target Restaurant")
    network = (await db.execute(select(Network).where(Network.slug == target_reg["slug"]))).scalar_one()

    resp = await client.post(
        f"/platform/admin/delete-network/{network.id}",
        data={"confirm_slug": "wrong-slug"},
        headers=auth_headers(admin_reg["token"]),
    )
    assert resp.status_code == 400

    still_there = (await db.execute(select(Network).where(Network.id == network.id))).scalar_one_or_none()
    assert still_there is not None


async def test_delete_network_erases_all_tenant_data(client: AsyncClient, db, monkeypatch):
    admin_reg = await register_network(client, name="Admin Net 2")
    monkeypatch.setattr(settings, "PLATFORM_ADMIN_EMAIL", admin_reg["email"])
    target_reg = await register_network(client, name="Doomed Restaurant")
    network = (await db.execute(select(Network).where(Network.slug == target_reg["slug"]))).scalar_one()

    venue_resp = await client.post("/api/venues/", json={"name": "Doomed Hall"}, headers=auth_headers(target_reg["token"]))
    assert venue_resp.status_code == 200
    item_resp = await client.post(
        f"/api/menu/{venue_resp.json()['id']}", json={"name": "Burger", "price": 2500},
        headers=auth_headers(target_reg["token"]),
    )
    assert item_resp.status_code == 200

    resp = await client.post(
        f"/platform/admin/delete-network/{network.id}",
        data={"confirm_slug": target_reg["slug"]},
        headers=auth_headers(admin_reg["token"]),
    )
    assert resp.status_code == 200, resp.text

    gone = (await db.execute(select(Network).where(Network.id == network.id))).scalar_one_or_none()
    assert gone is None
    no_venues = (await db.execute(select(Venue).where(Venue.network_id == network.id))).scalars().all()
    assert no_venues == []

    # The admin's own network must be untouched.
    login_still_works = await client.post("/auth/login", json={"email": admin_reg["email"], "password": "supersecret123"})
    assert login_still_works.status_code == 200
