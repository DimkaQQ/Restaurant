"""Webkassa fiscal-check integration: client contract (mocked HTTP) + the
order-completion hook that dispatches to it. No real network calls — this
must never hit the actual Webkassa sandbox from CI."""
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.venue import Venue
from app.services.fiscal import webkassa
from app.services.fiscal.service import issue_fiscal_check
from tests.conftest import register_network, auth_headers


class _FakeResp:
    def __init__(self, data):
        self._data = data

    def raise_for_status(self):
        pass

    def json(self):
        return self._data


class _FakeClient:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, **kwargs):
        return self._resp


def _mock_sequence(monkeypatch, responses):
    it = iter(responses)
    monkeypatch.setattr(webkassa.httpx, "AsyncClient", lambda **kw: _FakeClient(next(it)))


async def test_webkassa_issue_check_success(monkeypatch):
    _mock_sequence(monkeypatch, [
        _FakeResp({"Data": {"Token": "tok123"}}),
        _FakeResp({"Data": {"CheckNumber": "CHK-1", "TicketUrl": "https://devkkm.webkassa.kz/t/1"}}),
    ])

    result = await webkassa.issue_check(
        api_key="key", login="login", password="pass", cashbox_number="CB1",
        external_check_number="order-1",
        items=[{"name": "Burger", "quantity": 2, "price": Decimal("2500")}],
        total_amount=Decimal("5000"),
        payment_method="cash",
    )
    assert result == {"check_number": "CHK-1", "ticket_url": "https://devkkm.webkassa.kz/t/1"}


async def test_webkassa_duplicate_check_number_treated_as_success(monkeypatch):
    """Code 14 = this ExternalCheckNumber was already fiscalized — Webkassa still
    returns the original Data, so a retried request must not surface an error."""
    _mock_sequence(monkeypatch, [
        _FakeResp({"Data": {"Token": "tok123"}}),
        _FakeResp({
            "Data": {"CheckNumber": "CHK-1", "TicketUrl": "https://devkkm.webkassa.kz/t/1"},
            "Errors": [{"Code": 14, "Text": "Duplicate ExternalCheckNumber"}],
        }),
    ])

    result = await webkassa.issue_check(
        api_key="key", login="login", password="pass", cashbox_number="CB1",
        external_check_number="order-1",
        items=[{"name": "Burger", "quantity": 1, "price": Decimal("2500")}],
        total_amount=Decimal("2500"),
        payment_method="card",
    )
    assert result["check_number"] == "CHK-1"


async def test_webkassa_retries_transient_network_failure_then_succeeds(monkeypatch):
    """A fiscal check failing to post is a revenue/compliance problem, not
    just a UX hiccup — a transient connection error must be retried instead
    of failing the whole order on the first hiccup."""
    import httpx as httpx_module

    call_count = {"check": 0}

    class _FlakyThenOkClient:
        def __init__(self, is_check):
            self._is_check = is_check

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def post(self, url, **kwargs):
            if not self._is_check:
                return _FakeResp({"Data": {"Token": "tok123"}})
            call_count["check"] += 1
            if call_count["check"] == 1:
                raise httpx_module.ConnectError("connection reset")
            return _FakeResp({"Data": {"CheckNumber": "CHK-RETRY", "TicketUrl": "https://devkkm.webkassa.kz/t/retry"}})

    # Distinguish authorize vs check by call order — first AsyncClient() is
    # always the authorize call, everything after is the check call (and its
    # retries), since both endpoints are invoked with the same kwargs shape.
    calls = {"n": 0}

    def _factory(**kw):
        calls["n"] += 1
        return _FlakyThenOkClient(is_check=calls["n"] > 1)

    monkeypatch.setattr(webkassa.httpx, "AsyncClient", _factory)

    result = await webkassa.issue_check(
        api_key="key", login="login", password="pass", cashbox_number="CB1",
        external_check_number="order-retry",
        items=[{"name": "Burger", "quantity": 1, "price": Decimal("2500")}],
        total_amount=Decimal("2500"),
        payment_method="cash",
    )
    assert result["check_number"] == "CHK-RETRY"
    assert call_count["check"] == 2  # failed once, succeeded on retry


async def test_webkassa_authorize_failure_raises(monkeypatch):
    _mock_sequence(monkeypatch, [
        _FakeResp({"Errors": [{"Code": 1, "Text": "Bad credentials"}]}),
    ])

    with pytest.raises(webkassa.WebkassaError):
        await webkassa.issue_check(
            api_key="key", login="login", password="wrong", cashbox_number="CB1",
            external_check_number="order-1",
            items=[{"name": "Burger", "quantity": 1, "price": Decimal("2500")}],
            total_amount=Decimal("2500"),
            payment_method="cash",
        )


async def test_issue_fiscal_check_noop_when_provider_not_configured(client, db):
    """Most venues don't have fiscalization enabled — the hook must be a no-op,
    not an error, so order completion never blocks on it."""
    reg = await register_network(client)
    venue_resp = await client.post("/api/venues/", json={"name": "Hall"}, headers=auth_headers(reg["token"]))
    venue = (await db.execute(select(Venue).where(Venue.id == venue_resp.json()["id"]))).scalar_one()

    from app.models.order import Order
    order = Order(
        id=__import__("uuid").uuid4(), venue_id=venue.id, guest_id=None, status="ready",
        total_amount=Decimal("1000"), points_earned=0, payment_method="cash", items=[],
    )
    await issue_fiscal_check(order, venue)
    assert order.fiscal_status is None


async def test_order_completion_issues_fiscal_check(monkeypatch, client, db):
    _mock_sequence(monkeypatch, [
        _FakeResp({"Data": {"Token": "tok123"}}),
        _FakeResp({"Data": {"CheckNumber": "CHK-99", "TicketUrl": "https://devkkm.webkassa.kz/t/99"}}),
    ])

    reg = await register_network(client)
    venue_resp = await client.post("/api/venues/", json={"name": "Hall"}, headers=auth_headers(reg["token"]))
    venue_id = venue_resp.json()["id"]

    venue = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one()
    venue.fiscal_provider = "webkassa"
    venue.fiscal_api_key = "key"
    venue.fiscal_login = "login"
    venue.fiscal_password = "pass"
    venue.fiscal_cashbox_number = "CB1"
    await db.commit()

    item_resp = await client.post(
        f"/api/menu/{venue_id}", json={"name": "Burger", "price": 2500}, headers=auth_headers(reg["token"])
    )
    item_id = item_resp.json()["id"]

    order_resp = await client.post(
        "/api/pos/order",
        json={"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}]},
        headers=auth_headers(reg["token"]),
    )
    order_id = order_resp.json()["id"]

    # Note: PATCH /api/orders/{id}/status is actually served by dashboard.py's
    # HTMX handler (registered before orders.py in main.py — see the NOTE in
    # dashboard.py), which returns HTML, not the OrderOut JSON orders.py's
    # dead handler would. So verify via a fresh GET instead of the PATCH body.
    for status in ("confirmed", "preparing", "ready"):
        resp = await client.patch(f"/api/orders/{order_id}/status", json={"status": status}, headers=auth_headers(reg["token"]))
        assert resp.status_code == 200, resp.text

    resp = await client.patch(
        f"/api/orders/{order_id}/status",
        json={"status": "done", "payment_method": "cash"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200, resp.text

    order_resp = await client.get(f"/api/orders/{order_id}", headers=auth_headers(reg["token"]))
    body = order_resp.json()
    assert body["fiscal_status"] == "issued"
    assert body["fiscal_check_number"] == "CHK-99"
    assert body["fiscal_ticket_url"] == "https://devkkm.webkassa.kz/t/99"


async def test_order_completion_without_payment_method_marks_fiscal_failed(monkeypatch, client, db):
    """A venue with fiscalization on but no payment_method supplied on the
    done transition can't be fiscalized — must fail loudly in fiscal_error,
    not silently skip or crash the status update."""
    reg = await register_network(client)
    venue_resp = await client.post("/api/venues/", json={"name": "Hall"}, headers=auth_headers(reg["token"]))
    venue_id = venue_resp.json()["id"]

    venue = (await db.execute(select(Venue).where(Venue.id == venue_id))).scalar_one()
    venue.fiscal_provider = "webkassa"
    venue.fiscal_api_key = "key"
    venue.fiscal_login = "login"
    venue.fiscal_password = "pass"
    venue.fiscal_cashbox_number = "CB1"
    await db.commit()

    item_resp = await client.post(
        f"/api/menu/{venue_id}", json={"name": "Burger", "price": 2500}, headers=auth_headers(reg["token"])
    )
    item_id = item_resp.json()["id"]

    order_resp = await client.post(
        "/api/pos/order",
        json={"venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}]},
        headers=auth_headers(reg["token"]),
    )
    order_id = order_resp.json()["id"]

    for status in ("confirmed", "preparing", "ready", "done"):
        resp = await client.patch(f"/api/orders/{order_id}/status", json={"status": status}, headers=auth_headers(reg["token"]))
        assert resp.status_code == 200, resp.text

    order_resp = await client.get(f"/api/orders/{order_id}", headers=auth_headers(reg["token"]))
    assert order_resp.json()["fiscal_status"] == "failed"
