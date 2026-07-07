import asyncio
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import text

from app.config import settings
from app.database import engine
from app.models import *  # noqa: F401,F403 — registers all models with Base
from app.routers import auth, dashboard, venues, menu, orders, guests, analytics, staff, settings as settings_router, inventory, finance, shifts, bot_api, online_order, billing, platform_admin, pos, legal, cash_shifts, purchasing, api_v1
from app.services.cleanup_service import stale_order_cleanup_loop
from app.templates_env import templates

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

from app.ratelimit import limiter  # noqa: E402 — proxy-aware, shared with routers
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


_EXPECTED_ORIGIN = urlsplit(settings.PUBLIC_URL).netloc
# Server-to-server callbacks never carry our cookies and are authenticated
# their own way (Stripe signs its webhook body; the bot uses a shared secret) —
# an Origin/Referer check would just reject legitimate traffic from them.
_CSRF_EXEMPT_PREFIXES = ("/billing/webhook", "/api/bot", "/health")


@app.middleware("http")
async def silent_session_refresh(request: Request, call_next):
    """Access tokens are deliberately short-lived (30 min). When one expires
    but the httpOnly refresh cookie is still valid, mint a fresh access token
    transparently: inject it into this request and set the cookie on the
    response. This is what keeps a register/kitchen tablet logged in for
    weeks without ever holding a long-lived access token."""
    new_access = None
    access = request.cookies.get("access_token")
    refresh = request.cookies.get("refresh_token")
    has_auth_header = bool(request.headers.get("authorization"))
    if refresh and not has_auth_header:
        from app.services.auth_service import decode_token
        payload = decode_token(access) if access else None
        if not payload or payload.get("typ") == "refresh":
            from app.database import AsyncSessionLocal
            from app.services.auth_service import refresh_session
            async with AsyncSessionLocal() as db:
                refreshed = await refresh_session(refresh, db)
            if refreshed:
                _, new_access = refreshed
                # make THIS request authenticated too, not just the next one
                request.scope["headers"] = list(request.scope["headers"]) + [
                    (b"authorization", b"Bearer " + new_access.encode())
                ]
    response = await call_next(request)
    if new_access:
        response.set_cookie(
            key="access_token", value=new_access,
            httponly=True, samesite="lax",
            secure=settings.PUBLIC_URL.startswith("https://"),
            max_age=60 * settings.ACCESS_TOKEN_EXPIRE_MINUTES,
        )
    return response


@app.middleware("http")
async def csrf_origin_check(request: Request, call_next):
    # SameSite=Lax already blocks the cookie on cross-site POST/PUT/PATCH/DELETE
    # in modern browsers, but this is cheap defense-in-depth for older/edge-case
    # clients: any unsafe request authenticated purely by cookie (no Authorization
    # header — that path can't be forged cross-site anyway, since a remote page
    # can't read our httpOnly cookie or another origin's localStorage token) must
    # present an Origin/Referer that matches this deployment.
    if (
        settings.CSRF_ENABLED
        and request.method in ("POST", "PUT", "PATCH", "DELETE")
        and not request.headers.get("authorization")
        # either auth cookie counts: silent refresh can authenticate a
        # request from the refresh cookie alone, so it must be CSRF-checked too
        and (request.cookies.get("access_token") or request.cookies.get("refresh_token"))
        and not any(request.url.path.startswith(p) for p in _CSRF_EXEMPT_PREFIXES)
    ):
        origin = request.headers.get("origin") or request.headers.get("referer")
        origin_host = urlsplit(origin).netloc if origin else ""
        # Same-origin is judged against the Host the request actually came to,
        # not only PUBLIC_URL: a browser never lets a page forge Origin, so
        # Origin == Host is cross-site-safe no matter how the deployment is
        # addressed (IP:port, second domain, PUBLIC_URL left at its default).
        # PUBLIC_URL stays as an extra allowed value for proxies that rewrite
        # Host on the way in.
        allowed = {_EXPECTED_ORIGIN, request.url.netloc, request.headers.get("host", "")}
        allowed.discard("")
        if origin_host not in allowed:
            return JSONResponse(status_code=403, content={"detail": "Запрос отклонён (CSRF-проверка)"})
    return await call_next(request)


@app.middleware("http")
async def lang_cookie(request: Request, call_next):
    """A `?lang=en`/`?lang=ru` on any page persists the choice for every
    subsequent request — lets the language switcher live once in the sidebar
    (base.html) instead of every route setting its own cookie."""
    response = await call_next(request)
    lang = request.query_params.get("lang")
    if lang in ("ru", "en"):
        response.set_cookie("lang", lang, max_age=60 * 60 * 24 * 365)
    return response


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


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    # Served from the root path so the service worker's scope covers the whole
    # app (a worker served from /static/js/ could only control /static/js/).
    from fastapi.responses import FileResponse
    return FileResponse("app/static/js/sw.js", media_type="application/javascript")


@app.get("/health", include_in_schema=False)
async def health():
    """Liveness/readiness probe for uptime monitors and load balancers."""
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok", "db": "ok"}
    except Exception:
        logger.exception("Health check: database unreachable")
        return JSONResponse(status_code=503, content={"status": "degraded", "db": "unreachable"})

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
app.include_router(cash_shifts.router)
app.include_router(purchasing.router)
app.include_router(api_v1.router)


def _wants_html(request: Request) -> bool:
    return "text/html" in request.headers.get("accept", "")


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    # FastAPI's own HTTPException raises from routers already carry a
    # translated `detail` and correct status — this only intercepts the
    # ones nothing handled explicitly (chiefly 404s hitting an unknown
    # path) so a browser gets the branded page instead of raw JSON.
    if exc.status_code == 404 and _wants_html(request):
        return templates.TemplateResponse("error_404.html", {"request": request}, status_code=404)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    if settings.SENTRY_DSN:
        import sentry_sdk
        sentry_sdk.capture_exception(exc)
    if _wants_html(request):
        return templates.TemplateResponse("error_500.html", {"request": request}, status_code=500)
    return JSONResponse(status_code=500, content={"detail": "Внутренняя ошибка сервера"})


@app.get("/health")
async def health_check():
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error("Health check failed: %s", e)
        return JSONResponse(status_code=503, content={"status": "error", "detail": str(e)})
