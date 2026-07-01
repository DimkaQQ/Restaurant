"""Real-browser tests: fills in actual forms, clicks actual buttons, reads
actual rendered text — catches broken templates/JS that API-only tests can't."""
import uuid

import httpx
from playwright.sync_api import Page, expect


def _unique_email() -> str:
    return f"owner-{uuid.uuid4().hex[:8]}@example.com"


def _log_in_as(page: Page, live_server: str, token: str):
    """Templates read the token from BOTH the access_token cookie (server-side
    page renders) and localStorage (client-side fetch() calls) — a real login
    sets both, so tests that skip the login form must replicate that."""
    page.context.add_cookies([{"name": "access_token", "value": token, "url": live_server}])
    page.goto(live_server, wait_until="domcontentloaded")
    page.evaluate("token => localStorage.setItem('access_token', token)", token)


def test_register_page_renders(page: Page, live_server: str):
    page.goto(f"{live_server}/auth/register", wait_until="domcontentloaded")
    expect(page.locator("h1, .auth-logo")).to_be_visible()
    expect(page.get_by_placeholder("owner@restaurant.kz")).to_be_visible()


def test_full_registration_flow_reaches_onboarding(page: Page, live_server: str):
    page.goto(f"{live_server}/auth/register", wait_until="domcontentloaded")
    page.fill("#name", "Playwright Test Restaurant")
    page.fill("#email", _unique_email())
    page.fill("#password", "supersecret123")
    page.click("button[type=submit]")

    page.wait_for_url("**/onboarding**", wait_until="domcontentloaded", timeout=15000)
    assert "/onboarding" in page.url


def test_login_with_wrong_password_shows_error(page: Page, live_server: str):
    email = _unique_email()
    httpx.post(f"{live_server}/auth/register", json={
        "name": "Login Test", "slug": f"login-test-{uuid.uuid4().hex[:8]}",
        "email": email, "password": "supersecret123",
    })

    page.goto(f"{live_server}/auth/login", wait_until="domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", "wrong-password")
    page.click("button[type=submit]")

    error_banner = page.locator("#error-msg")
    expect(error_banner).to_be_visible(timeout=5000)
    expect(error_banner).to_contain_text("Неверный")


def test_login_and_dashboard_shows_sidebar_nav(page: Page, live_server: str):
    email = _unique_email()
    httpx.post(f"{live_server}/auth/register", json={
        "name": "Dashboard Test", "slug": f"dash-test-{uuid.uuid4().hex[:8]}",
        "email": email, "password": "supersecret123",
    })

    page.goto(f"{live_server}/auth/login", wait_until="domcontentloaded")
    page.fill("#email", email)
    page.fill("#password", "supersecret123")
    page.click("button[type=submit]")

    page.wait_for_url("**/dashboard**", wait_until="domcontentloaded", timeout=15000)
    sidebar = page.locator("nav.sidebar")
    expect(sidebar.get_by_role("link", name="Касса")).to_be_visible()
    expect(sidebar.get_by_role("link", name="Заказы", exact=True)).to_be_visible()


def test_pos_page_renders_menu_and_cart_updates_on_click(page: Page, live_server: str):
    email = _unique_email()
    reg = httpx.post(f"{live_server}/auth/register", json={
        "name": "POS UI Test", "slug": f"pos-ui-{uuid.uuid4().hex[:8]}",
        "email": email, "password": "supersecret123",
    }).json()
    token = reg["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    venue = httpx.post(f"{live_server}/api/venues/", json={"name": "Main Hall"}, headers=auth).json()
    httpx.post(f"{live_server}/api/menu/{venue['id']}", json={"name": "Плов", "price": 3200}, headers=auth)

    _log_in_as(page, live_server, token)
    page.goto(f"{live_server}/pos", wait_until="domcontentloaded")
    page.select_option("#venue-select", label="Main Hall")

    menu_item = page.locator(".pos-item", has_text="Плов")
    expect(menu_item).to_be_visible(timeout=5000)

    menu_item.click()
    expect(page.locator("#cart-total")).to_have_text("3 200 ₸")

    submit_btn = page.locator("#submit-btn")
    expect(submit_btn).to_be_enabled()


def test_settings_tables_add_and_render(page: Page, live_server: str):
    email = _unique_email()
    reg = httpx.post(f"{live_server}/auth/register", json={
        "name": "Tables UI Test", "slug": f"tables-ui-{uuid.uuid4().hex[:8]}",
        "email": email, "password": "supersecret123",
    }).json()
    token = reg["access_token"]
    httpx.post(
        f"{live_server}/api/venues/", json={"name": "Hall"},
        headers={"Authorization": f"Bearer {token}"},
    )

    _log_in_as(page, live_server, token)
    page.goto(f"{live_server}/settings/tables", wait_until="domcontentloaded")

    page.fill(".table-label-input", "12")
    page.fill(".table-seats-input", "6")
    with page.expect_navigation(wait_until="domcontentloaded", timeout=15000):
        page.click("button:has-text('Добавить стол')")

    expect(page.locator(".table-card", has_text="12")).to_be_visible(timeout=8000)
