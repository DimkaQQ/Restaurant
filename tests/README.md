# Running the tests

There are two independent suites — they use incompatible event-loop models
(async DB session vs. sync browser automation) and **must run as separate
pytest processes**. Running them together in one `pytest` invocation causes
a `Runner.run() cannot be called from a running event loop` error.

- `tests/` (backend) — hits the app in-process via `httpx.AsyncClient` +
  `ASGITransport`, no browser, no real HTTP server. Fast.
- `tests/e2e/` (browser) — launches a real Chromium against a real `uvicorn`
  server, fills in actual forms, reads actual rendered pixels/text. Slower,
  but catches broken templates/JS that the backend suite can't see (it's
  what caught the login/dashboard rendering and POS cart behavior working
  end-to-end, not just the API responses behind them).

Both run against a real PostgreSQL database (not SQLite/mocks) — the app
relies on Postgres-specific behavior (UUID columns, `gen_random_uuid()`,
`SELECT ... FOR UPDATE`), so a fake DB would hide real bugs. Two backend bugs
(`create_order`/`cancel_order` crashing on response serialization) were only
found once something exercised those endpoints end-to-end against a real DB.

## One-time setup

```bash
# Create a dedicated test database (separate from your dev/prod one)
sudo -u postgres psql -c "CREATE USER restos_test WITH PASSWORD 'test' SUPERUSER;"
sudo -u postgres psql -c "CREATE DATABASE restos_test OWNER restos_test;"

# Apply migrations to it
SECRET_KEY=x DATABASE_URL=postgresql+asyncpg://restos_test:test@localhost/restos_test \
  alembic upgrade head

pip install -r requirements-dev.txt
```

For the browser suite, Playwright needs Chromium installed:
```bash
playwright install chromium
```
(If Chromium is already provisioned elsewhere in your environment at a fixed
path, set `PLAYWRIGHT_CHROMIUM_PATH` instead of reinstalling — see
`tests/e2e/conftest.py`.)

## Running

```bash
make test       # backend suite
make test-e2e   # browser suite
```

Each test truncates all tables beforehand, so tests don't need to clean up
after themselves and can run in any order.

If your test DB isn't at the default URL, set `TEST_DATABASE_URL` before running.
