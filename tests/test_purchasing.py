"""Purchase invoices: posting a goods receipt increases stock, updates the
ingredient's cost (which feeds food-cost), and creates the supplier."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _setup(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=h)).json()["id"]
    ing = (await client.post("/api/inventory", headers=h, json={
        "venue_id": venue_id, "name": "Молоко", "unit": "л",
        "quantity": 5, "min_quantity": 1, "cost_per_unit": 400,
    })).json()
    return h, venue_id, ing["id"]


async def test_posting_invoice_applies_stock_and_cost(client: AsyncClient):
    h, venue_id, ing_id = await _setup(client)
    resp = await client.post("/api/purchasing/invoices", headers=h, json={
        "venue_id": venue_id,
        "supplier_name": "ТОО Продукты",
        "number": "N-42",
        "lines": [{"ingredient_id": ing_id, "quantity": 10, "unit_cost": 450}],
    })
    assert resp.status_code == 200, resp.text
    inv = resp.json()
    assert inv["total"] == 4500.0
    assert inv["supplier"] == "ТОО Продукты"

    # stock 5 → 15, cost 400 → 450 (latest price)
    inv_page = await client.get(f"/inventory?venue_id={venue_id}", headers=h)
    assert "15.00" in inv_page.text
    assert "450" in inv_page.text

    # supplier created and reusable
    sup = (await client.get("/api/purchasing/suppliers", headers=h)).json()
    assert [s["name"] for s in sup["suppliers"]] == ["ТОО Продукты"]

    listed = (await client.get(f"/api/purchasing/invoices?venue_id={venue_id}", headers=h)).json()
    assert len(listed["invoices"]) == 1
    assert listed["invoices"][0]["lines"][0]["ingredient_name"] == "Молоко"


async def test_foreign_ingredient_rejected(client: AsyncClient):
    h1, venue_id, _ = await _setup(client)
    _, _, foreign_ing = await _setup(client)  # another network's ingredient
    resp = await client.post("/api/purchasing/invoices", headers=h1, json={
        "venue_id": venue_id,
        "lines": [{"ingredient_id": foreign_ing, "quantity": 1, "unit_cost": 100}],
    })
    assert resp.status_code == 400
