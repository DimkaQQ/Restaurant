import logging

import httpx
from aiogram import Router, F
from aiogram.types import CallbackQuery

from bot.keyboards.main import back_keyboard

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "points")
async def show_points(callback: CallbackQuery, guest: dict | None):
    if not guest:
        await callback.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return
    points = guest["total_points"]
    tenge_value = points * 5
    await callback.message.edit_text(
        f"⭐ *Ваши баллы*\n\n"
        f"Накоплено: *{points} баллов*\n"
        f"Это {tenge_value} ₸ скидки\n\n"
        f"Баллы начисляются во всех заведениях сети.\n"
        f"100 баллов = скидка 500 ₸",
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )


@router.callback_query(F.data == "history")
async def show_history(callback: CallbackQuery, guest: dict | None, api_url: str):
    if not guest:
        await callback.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{api_url}/api/orders/",
                params={"telegram_id": guest["telegram_id"]},
                timeout=5.0,
            )
            if resp.status_code != 200:
                raise ValueError("API error")
    except Exception as e:
        logger.error("History fetch error: %s", e)
        await callback.message.edit_text("Не удалось загрузить историю.", reply_markup=back_keyboard())
        return

    orders = resp.json()
    if not orders:
        await callback.message.edit_text("У вас пока нет заказов.", reply_markup=back_keyboard())
        return

    status_map = {
        "new": "🆕", "confirmed": "✅", "preparing": "👨‍🍳",
        "ready": "🔔", "done": "✔️", "cancelled": "❌",
    }
    lines = []
    for o in orders[:10]:
        st = status_map.get(o["status"], "")
        items_str = ", ".join(f"{i['name']}" for i in o.get("items", []))
        lines.append(f"{st} {float(o['total_amount']):.0f} ₸ — {items_str}")

    await callback.message.edit_text(
        f"📜 *Ваши последние заказы*\n\n" + "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=back_keyboard(),
    )
