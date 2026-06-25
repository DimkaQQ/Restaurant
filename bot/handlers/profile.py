import logging
from collections import Counter

import httpx
from bot.http_client import bot_client
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.keyboards.main import back_keyboard
from bot.locales import t

router = Router()
logger = logging.getLogger(__name__)


STATUS_KEYS = {
    "new": "status_new",
    "confirmed": "status_confirmed",
    "preparing": "status_preparing",
    "ready": "status_ready",
    "done": "status_done",
    "cancelled": "status_cancelled",
}


@router.callback_query(F.data == "points")
async def show_points(callback: CallbackQuery, guest: dict | None, lang: str):
    if not guest:
        await callback.answer(t('register_first', lang), show_alert=True)
        return
    points = guest["total_points"]
    tenge_value = points * 5
    await callback.message.edit_text(
        t('points_info', lang, points=points, value=tenge_value),
        reply_markup=back_keyboard(lang),
    )


@router.callback_query(F.data == "history")
async def show_history(callback: CallbackQuery, guest: dict | None, api_url: str, lang: str):
    if not guest:
        await callback.answer(t('register_first', lang), show_alert=True)
        return
    try:
        async with bot_client() as client:
            resp = await client.get(
                f"{api_url}/api/orders/guest/history",
                params={"telegram_id": guest["telegram_id"], "limit": 10},
                timeout=5.0,
            )
            if resp.status_code != 200:
                raise ValueError(f"API error {resp.status_code}")
        orders = resp.json()
    except Exception as e:
        logger.error("History fetch error: %s", e)
        await callback.message.edit_text(t('conn_error', lang), reply_markup=back_keyboard(lang))
        return
    if not orders:
        await callback.message.edit_text(t('no_orders', lang), reply_markup=back_keyboard(lang))
        return

    lines = []
    for o in orders[:10]:
        status_key = STATUS_KEYS.get(o["status"], "status_new")
        st = t(status_key, lang)
        items_str = ", ".join(i.get('name', '?') for i in o.get("items", []))
        lines.append(f"{st} {float(o['total_amount']):.0f} ₸ — {items_str}")

    await callback.message.edit_text(
        f"{t('history_title', lang)}\n\n" + "\n".join(lines),
        reply_markup=back_keyboard(lang),
    )


@router.callback_query(F.data == "favorites")
async def show_favorites(callback: CallbackQuery, guest: dict | None, api_url: str, lang: str):
    if not guest:
        await callback.answer(t('register_first', lang), show_alert=True)
        return
    try:
        async with bot_client() as client:
            resp = await client.get(
                f"{api_url}/api/orders/guest/history",
                params={"telegram_id": guest["telegram_id"], "limit": 50},
                timeout=5.0,
            )
            if resp.status_code != 200:
                raise ValueError(f"API error {resp.status_code}")
        orders = resp.json()
    except Exception as e:
        logger.error("Favorites fetch error: %s", e)
        await callback.message.edit_text(t('conn_error', lang), reply_markup=back_keyboard(lang))
        return

    if not orders:
        await callback.message.edit_text(t('no_favorites', lang), reply_markup=back_keyboard(lang))
        return

    item_counts: Counter = Counter()
    item_names: dict[str, str] = {}
    for order in orders:
        for item in order.get("items", []):
            item_id = item.get("id") or item.get("menu_item_id", "")
            name = item.get("name", "")
            qty = item.get("quantity", 1)
            if item_id:
                item_counts[item_id] += qty
                item_names[item_id] = name

    if not item_counts:
        await callback.message.edit_text(t('no_favorites', lang), reply_markup=back_keyboard(lang))
        return

    top5 = item_counts.most_common(5)
    lines = [f"• {item_names[iid]} ×{cnt}" for iid, cnt in top5]
    await callback.message.edit_text(
        f"{t('favorites_title', lang)}\n\n" + "\n".join(lines),
        reply_markup=back_keyboard(lang),
    )
