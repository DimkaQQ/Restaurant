import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.handlers import start, menu, order, profile
from bot.middlewares.guest_middleware import GuestMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

API_URL = os.getenv("API_URL", "http://localhost:8000")
NETWORK_ID = os.getenv("NETWORK_ID", "")
VENUE_ID = os.getenv("VENUE_ID_1", "")
BOT_TOKEN = os.getenv("BOT_TOKEN_VENUE_1", "")


async def main():
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN_VENUE_1 not set")
        return

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())

    dp.update.middleware(GuestMiddleware(api_url=API_URL, network_id=NETWORK_ID))

    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(order.router)
    dp.include_router(profile.router)

    dp["api_url"] = API_URL
    dp["venue_id"] = VENUE_ID
    dp["network_id"] = NETWORK_ID

    logger.info("Bot starting for venue %s", VENUE_ID)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
