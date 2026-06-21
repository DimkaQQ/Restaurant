import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import start, menu, order, profile
from bot.handlers import settings_handler, broadcast
from bot.middlewares.guest_middleware import GuestMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

API_URL = os.getenv("API_URL", "http://localhost:8001")
NETWORK_ID = os.getenv("NETWORK_ID", "")
VENUE_ID = os.getenv("VENUE_ID_1", "")
BOT_TOKEN = os.getenv("BOT_TOKEN_VENUE_1", "")
HTTPS_PROXY = os.getenv("HTTPS_PROXY", "")
TELEGRAM_API_SERVER = os.getenv("TELEGRAM_API_SERVER", "")


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN_VENUE_1 not set")
        return
    if not VENUE_ID:
        logger.error("VENUE_ID_1 not set")
        return
    if not NETWORK_ID:
        logger.error("NETWORK_ID not set")
        return

    session_kwargs = {}
    if TELEGRAM_API_SERVER:
        session_kwargs["api"] = TelegramAPIServer.from_base(TELEGRAM_API_SERVER)
        logger.info("Using custom Telegram API server: %s", TELEGRAM_API_SERVER)
    elif HTTPS_PROXY:
        session_kwargs["proxy"] = HTTPS_PROXY
    session = AiohttpSession(**session_kwargs) if session_kwargs else None
    bot = Bot(token=BOT_TOKEN, session=session, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(GuestMiddleware(api_url=API_URL, network_id=NETWORK_ID))

    dp.include_router(start.router)
    dp.include_router(settings_handler.router)
    dp.include_router(menu.router)
    dp.include_router(order.router)
    dp.include_router(profile.router)

    dp["api_url"] = API_URL
    dp["venue_id"] = VENUE_ID
    dp["network_id"] = NETWORK_ID

    asyncio.create_task(broadcast.broadcast_loop(bot, API_URL, NETWORK_ID))

    logger.info("Bot starting for venue %s", VENUE_ID)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
