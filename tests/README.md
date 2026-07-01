# Running the tests

The suite runs against a real PostgreSQL database (not SQLite/mocks) — the
app relies on Postgres-specific behavior (UUID columns, `gen_random_uuid()`,
`SELECT ... FOR UPDATE`), so a fake DB would hide real bugs. Two of the bugs
these tests currently catch (`create_order`/`cancel_order` crashing on
response serialization) were never seen before because nothing had exercised
those endpoints end-to-end against a real database.

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

## Running

```bash
make test
# or directly:
python -m pytest tests/ -v
```

Each test truncates all tables beforehand (see `tests/conftest.py::_clean_db`),
so tests don't need to clean up after themselves and can run in any order.

If your test DB isn't at the default URL, set `TEST_DATABASE_URL` before running.
