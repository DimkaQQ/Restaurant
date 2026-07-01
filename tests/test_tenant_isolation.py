"""One tenant must never be able to read or write another tenant's data.
This is the exact class of bug the security review found (cross-network
telegram_id lookups) — these tests guard against that regressing."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _create_venue(client: AsyncClient, token: str, name: str = "Venue A") -> str:
    resp = await client.post(
        "/api/venues/", json={"name": name, "address": "Test St 1"}, headers=auth_headers(token)
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def test_owner_cannot_list_another_networks_venues(client: AsyncClient):
    net_a = await register_network(client, "Network A")
    net_b = await register_network(client, "Network B")

    venue_a_id = await _create_venue(client, net_a["token"], "Venue A")
    await _create_venue(client, net_b["token"], "Venue B")

    resp = await client.get("/api/venues/", headers=auth_headers(net_a["token"]))
    assert resp.status_code == 200
    venue_ids = [v["id"] for v in resp.json()]
    assert venue_a_id in venue_ids
    assert len(venue_ids) == 1  # never sees Network B's venue


async def test_owner_cannot_patch_another_networks_venue(client: AsyncClient):
    net_a = await register_network(client, "Network A")
    net_b = await register_network(client, "Network B")

    venue_b_id = await _create_venue(client, net_b["token"], "Venue B")

    resp = await client.patch(
        f"/api/venues/{venue_b_id}",
        json={"name": "Hijacked"},
        headers=auth_headers(net_a["token"]),
    )
    assert resp.status_code == 404


async def test_menu_item_creation_scoped_to_own_venue(client: AsyncClient):
    net_a = await register_network(client, "Network A")
    net_b = await register_network(client, "Network B")
    venue_b_id = await _create_venue(client, net_b["token"], "Venue B")

    # Network A's owner tries to create a menu item on Network B's venue
    resp = await client.post(
        f"/api/menu/{venue_b_id}",
        json={"name": "Stolen Pizza", "price": 1000},
        headers=auth_headers(net_a["token"]),
    )
    assert resp.status_code in (403, 404)


async def test_guest_history_requires_bot_secret(client: AsyncClient):
    """Regression test: this endpoint used to have NO auth at all and leaked
    order history to anyone who supplied a telegram_id."""
    resp = await client.get(
        "/api/orders/guest/history",
        params={"telegram_id": 123456789, "network_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 403


async def test_platform_admin_hidden_without_configured_email(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.get("/platform/admin", headers=auth_headers(reg["token"]))
    # PLATFORM_ADMIN_EMAIL isn't set in the test environment, so this must 404
    # (never leak the existence of the admin panel or any tenant's data).
    assert resp.status_code == 404
