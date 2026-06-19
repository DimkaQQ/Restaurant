import logging

import httpx
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.keyboards.main import categories_keyboard, menu_items_keyboard, back_keyboard

router = Router()
logger = logging.getLogger(__name__)


async def fetch_menu(api_url: str, venue_id: str) -> list[dict]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{api_url}/api/menu/{venue_id}", timeout=5.0)
            return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error("Fetch menu error: %s", e)
        return []


@router.callback_query(F.data == "menu")
async def show_menu(callback: CallbackQuery, api_url: str, venue_id: str):
    items = await fetch_menu(api_url, venue_id)
    available = [i for i in items if i.get("is_available")]

    if not available:
        await callback.message.edit_text("Меню пока недоступно.", reply_markup=back_keyboard())
        return

    categories = list(dict.fromkeys(i.get("category", "Прочее") for i in available))
    await callback.message.edit_text(
        "📋 *Меню*\nВыберите категорию:",
        parse_mode="Markdown",
        reply_markup=categories_keyboard(categories),
    )


@router.callback_query(F.data.startswith("cat:"))
async def show_category(callback: CallbackQuery, api_url: str, venue_id: str):
    category = callback.data.split(":", 1)[1]
    items = await fetch_menu(api_url, venue_id)
    cat_items = [i for i in items if i.get("category") == category and i.get("is_available")]

    if not cat_items:
        await callback.answer("В этой категории нет позиций", show_alert=True)
        return

    text = f"*{category}*\n\n" + "\n".join(
        f"• {i['name']} — {i['price']} ₸\n  _{i.get('description', '')}_" for i in cat_items
    )
    await callback.message.edit_text(
        text,
        parse_mode="Markdown",
        reply_markup=menu_items_keyboard(cat_items, category),
    )
