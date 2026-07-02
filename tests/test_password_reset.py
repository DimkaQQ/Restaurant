"""Forgot-password / reset-password flow."""
from httpx import AsyncClient

from tests.conftest import register_network


async def test_forgot_password_always_returns_200(client: AsyncClient):
    """Must not leak whether an email is registered via response differences."""
    resp = await client.post("/auth/forgot-password", json={"email": "nobody@example.com"})
    assert resp.status_code == 200


async def test_reset_password_with_valid_token_changes_password(client: AsyncClient):
    reg = await register_network(client)

    from app.services.auth_service import create_password_reset_token
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == reg["email"]))).scalar_one()
        token = create_password_reset_token(user)

    resp = await client.post("/auth/reset-password", json={"token": token, "password": "brandnewpass123"})
    assert resp.status_code == 200, resp.text

    login_resp = await client.post("/auth/login", json={"email": reg["email"], "password": "brandnewpass123"})
    assert login_resp.status_code == 200

    old_login = await client.post("/auth/login", json={"email": reg["email"], "password": "supersecret123"})
    assert old_login.status_code == 401


async def test_reset_password_rejects_reused_token(client: AsyncClient):
    """The token embeds the current password hash, so it's single-use — using
    it once must invalidate it for a second attempt."""
    reg = await register_network(client)

    from app.services.auth_service import create_password_reset_token
    from app.database import AsyncSessionLocal
    from app.models.user import User
    from sqlalchemy import select

    async with AsyncSessionLocal() as db:
        user = (await db.execute(select(User).where(User.email == reg["email"]))).scalar_one()
        token = create_password_reset_token(user)

    resp1 = await client.post("/auth/reset-password", json={"token": token, "password": "firstnewpass123"})
    assert resp1.status_code == 200

    resp2 = await client.post("/auth/reset-password", json={"token": token, "password": "secondnewpass123"})
    assert resp2.status_code == 400


async def test_reset_password_rejects_garbage_token(client: AsyncClient):
    resp = await client.post("/auth/reset-password", json={"token": "not-a-real-token", "password": "whatever123"})
    assert resp.status_code == 400
