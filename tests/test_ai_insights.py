"""AI insights: stats are computed in SQL, the LLM only interprets them.
The endpoint is owner-only and degrades gracefully without an API key."""
from httpx import AsyncClient

from tests.conftest import register_network, auth_headers


async def test_insights_unavailable_without_key(client: AsyncClient, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "ANTHROPIC_API_KEY", "")
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    resp = await client.post("/analytics/api/insights", headers=h)
    assert resp.status_code == 503


async def test_insights_with_mocked_model(client: AsyncClient, monkeypatch):
    from app.config import settings as app_settings
    monkeypatch.setattr(app_settings, "ANTHROPIC_API_KEY", "sk-test")

    import app.services.ai_insights as ai

    captured = {}

    class _FakeResp:
        status_code = 200
        def raise_for_status(self): pass
        def json(self):
            return {"content": [{"type": "text", "text": "• Уберите тирамису из меню"}]}

    class _FakeClient:
        def __init__(self, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return False
        async def post(self, url, **kw):
            captured["prompt"] = kw["json"]["messages"][0]["content"]
            return _FakeResp()

    monkeypatch.setattr(ai.httpx, "AsyncClient", _FakeClient)

    reg = await register_network(client)
    h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=h)).json()["id"]
    item_id = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Латте", "price": 1000}, headers=h
    )).json()["id"]
    await client.post("/api/pos/order", headers=h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 2}],
        "payment_method": "cash",
    })

    resp = await client.post("/analytics/api/insights", headers=h)
    assert resp.status_code == 200, resp.text
    assert "тирамису" in resp.json()["text"]
    # the model received the real computed stats, not raw DB access
    assert "Латте" in captured["prompt"]
    assert "2000" in captured["prompt"]
