import asyncio
import logging

import httpx
from bot.http_client import bot_client
from aiogram import Bot

logger = logging.getLogger(__name__)

POLL_INTERVAL = 300
REVIEW_POLL_INTERVAL = 300


async def broadcast_loop(bot: Bot, api_url: str, network_id: str):
    while True:
        try:
            await _send_broadcasts(bot, api_url, network_id)
        except Exception as e:
            logger.error("Broadcast loop error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


async def _send_broadcasts(bot: Bot, api_url: str, network_id: str):
    try:
        async with bot_client() as client:
            ids_resp = await client.get(
                f"{api_url}/api/bot/guest-ids",
                params={"network_id": network_id},
                timeout=10.0,
            )
            if ids_resp.status_code != 200:
                return
            telegram_ids: list[int] = ids_resp.json()

            bc_resp = await client.get(
                f"{api_url}/api/bot/broadcasts",
                params={"network_id": network_id},
                timeout=10.0,
            )
            if bc_resp.status_code != 200:
                return
            broadcasts: list[dict] = bc_resp.json()
    except Exception as e:
        logger.error("Broadcast fetch error: %s", e)
        return

    for broadcast in broadcasts:
        message = broadcast.get("message", "")
        for tg_id in telegram_ids:
            try:
                await bot.send_message(tg_id, f"📢 {message}")
                await asyncio.sleep(0.05)
            except Exception as e:
                logger.warning("Could not send broadcast to %s: %s", tg_id, e)


async def review_loop(bot: Bot, api_url: str, network_id: str):
    from bot.keyboards.main import rating_keyboard
    from bot.locales import t

    while True:
        await asyncio.sleep(REVIEW_POLL_INTERVAL)
        try:
            async with bot_client() as client:
                resp = await client.get(
                    f"{api_url}/api/bot/orders-for-review",
                    params={"network_id": network_id},
                    timeout=10.0,
                )
                if resp.status_code != 200:
                    continue
                orders = resp.json()
            for o in orders:
                tg_id = o["guest_telegram_id"]
                lang = o.get("guest_lang", "ru")
                venue_name = o["venue_name"]
                try:
                    await bot.send_message(
                        tg_id,
                        t("review_ask", lang, venue=venue_name),
                        reply_markup=rating_keyboard(o["order_id"]),
                    )
                except Exception as e:
                    logger.warning("Could not send review request to %s: %s", tg_id, e)
        except Exception as e:
            logger.error("Review loop error: %s", e)
