"""Payment is a separate event from the order lifecycle: a coffee shop takes
payment at the counter before preparing, a restaurant after the meal. These
tests pin that separation: status tracks logistics, payment_status tracks
money, and revenue counts money received."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _setup_order(client: AsyncClient, payment_method=None):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Hall"}, headers=h)).json()["id"]
    item_id = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Latte", "price": 1300}, headers=h
    )).json()["id"]
    body = {"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}]}
    if payment_method:
        body["payment_method"] = payment_method
    order = (await client.post("/api/pos/order", json=body, headers=h)).json()
    return reg, h, venue_id, order


async def test_pos_pay_at_counter_marks_order_paid_immediately(client: AsyncClient):
    _, h, _, order = await _setup_order(client, payment_method="card")
    assert order["payment_status"] == "paid"
    assert order["payment_method"] == "card"
    assert order["status"] == "new"  # payment does not advance the kitchen flow


async def test_pos_pay_later_creates_unpaid_order(client: AsyncClient):
    _, h, _, order = await _setup_order(client)
    assert order["payment_status"] == "unpaid"
    assert order["payment_method"] is None


async def test_order_can_be_paid_at_any_lifecycle_stage(client: AsyncClient):
    _, h, _, order = await _setup_order(client)
    oid = order["id"]
    resp = await client.patch(f"/api/orders/{oid}/status", json={"status": "confirmed"}, headers=h)
    assert resp.status_code == 200

    resp = await client.post(f"/api/orders/{oid}/pay", json={"method": "cash"}, headers=h)
    assert resp.status_code == 200

    body = (await client.get(f"/api/orders/{oid}", headers=h)).json()
    assert body["payment_status"] == "paid"
    assert body["status"] == "confirmed"  # unchanged by payment


async def test_double_payment_rejected(client: AsyncClient):
    _, h, _, order = await _setup_order(client, payment_method="cash")
    resp = await client.post(f"/api/orders/{order['id']}/pay", json={"method": "card"}, headers=h)
    assert resp.status_code == 400


async def test_cancelled_order_cannot_be_paid(client: AsyncClient):
    _, h, _, order = await _setup_order(client)
    oid = order["id"]
    resp = await client.patch(f"/api/orders/{oid}/status", json={"status": "cancelled"}, headers=h)
    assert resp.status_code == 200
    resp = await client.post(f"/api/orders/{oid}/pay", json={"method": "cash"}, headers=h)
    assert resp.status_code == 400


async def test_serving_does_not_imply_payment(client: AsyncClient):
    _, h, _, order = await _setup_order(client)
    oid = order["id"]
    for status in ("confirmed", "preparing", "ready", "done"):
        resp = await client.patch(f"/api/orders/{oid}/status", json={"status": status}, headers=h)
        assert resp.status_code == 200, resp.text
    body = (await client.get(f"/api/orders/{oid}", headers=h)).json()
    assert body["status"] == "done"
    assert body["payment_status"] == "unpaid"


async def test_revenue_counts_paid_not_served(client: AsyncClient):
    """Dashboard revenue must reflect money received: an upfront-paid order
    counts immediately; a served-but-unpaid order does not count."""
    reg, h, venue_id, paid_order = await _setup_order(client, payment_method="cash")

    # second order: served through the full flow but never paid
    item_id = paid_order["items"][0]["menu_item_id"]
    unpaid = (await client.post(
        "/api/pos/order",
        json={"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 2}]},
        headers=h,
    )).json()
    for status in ("confirmed", "preparing", "ready", "done"):
        await client.patch(f"/api/orders/{unpaid['id']}/status", json={"status": status}, headers=h)

    resp = await client.get("/dashboard", headers=h)
    assert resp.status_code == 200
    # The dashboard's money filter renders 1300 → "1 тыс". If the unpaid
    # served order (2600) leaked into revenue it would show "4 тыс" (3900).
    assert "1 тыс" in resp.text
    assert "4 тыс" not in resp.text


async def test_served_unpaid_order_stays_on_orders_board(client: AsyncClient):
    _, h, _, order = await _setup_order(client)
    oid = order["id"]
    for status in ("confirmed", "preparing", "ready", "done"):
        await client.patch(f"/api/orders/{oid}/status", json={"status": status}, headers=h)

    resp = await client.get("/partials/orders", headers=h)
    assert resp.status_code == 200
    assert oid[:8] in resp.text  # card still visible, awaiting payment
    assert "Принять оплату" in resp.text
