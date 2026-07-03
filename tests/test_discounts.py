"""Staff discounts and guest promo codes. Amounts are recomputed
server-side; promo validity (active/expiry/usage cap) is enforced there too."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _setup(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=h)).json()["id"]
    item_id = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Латте", "price": 1000}, headers=h
    )).json()["id"]
    return h, venue_id, item_id


async def test_percent_discount_recomputed_server_side(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 2}],
        "discount_type": "percent",
        "discount_value": 10,
    })).json()
    assert float(order["subtotal_amount"]) == 2000.0
    assert float(order["total_amount"]) == 1800.0


async def test_amount_discount_capped_at_subtotal(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "discount_type": "amount",
        "discount_value": 5000,
    })).json()
    assert float(order["total_amount"]) == 0.0


async def test_discount_over_100_percent_rejected(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "discount_type": "percent",
        "discount_value": 150,
    })
    assert resp.status_code == 400


async def test_promo_code_applies_and_counts_usage(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    resp = await client.post("/settings/api/promos", headers=h, json={
        "code": "welcome10", "type": "percent", "value": 10, "max_uses": 1,
    })
    assert resp.status_code == 200, resp.text

    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "promo_code": "WELCOME10",
    })).json()
    assert float(order["total_amount"]) == 900.0
    assert order["promo_code"] == "WELCOME10"

    # usage cap reached — second use rejected
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "promo_code": "WELCOME10",
    })
    assert resp.status_code == 400


async def test_inactive_promo_rejected(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    created = (await client.post("/settings/api/promos", headers=h, json={
        "code": "OFF", "type": "amount", "value": 100,
    })).json()
    await client.patch(f"/settings/api/promos/{created['id']}", headers=h)  # toggle off

    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "promo_code": "OFF",
    })
    assert resp.status_code == 400


async def test_promo_scoped_to_network(client: AsyncClient):
    """Another tenant's promo code must not apply."""
    h1, venue_id, item_id = await _setup(client)
    reg2 = await register_network(client)
    h2 = auth_headers(reg2["token"])
    await client.post("/settings/api/promos", headers=h2, json={
        "code": "THEIRS", "type": "percent", "value": 50,
    })

    resp = await client.post("/api/pos/order", headers=h1, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "promo_code": "THEIRS",
    })
    assert resp.status_code == 400
