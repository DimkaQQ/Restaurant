import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from bot.http_client import bot_client

logger = logging.getLogger(__name__)

REPORT_HOUR_UTC = 6  # ~09:00 in Asia/Almaty (UTC+3)


async def daily_report_loop(bot: Bot, api_url: str, network_id: str):
    while True:
        now = datetime.now(timezone.utc)
        next_run = now.replace(hour=REPORT_HOUR_UTC, minute=0, second=0, microsecond=0)
        if next_run <= now:
            next_run += timedelta(days=1)
        await asyncio.sleep((next_run - now).total_seconds())
        try:
            await _send_daily_report(bot, api_url, network_id)
        except Exception as e:
            logger.error("Daily report loop error: %s", e)


async def _send_daily_report(bot: Bot, api_url: str, network_id: str):
    async with bot_client() as client:
        resp = await client.get(
            f"{api_url}/api/bot/daily-report",
            params={"network_id": network_id},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return
        report = resp.json()

    owner_tg_id = report.get("owner_telegram_id")
    if not owner_tg_id:
        return

    text = (
        f"📊 <b>Отчёт за {report['date']}</b>\n\n"
        f"Выручка: <b>{report['revenue']:,.0f} ₸</b>\n"
        f"Заказов: {report['orders_count']}\n"
        f"Новых гостей: {report['new_guests']}\n"
    )
    if report.get("top_item"):
        text += f"Хит продаж: {report['top_item']}\n"

    try:
        await bot.send_message(owner_tg_id, text.replace(",", " "))
    except Exception as e:
        logger.warning("Could not send daily report to %s: %s", owner_tg_id, e)
