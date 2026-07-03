"""Public API v1 (X-API-Key) and outbound webhooks (HMAC-signed)."""
import hashlib
import hmac
import json

from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def _setup_with_key(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=h)).json()["id"]
    item_id = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Латте", "price": 1000}, headers=h
    )).json()["id"]
    key = (await client.post("/settings/api/keys", headers=h, json={"name": "test"})).json()["key"]
    return h, venue_id, item_id, key


async def test_api_key_auth_and_scoping(client: AsyncClient):
    h, venue_id, item_id, key = await _setup_with_key(client)
    await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}],
    })

    # no key → 401/422
    assert (await client.get("/api/v1/venues")).status_code in (401, 422)
    # wrong key → 401
    assert (await client.get("/api/v1/venues", headers={"X-API-Key": "rk_wrong"})).status_code == 401

    venues = (await client.get("/api/v1/venues", headers={"X-API-Key": key})).json()
    assert venues["venues"][0]["name"] == "Cafe"

    menu = (await client.get(f"/api/v1/menu?venue_id={venue_id}", headers={"X-API-Key": key})).json()
    assert menu["items"][0]["name"] == "Латте"

    orders = (await client.get("/api/v1/orders", headers={"X-API-Key": key})).json()
    assert len(orders["orders"]) == 1
    assert orders["orders"][0]["total_amount"] == 1000.0

    # another tenant's key must not see this data
    reg2 = await register_network(client)
    h2 = auth_headers(reg2["token"])
    key2 = (await client.post("/settings/api/keys", headers=h2, json={"name": "x"})).json()["key"]
    other = (await client.get("/api/v1/orders", headers={"X-API-Key": key2})).json()
    assert other["orders"] == []


async def test_revoked_key_rejected(client: AsyncClient):
    h, venue_id, item_id, key = await _setup_with_key(client)
    # find id via page state: create a second key, revoke via listing endpoint isn't exposed —
    # simplest: revoke by recreating; instead delete via the settings page id from DB listing page
    page = await client.get("/settings/api-access", headers=h)
    assert page.status_code == 200
    # extract key id from the page
    import re
    m = re.search(r'key-([0-9a-f-]{36})', page.text)
    assert m
    resp = await client.delete(f"/settings/api/keys/{m.group(1)}", headers=h)
    assert resp.status_code == 200
    assert (await client.get("/api/v1/venues", headers={"X-API-Key": key})).status_code == 401


async def test_webhook_delivery_signed(client: AsyncClient, monkeypatch):
    """order.created fires a signed POST to the subscriber URL."""
    import asyncio
    import app.services.webhooks as wh

    delivered = {}

    async def fake_post(url, body, headers):
        delivered["url"] = url
        delivered["body"] = body
        delivered["headers"] = headers

    monkeypatch.setattr(wh, "_post", fake_post)

    h, venue_id, item_id, _ = await _setup_with_key(client)
    hook = (await client.post("/settings/api/webhooks", headers=h, json={
        "url": "https://example.com/hook", "events": ["order.created", "order.paid"],
    })).json()

    await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}],
        "payment_method": "cash",
    })
    # let fire-and-forget tasks run
    await asyncio.sleep(0.1)

    assert delivered.get("url") == "https://example.com/hook"
    body = json.loads(delivered["body"])
    assert body["event"] in ("order.created", "order.paid")
    assert body["data"]["total_amount"] == 1000.0
    # signature verifies with the secret returned at creation
    expected = hmac.new(hook["secret"].encode(), delivered["body"], hashlib.sha256).hexdigest()
    assert delivered["headers"]["X-RestOS-Signature"] == expected
