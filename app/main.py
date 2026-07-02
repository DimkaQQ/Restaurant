import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.models import *  # noqa: F401,F403 — registers all models with Base
from app.routers import auth, dashboard, venues, menu, orders, guests, analytics, staff, settings as settings_router, inventory, finance, shifts, bot_api, online_order, billing, platform_admin, pos, legal
from app.services.cleanup_service import stale_order_cleanup_loop

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

if settings.SENTRY_DSN:
    import sentry_sdk
    sentry_sdk.init(dsn=settings.SENTRY_DSN, traces_sample_rate=0.1)
    logger.info("Sentry error monitoring enabled")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("RestOS starting up")
    cleanup_task = asyncio.create_task(stale_order_cleanup_loop())
    yield
    cleanup_task.cancel()
    await engine.dispose()
    logger.info("RestOS shut down")


app = FastAPI(title="RestOS", version="1.0.0", lifespan=lifespan)

limiter = Limiter(key_func=get_remote_address, enabled=settings.RATE_LIMIT_ENABLED)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    # Inline <script>/<style> are used throughout the Jinja templates (HTMX
    # attributes, small page scripts), so 'unsafe-inline' stays until those
    # are extracted — CSP here is still worth it for locking down external
    # sources (script/frame injection, data exfil) even without nonces.
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: https:; "
        "frame-ancestors 'none'"
    )
    if settings.PUBLIC_URL.startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response


app.mount("/static", StaticFiles(directory="app/static"), name="static")

app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(venues.router)
app.include_router(menu.router)
app.include_router(orders.router)
app.include_router(guests.router)
app.include_router(analytics.router)
app.include_router(staff.router)
app.include_router(settings_router.router)
app.include_router(inventory.router)
app.include_router(finance.router)
app.include_router(shifts.router)
app.include_router(bot_api.router)
app.include_router(online_order.router)
app.include_router(billing.router)
app.include_router(platform_admin.router)
app.include_router(pos.router)
app.include_router(legal.router)


@app.get("/health")
async def health_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})
