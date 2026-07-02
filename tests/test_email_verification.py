"""Email verification: soft-gated (registration works without it, doesn't
block dashboard access), verifiable via a time-limited link."""
from httpx import AsyncClient
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.user import User
from app.services.auth_service import create_email_verification_token
from tests.conftest import register_network, auth_headers


async def test_new_account_starts_unverified(client: AsyncClient, db):
    reg = await register_network(client)
    user = (await db.execute(select(User).where(User.email == reg["email"]))).scalar_one()
    assert user.email_verified is False


async def test_verify_email_with_valid_token(client: AsyncClient):
    reg = await register_network(client)

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == reg["email"]))).scalar_one()
        token = create_email_verification_token(user)

    resp = await client.get(f"/auth/verify-email?token={token}")
    assert resp.status_code == 200
    assert "подтверждён" in resp.text.lower()

    async with AsyncSessionLocal() as session:
        user = (await session.execute(select(User).where(User.email == reg["email"]))).scalar_one()
        assert user.email_verified is True


async def test_verify_email_rejects_garbage_token(client: AsyncClient):
    resp = await client.get("/auth/verify-email?token=not-a-real-token")
    assert resp.status_code == 400


async def test_resend_verification_requires_auth(client: AsyncClient):
    resp = await client.post("/auth/resend-verification")
    assert resp.status_code in (401, 307)


async def test_resend_verification_when_authenticated(client: AsyncClient):
    reg = await register_network(client)
    resp = await client.post("/auth/resend-verification", headers=auth_headers(reg["token"]))
    assert resp.status_code == 200
