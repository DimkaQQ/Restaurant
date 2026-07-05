"""Role-based access: one linear hierarchy (cashier < manager <
administrator < owner). Each tier keeps its floor duties and loses the
back office it doesn't need."""
import uuid

from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _network_with_users(client: AsyncClient):
    """Owner + one user of each role, plus a venue and a menu item."""
    reg = await register_network(client)
    owner_h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=owner_h)).json()["id"]
    item_id = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Латте", "price": 1000}, headers=owner_h
    )).json()["id"]

    tokens = {"owner": reg["token"]}
    for role in ("cashier", "manager", "administrator"):
        email = f"{role}-{uuid.uuid4().hex[:6]}@example.com"
        resp = await client.post("/settings/users", headers=owner_h, json={
            "email": email, "password": "password123", "role": role,
        })
        assert resp.status_code == 200, resp.text
        login = await client.post("/auth/login", json={"email": email, "password": "password123"})
        tokens[role] = login.json()["access_token"]
    return tokens, venue_id, item_id


async def test_cashier_can_work_the_register(client: AsyncClient):
    tokens, venue_id, item_id = await _network_with_users(client)
    h = auth_headers(tokens["cashier"])
    client.cookies.clear()
    # sell
    resp = await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}],
        "payment_method": "cash",
    })
    assert resp.status_code == 200, resp.text
    # stop-list toggle
    resp = await client.patch(f"/api/menu/{item_id}", headers=h, json={"is_available": False})
    assert resp.status_code == 200, resp.text
    # cash shift
    resp = await client.post("/api/cash-shifts/open", headers=h,
                             json={"venue_id": venue_id, "opening_cash": 0})
    assert resp.status_code == 200, resp.text


async def test_cashier_blocked_from_back_office(client: AsyncClient):
    tokens, venue_id, item_id = await _network_with_users(client)
    h = auth_headers(tokens["cashier"])
    client.cookies.clear()
    for path in ["/api/guests/", "/api/purchasing/invoices", "/api/purchasing/suppliers"]:
        resp = await client.get(path, headers=h)
        assert resp.status_code == 403, (path, resp.status_code)
    # price change is a manager action, not a stop-list toggle
    resp = await client.patch(f"/api/menu/{item_id}", headers=h, json={"price": 1})
    assert resp.status_code == 403
    # HTML pages redirect home instead of erroring
    resp = await client.get("/analytics/", headers={**h, "Accept": "text/html"})
    assert resp.status_code == 307


async def test_manager_gets_analytics_but_not_finance(client: AsyncClient):
    tokens, venue_id, item_id = await _network_with_users(client)
    h = auth_headers(tokens["manager"])
    client.cookies.clear()
    assert (await client.get("/api/guests/", headers=h)).status_code == 200
    assert (await client.get("/api/purchasing/suppliers", headers=h)).status_code == 200
    resp = await client.patch(f"/api/menu/{item_id}", headers=h, json={"price": 1200})
    assert resp.status_code == 200
    # finance is administrator+
    resp = await client.get("/finance/export/sales.csv?period=month", headers=h)
    assert resp.status_code == 403
    # broadcasts are administrator+
    resp = await client.post("/settings/api/broadcasts", headers=h, json={"message": "hi"})
    assert resp.status_code == 403


async def test_administrator_gets_finance_not_settings(client: AsyncClient):
    tokens, venue_id, _ = await _network_with_users(client)
    h = auth_headers(tokens["administrator"])
    client.cookies.clear()
    resp = await client.get("/finance/export/sales.csv?period=month", headers=h)
    assert resp.status_code == 200
    # owner-only settings stay closed
    resp = await client.post("/settings/api/promos", headers=h,
                             json={"code": "X", "type": "percent", "value": 5})
    assert resp.status_code == 403
    resp = await client.post("/settings/api/keys", headers=h, json={"name": "k"})
    assert resp.status_code == 403
