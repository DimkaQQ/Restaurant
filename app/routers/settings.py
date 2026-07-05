from app.templates_env import templates
import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload


import os as _os

from app.database import get_db
from app.models.broadcast import Broadcast
from app.models.guest import Guest
from app.models.inventory import Ingredient
from app.models.menu import MenuItem
from app.models.network import Network
from app.models.order import Order
from app.models.staff import Staff
from app.models.table import Table
from app.models.user import User
from app.models.venue import Venue
from app.routers.deps import get_current_user_dep
from app.services.auth_service import hash_password
from app.services.plan_limits import check_staff_limit

_BOT_NAME = _os.getenv("BOT_NAME", "")

router = APIRouter(prefix="/settings", tags=["settings"])


logger = logging.getLogger(__name__)


class BroadcastCreate(BaseModel):
    message: str
    lang_filter: str | None = None



def _require_admin(current_user: User) -> None:
    """Administrator or owner — broadcasts and other venue-администратор tasks."""
    from app.routers.deps import role_at_least
    if not role_at_least(current_user, "administrator"):
        raise HTTPException(status_code=403, detail="Недостаточно прав")


def _require_owner(current_user: User) -> None:
    if current_user.role != "owner":
        raise HTTPException(status_code=403, detail="Доступ запрещён: только для владельца")


@router.get("/api/export")
async def export_network_data(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Self-service GDPR-style data export — the portability promise made in
    the privacy policy. Owner-only; excludes credentials (password hashes,
    fiscal API keys) and internal-only fields."""
    _require_owner(current_user)
    network_id = current_user.network_id

    network = (await db.execute(select(Network).where(Network.id == network_id))).scalar_one()
    venues = (await db.execute(select(Venue).where(Venue.network_id == network_id))).scalars().all()
    venue_ids = [v.id for v in venues]

    users = (await db.execute(select(User).where(User.network_id == network_id))).scalars().all()
    staff = (await db.execute(select(Staff).where(Staff.network_id == network_id))).scalars().all()
    guests = (await db.execute(select(Guest).where(Guest.network_id == network_id))).scalars().all()
    ingredients = (await db.execute(select(Ingredient).where(Ingredient.network_id == network_id))).scalars().all()
    menu_items = (await db.execute(select(MenuItem).where(MenuItem.venue_id.in_(venue_ids)))).scalars().all() if venue_ids else []
    orders = (
        await db.execute(
            select(Order).options(selectinload(Order.items)).where(Order.venue_id.in_(venue_ids))
        )
    ).scalars().all() if venue_ids else []

    from datetime import datetime, timezone
    return {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "network": {"id": str(network.id), "name": network.name, "slug": network.slug, "created_at": str(network.created_at)},
        "venues": [{"id": str(v.id), "name": v.name, "address": v.address, "city": v.city} for v in venues],
        "users": [{"id": str(u.id), "email": u.email, "role": u.role, "created_at": str(u.created_at)} for u in users],
        "staff": [{"id": str(s.id), "name": s.name, "role": s.role, "venue_id": str(s.venue_id)} for s in staff],
        "guests": [
            {
                "id": str(g.id), "name": g.name, "phone": g.phone, "telegram_id": g.telegram_id,
                "total_points": g.total_points, "total_visits": g.total_visits, "created_at": str(g.created_at),
            }
            for g in guests
        ],
        "menu_items": [{"id": str(m.id), "name": m.name, "price": str(m.price), "venue_id": str(m.venue_id)} for m in menu_items],
        "ingredients": [{"id": str(i.id), "name": i.name, "quantity": str(i.quantity), "unit": i.unit} for i in ingredients],
        "orders": [
            {
                "id": str(o.id), "venue_id": str(o.venue_id), "status": o.status,
                "total_amount": str(o.total_amount), "created_at": str(o.created_at),
                "items": [{"name": i.name, "quantity": i.quantity, "price": str(i.price)} for i in o.items],
            }
            for o in orders
        ],
    }


@router.get("/users", response_class=HTMLResponse)
async def settings_users_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        _require_owner(current_user)

        users = (await db.execute(
            select(User)
            .where(User.network_id == current_user.network_id)
            .options(selectinload(User.venue))
            .order_by(User.created_at)
        )).scalars().all()

        venues = (await db.execute(
            select(Venue)
            .where(Venue.network_id == current_user.network_id, Venue.is_active == True)
            .order_by(Venue.name)
        )).scalars().all()

        return templates.TemplateResponse("settings_users.html", {
            "request": request,
            "user": current_user,
            "users": users,
            "venues": venues,
            "bot_name": _BOT_NAME,
        })
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Settings users page error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка загрузки страницы пользователей")


@router.post("/users")
async def create_user(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        _require_owner(current_user)
        await check_staff_limit(current_user.network_id, db)

        body = await request.json()
        email = body.get("email", "").strip()
        password = body.get("password", "").strip()
        role = body.get("role", "manager")
        venue_id_str = body.get("venue_id") or None

        if not email:
            raise HTTPException(status_code=400, detail="Email обязателен")
        # Password is optional: leaving it blank sends an email invite with
        # a set-password link instead of the owner choosing a password for
        # someone else (the previous, only, flow).
        send_invite = not password
        if password and len(password) < 8:
            raise HTTPException(status_code=400, detail="Пароль должен быть не короче 8 символов")
        if send_invite:
            import secrets
            password = secrets.token_urlsafe(24)
        if role not in ("manager", "cashier", "administrator"):
            raise HTTPException(status_code=400, detail="Некорректная роль")

        existing = (await db.execute(
            select(User).where(User.email == email, User.network_id == current_user.network_id)
        )).scalar_one_or_none()
        if existing:
            raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")

        venue_id = None
        if venue_id_str:
            try:
                venue_id = uuid.UUID(venue_id_str)
            except ValueError:
                raise HTTPException(status_code=400, detail="Некорректный venue_id")
            venue = (await db.execute(
                select(Venue).where(Venue.id == venue_id, Venue.network_id == current_user.network_id)
            )).scalar_one_or_none()
            if not venue:
                raise HTTPException(status_code=404, detail="Заведение не найдено")

        new_user = User(
            id=uuid.uuid4(),
            network_id=current_user.network_id,
            email=email,
            hashed_password=hash_password(password),
            role=role,
            venue_id=venue_id,
        )
        db.add(new_user)
        from app.services.audit import log_action
        log_action(db, current_user.network_id, current_user.email, "user_created", f"{email} ({role})")
        await db.commit()
        await db.refresh(new_user)

        if send_invite:
            from app.config import settings as app_settings
            from app.services.auth_service import create_password_reset_token
            from app.services.email_service import send_email
            token = create_password_reset_token(new_user, expire_minutes=60 * 24 * 7)
            invite_url = f"{app_settings.PUBLIC_URL}/auth/reset-password?token={token}"
            await send_email(
                new_user.email,
                "Приглашение в RestOS",
                f"<p>{current_user.email} пригласил вас в команду RestOS.</p>"
                f"<p>Чтобы задать пароль и войти, перейдите по ссылке (действует 7 дней):</p>"
                f"<p><a href='{invite_url}'>{invite_url}</a></p>",
            )

        return {"id": str(new_user.id), "email": new_user.email, "role": new_user.role, "invited": send_invite}
    except HTTPException:
        raise
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Пользователь с таким email уже существует")
    except Exception as e:
        logger.error("Create user error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка создания пользователя")


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    try:
        _require_owner(current_user)

        if user_id == current_user.id:
            raise HTTPException(status_code=400, detail="Нельзя удалить самого себя")

        target = (await db.execute(
            select(User).where(User.id == user_id, User.network_id == current_user.network_id)
        )).scalar_one_or_none()
        if not target:
            raise HTTPException(status_code=404, detail="Пользователь не найден")

        await db.delete(target)
        from app.services.audit import log_action
        log_action(db, current_user.network_id, current_user.email, "user_deleted", target.email if hasattr(target, "email") else str(user_id))
        await db.commit()
        return {"message": "Удалено"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Delete user error: %s", e)
        raise HTTPException(status_code=500, detail="Ошибка удаления пользователя")


@router.get("/broadcasts", response_class=HTMLResponse)
async def broadcasts_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    broadcasts = (await db.execute(
        select(Broadcast)
        .where(Broadcast.network_id == current_user.network_id)
        .order_by(Broadcast.created_at.desc())
    )).scalars().all()

    total_guests = (await db.execute(
        select(func.count(Guest.id)).where(Guest.network_id == current_user.network_id)
    )).scalar() or 0
    tg_guests = (await db.execute(
        select(func.count(Guest.id)).where(
            Guest.network_id == current_user.network_id,
            Guest.telegram_id != None,
        )
    )).scalar() or 0
    total_sent = sum(1 for b in broadcasts if b.sent_at)

    return templates.TemplateResponse("broadcasts.html", {
        "request": request,
        "user": current_user,
        "broadcasts": broadcasts,
        "total_guests": total_guests,
        "tg_guests": tg_guests,
        "total_sent": total_sent,
    })


@router.post("/api/broadcasts")
async def create_broadcast_api(
    data: BroadcastCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_admin(current_user)
    if not data.message.strip():
        raise HTTPException(status_code=400, detail="Сообщение не может быть пустым")
    bc = Broadcast(
        id=uuid.uuid4(),
        network_id=current_user.network_id,
        message=data.message.strip(),
        lang_filter=data.lang_filter,
    )
    db.add(bc)
    await db.commit()
    return {"id": str(bc.id)}


@router.delete("/api/broadcasts/{bc_id}")
async def delete_broadcast_api(
    bc_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    bc = (await db.execute(
        select(Broadcast).where(Broadcast.id == bc_id, Broadcast.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not bc:
        raise HTTPException(status_code=404, detail="Не найдено")
    await db.delete(bc)
    await db.commit()
    return {"ok": True}


_VALID_FISCAL_PROVIDERS = ("webkassa",)


class VenueSettingsPatch(BaseModel):
    gis_url: str | None = None
    manager_telegram_id: int | None = None
    fiscal_provider: str | None = None
    fiscal_api_key: str | None = None
    fiscal_login: str | None = None
    fiscal_password: str | None = None
    fiscal_cashbox_number: str | None = None


@router.get("/venues", response_class=HTMLResponse)
async def settings_venues_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    venues = (await db.execute(
        select(Venue)
        .where(Venue.network_id == current_user.network_id)
        .order_by(Venue.name)
    )).scalars().all()
    return templates.TemplateResponse("settings_venues.html", {
        "request": request,
        "user": current_user,
        "venues": venues,
    })


@router.patch("/api/venues/{venue_id}")
async def update_venue_settings(
    venue_id: uuid.UUID,
    data: VenueSettingsPatch,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    venue = (await db.execute(
        select(Venue).where(Venue.id == venue_id, Venue.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")
    if 'gis_url' in data.model_fields_set:
        venue.gis_url = data.gis_url.strip() if data.gis_url else None
    if 'manager_telegram_id' in data.model_fields_set:
        venue.manager_telegram_id = data.manager_telegram_id  # None clears the field
    if 'fiscal_provider' in data.model_fields_set:
        provider = data.fiscal_provider.strip() if data.fiscal_provider else None
        if provider and provider not in _VALID_FISCAL_PROVIDERS:
            raise HTTPException(status_code=400, detail="Неизвестный провайдер фискализации")
        venue.fiscal_provider = provider
    # Credential fields are write-only (never sent back to the client), so the
    # settings form always submits them blank unless the owner is actively
    # changing one — treat blank as "leave unchanged", not "clear".
    if data.fiscal_api_key:
        venue.fiscal_api_key = data.fiscal_api_key.strip()
    if data.fiscal_login:
        venue.fiscal_login = data.fiscal_login.strip()
    if data.fiscal_password:
        venue.fiscal_password = data.fiscal_password.strip()
    if data.fiscal_cashbox_number:
        venue.fiscal_cashbox_number = data.fiscal_cashbox_number.strip()
    await db.commit()
    return {"ok": True, "id": str(venue.id)}


class TableCreate(BaseModel):
    venue_id: uuid.UUID
    label: str
    seats: int = 4


class TableStatusUpdate(BaseModel):
    status: str


@router.get("/tables", response_class=HTMLResponse)
async def settings_tables_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    venues = (await db.execute(
        select(Venue).where(Venue.network_id == current_user.network_id, Venue.is_active == True).order_by(Venue.name)
    )).scalars().all()
    tables = (await db.execute(
        select(Table).join(Venue).where(Venue.network_id == current_user.network_id).order_by(Table.label)
    )).scalars().all()
    tables_by_venue: dict[uuid.UUID, list[Table]] = {}
    for t in tables:
        tables_by_venue.setdefault(t.venue_id, []).append(t)
    return templates.TemplateResponse("settings_tables.html", {
        "request": request,
        "user": current_user,
        "venues": venues,
        "tables_by_venue": tables_by_venue,
    })


@router.post("/api/tables")
async def create_table(
    data: TableCreate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    venue = (await db.execute(
        select(Venue).where(Venue.id == data.venue_id, Venue.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not venue:
        raise HTTPException(status_code=404, detail="Заведение не найдено")
    if not data.label.strip():
        raise HTTPException(status_code=400, detail="Название стола обязательно")
    duplicate = (await db.execute(
        select(Table).where(Table.venue_id == data.venue_id, Table.label == data.label.strip())
    )).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=400, detail="Стол с таким названием уже есть в этом заведении")

    table = Table(id=uuid.uuid4(), venue_id=data.venue_id, label=data.label.strip(), seats=max(1, data.seats))
    db.add(table)
    await db.commit()
    return {"id": str(table.id), "label": table.label, "seats": table.seats, "status": table.status}


@router.patch("/api/tables/{table_id}")
async def update_table_status(
    table_id: uuid.UUID,
    data: TableStatusUpdate,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    if data.status not in ("free", "occupied", "reserved"):
        raise HTTPException(status_code=400, detail="Неверный статус")
    table = (await db.execute(
        select(Table).join(Venue).where(Table.id == table_id, Venue.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Стол не найден")
    table.status = data.status
    await db.commit()
    return {"ok": True, "status": table.status}


@router.delete("/api/tables/{table_id}")
async def delete_table(
    table_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    table = (await db.execute(
        select(Table).join(Venue).where(Table.id == table_id, Venue.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not table:
        raise HTTPException(status_code=404, detail="Стол не найден")
    await db.delete(table)
    await db.commit()
    return {"message": "Удалено"}


import secrets as _secrets


@router.post("/api/me/bot-token")
async def generate_bot_link_token(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Generate a one-time token to link staff Telegram account via bot deeplink."""
    token = _secrets.token_urlsafe(32)
    current_user.bot_link_token = token
    await db.commit()
    return {"token": token}


@router.delete("/api/me/bot-token")
async def unlink_telegram(
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    """Unlink Telegram from staff account."""
    current_user.telegram_id = None
    current_user.bot_link_token = None
    await db.commit()
    return {"ok": True}


# ── Promo codes ──────────────────────────────────────────────────────────

@router.get("/promos", response_class=HTMLResponse)
async def settings_promos_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    from app.models.promo import PromoCode
    promos = (await db.execute(
        select(PromoCode)
        .where(PromoCode.network_id == current_user.network_id)
        .order_by(PromoCode.created_at.desc())
    )).scalars().all()
    return templates.TemplateResponse("settings_promos.html", {
        "request": request,
        "user": current_user,
        "promos": promos,
    })


@router.post("/api/promos")
async def create_promo(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    from app.models.promo import PromoCode
    from decimal import Decimal as _Dec
    body = await request.json()
    code = (body.get("code") or "").strip().upper()
    ptype = body.get("type")
    try:
        value = _Dec(str(body.get("value")))
    except Exception:
        raise HTTPException(status_code=400, detail="Неверное значение скидки")
    if not code or len(code) > 50:
        raise HTTPException(status_code=400, detail="Введите код (до 50 символов)")
    if ptype not in ("percent", "amount") or value <= 0:
        raise HTTPException(status_code=400, detail="Неверный тип или значение скидки")
    if ptype == "percent" and value > 100:
        raise HTTPException(status_code=400, detail="Процент не может превышать 100")
    max_uses = body.get("max_uses")
    if max_uses is not None:
        try:
            max_uses = int(max_uses) or None
        except (TypeError, ValueError):
            max_uses = None
    expires_at = None
    if body.get("expires_at"):
        from datetime import datetime as _dt, time as _time, timezone as _tz
        try:
            # Date from the form → the code works through the end of that day.
            d = _dt.strptime(str(body["expires_at"]), "%Y-%m-%d").date()
            expires_at = _dt.combine(d, _time.max).replace(tzinfo=_tz.utc)
        except ValueError:
            raise HTTPException(status_code=400, detail="Неверная дата окончания")

    duplicate = (await db.execute(
        select(PromoCode).where(PromoCode.network_id == current_user.network_id, PromoCode.code == code)
    )).scalar_one_or_none()
    if duplicate:
        raise HTTPException(status_code=400, detail="Такой код уже существует")

    promo = PromoCode(
        id=uuid.uuid4(), network_id=current_user.network_id,
        code=code, type=ptype, value=value, max_uses=max_uses, expires_at=expires_at,
    )
    db.add(promo)
    from app.services.audit import log_action
    log_action(db, current_user.network_id, current_user.email, "promo_created", f"{code}: {ptype} {value}")
    await db.commit()
    return {"id": str(promo.id), "code": promo.code}


@router.patch("/api/promos/{promo_id}")
async def toggle_promo(
    promo_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    from app.models.promo import PromoCode
    promo = (await db.execute(
        select(PromoCode).where(PromoCode.id == promo_id, PromoCode.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Промокод не найден")
    promo.active = not promo.active
    await db.commit()
    return {"active": promo.active}


@router.delete("/api/promos/{promo_id}")
async def delete_promo(
    promo_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    from app.models.promo import PromoCode
    promo = (await db.execute(
        select(PromoCode).where(PromoCode.id == promo_id, PromoCode.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not promo:
        raise HTTPException(status_code=404, detail="Промокод не найден")
    await db.delete(promo)
    await db.commit()
    return {"ok": True}


# ── Staff audit log viewer ───────────────────────────────────────────────

@router.get("/audit", response_class=HTMLResponse)
async def settings_audit_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    from app.models.audit_log import StaffAuditLog
    entries = (await db.execute(
        select(StaffAuditLog)
        .where(StaffAuditLog.network_id == current_user.network_id)
        .order_by(StaffAuditLog.created_at.desc())
        .limit(200)
    )).scalars().all()
    return templates.TemplateResponse("settings_audit.html", {
        "request": request,
        "user": current_user,
        "entries": entries,
    })


# ── API keys & webhooks ──────────────────────────────────────────────────

@router.get("/api-access", response_class=HTMLResponse)
async def settings_api_page(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    from app.models.api_key import ApiKey, WebhookSubscription
    keys = (await db.execute(
        select(ApiKey).where(ApiKey.network_id == current_user.network_id).order_by(ApiKey.created_at.desc())
    )).scalars().all()
    hooks = (await db.execute(
        select(WebhookSubscription).where(WebhookSubscription.network_id == current_user.network_id)
        .order_by(WebhookSubscription.created_at.desc())
    )).scalars().all()
    return templates.TemplateResponse("settings_api.html", {
        "request": request,
        "user": current_user,
        "keys": keys,
        "hooks": hooks,
    })


@router.post("/api/keys")
async def create_api_key(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    import hashlib
    import secrets as _sec
    from app.models.api_key import ApiKey
    body = await request.json()
    name = (body.get("name") or "").strip() or "API key"
    raw = "rk_" + _sec.token_urlsafe(32)
    key = ApiKey(
        id=uuid.uuid4(), network_id=current_user.network_id, name=name[:100],
        key_hash=hashlib.sha256(raw.encode()).hexdigest(), prefix=raw[:11],
    )
    db.add(key)
    from app.services.audit import log_action
    log_action(db, current_user.network_id, current_user.email, "api_key_created", name)
    await db.commit()
    # The full key is returned exactly once — never retrievable again.
    return {"id": str(key.id), "key": raw}


@router.delete("/api/keys/{key_id}")
async def revoke_api_key(
    key_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    from app.models.api_key import ApiKey
    key = (await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.network_id == current_user.network_id)
    )).scalar_one_or_none()
    if not key:
        raise HTTPException(status_code=404, detail="Ключ не найден")
    await db.delete(key)
    await db.commit()
    return {"ok": True}


@router.post("/api/webhooks")
async def create_webhook(
    request: Request,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    import secrets as _sec
    from app.models.api_key import WebhookSubscription
    from app.services.webhooks import EVENTS
    body = await request.json()
    url = (body.get("url") or "").strip()
    events = [e for e in (body.get("events") or []) if e in EVENTS]
    if not url.startswith(("http://", "https://")) or len(url) > 500:
        raise HTTPException(status_code=400, detail="Введите корректный URL")
    if not events:
        raise HTTPException(status_code=400, detail="Выберите хотя бы одно событие")
    hook = WebhookSubscription(
        id=uuid.uuid4(), network_id=current_user.network_id,
        url=url, secret=_sec.token_hex(32), events=",".join(events),
    )
    db.add(hook)
    await db.commit()
    return {"id": str(hook.id), "secret": hook.secret}


@router.delete("/api/webhooks/{hook_id}")
async def delete_webhook(
    hook_id: uuid.UUID,
    current_user: User = Depends(get_current_user_dep),
    db: AsyncSession = Depends(get_db),
):
    _require_owner(current_user)
    from app.models.api_key import WebhookSubscription
    hook = (await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.id == hook_id,
            WebhookSubscription.network_id == current_user.network_id,
        )
    )).scalar_one_or_none()
    if not hook:
        raise HTTPException(status_code=404, detail="Вебхук не найден")
    await db.delete(hook)
    await db.commit()
    return {"ok": True}
