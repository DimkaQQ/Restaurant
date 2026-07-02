"""Plan-tier limits (venues/staff) — advertised on the billing page, must
actually be enforced. Trials stay unrestricted so a prospect can fully
evaluate the product; limits only apply once a paid subscription is active."""
from httpx import AsyncClient
from sqlalchemy import select

from app.models.subscription import Subscription
from tests.conftest import register_network, auth_headers


async def _activate_plan(db, network_id, plan: str):
    sub = (await db.execute(select(Subscription).where(Subscription.network_id == network_id))).scalar_one()
    sub.plan = plan
    sub.status = "active"
    await db.commit()


async def test_trial_network_has_no_venue_limit(client: AsyncClient, db):
    reg = await register_network(client)
    from app.models.network import Network
    network = (await db.execute(select(Network).where(Network.slug == reg["slug"]))).scalar_one()

    # Starter's advertised limit is 1 venue — trial should allow more.
    for i in range(3):
        resp = await client.post("/api/venues/", json={"name": f"Venue {i}"}, headers=auth_headers(reg["token"]))
        assert resp.status_code == 200, resp.text


async def test_starter_plan_blocks_second_venue(client: AsyncClient, db):
    reg = await register_network(client)
    from app.models.network import Network
    network = (await db.execute(select(Network).where(Network.slug == reg["slug"]))).scalar_one()
    await _activate_plan(db, network.id, "starter")

    first = await client.post("/api/venues/", json={"name": "Main Hall"}, headers=auth_headers(reg["token"]))
    assert first.status_code == 200, first.text

    second = await client.post("/api/venues/", json={"name": "Second Hall"}, headers=auth_headers(reg["token"]))
    assert second.status_code == 402
    assert "лимит" in second.json()["detail"].lower()


async def test_pro_plan_allows_up_to_five_venues(client: AsyncClient, db):
    reg = await register_network(client)
    from app.models.network import Network
    network = (await db.execute(select(Network).where(Network.slug == reg["slug"]))).scalar_one()
    await _activate_plan(db, network.id, "pro")

    for i in range(5):
        resp = await client.post("/api/venues/", json={"name": f"Venue {i}"}, headers=auth_headers(reg["token"]))
        assert resp.status_code == 200, resp.text

    sixth = await client.post("/api/venues/", json={"name": "Venue 6"}, headers=auth_headers(reg["token"]))
    assert sixth.status_code == 402


async def test_enterprise_plan_has_no_venue_limit(client: AsyncClient, db):
    reg = await register_network(client)
    from app.models.network import Network
    network = (await db.execute(select(Network).where(Network.slug == reg["slug"]))).scalar_one()
    await _activate_plan(db, network.id, "enterprise")

    for i in range(7):
        resp = await client.post("/api/venues/", json={"name": f"Venue {i}"}, headers=auth_headers(reg["token"]))
        assert resp.status_code == 200, resp.text


async def test_starter_plan_blocks_fourth_staff_member(client: AsyncClient, db):
    reg = await register_network(client)
    from app.models.network import Network
    network = (await db.execute(select(Network).where(Network.slug == reg["slug"]))).scalar_one()
    await _activate_plan(db, network.id, "starter")

    # Owner counts as 1 of the 3 — 2 more should succeed, the 3rd should be blocked.
    for i in range(2):
        resp = await client.post(
            "/settings/users",
            json={"email": f"staff{i}@example.com", "password": "somesecurepass", "role": "manager"},
            headers=auth_headers(reg["token"]),
        )
        assert resp.status_code == 200, resp.text

    blocked = await client.post(
        "/settings/users",
        json={"email": "onemore@example.com", "password": "somesecurepass", "role": "manager"},
        headers=auth_headers(reg["token"]),
    )
    assert blocked.status_code == 402
