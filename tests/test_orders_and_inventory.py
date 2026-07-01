"""End-to-end coverage of order lifecycle, recipe-based auto stock deduction,
and table status sync (POS features added this project phase)."""
from decimal import Decimal

from httpx import AsyncClient
from sqlalchemy import select

from app.models.inventory import Ingredient
from app.models.table import Table
from tests.conftest import register_network, auth_headers


async def _setup_venue_menu_ingredient(client: AsyncClient, token: str):
    venue_resp = await client.post(
        "/api/venues/", json={"name": "Main Hall"}, headers=auth_headers(token)
    )
    venue_id = venue_resp.json()["id"]

    ing_resp = await client.post(
        "/api/inventory",
        json={"venue_id": venue_id, "name": "Buns", "unit": "шт", "quantity": 100, "min_quantity": 10},
        headers=auth_headers(token),
    )
    assert ing_resp.status_code == 200, ing_resp.text
    ingredient_id = ing_resp.json()["id"]

    item_resp = await client.post(
        f"/api/menu/{venue_id}",
        json={"name": "Burger", "price": 2500},
        headers=auth_headers(token),
    )
    assert item_resp.status_code == 200, item_resp.text
    item_id = item_resp.json()["id"]

    recipe_resp = await client.put(
        f"/api/menu/{item_id}/recipe",
        json=[{"ingredient_id": ingredient_id, "quantity": 2}],
        headers=auth_headers(token),
    )
    assert recipe_resp.status_code == 200, recipe_resp.text

    return venue_id, item_id, ingredient_id


async def test_pos_order_deducts_ingredient_stock_on_completion(client: AsyncClient, db):
    reg = await register_network(client)
    venue_id, item_id, ingredient_id = await _setup_venue_menu_ingredient(client, reg["token"])

    order_resp = await client.post(
        "/api/pos/order",
        json={"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 3}]},
        headers=auth_headers(reg["token"]),
    )
    assert order_resp.status_code == 200, order_resp.text
    order = order_resp.json()
    assert order["source"] == "pos"

    # Stock shouldn't move until the order is actually completed.
    ingredient = (await db.execute(select(Ingredient).where(Ingredient.id == ingredient_id))).scalar_one()
    assert ingredient.quantity == Decimal("100")

    for status in ("confirmed", "preparing", "ready", "done"):
        resp = await client.patch(
            f"/api/orders/{order['id']}/status",
            json={"status": status},
            headers=auth_headers(reg["token"]),
        )
        assert resp.status_code == 200, resp.text

    await db.refresh(ingredient)
    # 3 burgers * 2 buns/burger = 6 buns consumed
    assert ingredient.quantity == Decimal("94.000")


async def test_pos_order_with_table_marks_it_occupied_then_frees_it(client: AsyncClient, db):
    reg = await register_network(client)
    venue_id, item_id, _ = await _setup_venue_menu_ingredient(client, reg["token"])

    table_resp = await client.post(
        "/settings/api/tables",
        json={"venue_id": venue_id, "label": "5", "seats": 4},
        headers=auth_headers(reg["token"]),
    )
    assert table_resp.status_code == 200, table_resp.text
    table_id = table_resp.json()["id"]

    order_resp = await client.post(
        "/api/pos/order",
        json={"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}], "table_id": table_id},
        headers=auth_headers(reg["token"]),
    )
    assert order_resp.status_code == 200, order_resp.text
    order_id = order_resp.json()["id"]

    table = (await db.execute(select(Table).where(Table.id == table_id))).scalar_one()
    assert table.status == "occupied"

    for status in ("confirmed", "preparing", "ready", "done"):
        resp = await client.patch(
            f"/api/orders/{order_id}/status", json={"status": status}, headers=auth_headers(reg["token"])
        )
        assert resp.status_code == 200, resp.text

    await db.refresh(table)
    assert table.status == "free"


async def test_cancel_order_returns_serializable_response(client: AsyncClient):
    """Regression test: cancel_order() used to db.refresh(order) at the end,
    which expires the eagerly-loaded items/guest relationships — serializing
    OrderOut then crashed with a 500 (MissingGreenlet)."""
    reg = await register_network(client)
    venue_id, item_id, _ = await _setup_venue_menu_ingredient(client, reg["token"])

    order_resp = await client.post(
        "/api/pos/order",
        json={"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}]},
        headers=auth_headers(reg["token"]),
    )
    order_id = order_resp.json()["id"]

    resp = await client.post(f"/api/orders/{order_id}/cancel", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "cancelled"


async def test_cannot_skip_order_status_transitions(client: AsyncClient):
    reg = await register_network(client)
    venue_id, item_id, _ = await _setup_venue_menu_ingredient(client, reg["token"])

    order_resp = await client.post(
        "/api/pos/order",
        json={"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}]},
        headers=auth_headers(reg["token"]),
    )
    order_id = order_resp.json()["id"]

    # new -> done directly should be rejected (must go through confirmed/preparing/ready)
    resp = await client.patch(
        f"/api/orders/{order_id}/status", json={"status": "done"}, headers=auth_headers(reg["token"])
    )
    assert resp.status_code == 400
