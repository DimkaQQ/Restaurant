import logging

import httpx
from bot.http_client import bot_client
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.main import categories_keyboard, back_keyboard
from bot.locales import t

router = Router()
logger = logging.getLogger(__name__)


async def fetch_menu(api_url: str, venue_id: str) -> list[dict]:
    try:
        async with bot_client() as client:
            resp = await client.get(f"{api_url}/api/bot/menu", params={"venue_id": venue_id}, timeout=5.0)
            return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error("Fetch menu error: %s", e)
        return []


@router.callback_query(F.data == "menu")
async def show_menu(callback: CallbackQuery, state: FSMContext, api_url: str, venue_id: str, lang: str):
    data = await state.get_data()
    effective_venue = data.get('order_venue_id') or venue_id

    items = await fetch_menu(api_url, effective_venue)
    available = [i for i in items if i.get("is_available")]

    if not available:
        await callback.message.edit_text(t('no_menu', lang), reply_markup=back_keyboard(lang))
        return

    categories = list(dict.fromkeys(i.get("category", "Прочее") for i in available))
    await callback.message.edit_text(
        t('choose_category', lang),
        reply_markup=categories_keyboard(categories, lang),
    )


