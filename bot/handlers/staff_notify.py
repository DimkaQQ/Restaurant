"""Delivers queued staff notifications («стол 3 готов» for the waiter).
The server enqueues rows in bot_notifications; this loop polls and sends."""
import asyncio
import logging

from aiogram import Bot

from bot.http_client import bot_client

logger = logging.getLogger(__name__)

POLL_INTERVAL = 15  # seconds — a ready-order alert is only useful while hot


async def staff_notify_loop(bot: Bot, api_url: str, network_id: str):
    while True:
        try:
            await _deliver(bot, api_url, network_id)
        except Exception as e:
            logger.error("Staff notify loop error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


async def _deliver(bot: Bot, api_url: str, network_id: str):
    async with bot_client() as client:
        resp = await client.get(
            f"{api_url}/api/bot/notifications",
            params={"network_id": network_id},
            timeout=10.0,
        )
        if resp.status_code != 200:
            return
        notifications: list[dict] = resp.json()

    for n in notifications:
        try:
            await bot.send_message(n["telegram_id"], n["text"])
            await asyncio.sleep(0.05)
        except Exception as e:
            logger.warning("Could not deliver staff notification to %s: %s", n.get("telegram_id"), e)
