"""The dashboard shows a step-by-step "quick start" checklist for owners
who haven't finished setup, and hides it once everything is done — this is
the guided-onboarding UX (find a venue, add a menu, invite staff, etc.)."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def test_fresh_owner_sees_onboarding_checklist(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.get("/dashboard", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
    assert "Быстрый старт" in resp.text
    assert "0 / 5" in resp.text


async def test_checklist_progress_updates_after_creating_venue(client: AsyncClient):
    reg = await register_network(client)
    await client.post("/api/venues/", json={"name": "Main Hall"}, headers=auth_headers(reg["token"]))

    resp = await client.get("/dashboard", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
    assert "1 / 5" in resp.text


async def test_non_owner_never_sees_onboarding_checklist(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.post(
        "/settings/users",
        json={"email": "staffer@example.com", "password": "StaffPass123!", "role": "manager"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200
    staff_login = await client.post("/auth/login", json={"email": "staffer@example.com", "password": "StaffPass123!"})
    staff_token = staff_login.json()["access_token"]

    resp = await client.get("/dashboard", headers=auth_headers(staff_token))
    assert resp.status_code == 200
    assert "Быстрый старт" not in resp.text
