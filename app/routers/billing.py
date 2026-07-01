from app.templates_env import templates
import asyncio
import logging
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
        network_id = data.get("metadata", {}).get("network_id") or data.get("client_reference_id")
        plan = data.get("metadata", {}).get("plan", "starter")
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

    return {"received": True}
