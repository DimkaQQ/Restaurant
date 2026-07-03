"""Public queue board (TV screen) and the guest's live order status.
Both are unauthenticated by design; the board leaks only order numbers,
the status endpoint requires the unguessable order UUID."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _setup_with_order(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=h)).json()["id"]
    item_id = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Латте", "price": 1000}, headers=h
    )).json()["id"]
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}],
    })).json()
    return h, venue_id, order


async def test_queue_board_shows_numbers_only(client: AsyncClient):
    h, venue_id, order = await _setup_with_order(client)
    await client.patch(f"/api/orders/{order['id']}/status", json={"status": "confirmed"}, headers=h)

    page = await client.get(f"/queue/{venue_id}")
    assert page.status_code == 200

    data = (await client.get(f"/queue/{venue_id}/data")).json()
    short = order["id"][:8].upper()
    assert short in data["preparing"]
    assert data["ready"] == []
    # no item names or amounts leak
    assert "Латте" not in str(data)

    # advance to ready → moves columns
    await client.patch(f"/api/orders/{order['id']}/status", json={"status": "preparing"}, headers=h)
    await client.patch(f"/api/orders/{order['id']}/status", json={"status": "ready"}, headers=h)
    data = (await client.get(f"/queue/{venue_id}/data")).json()
    assert short in data["ready"]


async def test_guest_status_endpoint(client: AsyncClient):
    h, venue_id, order = await _setup_with_order(client)
    resp = await client.get(f"/order/{venue_id}/status/{order['id']}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "new"

    # wrong venue → 404 (no cross-venue probing)
    import uuid as _uuid
    resp = await client.get(f"/order/{_uuid.uuid4()}/status/{order['id']}")
    assert resp.status_code == 404
