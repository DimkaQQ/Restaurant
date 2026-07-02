"""Minimal transactional email sender. Sends via SMTP when SMTP_HOST is
configured; otherwise logs the message so password-reset/invite links are
still visible in dev/staging without needing real mail infrastructure."""
import asyncio
import logging
import smtplib
from email.message import EmailMessage

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

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


# Password-reset/invite links are one-shot and time-sensitive — worth a
# couple of retries on a flaky connection to the mail server before giving
# up silently. Auth failures (bad credentials) aren't retried since retrying
# those just repeats the same failure.
@retry(
    retry=retry_if_exception_type((smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected, TimeoutError, OSError)),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=6),
    reraise=True,
)
def _send_sync_with_retry(to: str, subject: str, html_body: str) -> None:
    _send_sync(to, subject, html_body)


async def send_email(to: str, subject: str, html_body: str) -> None:
    if not settings.SMTP_HOST:
        logger.info("SMTP not configured — email to %s not sent. Subject: %s\n%s", to, subject, html_body)
        return
    try:
        await asyncio.to_thread(_send_sync_with_retry, to, subject, html_body)
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to, e)
