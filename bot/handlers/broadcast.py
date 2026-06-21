import asyncio
import logging

import httpx
from aiogram import Bot

logger = logging.getLogger(__name__)

POLL_INTERVAL = 300


async def broadcast_loop(bot: Bot, api_url: str, network_id: str):
    while True:
        try:
            await _send_broadcasts(bot, api_url, network_id)
        except Exception as e:
            logger.error("Broadcast loop error: %s", e)
        await asyncio.sleep(POLL_INTERVAL)


async def _send_broadcasts(bot: Bot, api_url: str, network_id: str):
    try:
        async with httpx.AsyncClient() as client:
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
