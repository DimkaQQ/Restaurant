"""Regression tests for the subscription access gate (app/routers/deps.py).
Covers the past_due bug found in security review: billing.html displayed
past_due as blocked, but the gate only checked suspended/cancelled."""
from datetime import datetime, timedelta, timezone

from httpx import AsyncClient
from sqlalchemy import select

from app.models.network import Network
from app.models.subscription import Subscription
from tests.conftest import register_network, auth_headers


async def _set_subscription(db, slug: str, **fields):
    network = (await db.execute(select(Network).where(Network.slug == slug))).scalar_one()
    sub = (await db.execute(select(Subscription).where(Subscription.network_id == network.id))).scalar_one()
    for k, v in fields.items():
        setattr(sub, k, v)
    await db.commit()


async def test_active_trial_has_full_access(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.get("/dashboard", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200


async def test_expired_trial_is_blocked(client: AsyncClient, db):
    reg = await register_network(client)
    await _set_subscription(db, reg["slug"], trial_ends_at=datetime.now(timezone.utc) - timedelta(days=1))

    resp = await client.get("/dashboard", headers=auth_headers(reg["token"]))
    assert resp.status_code == 402


async def test_past_due_subscription_is_blocked(client: AsyncClient, db):
    """This is the exact bug the security audit found: past_due was shown as
    blocked in the UI but the gate let it through."""
    reg = await register_network(client)
    await _set_subscription(db, reg["slug"], status="past_due")

    resp = await client.get("/dashboard", headers=auth_headers(reg["token"]))
    assert resp.status_code == 402


async def test_suspended_subscription_is_blocked(client: AsyncClient, db):
    reg = await register_network(client)
    await _set_subscription(db, reg["slug"], status="suspended")

    resp = await client.get("/dashboard", headers=auth_headers(reg["token"]))
    assert resp.status_code == 402


async def test_blocked_subscription_can_still_reach_billing_page(client: AsyncClient, db):
    reg = await register_network(client)
    await _set_subscription(db, reg["slug"], status="suspended")

    resp = await client.get("/billing", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
