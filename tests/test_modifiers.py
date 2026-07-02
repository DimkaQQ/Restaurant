"""Menu item modifiers: option groups with price deltas. The server is the
source of truth for pricing — client-sent option ids are validated against
the item and deltas are applied server-side."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _setup(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=h)).json()["id"]
    item = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Капучино", "price": 1200}, headers=h
    )).json()
    return h, venue_id, item


async def test_set_and_list_modifiers(client: AsyncClient):
    h, venue_id, item = await _setup(client)
    resp = await client.put(f"/api/menu/{item['id']}/modifiers", headers=h, json=[
        {"name": "Размер", "required": True, "multi": False, "options": [
            {"name": "S", "price_delta": 0},
            {"name": "M", "price_delta": 200},
            {"name": "L", "price_delta": 400},
        ]},
        {"name": "Молоко", "required": False, "multi": False, "options": [
            {"name": "Овсяное", "price_delta": 300},
        ]},
    ])
    assert resp.status_code == 200, resp.text
    groups = resp.json()
    assert len(groups) == 2
    assert groups[0]["name"] == "Размер"
    assert len(groups[0]["options"]) == 3

    # groups come back embedded in the menu list (what POS/QR consume)
    menu = (await client.get(f"/api/menu/{venue_id}", headers=h)).json()
    assert menu[0]["modifier_groups"][0]["options"][2]["name"] == "L"


async def test_order_price_includes_modifier_deltas(client: AsyncClient):
    h, venue_id, item = await _setup(client)
    groups = (await client.put(f"/api/menu/{item['id']}/modifiers", headers=h, json=[
        {"name": "Размер", "required": True, "multi": False, "options": [
            {"name": "L", "price_delta": 400},
        ]},
        {"name": "Добавки", "required": False, "multi": True, "options": [
            {"name": "Овсяное молоко", "price_delta": 300},
        ]},
    ])).json()
    size_l = groups[0]["options"][0]["id"]
    oat = groups[1]["options"][0]["id"]

    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item["id"], "quantity": 2, "modifier_option_ids": [size_l, oat]}],
    })).json()
    # (1200 + 400 + 300) * 2 = 3800
    assert float(order["total_amount"]) == 3800.0
    assert order["items"][0]["modifiers"] == "L · Овсяное молоко"


async def test_foreign_modifier_option_rejected(client: AsyncClient):
    """An option id belonging to another item (or another tenant's item) must
    be rejected — otherwise a client could manipulate line pricing."""
    h, venue_id, item = await _setup(client)
    other = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Латте", "price": 1300}, headers=h
    )).json()
    groups = (await client.put(f"/api/menu/{other['id']}/modifiers", headers=h, json=[
        {"name": "Размер", "required": False, "multi": False, "options": [
            {"name": "XL", "price_delta": -1000},
        ]},
    ])).json()
    foreign_option = groups[0]["options"][0]["id"]

    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item["id"], "quantity": 1, "modifier_option_ids": [foreign_option]}],
    })
    assert resp.status_code == 400
