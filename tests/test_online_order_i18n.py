"""Guest-facing QR/online-order page language handling (ru/kz/en) —
separate mechanism from the staff RU/EN switcher since the guest has no
login. Language comes from ?lang=, falls back to Accept-Language, and is
written back to Guest.language once a guest is identified by phone."""
from httpx import AsyncClient
from sqlalchemy import select

from app.models.guest import Guest
from app.models.venue import Venue
from tests.conftest import register_network, auth_headers


async def _setup_venue_with_item(client: AsyncClient, token: str):
    venue_resp = await client.post("/api/venues/", json={"name": "QR Hall"}, headers=auth_headers(token))
    venue_id = venue_resp.json()["id"]
    item_resp = await client.post(
        f"/api/menu/{venue_id}", json={"name": "Burger", "price": 2500}, headers=auth_headers(token)
    )
    assert item_resp.status_code == 200
    return venue_id


async def test_online_order_page_defaults_to_russian(client: AsyncClient):
    reg = await register_network(client)
    venue_id = await _setup_venue_with_item(client, reg["token"])

    resp = await client.get(f"/order/{venue_id}")
    assert resp.status_code == 200
    assert "Заказать" in resp.text


async def test_online_order_page_switches_to_kazakh(client: AsyncClient):
    reg = await register_network(client)
    venue_id = await _setup_venue_with_item(client, reg["token"])

    resp = await client.get(f"/order/{venue_id}?lang=kz")
    assert resp.status_code == 200
    assert "Тапсырыс беру" in resp.text
    assert resp.cookies.get("guest_lang") == "kz"


async def test_online_order_page_switches_to_english(client: AsyncClient):
    reg = await register_network(client)
    venue_id = await _setup_venue_with_item(client, reg["token"])

    resp = await client.get(f"/order/{venue_id}?lang=en")
    assert resp.status_code == 200
    assert "Place order" in resp.text


async def test_online_order_page_respects_accept_language_header(client: AsyncClient):
    reg = await register_network(client)
    venue_id = await _setup_venue_with_item(client, reg["token"])

    resp = await client.get(f"/order/{venue_id}", headers={"Accept-Language": "kk-KZ,kk;q=0.9"})
    assert "Тапсырыс беру" in resp.text


async def test_guest_language_persisted_on_order_submit(client: AsyncClient, db):
    reg = await register_network(client)
    venue_id = await _setup_venue_with_item(client, reg["token"])
    menu_resp = await client.get(f"/api/menu/{venue_id}", headers=auth_headers(reg["token"]))
    item_id = menu_resp.json()[0]["id"]

    resp = await client.post(
        f"/order/{venue_id}/submit",
        json={
            "items": [{"menu_item_id": item_id, "quantity": 1}],
            "guest_phone": "+77771234567",
            "guest_lang": "kz",
        },
    )
    assert resp.status_code == 200, resp.text

    guest = (await db.execute(select(Guest).where(Guest.phone == "+77771234567"))).scalar_one()
    assert guest.language == "kz"


async def test_guest_language_updates_on_repeat_order(client: AsyncClient, db):
    reg = await register_network(client)
    venue_id = await _setup_venue_with_item(client, reg["token"])
    menu_resp = await client.get(f"/api/menu/{venue_id}", headers=auth_headers(reg["token"]))
    item_id = menu_resp.json()[0]["id"]

    await client.post(
        f"/order/{venue_id}/submit",
        json={"items": [{"menu_item_id": item_id, "quantity": 1}], "guest_phone": "+77779998877", "guest_lang": "ru"},
    )
    await client.post(
        f"/order/{venue_id}/submit",
        json={"items": [{"menu_item_id": item_id, "quantity": 1}], "guest_phone": "+77779998877", "guest_lang": "en"},
    )

    guest = (await db.execute(select(Guest).where(Guest.phone == "+77779998877"))).scalar_one()
    assert guest.language == "en"
