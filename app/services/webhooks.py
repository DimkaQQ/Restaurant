"""Outbound webhooks: signed JSON POSTs to subscriber URLs on order events.

Delivery is fire-and-forget (asyncio task per subscription) with retries —
a slow or dead subscriber endpoint must never slow down order taking.
The body is signed with HMAC-SHA256 (X-RestOS-Signature) so the receiver
can verify authenticity, mirroring how Stripe signs its webhooks to us.
"""
import asyncio
import hashlib
import hmac
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.models.api_key import WebhookSubscription

logger = logging.getLogger(__name__)

EVENTS = ("order.created", "order.paid")


@retry(
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError, httpx.ReadError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=8),
    reraise=True,
)
async def _post(url: str, body: bytes, headers: dict) -> None:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(url, content=body, headers=headers)
        resp.raise_for_status()


async def _deliver(url: str, secret: str, event: str, payload: dict) -> None:
    body = json.dumps({
        "event": event,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "data": payload,
    }, ensure_ascii=False).encode()
    signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-RestOS-Event": event,
        "X-RestOS-Signature": signature,
    }
    try:
        await _post(url, body, headers)
        logger.info("Webhook %s delivered to %s", event, url)
    except Exception as e:
        logger.warning("Webhook %s to %s failed after retries: %s", event, url, e)


async def dispatch_event(db: AsyncSession, network_id: uuid.UUID, event: str, payload: dict) -> None:
    """Query matching subscriptions with the caller's session (cheap), then
    hand each delivery to a background task — the caller never waits."""
    subs = (await db.execute(
        select(WebhookSubscription).where(
            WebhookSubscription.network_id == network_id,
            WebhookSubscription.active == True,  # noqa: E712
        )
    )).scalars().all()
    for sub in subs:
        if event in [e.strip() for e in (sub.events or "").split(",")]:
            asyncio.create_task(_deliver(sub.url, sub.secret, event, payload))
