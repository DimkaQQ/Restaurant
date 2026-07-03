"""Cash register shifts: the Z-report snapshot (cash/card sales, expected
drawer vs actual recount) is the owner's primary anti-theft control."""
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


async def test_open_close_shift_z_report(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)

    resp = await client.post("/api/cash-shifts/open", headers=h, json={
        "venue_id": venue_id, "opening_cash": 5000,
    })
    assert resp.status_code == 200, resp.text
    shift_id = resp.json()["shift"]["id"]

    # one cash and one card sale during the shift
    await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 2}],
        "payment_method": "cash",
    })
    await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}],
        "payment_method": "card",
    })

    # drawer recount is 500 short
    resp = await client.post(f"/api/cash-shifts/{shift_id}/close", headers=h, json={
        "closing_cash_actual": 6500,
    })
    assert resp.status_code == 200, resp.text
    z = resp.json()["shift"]
    assert z["cash_sales"] == 2000.0
    assert z["card_sales"] == 1000.0
    assert z["orders_count"] == 2
    assert z["expected_cash"] == 7000.0   # 5000 float + 2000 cash sales
    assert z["difference"] == -500.0


async def test_double_open_rejected(client: AsyncClient):
    h, venue_id, _ = await _setup(client)
    assert (await client.post("/api/cash-shifts/open", headers=h, json={
        "venue_id": venue_id, "opening_cash": 0,
    })).status_code == 200
    resp = await client.post("/api/cash-shifts/open", headers=h, json={
        "venue_id": venue_id, "opening_cash": 0,
    })
    assert resp.status_code == 400


async def test_shift_scoped_to_accessible_venues(client: AsyncClient):
    h1, venue_id, _ = await _setup(client)
    reg2 = await register_network(client)
    h2 = auth_headers(reg2["token"])
    resp = await client.post("/api/cash-shifts/open", headers=h2, json={
        "venue_id": venue_id, "opening_cash": 0,
    })
    assert resp.status_code == 403
