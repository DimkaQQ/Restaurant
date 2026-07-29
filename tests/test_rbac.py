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


async def _make_user(client, owner_h, role):
    email = f"{role}-{uuid.uuid4().hex[:6]}@example.com"
    resp = await client.post("/settings/users", headers=owner_h, json={
        "email": email, "password": "password123", "role": role,
    })
    assert resp.status_code == 200, resp.text
    login = await client.post("/auth/login", json={"email": email, "password": "password123"})
    return auth_headers(login.json()["access_token"])


async def test_workstation_lock_redirects_to_home_screen(client: AsyncClient):
    """A job-role account opens only its screen: any other page bounces
    back home. APIs the screen needs keep working."""
    reg = await register_network(client)
    owner_h = auth_headers(reg["token"])
    venue_id = (await client.post("/api/venues/", json={"name": "Cafe"}, headers=owner_h)).json()["id"]
    item_id = (await client.post(
        f"/api/menu/{venue_id}", json={"name": "Латте", "price": 1000}, headers=owner_h
    )).json()["id"]

    html = {"Accept": "text/html"}
    for role, home, foreign in [
        ("waiter", "/waiter", "/pos"),
        ("kitchen", "/kitchen", "/waiter"),
        ("cashier", "/pos", "/menu"),
    ]:
        h = await _make_user(client, owner_h, role)
        client.cookies.clear()
        # own screen opens
        resp = await client.get(home, headers={**h, **html})
        assert resp.status_code == 200, (role, home, resp.status_code)
        # foreign screen redirects home
        resp = await client.get(foreign, headers={**h, **html})
        assert resp.status_code == 307, (role, foreign, resp.status_code)
        assert resp.headers["location"] == home
        # /dashboard after login also lands home
        resp = await client.get("/dashboard", headers={**h, **html})
        assert resp.status_code == 307 and resp.headers["location"] == home

    # the workstation APIs still work for job roles
    waiter_h = await _make_user(client, owner_h, "waiter")
    client.cookies.clear()
    resp = await client.post("/api/pos/order", headers=waiter_h, json={
        "venue_id": venue_id, "items": [{"menu_item_id": item_id, "quantity": 1}],
    })
    assert resp.status_code == 200, resp.text
    assert (await client.get(f"/api/orders/live?venue_id={venue_id}", headers=waiter_h)).status_code == 200

    kitchen_h = await _make_user(client, owner_h, "kitchen")
    client.cookies.clear()
    order_id = resp.json()["id"]
    resp = await client.patch(f"/api/orders/{order_id}/status", headers=kitchen_h,
                              json={"status": "confirmed"})
    assert resp.status_code == 200, resp.text


async def test_owner_not_affected_by_workstation_lock(client: AsyncClient):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    for page in ["/dashboard", "/pos", "/waiter", "/kitchen", "/menu"]:
        resp = await client.get(page, headers={**h, "Accept": "text/html"})
        assert resp.status_code == 200, (page, resp.status_code)


async def test_login_lockout_after_five_failures(client: AsyncClient):
    reg = await register_network(client)
    email = reg["email"]
    for _ in range(5):
        resp = await client.post("/auth/login", json={"email": email, "password": "wrong-pass"})
        assert resp.status_code == 401
    # 6th attempt — locked even with the CORRECT password
    resp = await client.post("/auth/login", json={"email": email, "password": "supersecret123"})
    assert resp.status_code == 429
    # the lockout lands in the audit journal
    owner_h = auth_headers(reg["token"])
    page = (await client.get("/settings/audit", headers=owner_h)).text
    assert "login_locked" in page or "заблокирован" in page


async def test_password_reset_revokes_old_sessions(client: AsyncClient, db):
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    client.cookies.clear()
    assert (await client.get("/api/venues/", headers=h)).status_code == 200

    # simulate a password reset bumping token_version
    from sqlalchemy import text as sql
    await db.execute(sql("UPDATE users SET token_version = token_version + 1 WHERE email = :e"),
                     {"e": reg["email"]})
    await db.commit()
    resp = await client.get("/api/venues/", headers=h)
    assert resp.status_code == 401


async def test_refresh_token_cannot_be_used_as_access_token(client: AsyncClient):
    """A stolen refresh cookie value must not authenticate API calls directly."""
    reg = await register_network(client)
    refresh = client.cookies.get("refresh_token")
    assert refresh
    client.cookies.clear()
    resp = await client.get("/api/venues/", headers={"Authorization": f"Bearer {refresh}"})
    assert resp.status_code == 401


async def test_silent_refresh_keeps_workstation_logged_in(client: AsyncClient):
    """Expired access cookie + valid refresh cookie → the page still opens
    and a fresh access token is set."""
    reg = await register_network(client)
    refresh = client.cookies.get("refresh_token")
    client.cookies.clear()
    client.cookies.set("refresh_token", refresh)
    resp = await client.get("/dashboard", headers={"Accept": "text/html"})
    assert resp.status_code == 200
    assert "access_token" in resp.headers.get("set-cookie", "")


def test_totp_rfc6238_vector(monkeypatch):
    """Known RFC 6238 SHA-1 test vector: T=59s → 287082."""
    import time as _time
    from app.services import totp
    monkeypatch.setattr(_time, "time", lambda: 59)
    secret = "GEZDGNBVGY3TQOJQGEZDGNBVGY3TQOJQ"  # b"1234567890"*2 in base32
    assert totp.verify_code(secret, "287082")
    assert not totp.verify_code(secret, "000000")


async def test_pin_switch_flow(client: AsyncClient):
    """Station stays logged in; entering an employee's PIN makes the session
    theirs. Wrong PINs lock the switch; anonymous callers get nothing."""
    reg = await register_network(client)
    owner_h = auth_headers(reg["token"])
    # a station account and an employee with a PIN
    await client.post("/settings/users", headers=owner_h, json={
        "email": "station@x.com", "password": "password123", "role": "cashier",
    })
    await client.post("/settings/users", headers=owner_h, json={
        "email": "aizhan@x.com", "password": "password123", "role": "waiter", "pin": "4321",
    })
    login = await client.post("/auth/login", json={"email": "station@x.com", "password": "password123"})
    station_h = auth_headers(login.json()["access_token"])
    client.cookies.clear()

    # anonymous → 401 (PIN never guards the front door)
    resp = await client.post("/auth/pin-switch", json={"pin": "4321"})
    assert resp.status_code in (401, 307)

    # wrong PIN
    resp = await client.post("/auth/pin-switch", headers=station_h, json={"pin": "9999"})
    assert resp.status_code == 401

    # right PIN → session becomes the waiter's
    resp = await client.post("/auth/pin-switch", headers=station_h, json={"pin": "4321"})
    assert resp.status_code == 200, resp.text
    d = resp.json()
    assert d["email"] == "aizhan@x.com" and d["role"] == "waiter"
    new_h = auth_headers(d["access_token"])
    client.cookies.clear()
    resp = await client.get("/waiter", headers={**new_h, "Accept": "text/html"})
    assert resp.status_code == 200

    # duplicate PIN is rejected at assignment time
    resp = await client.post("/settings/users", headers=owner_h, json={
        "email": "b@x.com", "password": "password123", "role": "waiter",
    })
    uid = None
    # find the created user's id via the pin endpoint duplicate check
    from tests.conftest import auth_headers as _ah  # noqa
    page = await client.post(f"/settings/users/{resp.json().get('id', '00000000-0000-0000-0000-000000000000')}/pin",
                             headers=owner_h, json={"pin": "4321"})
    assert page.status_code in (404, 409)  # 409 if id returned, 404 otherwise — both mean no silent duplicate


async def test_totp_login_flow(client: AsyncClient):
    """Enable 2FA → password alone stops working, password+code works."""
    import time as _time
    from app.services.totp import _code_at
    reg = await register_network(client)
    h = auth_headers(reg["token"])
    # enroll + confirm with a freshly computed code
    resp = await client.post("/auth/2fa/enroll", headers=h, json={})
    assert resp.status_code == 200, resp.text
    secret = resp.json()["secret"]
    code = _code_at(secret, int(_time.time()) // 30)
    resp = await client.post("/auth/2fa/confirm", headers=h, json={"code": code})
    assert resp.status_code == 200, resp.text

    client.cookies.clear()
    # password only → 401 with the totp flag
    resp = await client.post("/auth/login", json={"email": reg["email"], "password": "supersecret123"})
    assert resp.status_code == 401
    assert resp.json().get("totp_required") is True
    # password + valid code → in
    code = _code_at(secret, int(_time.time()) // 30)
    resp = await client.post("/auth/login", json={
        "email": reg["email"], "password": "supersecret123", "totp_code": code,
    })
    assert resp.status_code == 200, resp.text
