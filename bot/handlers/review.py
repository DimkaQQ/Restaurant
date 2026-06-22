import logging

import httpx
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message

from bot.keyboards.main import back_keyboard, gis_keyboard, skip_keyboard, main_menu_keyboard
from bot.locales import t

router = Router()
logger = logging.getLogger(__name__)


class ReviewStates(StatesGroup):
    waiting_comment = State()


@router.callback_query(F.data.startswith("rate:"))
async def handle_rating(
    callback: CallbackQuery,
    state: FSMContext,
    guest: dict,
    api_url: str,
    lang: str,
    bot_instance: Bot,
):
    await callback.answer()
    parts = callback.data.split(":")
    if len(parts) < 3:
        return
    order_id = parts[1]
    try:
        rating = int(parts[2])
    except ValueError:
        return

    tg_id = callback.from_user.id

    if rating >= 4:
        # Submit review immediately without comment
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{api_url}/api/bot/review",
                    json={
                        "order_id": order_id,
                        "guest_telegram_id": tg_id,
                        "overall_rating": rating,
                        "comment": None,
                    },
                    timeout=10.0,
                )
                result = resp.json() if resp.status_code == 200 else {}
        except Exception as e:
            logger.error("Review submit error: %s", e)
            result = {}

        gis_url = result.get("venue_gis_url")
        if gis_url:
            markup = gis_keyboard(gis_url, lang)
        else:
            markup = back_keyboard(lang)

        await callback.message.answer(
            t("review_thanks_good", lang),
            reply_markup=markup,
        )
    else:
        # Ask for comment
        await state.set_state(ReviewStates.waiting_comment)
        await state.update_data(order_id=order_id, rating=rating)
        await callback.message.answer(
            t("review_ask_comment", lang),
            reply_markup=skip_keyboard(lang),
        )


@router.message(ReviewStates.waiting_comment)
async def handle_comment(
    message: Message,
    state: FSMContext,
    guest: dict,
    api_url: str,
    lang: str,
    bot_instance: Bot,
):
    data = await state.get_data()
    order_id = data.get("order_id")
    rating = data.get("rating", 1)
    comment = message.text or ""
    tg_id = message.from_user.id

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{api_url}/api/bot/review",
                json={
                    "order_id": order_id,
                    "guest_telegram_id": tg_id,
                    "overall_rating": rating,
                    "comment": comment,
                },
                timeout=10.0,
            )
            result = resp.json() if resp.status_code == 200 else {}
    except Exception as e:
        logger.error("Review comment submit error: %s", e)
        result = {}

    await state.clear()
    await message.answer(
        t("review_thanks_bad", lang),
        reply_markup=main_menu_keyboard(lang),
    )

    # Notify manager if manager_telegram_id is set
    manager_tg_id = result.get("manager_telegram_id")
    venue_name = result.get("venue_name", "")
    guest_name = guest.get("name", "") if guest else ""

    if manager_tg_id:
        alert = (
            f"🔴 Новый негативный отзыв\n"
            f"Заведение: {venue_name}\n"
            f"Гость: {guest_name}\n"
            f"Оценка: ⭐ {rating}/5\n"
            f"Комментарий: {comment}"
        )
        try:
            await bot_instance.send_message(manager_tg_id, alert)
        except Exception as e:
            logger.warning("Could not notify manager %s: %s", manager_tg_id, e)


@router.callback_query(F.data == "skip_review")
async def skip_review(
    callback: CallbackQuery,
    state: FSMContext,
    lang: str,
):
    await callback.answer()
    await state.clear()
    await callback.message.answer(
        t("main_menu", lang),
        reply_markup=main_menu_keyboard(lang),
    )
