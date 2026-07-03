"""Staff audit trail: sensitive actions land in the owner-visible journal."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def test_sensitive_actions_are_audited(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=h)).json()["id"]
    item = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Латте", "price": 1000}, headers=h
    )).json()

    # discount
    await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id,
        "items": [{"menu_item_id": item["id"], "quantity": 1}],
        "discount_type": "percent", "discount_value": 15,
    })
    # order cancel
    order = (await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item["id"], "quantity": 1}],
    })).json()
    await client.patch(f"/api/orders/{order['id']}/status", json={"status": "cancelled"}, headers=h)
    # menu item deletion
    await client.delete(f"/api/menu/{item['id']}", headers=h)

    page = await client.get("/settings/audit", headers=h)
    assert page.status_code == 200
    assert "Применил скидку" in page.text
    assert "Отменил заказ" in page.text
    assert "Удалил позицию меню" in page.text
    assert "Латте" in page.text


async def test_audit_page_owner_only(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    await client.post("/settings/users", headers=h, json={
        "email": "mgr@x.kz", "password": "Manager123!", "role": "manager",
    })
    login = await client.post("/auth/login", json={"email": "mgr@x.kz", "password": "Manager123!"})
    mgr_token = login.json()["access_token"]
    resp = await client.get("/settings/audit", headers=auth_headers(mgr_token))
    assert resp.status_code == 403
