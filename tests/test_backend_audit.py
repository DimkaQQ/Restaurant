"""Adversarial cross-feature tests from the backend audit: refunds vs
revenue/Z-reports, discount+promo conflicts, idempotency races, boundary
values. These probe interactions the per-feature suites don't cover."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _setup(client: AsyncClient, price: int = 1000):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=h)).json()["id"]
    item_id = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Латте", "price": price}, headers=h
    )).json()["id"]
    return h, venue_id, item_id


async def _paid_order(client: AsyncClient, h, venue_id, item_id, qty=1, method="cash"):
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": qty}],
        "payment_method": method,
    })
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_cancelled_paid_order_is_refunded_and_leaves_revenue(client: AsyncClient):
    """Cancel after payment → payment_status=refunded, money drops out of
    the Z-report and dashboard revenue."""
    h, venue_id, item_id = await _setup(client)
    await client.post("/api/cash-shifts/open", headers=h, json={"venue_id": venue_id, "opening_cash": 0})
    kept = await _paid_order(client, h, venue_id, item_id)         # stays paid
    cancelled = await _paid_order(client, h, venue_id, item_id)    # will be cancelled

    resp = await client.patch(
        f"/api/orders/{cancelled['id']}/status", headers=h, json={"status": "cancelled"},
    )
    assert resp.status_code == 200, resp.text

    orders = (await client.get(f"/api/orders/?venue_id={venue_id}", headers=h)).json()
    by_id = {o["id"]: o for o in orders}
    assert by_id[cancelled["id"]]["status"] == "cancelled"
    assert by_id[cancelled["id"]]["payment_status"] == "refunded"
    assert by_id[kept["id"]]["payment_status"] == "paid"

    # Z-report counts only the order that stayed paid
    shift = (await client.get(f"/api/cash-shifts/current?venue_id={venue_id}", headers=h)).json()["shift"]
    closed = (await client.post(
        f"/api/cash-shifts/{shift['id']}/close", headers=h,
        json={"closing_cash_actual": 1000},
    )).json()["shift"]
    assert closed["cash_sales"] == 1000.0
    assert closed["orders_count"] == 1
    assert closed["difference"] == 0.0


async def test_cancel_via_service_endpoint_also_refunds(client: AsyncClient):
    """The staff cancel endpoint (orders.py → cancel_order) must apply the
    same refund marking as the dashboard path."""
    h, venue_id, item_id = await _setup(client)
    order = await _paid_order(client, h, venue_id, item_id)
    resp = await client.post(f"/api/orders/{order['id']}/cancel", headers=h)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "cancelled"
    assert body["payment_status"] == "refunded"


async def test_discount_and_promo_together_rejected(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    await client.post("/settings/api/promos", headers=h, json={
        "code": "BOTH", "type": "percent", "value": 10,
    })
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "discount_type": "percent", "discount_value": 20,
        "promo_code": "BOTH",
    })
    assert resp.status_code == 400
    # and the promo's usage counter must not have been burned
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "promo_code": "BOTH",
    })).json()
    assert float(order["total_amount"]) == 900.0


async def test_expired_promo_rejected_future_promo_works(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    resp = await client.post("/settings/api/promos", headers=h, json={
        "code": "OLD", "type": "percent", "value": 10, "expires_at": "2020-01-01",
    })
    assert resp.status_code == 200, resp.text
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "promo_code": "OLD",
    })
    assert resp.status_code == 400

    await client.post("/settings/api/promos", headers=h, json={
        "code": "FRESH", "type": "percent", "value": 10, "expires_at": "2099-01-01",
    })
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "promo_code": "FRESH",
    })
    assert resp.status_code == 200, resp.text


async def test_free_order_after_full_discount_can_be_paid(client: AsyncClient):
    """100% promo → 0 ₸ order still completes the payment flow (receipt,
    Z-report count) without division-by-zero anywhere."""
    h, venue_id, item_id = await _setup(client)
    await client.post("/settings/api/promos", headers=h, json={
        "code": "FREE", "type": "percent", "value": 100,
    })
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "promo_code": "FREE",
        "payment_method": "cash",
    })).json()
    assert float(order["total_amount"]) == 0.0
    assert order["payment_status"] == "paid"


async def test_foreign_client_order_id_returns_403_not_500(client: AsyncClient):
    """Idempotency lookup that hits another tenant's order must surface 403
    (HTTPException), not be swallowed into a 500."""
    h1, venue1, item1 = await _setup(client)
    await client.post("/api/pos/order", headers=h1, json={
        "venue_id": venue1,
        "items": [{"menu_item_id": item1, "quantity": 1}],
        "client_order_id": "shared-key-123",
    })
    h2, venue2, item2 = await _setup(client)
    resp = await client.post("/api/pos/order", headers=h2, json={
        "venue_id": venue2,
        "items": [{"menu_item_id": item2, "quantity": 1}],
        "client_order_id": "shared-key-123",
    })
    assert resp.status_code == 403


async def test_pos_audit_logs_promo_not_raw_request(client: AsyncClient):
    """Audit trail must record the discount actually applied."""
    h, venue_id, item_id = await _setup(client)
    await client.post("/settings/api/promos", headers=h, json={
        "code": "LOG15", "type": "percent", "value": 15,
    })
    await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "promo_code": "log15",
    })
    page = (await client.get("/settings/audit", headers=h)).text
    assert "LOG15" in page


async def test_invoice_with_duplicate_ingredient_lines_sums_stock(client: AsyncClient, db):
    h, venue_id, _ = await _setup(client)
    ing = (await client.post("/api/inventory", headers=h, json={
        "venue_id": venue_id, "name": "Молоко", "unit": "л", "quantity": 0,
    })).json()
    resp = await client.post("/api/purchasing/invoices", headers=h, json={
        "venue_id": venue_id,
        "supplier_name": "Base",
        "lines": [
            {"ingredient_id": ing["id"], "quantity": 5, "unit_cost": 400},
            {"ingredient_id": ing["id"], "quantity": 3, "unit_cost": 450},
        ],
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["total"] == 5 * 400 + 3 * 450
    from app.models.inventory import Ingredient
    from sqlalchemy import select
    milk = (await db.execute(select(Ingredient).where(Ingredient.id == ing["id"]))).scalar_one()
    assert float(milk.quantity) == 8.0
    assert float(milk.cost_per_unit) == 450.0


async def test_online_order_whitespace_name_gets_default(client: AsyncClient):
    h, venue_id, item_id = await _setup(client)
    resp = await client.post(f"/order/{venue_id}/submit", json={
        "items": [{"menu_item_id": item_id, "quantity": 1}],
        "guest_name": "   ",
        "guest_lang": "ru",
    })
    assert resp.status_code == 200, resp.text
    orders = (await client.get(f"/api/orders/?venue_id={venue_id}", headers=h)).json()
    guest_name = orders[0]["guest"]["name"]
    assert guest_name.strip() != ""


async def test_queue_board_hides_orders_older_than_a_day(client: AsyncClient, db):
    h, venue_id, item_id = await _setup(client)
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item_id, "quantity": 1}],
    })).json()
    await client.patch(f"/api/orders/{order['id']}/status", headers=h, json={"status": "confirmed"})

    data = (await client.get(f"/queue/{venue_id}/data")).json()
    short = order["id"][:8].upper()
    assert short in data["preparing"]

    # age the order two days and it must fall off the board
    from sqlalchemy import text
    await db.execute(text(
        "UPDATE orders SET created_at = created_at - interval '2 days' WHERE id = :oid"
    ), {"oid": order["id"]})
    await db.commit()
    data = (await client.get(f"/queue/{venue_id}/data")).json()
    assert short not in data["preparing"]


async def test_dashboard_cancel_reverses_guest_points_and_visits(client: AsyncClient):
    """The HTMX board cancel path must reverse loyalty like the service
    path does (this used to leak points)."""
    h, venue_id, item_id = await _setup(client)
    # online order creates a real (non-walkin) guest who earns points
    resp = await client.post(f"/order/{venue_id}/submit", json={
        "items": [{"menu_item_id": item_id, "quantity": 2}],
        "guest_name": "Айгерим", "guest_phone": "+77001234567",
    })
    order_id = resp.json()["order_id"]

    guests = (await client.get("/api/guests/", headers=h)).json()
    guest_before = next(g for g in guests if g.get("phone") == "+77001234567")
    assert guest_before["total_points"] > 0
    assert guest_before["total_visits"] == 1

    resp = await client.patch(f"/api/orders/{order_id}/status", headers=h, json={"status": "cancelled"})
    assert resp.status_code == 200, resp.text

    guests = (await client.get("/api/guests/", headers=h)).json()
    guest_after = next(g for g in guests if g.get("phone") == "+77001234567")
    assert guest_after["total_points"] == 0
    assert guest_after["total_visits"] == 0


async def test_pos_free_form_line(client: AsyncClient):
    """POS can sell an off-menu item (a bag, delivery fee) with a typed
    name and price."""
    h, venue_id, item_id = await _setup(client)
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [
            {"menu_item_id": item_id, "quantity": 1},
            {"menu_item_id": None, "name": "Пакет", "price": 50, "quantity": 2},
        ],
        "payment_method": "cash",
    })
    assert resp.status_code == 200, resp.text
    order = resp.json()
    assert float(order["total_amount"]) == 1000 + 100
    names = {i["name"] for i in order["items"]}
    assert "Пакет" in names


async def test_free_form_line_requires_name_and_price(client: AsyncClient):
    h, venue_id, _ = await _setup(client)
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": None, "name": "  ", "price": 50, "quantity": 1}],
    })
    assert resp.status_code == 400


async def test_guest_qr_cannot_send_free_form_line(client: AsyncClient):
    """The public endpoint's schema requires a real menu_item_id."""
    h, venue_id, _ = await _setup(client)
    resp = await client.post(f"/order/{venue_id}/submit", json={
        "items": [{"menu_item_id": None, "name": "Хак", "price": 1, "quantity": 1}],
    })
    assert resp.status_code == 422


async def test_split_order_moves_lines_and_totals(client: AsyncClient):
    h, venue_id, latte = await _setup(client)
    cake = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Чизкейк", "price": 1900}, headers=h
    )).json()["id"]
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": latte, "quantity": 2}, {"menu_item_id": cake, "quantity": 1}],
        "table_number": "5",
    })).json()
    cake_line = next(i for i in order["items"] if i["name"] == "Чизкейк")

    resp = await client.post(f"/api/orders/{order['id']}/split", headers=h,
                             json={"item_ids": [cake_line["id"]]})
    assert resp.status_code == 200, resp.text
    kept, split_off = resp.json()
    assert float(kept["total_amount"]) == 2000.0
    assert float(split_off["total_amount"]) == 1900.0
    assert split_off["table_number"] == "5"
    assert {i["name"] for i in split_off["items"]} == {"Чизкейк"}
    # each check pays separately
    pay = await client.post(f"/api/orders/{split_off['id']}/pay", headers=h,
                            data={"method": "cash"})
    assert pay.status_code == 200


async def test_split_paid_or_discounted_order_rejected(client: AsyncClient):
    h, venue_id, latte = await _setup(client)
    paid = await _paid_order(client, h, venue_id, latte, qty=2)
    line = paid["items"][0]["id"]
    resp = await client.post(f"/api/orders/{paid['id']}/split", headers=h, json={"item_ids": [line]})
    assert resp.status_code == 400

    disc = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": latte, "quantity": 2}],
        "discount_type": "percent", "discount_value": 10,
    })).json()
    resp = await client.post(f"/api/orders/{disc['id']}/split", headers=h,
                             json={"item_ids": [disc["items"][0]["id"]]})
    assert resp.status_code == 400


async def test_move_order_to_another_table(client: AsyncClient):
    h, venue_id, latte = await _setup(client)
    t1 = (await client.post("/settings/api/tables", headers=h,
                            json={"venue_id": venue_id, "label": "1", "seats": 2})).json()
    t2 = (await client.post("/settings/api/tables", headers=h,
                            json={"venue_id": venue_id, "label": "2", "seats": 2})).json()
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": latte, "quantity": 1}],
        "table_id": t1["id"],
    })).json()
    resp = await client.patch(f"/api/orders/{order['id']}/table", headers=h,
                              json={"table_id": t2["id"]})
    assert resp.status_code == 200, resp.text
    moved = resp.json()
    assert moved["table_id"] == t2["id"]
    assert moved["table_number"] == "2"
    # old table freed, new occupied
    tables = (await client.get(f"/api/pos/tables?venue_id={venue_id}", headers=h)).json()
    by_label = {t["label"]: t["status"] for t in tables}
    assert by_label["1"] == "free"
    assert by_label["2"] == "occupied"
