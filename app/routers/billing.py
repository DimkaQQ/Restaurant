from app.templates_env import templates
import asyncio
import logging
import uuid
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models.subscription import Subscription
from app.routers.deps import get_user_from_request

router = APIRouter(prefix="/billing", tags=["billing"])
logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY
# Stripe's own SDK retries idempotent requests (GET, and POST with an
# idempotency key — which Session.create/Portal.create send automatically)
# on connection errors and 5xx, so a transient network blip to Stripe
# doesn't surface directly as a user-facing checkout failure.
stripe.max_network_retries = 2

_PLAN_PRICE_IDS = {
    "starter": settings.STRIPE_PRICE_STARTER,
    "pro": settings.STRIPE_PRICE_PRO,
    "enterprise": settings.STRIPE_PRICE_ENTERPRISE,
}


async def _get_subscription(network_id, db: AsyncSession) -> Subscription | None:
    return (await db.execute(
        select(Subscription).where(Subscription.network_id == network_id)
    )).scalar_one_or_none()


@router.get("", response_class=HTMLResponse)
async def billing_page(request: Request, db: AsyncSession = Depends(get_db)):
    current_user = await get_user_from_request(request, db)
    if not current_user:
        return RedirectResponse(url="/auth/login")

    sub = await _get_subscription(current_user.network_id, db)

    days_left = None
    if sub and sub.status == "trial" and sub.trial_ends_at:
        delta = sub.trial_ends_at - datetime.now(timezone.utc)
        days_left = max(0, delta.days)

    return templates.TemplateResponse("billing.html", {
        "request": request,
        "user": current_user,
        "subscription": sub,
        "days_left": days_left,
        "stripe_enabled": bool(settings.STRIPE_SECRET_KEY),
    })


@router.get("/build", response_class=HTMLResponse)
async def plan_builder_page(request: Request, db: AsyncSession = Depends(get_db)):
    """Build-your-own subscription: toggle modules, see the live price."""
    current_user = await get_user_from_request(request, db)
    if not current_user:
        return RedirectResponse(url="/auth/login")
    if current_user.role != "owner":
        raise HTTPException(status_code=403, detail="Только для владельца")

    from app.services import plan_builder
    sub = await _get_subscription(current_user.network_id, db)
    return templates.TemplateResponse("billing_build.html", {
        "request": request,
        "user": current_user,
        "subscription": sub,
        "base_price": plan_builder.BASE_PRICE,
        "extra_venue_price": plan_builder.EXTRA_VENUE_PRICE,
        "currency": plan_builder.CURRENCY,
        "modules": plan_builder.MODULES,
        "module_order": plan_builder.MODULE_ORDER,
        "selected": (sub.features if sub and sub.plan == "custom" else []) or [],
        "extra_venues": (sub.extra_venues if sub and sub.plan == "custom" else 0) or 0,
        "stripe_enabled": bool(settings.STRIPE_SECRET_KEY),
    })


@router.post("/build")
async def apply_custom_plan(request: Request, db: AsyncSession = Depends(get_db)):
    """Save the assembled plan. With Stripe on, send the owner to a checkout for
    the computed monthly price; without it, store the selection and point them
    at support (same as the fixed tiers)."""
    current_user = await get_user_from_request(request, db)
    if not current_user:
        return RedirectResponse(url="/auth/login")
    if current_user.role != "owner":
        raise HTTPException(status_code=403, detail="Только для владельца")

    from app.services import plan_builder
    body = await request.json()
    features = plan_builder.sanitize_features(body.get("features"))
    try:
        extra_venues = max(0, min(50, int(body.get("extra_venues") or 0)))
    except (TypeError, ValueError):
        extra_venues = 0
    price = plan_builder.compute_price(features, extra_venues)

    sub = await _get_subscription(current_user.network_id, db)
    if not sub:
        sub = Subscription(network_id=current_user.network_id, status="trial")
        db.add(sub)
    sub.plan = "custom"
    sub.features = features
    sub.extra_venues = extra_venues
    await db.commit()

    if not settings.STRIPE_SECRET_KEY:
        # No online payment configured — selection is saved; activation is manual.
        return {"ok": True, "price": price, "checkout_url": None}

    try:
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": "RestOS — свой тариф"},
                    "unit_amount": price * 100,
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }],
            customer=sub.stripe_customer_id if sub.stripe_customer_id else None,
            customer_email=current_user.email if not sub.stripe_customer_id else None,
            client_reference_id=str(current_user.network_id),
            metadata={"network_id": str(current_user.network_id), "plan": "custom",
                      "features": ",".join(features), "extra_venues": str(extra_venues)},
            success_url=f"{settings.PUBLIC_URL}/billing?checkout=success",
            cancel_url=f"{settings.PUBLIC_URL}/billing?checkout=cancelled",
        )
    except stripe.error.StripeError as e:
        logger.error("Stripe custom checkout error: %s", e)
        raise HTTPException(status_code=502, detail="Ошибка платёжной системы")
    return {"ok": True, "price": price, "checkout_url": session.url}


@router.post("/checkout/{plan}")
async def create_checkout(plan: str, request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Оплата пока не подключена, напишите в поддержку")
    price_id = _PLAN_PRICE_IDS.get(plan)
    if not price_id:
        raise HTTPException(status_code=400, detail="Неизвестный тариф")

    current_user = await get_user_from_request(request, db)
    if not current_user:
        return RedirectResponse(url="/auth/login")

    sub = await _get_subscription(current_user.network_id, db)

    try:
        # stripe-python is a blocking/sync HTTP client — run it off the event
        # loop so one slow Stripe round-trip doesn't stall every other request.
        session = await asyncio.to_thread(
            stripe.checkout.Session.create,
            mode="subscription",
            payment_method_types=["card"],
            line_items=[{"price": price_id, "quantity": 1}],
            customer=sub.stripe_customer_id if sub and sub.stripe_customer_id else None,
            customer_email=current_user.email if not (sub and sub.stripe_customer_id) else None,
            client_reference_id=str(current_user.network_id),
            metadata={"network_id": str(current_user.network_id), "plan": plan},
            success_url=f"{settings.PUBLIC_URL}/billing?checkout=success",
            cancel_url=f"{settings.PUBLIC_URL}/billing?checkout=cancelled",
        )
    except stripe.error.StripeError as e:
        logger.error("Stripe checkout error: %s", e)
        raise HTTPException(status_code=502, detail="Ошибка платёжной системы")

    return RedirectResponse(url=session.url, status_code=303)


@router.post("/portal")
async def create_portal_session(request: Request, db: AsyncSession = Depends(get_db)):
    if not settings.STRIPE_SECRET_KEY:
        raise HTTPException(status_code=503, detail="Оплата пока не подключена")

    current_user = await get_user_from_request(request, db)
    if not current_user:
        return RedirectResponse(url="/auth/login")

    sub = await _get_subscription(current_user.network_id, db)
    if not sub or not sub.stripe_customer_id:
        raise HTTPException(status_code=400, detail="Нет активной оплаты через Stripe")

    session = await asyncio.to_thread(
        stripe.billing_portal.Session.create,
        customer=sub.stripe_customer_id,
        return_url=f"{settings.PUBLIC_URL}/billing",
    )
    return RedirectResponse(url=session.url, status_code=303)


@router.post("/webhook")
async def stripe_webhook(request: Request, db: AsyncSession = Depends(get_db)):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError) as e:
        logger.warning("Invalid Stripe webhook: %s", e)
        raise HTTPException(status_code=400, detail="Invalid webhook signature")

    data = event["data"]["object"]
    event_type = event["type"]

    if event_type == "checkout.session.completed":
        raw_network_id = data.get("metadata", {}).get("network_id") or data.get("client_reference_id")
        plan = data.get("metadata", {}).get("plan", "starter")
        # Stripe metadata values are strings; the column is UUID. A malformed
        # id must not 500 (Stripe would retry the webhook forever) — log and ack.
        network_id = None
        if raw_network_id:
            try:
                network_id = uuid.UUID(raw_network_id)
            except ValueError:
                logger.error("Webhook checkout.session.completed with bad network_id: %r", raw_network_id)
        if network_id:
            sub = await _get_subscription(network_id, db)
            if sub:
                sub.status = "active"
                sub.plan = plan
                sub.stripe_customer_id = data.get("customer")
                sub.stripe_subscription_id = data.get("subscription")
                await db.commit()
                logger.info("Subscription activated for network %s (plan=%s)", network_id, plan)

    elif event_type == "invoice.paid":
        stripe_sub_id = data.get("subscription")
        period_end = data.get("lines", {}).get("data", [{}])[0].get("period", {}).get("end")
        if stripe_sub_id:
            sub = (await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
            )).scalar_one_or_none()
            if sub:
                sub.status = "active"
                if period_end:
                    sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
                await db.commit()

    elif event_type == "invoice.payment_failed":
        stripe_sub_id = data.get("subscription")
        if stripe_sub_id:
            sub = (await db.execute(
                select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
            )).scalar_one_or_none()
            if sub:
                sub.status = "past_due"
                await db.commit()

    elif event_type == "customer.subscription.deleted":
        stripe_sub_id = data.get("id")
        sub = (await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )).scalar_one_or_none()
        if sub:
            sub.status = "cancelled"
            await db.commit()

    elif event_type == "customer.subscription.updated":
        # Covers plan upgrades/downgrades and status changes made from the
        # Stripe side (e.g. via the customer billing portal) so our copy of
        # the subscription doesn't drift from what Stripe actually has.
        stripe_sub_id = data.get("id")
        sub = (await db.execute(
            select(Subscription).where(Subscription.stripe_subscription_id == stripe_sub_id)
        )).scalar_one_or_none()
        if sub:
            price_id = (data.get("items", {}).get("data") or [{}])[0].get("price", {}).get("id")
            plan = next((p for p, pid in _PLAN_PRICE_IDS.items() if pid and pid == price_id), None)
            if plan:
                sub.plan = plan
            stripe_status = data.get("status")
            if stripe_status in ("active", "trialing"):
                sub.status = "active"
            elif stripe_status == "past_due":
                sub.status = "past_due"
            elif stripe_status in ("canceled", "unpaid", "incomplete_expired"):
                sub.status = "cancelled"
            period_end = data.get("current_period_end")
            if period_end:
                sub.current_period_end = datetime.fromtimestamp(period_end, tz=timezone.utc)
            await db.commit()
            logger.info("Subscription %s updated via Stripe: status=%s plan=%s", stripe_sub_id, sub.status, sub.plan)

    return {"received": True}
