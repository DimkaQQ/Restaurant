import uuid
from datetime import date, time

from httpx import AsyncClient
from sqlalchemy import select

from app.models.network import Network
from app.models.staff import Staff
from tests.conftest import register_network, auth_headers


async def _create_venue(client: AsyncClient, token: str, name: str = "Main Hall") -> str:
    resp = await client.post("/api/venues/", json={"name": name}, headers=auth_headers(token))
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


async def _create_staff(db, slug: str, venue_id: str, name: str = "Ivan") -> str:
    network = (await db.execute(select(Network).where(Network.slug == slug))).scalar_one()
    staff = Staff(id=uuid.uuid4(), network_id=network.id, venue_id=uuid.UUID(venue_id), name=name, role="waiter")
    db.add(staff)
    await db.commit()
    return str(staff.id)


async def test_create_shift_and_list_it(client: AsyncClient, db):
    reg = await register_network(client)
    venue_id = await _create_venue(client, reg["token"])
    staff_id = await _create_staff(db, reg["slug"], venue_id)

    resp = await client.post(
        "/api/shifts",
        json={
            "staff_id": staff_id, "venue_id": venue_id,
            "shift_date": str(date.today()), "start_time": "09:00:00", "end_time": "18:00:00",
        },
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200, resp.text

    page_resp = await client.get("/shifts", headers=auth_headers(reg["token"]))
    assert page_resp.status_code == 200
    assert "Ivan" in page_resp.text


async def test_shift_rejects_end_before_start(client: AsyncClient, db):
    reg = await register_network(client)
    venue_id = await _create_venue(client, reg["token"])
    staff_id = await _create_staff(db, reg["slug"], venue_id)

    resp = await client.post(
        "/api/shifts",
        json={
            "staff_id": staff_id, "venue_id": venue_id,
            "shift_date": str(date.today()), "start_time": "18:00:00", "end_time": "09:00:00",
        },
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 400


async def test_cannot_assign_shift_to_staff_from_another_venue(client: AsyncClient, db):
    reg = await register_network(client)
    venue_a = await _create_venue(client, reg["token"], "Venue A")
    venue_b = await _create_venue(client, reg["token"], "Venue B")
    staff_id = await _create_staff(db, reg["slug"], venue_a)

    resp = await client.post(
        "/api/shifts",
        json={
            "staff_id": staff_id, "venue_id": venue_b,
            "shift_date": str(date.today()), "start_time": "09:00:00", "end_time": "18:00:00",
        },
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 404


async def test_recipe_rejects_ingredient_from_another_venue(client: AsyncClient):
    reg = await register_network(client)
    venue_a = await _create_venue(client, reg["token"], "Venue A")
    venue_b = await _create_venue(client, reg["token"], "Venue B")

    item_resp = await client.post(
        f"/api/menu/{venue_a}", json={"name": "Burger", "price": 2000}, headers=auth_headers(reg["token"])
    )
    item_id = item_resp.json()["id"]

    ing_resp = await client.post(
        "/api/inventory",
        json={"venue_id": venue_b, "name": "Buns", "unit": "шт", "quantity": 100},
        headers=auth_headers(reg["token"]),
    )
    ingredient_id = ing_resp.json()["id"]

    resp = await client.put(
        f"/api/menu/{item_id}/recipe",
        json=[{"ingredient_id": ingredient_id, "quantity": 1}],
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 400
