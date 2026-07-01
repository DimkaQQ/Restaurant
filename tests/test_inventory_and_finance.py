"""Coverage for inventory (writeoff/restock stock math) and finance (expenses)."""
from decimal import Decimal

from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _create_venue(client: AsyncClient, token: str) -> str:
    resp = await client.post("/api/venues/", json={"name": "Main Hall"}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def test_writeoff_reduces_stock(client: AsyncClient):
    reg = await register_network(client)
    venue_id = await _create_venue(client, reg["token"])

    ing = await client.post(
        "/api/inventory",
        json={"venue_id": venue_id, "name": "Tomatoes", "unit": "кг", "quantity": 20, "min_quantity": 2},
        headers=auth_headers(reg["token"]),
    )
    assert ing.status_code == 200, ing.text
    ing_id = ing.json()["id"]

    resp = await client.post(
        f"/api/inventory/{ing_id}/writeoff",
        json={"quantity": 5, "reason": "spoilage"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quantity"] == 15.0


async def test_writeoff_rejects_more_than_available(client: AsyncClient):
    reg = await register_network(client)
    venue_id = await _create_venue(client, reg["token"])

    ing = await client.post(
        "/api/inventory",
        json={"venue_id": venue_id, "name": "Cheese", "unit": "кг", "quantity": 3},
        headers=auth_headers(reg["token"]),
    )
    ing_id = ing.json()["id"]

    resp = await client.post(
        f"/api/inventory/{ing_id}/writeoff",
        json={"quantity": 999, "reason": "usage"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 400


async def test_restock_increases_stock(client: AsyncClient):
    reg = await register_network(client)
    venue_id = await _create_venue(client, reg["token"])

    ing = await client.post(
        "/api/inventory",
        json={"venue_id": venue_id, "name": "Flour", "unit": "кг", "quantity": 10},
        headers=auth_headers(reg["token"]),
    )
    ing_id = ing.json()["id"]

    resp = await client.post(
        f"/api/inventory/{ing_id}/restock",
        json={"quantity": 25},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["quantity"] == 35.0


async def test_cannot_writeoff_another_networks_ingredient(client: AsyncClient):
    net_a = await register_network(client, "Network A")
    net_b = await register_network(client, "Network B")
    venue_b = await _create_venue(client, net_b["token"])

    ing = await client.post(
        "/api/inventory",
        json={"venue_id": venue_b, "name": "Secret Sauce", "unit": "л", "quantity": 10},
        headers=auth_headers(net_b["token"]),
    )
    ing_id = ing.json()["id"]

    resp = await client.post(
        f"/api/inventory/{ing_id}/writeoff",
        json={"quantity": 1},
        headers=auth_headers(net_a["token"]),
    )
    assert resp.status_code == 404


async def test_create_and_delete_expense(client: AsyncClient):
    reg = await register_network(client)
    venue_id = await _create_venue(client, reg["token"])

    resp = await client.post(
        "/api/expenses",
        json={"venue_id": venue_id, "category": "rent", "amount": 150000, "expense_date": "2026-01-15"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200, resp.text
    expense_id = resp.json()["id"]

    del_resp = await client.delete(f"/api/expenses/{expense_id}", headers=auth_headers(reg["token"]))
    assert del_resp.status_code == 200
