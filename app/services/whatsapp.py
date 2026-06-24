"""WhatsApp notification service via Twilio.

Set env vars to enable:
  TWILIO_ACCOUNT_SID=ACxxxxxx
  TWILIO_AUTH_TOKEN=your_token
  TWILIO_WHATSAPP_FROM=whatsapp:+14155238886  (Twilio sandbox or approved number)
"""
import logging
import os
from base64 import b64encode

import httpx

logger = logging.getLogger(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_WHATSAPP_FROM = os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886")

_ENABLED = bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN)


def _normalize_phone(phone: str) -> str:
    """Ensure phone is in whatsapp:+XXXXXXXXXXX format."""
    digits = "".join(c for c in phone if c.isdigit() or c == "+")
    if not digits.startswith("+"):
        digits = "+" + digits
    return f"whatsapp:{digits}"


async def send_whatsapp(to_phone: str, message: str) -> bool:
    """Send WhatsApp message. Returns True on success, False if disabled or failed."""
    if not _ENABLED:
        logger.debug("WhatsApp disabled (no Twilio credentials)")
        return False

    url = f"https://api.twilio.com/2010-04-01/Accounts/{TWILIO_ACCOUNT_SID}/Messages.json"
    auth = b64encode(f"{TWILIO_ACCOUNT_SID}:{TWILIO_AUTH_TOKEN}".encode()).decode()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(
                url,
                headers={"Authorization": f"Basic {auth}"},
                data={
                    "From": TWILIO_WHATSAPP_FROM,
                    "To": _normalize_phone(to_phone),
                    "Body": message,
                },
            )
            if resp.status_code in (200, 201):
                logger.info("WhatsApp sent to %s", to_phone)
                return True
            else:
                logger.warning("WhatsApp failed (%s): %s", resp.status_code, resp.text[:200])
                return False
    except Exception as e:
        logger.error("WhatsApp error: %s", e)
        return False


async def send_order_confirmation(guest_phone: str, guest_name: str, order_short_id: str, total: float, venue_name: str) -> bool:
    msg = (
        f"✅ Ваш заказ #{order_short_id} принят в «{venue_name}»!\n"
        f"Сумма: {total:.0f} ₸\n"
        f"Мы уведомим вас, когда заказ будет готов."
    )
    return await send_whatsapp(guest_phone, msg)


async def send_review_request(guest_phone: str, venue_name: str, order_short_id: str, web_url: str) -> bool:
    msg = (
        f"⭐ Как вам визит в «{venue_name}»?\n"
        f"Оставьте отзыв о заказе #{order_short_id}:\n"
        f"{web_url}"
    )
    return await send_whatsapp(guest_phone, msg)


async def send_order_ready(guest_phone: str, guest_name: str, order_short_id: str) -> bool:
    msg = f"🔔 {guest_name}, ваш заказ #{order_short_id} готов! Можете забирать."
    return await send_whatsapp(guest_phone, msg)
