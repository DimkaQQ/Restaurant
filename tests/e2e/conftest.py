"""Browser-driven E2E tests: a real uvicorn server + real Chromium, so these
catch what backend-only tests can't — broken templates, JS errors, elements
that never render, forms that don't actually submit."""
import asyncio
import os
import socket
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import asyncpg
import pytest
from playwright.sync_api import sync_playwright

# Same DB the async backend suite uses (see tests/conftest.py) — the server
# subprocess and the test process both talk to the same Postgres instance.
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+asyncpg://restos_test:test@localhost/restos_test"
)
# asyncpg wants a plain postgres:// DSN, not SQLAlchemy's postgresql+asyncpg:// one.
_ASYNCPG_DSN = TEST_DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")


async def _truncate_all_tables():
    conn = await asyncpg.connect(_ASYNCPG_DSN)
    try:
        rows = await conn.fetch(
            "SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename != 'alembic_version'"
        )
        if rows:
            names = ", ".join(r["tablename"] for r in rows)
            await conn.execute(f"TRUNCATE {names} RESTART IDENTITY CASCADE")
    finally:
        await conn.close()


@pytest.fixture(autouse=True)
def _clean_db():
    # pytest-asyncio (asyncio_mode=auto, configured repo-wide in pytest.ini)
    # keeps a session event loop running even in this all-sync test file, so
    # asyncio.run() here would hit "cannot be called from a running event
    # loop" — run it on its own thread instead, which has no such loop.
    with ThreadPoolExecutor(max_workers=1) as executor:
        executor.submit(asyncio.run, _truncate_all_tables()).result()
    yield


def _resolve_chromium_path() -> str | None:
    """Explicit env var wins; otherwise fall back to this sandbox's
    pre-provisioned Chromium if present, else None (Playwright resolves its
    own default — requires `playwright install chromium` to have been run)."""
    if os.environ.get("PLAYWRIGHT_CHROMIUM_PATH"):
        return os.environ["PLAYWRIGHT_CHROMIUM_PATH"]
    sandbox_default = "/opt/pw-browsers/chromium-1194/chrome-linux/chrome"
    return sandbox_default if os.path.exists(sandbox_default) else None


CHROMIUM_PATH = _resolve_chromium_path()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="session")
def live_server():
    port = _free_port()
    base_url = f"http://127.0.0.1:{port}"
    env = {
        **os.environ,
        "SECRET_KEY": "e2e-test-secret",
        "DATABASE_URL": TEST_DATABASE_URL,
        "BOT_API_SECRET": "test-bot-secret",
        "PUBLIC_URL": base_url,
    }
    proc = subprocess.Popen(
        ["uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", str(port)],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(50):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            proc.terminate()
            raise RuntimeError("Server never came up: " + (proc.stdout.read().decode() if proc.stdout else ""))
        yield base_url
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=CHROMIUM_PATH)
        yield browser
        browser.close()


@pytest.fixture
def page(browser):
    context = browser.new_context()
    page = context.new_page()
    # Templates pull Google Fonts / htmx from public CDNs; this sandbox's
    # outbound network can be slow/flaky to reach them, which would otherwise
    # stall Playwright's default "wait for full load" navigations. Tests only
    # need the page's own HTML/JS, not those optional assets.
    page.set_default_navigation_timeout(15000)
    page.set_default_timeout(15000)
    yield page
    context.close()
