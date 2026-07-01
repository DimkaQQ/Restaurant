import asyncio
import os
import uuid

# Must happen before any `app.*` import, since app.config.Settings() is read
# once at import time and app.database creates its engine from it eagerly.
os.environ.setdefault("SECRET_KEY", "test-secret-key")
os.environ["DATABASE_URL"] = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://restos_test:test@localhost/restos_test"
)
# Set like production would (see .env.example) so bot-secret-gated endpoints
# actually enforce the check instead of silently no-op'ing for "local dev".
os.environ.setdefault("BOT_API_SECRET", "test-bot-secret")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import text

from app.database import engine, AsyncSessionLocal
from app.main import app

# app.database's engine/connection pool is a module-level singleton bound to
# whichever event loop first uses it, so all tests must share one loop
# (configured via asyncio_default_test_loop_scope=session in pytest.ini)
# instead of pytest-asyncio's per-test default.


@pytest_asyncio.fixture(autouse=True)
async def _clean_db():
    """Truncate every table before each test so tests don't see each other's data.
    Assumes migrations have already been applied to the test DB (see README)."""
    async with engine.begin() as conn:
        rows = await conn.execute(text(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename != 'alembic_version'"
        ))
        table_names = [row[0] for row in rows]
        if table_names:
            await conn.execute(text(f"TRUNCATE {', '.join(table_names)} RESTART IDENTITY CASCADE"))
    yield


@pytest_asyncio.fixture
async def client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture
async def db():
    async with AsyncSessionLocal() as session:
        yield session


async def register_network(client: AsyncClient, name: str = "Test Restaurant") -> dict:
    """Register a fresh network+owner and return {"token", "email", "network_name"}.
    Uses the real /auth/register endpoint so tests exercise the actual signup path."""
    slug = f"test-{uuid.uuid4().hex[:10]}"
    email = f"owner-{uuid.uuid4().hex[:8]}@example.com"
    resp = await client.post("/auth/register", json={
        "name": name,
        "slug": slug,
        "email": email,
        "password": "supersecret123",
    })
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"token": token, "email": email, "slug": slug}


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}
