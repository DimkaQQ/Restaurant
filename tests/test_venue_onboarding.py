"""A freshly registered network has zero venues, and the owner must be able
to create the first one entirely through the UI/API — no direct DB access.
This is the actual "launch in 15 minutes, no engineers" onboarding path."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def test_fresh_network_has_no_venues(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.get("/api/venues/", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
    assert resp.json() == []


async def test_settings_venues_page_shows_create_form_when_empty(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.get("/settings/venues", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
    assert "new-venue-name" in resp.text
    assert "createVenue" in resp.text


async def test_owner_can_create_first_venue_via_api(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.post(
        "/api/venues/",
        json={"name": "Кофейня на Абая", "address": "ул. Абая 10"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Кофейня на Абая"

    listed = await client.get("/api/venues/", headers=auth_headers(reg["token"]))
    assert len(listed.json()) == 1
