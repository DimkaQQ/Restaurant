"""Print-friendly receipt/kitchen-ticket page."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def test_receipt_renders_for_own_order(client: AsyncClient):
    reg = await register_network(client)
    venue_resp = await client.post("/api/venues/", json={"name": "Hall"}, headers=auth_headers(reg["token"]))
    venue_id = venue_resp.json()["id"]
    item_resp = await client.post(
        f"/api/menu/{venue_id}", json={"name": "Burger", "price": 2500}, headers=auth_headers(reg["token"])
    )
    item_id = item_resp.json()["id"]
    order_resp = await client.post(
        "/api/pos/order",
        json={"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 2}]},
        headers=auth_headers(reg["token"]),
    )
    order_id = order_resp.json()["id"]

    resp = await client.get(f"/orders/{order_id}/receipt", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
    assert "Burger" in resp.text
    assert "5,000" in resp.text or "5000" in resp.text


async def test_receipt_404s_for_another_networks_order(client: AsyncClient):
    reg1 = await register_network(client)
    venue_resp = await client.post("/api/venues/", json={"name": "Hall"}, headers=auth_headers(reg1["token"]))
    venue_id = venue_resp.json()["id"]
    item_resp = await client.post(
        f"/api/menu/{venue_id}", json={"name": "Burger", "price": 2500}, headers=auth_headers(reg1["token"])
    )
    item_id = item_resp.json()["id"]
    order_resp = await client.post(
        "/api/pos/order",
        json={"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}]},
        headers=auth_headers(reg1["token"]),
    )
    order_id = order_resp.json()["id"]

    reg2 = await register_network(client)
    resp = await client.get(f"/orders/{order_id}/receipt", headers=auth_headers(reg2["token"]))
    assert resp.status_code == 404
