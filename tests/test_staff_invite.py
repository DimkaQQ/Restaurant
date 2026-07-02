"""Owner creates staff accounts with an email invite (blank password) or
directly with a chosen password (backward-compatible path)."""
from httpx import AsyncClient
from sqlalchemy import select

from app.models.user import User
from tests.conftest import register_network, auth_headers


async def test_create_user_without_password_sends_invite(client: AsyncClient, db):
    reg = await register_network(client)
    resp = await client.post(
        "/settings/users",
        json={"email": "invitee@example.com", "password": "", "role": "manager"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["invited"] is True

    user = (await db.execute(select(User).where(User.email == "invitee@example.com"))).scalar_one()
    assert user.hashed_password  # a random unguessable password was set


async def test_create_user_with_password_does_not_invite(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.post(
        "/settings/users",
        json={"email": "direct@example.com", "password": "somesecurepass", "role": "cashier"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["invited"] is False


async def test_invited_user_can_set_password_via_reset_link(client: AsyncClient, db):
    reg = await register_network(client)
    await client.post(
        "/settings/users",
        json={"email": "setpw@example.com", "password": "", "role": "manager"},
        headers=auth_headers(reg["token"]),
    )
    user = (await db.execute(select(User).where(User.email == "setpw@example.com"))).scalar_one()

    from app.services.auth_service import create_password_reset_token
    token = create_password_reset_token(user, expire_minutes=60 * 24 * 7)

    resp = await client.post("/auth/reset-password", json={"token": token, "password": "mynewpassword1"})
    assert resp.status_code == 200

    login_resp = await client.post("/auth/login", json={"email": "setpw@example.com", "password": "mynewpassword1"})
    assert login_resp.status_code == 200


async def test_create_user_requires_owner_role(client: AsyncClient):
    reg = await register_network(client)
    # Create a non-owner user directly, then try to invite as them.
    resp = await client.post(
        "/settings/users",
        json={"email": "manager1@example.com", "password": "somesecurepass", "role": "manager"},
        headers=auth_headers(reg["token"]),
    )
    assert resp.status_code == 200

    manager_login = await client.post("/auth/login", json={"email": "manager1@example.com", "password": "somesecurepass"})
    manager_token = manager_login.json()["access_token"]

    resp = await client.post(
        "/settings/users",
        json={"email": "another@example.com", "password": "somesecurepass", "role": "manager"},
        headers=auth_headers(manager_token),
    )
    assert resp.status_code == 403
