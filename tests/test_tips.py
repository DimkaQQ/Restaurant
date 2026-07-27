"""Gratuity (Square-style tips) on POS orders. Tips are stored separately from
total_amount so they never inflate revenue; cash tips land in the drawer and
are reflected in the shift's expected cash at close."""
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


async def test_tip_recorded_and_kept_out_of_total(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 2}],
        "payment_method": "card",
        "tip_amount": 150,
    })).json()
    # Goods total is untouched by the tip; the tip rides on top.
    assert float(order["total_amount"]) == 2000.0
    assert float(order["tip_amount"]) == 150.0


async def test_tip_defaults_to_zero(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
    })).json()
    assert float(order["tip_amount"]) == 0.0


async def test_negative_tip_rejected(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "tip_amount": -50,
    })
    assert resp.status_code == 422


async def test_cash_tip_folds_into_expected_drawer(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    # Open the shift so a cash sale can be reconciled.
    shift = (await client.post("/api/cash-shifts/open", headers=h, json={
        "venue_id": venue_id, "opening_cash": 0,
    })).json()["shift"]

    # Cash sale of 1000 goods + 100 tip.
    await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "payment_method": "cash",
        "tip_amount": 100,
    })

    closed = (await client.post(
        f"/api/cash-shifts/{shift['id']}/close", headers=h,
        json={"closing_cash_actual": 1100},
    )).json()["shift"]
    # Goods revenue only in cash_sales; the tip shows up in the drawer.
    assert float(closed["cash_sales"]) == 1000.0
    assert float(closed["expected_cash"]) == 1100.0
    assert float(closed["difference"]) == 0.0
