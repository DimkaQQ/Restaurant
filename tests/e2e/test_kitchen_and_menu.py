import uuid

import httpx
from playwright.sync_api import Page, expect

from tests.e2e.test_ui_flows import _log_in_as, _unique_email


def test_menu_page_add_item_and_open_recipe_modal(page: Page, live_server: str):
    email = _unique_email()
    reg = httpx.post(f"{live_server}/auth/register", json={
        "name": "Menu UI Test", "slug": f"menu-ui-{uuid.uuid4().hex[:8]}",
        "email": email, "password": "supersecret123",
    }).json()
    token = reg["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    httpx.post(f"{live_server}/api/venues/", json={"name": "Main Hall"}, headers=auth)

    _log_in_as(page, live_server, token)
    page.goto(f"{live_server}/menu", wait_until="domcontentloaded")
    page.select_option("#venue-select", label="Main Hall")

    page.click("text=+ Добавить позицию")
    page.fill("#add-form input[name=name]", "Плов")
    page.fill("#add-form input[name=price]", "3200")
    page.click("#add-form button[type=submit]")

    menu_card = page.locator(".menu-card", has_text="Плов")
    expect(menu_card).to_be_visible(timeout=8000)

    # Open the recipe ("Техкарта") modal for the item we just created.
    menu_card.get_by_role("button", name="Техкарта").click()
    expect(page.locator("#recipe-modal")).to_be_visible()
    expect(page.locator("#recipe-item-name")).to_have_text("Плов")


def test_kitchen_board_shows_active_pos_order(page: Page, live_server: str):
    email = _unique_email()
    reg = httpx.post(f"{live_server}/auth/register", json={
        "name": "Kitchen UI Test", "slug": f"kitchen-ui-{uuid.uuid4().hex[:8]}",
        "email": email, "password": "supersecret123",
    }).json()
    token = reg["access_token"]
    auth = {"Authorization": f"Bearer {token}"}

    venue = httpx.post(f"{live_server}/api/venues/", json={"name": "Main Hall"}, headers=auth).json()
    item = httpx.post(f"{live_server}/api/menu/{venue['id']}", json={"name": "Лагман", "price": 2800}, headers=auth).json()
    httpx.post(
        f"{live_server}/api/pos/order",
        json={"venue_id": venue["id"], "items": [{"menu_item_id": item["id"], "quantity": 1}]},
        headers=auth,
    )

    _log_in_as(page, live_server, token)
    page.goto(f"{live_server}/kitchen", wait_until="domcontentloaded")
    expect(page.locator(".kds-item", has_text="Лагман")).to_be_visible(timeout=10000)
