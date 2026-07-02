"""Minimal transactional email sender. Sends via SMTP when SMTP_HOST is
configured; otherwise logs the message so password-reset/invite links are
still visible in dev/staging without needing real mail infrastructure."""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from app.config import settings

logger = logging.getLogger(__name__)


def _send_sync(to: str, subject: str, html_body: str) -> None:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM
    msg["To"] = to
    msg.set_content("Откройте это письмо в клиенте с поддержкой HTML.")
    msg.add_alternative(html_body, subtype="html")

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
        server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)


async def send_email(to: str, subject: str, html_body: str) -> None:
    if not settings.SMTP_HOST:
        logger.info("SMTP not configured — email to %s not sent. Subject: %s\n%s", to, subject, html_body)
        return
    try:
        await asyncio.to_thread(_send_sync, to, subject, html_body)
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
