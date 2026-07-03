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


async def test_sales_csv_export(client: AsyncClient):
    """The accountant's CSV export: paid orders with discount columns,
    utf-8-sig so Russian Excel opens it with a double click."""
    h, venue_id, item_id = await _setup(client)
    await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}],
        "payment_method": "cash",
    })
    resp = await client.get("/finance/export/sales.csv?period=month", headers=h)
    assert resp.status_code == 200
    assert "text/csv" in resp.headers["content-type"]
    body = resp.text
    assert "Дата оплаты" in body
    assert "Латте x1" in body


async def test_food_cost_on_analytics_page(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    # ingredient 200₸/unit, recipe uses 2 units → cost 400 on a 1000₸ item = 60% margin
    ing = (await client.post("/api/inventory", headers=h, json={
        "venue_id": venue_id, "name": "Молоко", "unit": "л",
        "quantity": 10, "min_quantity": 1, "cost_per_unit": 200,
    })).json()
    await client.put(f"/api/menu/{item_id}/recipe", headers=h, json=[
        {"ingredient_id": ing["id"], "quantity": 2},
    ])
    resp = await client.get("/analytics/", headers=h)
    assert resp.status_code == 200
    assert "Меню-инжиниринг" in resp.text
    assert "60.0%" in resp.text
