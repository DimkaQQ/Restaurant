"""Public online ordering page — accessible via QR code at table."""
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.guest import Guest
from app.ratelimit import limiter
from app.models.menu import MenuItem
from app.models.network import Network
from app.models.venue import Venue
from app.schemas.order import OrderCreate, OrderItemCreate
from app.services.online_order_i18n import get_guest_lang, t
from app.services.order_service import create_order
from app.templates_env import templates

router = APIRouter(tags=["online_order"])
logger = logging.getLogger(__name__)


@router.get("/order/{venue_id}", response_class=HTMLResponse)
async def online_menu_page(
    request: Request,
    venue_id: uuid.UUID,
    table: str | None = None,
    lang: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    venue = (await db.execute(
        select(Venue).options(selectinload(Venue.network))
        .where(Venue.id == venue_id, Venue.is_active == True)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")

    guest_lang = get_guest_lang(lang, request.cookies.get("guest_lang"), request.headers.get("accept-language"))
    strings = t(guest_lang)

    from app.models.menu import ModifierGroup
    items_result = await db.execute(
        select(MenuItem)
        .options(selectinload(MenuItem.modifier_groups).selectinload(ModifierGroup.options))
        .where(MenuItem.venue_id == venue_id, MenuItem.is_available == True)
        .order_by(MenuItem.category, MenuItem.name)
    )
    menu_items = items_result.scalars().all()

    categories: dict[str, list] = {}
    for item in menu_items:
        cat = item.category or strings["other_category"]
        categories.setdefault(cat, []).append({
            "id": str(item.id),
            "name": item.name,
            "description": item.description or "",
            "price": float(item.price),
            "image_url": item.image_url or "",
            "modifier_groups": [
                {
                    "id": str(g.id), "name": g.name, "required": g.required, "multi": g.multi,
                    "options": [
                        {"id": str(o.id), "name": o.name, "price_delta": float(o.price_delta)}
                        for o in g.options
                    ],
                }
                for g in item.modifier_groups
            ],
        })

    net = venue.network
    brand_name = net.brand_name if net and net.brand_name else None
    brand_color = net.brand_color if net and net.brand_color else None
    response = templates.TemplateResponse("online_order.html", {
        "request": request,
        "venue": venue,
        "categories": categories,
        "table": table or "",
        "guest_lang": guest_lang,
        "t": strings,
        "brand_name": brand_name,
        "brand_color": brand_color,
        "brand_logo": (net.logo_url if net and net.logo_url else None),
    })
    if lang:
        response.set_cookie("guest_lang", guest_lang, max_age=60 * 60 * 24 * 365)
    return response


_DEFAULT_BRAND_COLOR = "#0A0A0A"


@router.get("/order/{venue_id}/manifest.webmanifest")
async def guest_manifest(venue_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    """Per-venue PWA manifest generated on the fly. The guest installs the
    restaurant's own branded app (name, color, icon) — never "RestOS"."""
    venue = (await db.execute(
        select(Venue).options(selectinload(Venue.network))
        .where(Venue.id == venue_id, Venue.is_active == True)  # noqa: E712
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")
    net = venue.network
    name = (net.brand_name if net and net.brand_name else venue.name)
    color = (net.brand_color if net and net.brand_color else _DEFAULT_BRAND_COLOR)
    if net and net.logo_url:
        icons = [{"src": net.logo_url, "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}]
    else:
        icons = [
            {"src": "/static/favicon-192.png", "sizes": "192x192", "type": "image/png", "purpose": "any maskable"},
            {"src": "/static/favicon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"},
        ]
    manifest = {
        "name": name,
        "short_name": name[:12],
        "start_url": f"/order/{venue_id}",
        "scope": "/order/",
        "display": "standalone",
        "orientation": "portrait",
        "background_color": color,
        "theme_color": color,
        "icons": icons,
    }
    return JSONResponse(manifest, media_type="application/manifest+json",
                        headers={"Cache-Control": "public, max-age=300"})


# Guest service worker. Served from the site root so it can claim the "/order/"
# scope (a script's default scope is its own directory; a narrower scope like
# "/order/" needs no Service-Worker-Allowed header). Caches the menu shell and
# static assets so the QR menu opens instantly and survives flaky venue Wi-Fi.
_GUEST_SW_JS = """\
const CACHE = 'restos-guest-v1';
const ASSETS = ['/static/fonts/fonts.css', '/static/favicon-192.png', '/static/favicon-512.png'];

self.addEventListener('install', (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(ASSETS)).then(() => self.skipWaiting()));
});
self.addEventListener('activate', (e) => {
  e.waitUntil(
    caches.keys().then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});
self.addEventListener('fetch', (e) => {
  const req = e.request;
  if (req.method !== 'GET') return;                 // never cache order submits
  const url = new URL(req.url);
  if (url.origin !== location.origin) return;
  // The menu page itself: network-first so prices/stop-list stay fresh, with a
  // cached fallback so a dropped connection still shows the last good menu.
  if (url.pathname.startsWith('/order/')) {
    e.respondWith(
      fetch(req).then((res) => {
        const copy = res.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return res;
      }).catch(() => caches.match(req))
    );
    return;
  }
  // Static assets: cache-first.
  if (url.pathname.startsWith('/static/')) {
    e.respondWith(caches.match(req).then((hit) => hit || fetch(req).then((res) => {
      const copy = res.clone();
      caches.open(CACHE).then((c) => c.put(req, copy));
      return res;
    })));
  }
});
"""


@router.get("/guest-sw.js", include_in_schema=False)
async def guest_service_worker():
    return Response(
        _GUEST_SW_JS,
        media_type="application/javascript",
        headers={"Service-Worker-Allowed": "/order/", "Cache-Control": "no-cache"},
    )


class OnlineOrderItem(BaseModel):
    menu_item_id: uuid.UUID
    quantity: int = Field(1, ge=1)
    comment: str | None = None
    modifier_option_ids: list[uuid.UUID] = []


class OnlineOrderSubmit(BaseModel):
    items: list[OnlineOrderItem] = Field(..., min_length=1, max_length=50)
    guest_name: str | None = Field(None, max_length=100)
    guest_phone: str | None = Field(None, max_length=32)
    table_number: str | None = Field(None, max_length=20)  # matches the DB column
    notes: str | None = Field(None, max_length=500)
    guest_lang: str | None = None
    promo_code: str | None = Field(None, max_length=50)


@router.post("/order/{venue_id}/submit")
@limiter.limit("10/minute")
async def submit_online_order(
    request: Request,
    venue_id: uuid.UUID,
    data: OnlineOrderSubmit,
    db: AsyncSession = Depends(get_db),
):
    venue = (await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.is_active == True)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")

    if not data.items:
        raise HTTPException(status_code=400, detail="Корзина пуста")

    lang = data.guest_lang if data.guest_lang in ("ru", "kz", "en") else None
    strings = t(lang or "ru")

    # Find or create guest — the page's language selection is written back
    # to Guest.language so it's remembered for future bot broadcasts/orders,
    # since this page has no login to read an existing preference from.
    guest = None
    guest_name_clean = (data.guest_name or "").strip() or None
    if data.guest_phone and data.guest_phone.strip():
        phone_clean = data.guest_phone.strip()
        guest = (await db.execute(
            select(Guest).where(Guest.phone == phone_clean, Guest.network_id == venue.network_id)
        )).scalar_one_or_none()
        if not guest:
            guest = Guest(
                id=uuid.uuid4(),
                network_id=venue.network_id,
                name=guest_name_clean or strings["guest"],
                phone=phone_clean,
                language=lang or "ru",
            )
            db.add(guest)
            await db.flush()
        elif lang:
            guest.language = lang
    else:
        guest = Guest(
            id=uuid.uuid4(),
            network_id=venue.network_id,
            name=guest_name_clean or strings["online_guest"],
            phone=None,
            language=lang or "ru",
        )
        db.add(guest)
        await db.flush()

    order_data = OrderCreate(
        venue_id=venue_id,
        items=[
            OrderItemCreate(
                menu_item_id=i.menu_item_id, quantity=i.quantity, comment=i.comment,
                modifier_option_ids=i.modifier_option_ids,
            )
            for i in data.items
        ],
        notes=data.notes,
        table_number=data.table_number,
        source="online",
        promo_code=data.promo_code,
    )

    try:
        order = await create_order(order_data, guest, db, changed_by="online")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    from app.services.webhooks import dispatch_event
    await dispatch_event(db, venue.network_id, "order.created", {
        "id": str(order.id), "venue_id": str(order.venue_id), "status": order.status,
        "payment_status": order.payment_status, "total_amount": float(order.total_amount),
    })

    return {
        "ok": True,
        "order_id": str(order.id),
        "short_id": str(order.id)[:8].upper(),
        "total": float(order.total_amount),
        "points_earned": order.points_earned,
    }


@router.get("/order/{venue_id}/status/{order_id}")
async def guest_order_status(
    venue_id: uuid.UUID,
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Live status for the guest who just ordered. The order UUID is the
    capability: unguessable, returned only to the client that placed it.
    Response is deliberately minimal — status and short id only."""
    from app.models.order import Order
    order = (await db.execute(
        select(Order.status).where(Order.id == order_id, Order.venue_id == venue_id)
    )).scalar_one_or_none()
    if order is None:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    return {"status": order, "short_id": str(order_id)[:8].upper()}


# ── Public queue board (TV screen near the counter) ─────────────────────

@router.get("/queue/{venue_id}", response_class=HTMLResponse)
async def queue_board_page(
    request: Request,
    venue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    venue = (await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.is_active == True)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")
    return templates.TemplateResponse("queue_board.html", {
        "request": request,
        "venue": venue,
    })


@router.get("/queue/{venue_id}/data")
async def queue_board_data(
    venue_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Order numbers only — safe to show on a public screen. Limited to the
    last 24h so an order stuck in "confirmed" days ago doesn't haunt the TV."""
    from datetime import datetime, timedelta, timezone
    from app.models.order import Order
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    rows = (await db.execute(
        select(Order.id, Order.status)
        .where(
            Order.venue_id == venue_id,
            Order.status.in_(["confirmed", "preparing", "ready"]),
            Order.created_at >= since,
        )
        .order_by(Order.created_at)
        .limit(40)
    )).all()
    preparing = [str(r.id)[:8].upper() for r in rows if r.status in ("confirmed", "preparing")]
    ready = [str(r.id)[:8].upper() for r in rows if r.status == "ready"]
    return {"preparing": preparing, "ready": ready}
