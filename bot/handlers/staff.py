"""Staff bot handler — waiter/manager ordering and order management."""
import logging

import httpx
from bot.http_client import bot_client
from aiogram import Router, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, Message, InlineKeyboardMarkup, InlineKeyboardButton

from bot.keyboards.main import staff_menu_keyboard, table_number_keyboard, back_keyboard, categories_keyboard, menu_items_keyboard, quantity_keyboard, cart_keyboard
from bot.locales import t

router = Router()
logger = logging.getLogger(__name__)


class StaffStates(StatesGroup):
    waiting_email = State()
    waiting_password = State()
    waiting_table_custom = State()
    waiting_guest_phone = State()
    waiting_order_note = State()


@router.message(Command("staff"))
async def staff_command(message: Message, staff_user: dict | None, lang: str):
    if staff_user:
        await message.answer(
            f"👨‍💼 Меню сотрудника\n"
            f"Email: {staff_user['email']}\n"
            f"Роль: {staff_user['role']}",
            reply_markup=staff_menu_keyboard(lang),
        )
    else:
        await message.answer(
            "🔐 Войдите как сотрудник:\n\n"
            "1️⃣ <b>Через дашборд</b> (рекомендуется):\n"
            "Настройки → Мой профиль → «Привязать Telegram» → перейдите по ссылке\n\n"
            "2️⃣ <b>Через пароль</b>:\n"
            "Нажмите кнопку ниже и введите email + пароль",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔑 Войти по паролю", callback_data="staff_login_password")],
            ]),
        )


@router.callback_query(F.data == "staff_login_password")
async def start_staff_login(callback: CallbackQuery, state: FSMContext, lang: str):
    await callback.message.edit_text(t('ask_staff_email', lang))
    await state.set_state(StaffStates.waiting_email)


@router.message(StaffStates.waiting_email)
async def process_staff_email(message: Message, state: FSMContext, lang: str):
    email = message.text.strip() if message.text else ""
    if not email or "@" not in email:
        await message.answer("❌ Введите корректный email:")
        return
    await state.update_data(staff_email=email)
    await message.answer(t('ask_staff_password', lang))
    await state.set_state(StaffStates.waiting_password)


@router.message(StaffStates.waiting_password)
async def process_staff_password(message: Message, state: FSMContext, api_url: str, lang: str):
    data = await state.get_data()
    email = data.get("staff_email", "")
    password = message.text.strip() if message.text else ""
    await state.clear()

    # Delete the password message for security
    try:
        await message.delete()
    except Exception:
        pass

    try:
        async with bot_client(timeout=5.0) as client:
            resp = await client.post(
                f"{api_url}/api/bot/staff/login",
                json={"email": email, "password": password, "telegram_id": message.from_user.id},
            )
        if resp.status_code == 200:
            result = resp.json()
            await message.answer(
                t('staff_linked', lang, email=result['email']),
                reply_markup=staff_menu_keyboard(lang),
            )
        else:
            try:
                err = resp.json().get("detail", "Ошибка")
            except Exception:
                err = "Ошибка"
            await message.answer(f"❌ {err}")
    except Exception as e:
        logger.error("Staff login error: %s", e)
        await message.answer(t('conn_error', lang))


@router.callback_query(F.data == "back_staff")
async def back_to_staff_menu(callback: CallbackQuery, staff_user: dict | None, lang: str):
    if staff_user:
        await callback.message.edit_text(
            f"👨‍💼 Меню сотрудника",
            reply_markup=staff_menu_keyboard(lang),
        )
    else:
        await callback.message.edit_text("Меню сотрудника недоступно")


@router.callback_query(F.data == "staff_orders")
async def view_staff_orders(callback: CallbackQuery, staff_user: dict | None, api_url: str, lang: str):
    if not staff_user:
        await callback.answer("Требуется авторизация", show_alert=True)
        return
    try:
        async with bot_client(timeout=5.0) as client:
            resp = await client.get(
                f"{api_url}/api/bot/staff/orders/active",
                params={"telegram_id": callback.from_user.id},
            )
        orders = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error("Staff orders fetch error: %s", e)
        orders = []

    if not orders:
        await callback.message.edit_text(
            t('staff_orders_empty', lang),
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="◀ Назад", callback_data="back_staff")],
            ]),
        )
        return

    status_labels = {"new": "🆕 Новый", "confirmed": "✅ Принят", "preparing": "👨‍🍳 Готовится", "ready": "🔔 Готов"}
    lines = ["<b>📋 Активные заказы:</b>\n"]
    for o in orders:
        status = status_labels.get(o.get('status', ''), o.get('status', ''))
        lines.append(f"#{o.get('short_id', '?')} · Стол <b>{o.get('table', '—')}</b> · {float(o.get('total', 0)):.0f} ₸ · {status} · {o.get('age_min', '?')} мин")
    text = "\n".join(lines)

    await callback.message.edit_text(
        text,
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Обновить", callback_data="staff_orders")],
            [InlineKeyboardButton(text="◀ Назад", callback_data="back_staff")],
        ]),
    )


@router.callback_query(F.data == "staff_new_order")
async def staff_new_order_start(callback: CallbackQuery, state: FSMContext, staff_user: dict | None, lang: str):
    if not staff_user:
        await callback.answer("Требуется авторизация", show_alert=True)
        return
    await callback.message.edit_text(
        t('enter_table', lang),
        reply_markup=table_number_keyboard(),
    )


@router.callback_query(F.data.startswith("table:"))
async def select_table(callback: CallbackQuery, state: FSMContext, lang: str):
    value = callback.data.split(":", 1)[1]
    if value == "custom":
        await callback.message.edit_text("Введите номер стола:")
        await state.set_state(StaffStates.waiting_table_custom)
        return
    await state.update_data(staff_table=value, is_staff_order=True)
    await callback.message.edit_text(
        f"✅ {t('table_selected', lang, table=value)}\n\n👤 Введите телефон гостя (или нажмите «Пропустить»):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить →", callback_data="staff_skip_guest")],
            [InlineKeyboardButton(text="◀ Назад", callback_data="back_staff")],
        ]),
    )
    await state.set_state(StaffStates.waiting_guest_phone)


@router.message(StaffStates.waiting_table_custom)
async def process_custom_table(message: Message, state: FSMContext, lang: str):
    table = message.text.strip() if message.text else ""
    if not table:
        await message.answer("Введите номер стола:")
        return
    await state.update_data(staff_table=table, is_staff_order=True)
    await message.answer(
        f"✅ {t('table_selected', lang, table=table)}\n\n👤 Введите телефон гостя (или нажмите «Пропустить»):",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Пропустить →", callback_data="staff_skip_guest")],
            [InlineKeyboardButton(text="◀ Назад", callback_data="back_staff")],
        ]),
    )
    await state.set_state(StaffStates.waiting_guest_phone)


@router.message(StaffStates.waiting_guest_phone)
async def process_guest_phone(message: Message, state: FSMContext, api_url: str, venue_id: str, lang: str):
    phone = message.text.strip() if message.text else ""
    await state.update_data(staff_guest_phone=phone)
    await _show_menu_for_staff(message, state, api_url, venue_id, lang)


@router.callback_query(F.data == "staff_skip_guest")
async def skip_guest_phone(callback: CallbackQuery, state: FSMContext, api_url: str, venue_id: str, lang: str):
    await state.update_data(staff_guest_phone=None)
    await state.set_state(None)

    data = await state.get_data()
    effective_venue = data.get('order_venue_id') or venue_id

    try:
        async with bot_client() as client:
            resp = await client.get(f"{api_url}/api/bot/menu", params={"venue_id": effective_venue}, timeout=5.0)
            items = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error("Menu fetch error: %s", e)
        items = []

    available = [i for i in items if i.get("is_available")]
    if not available:
        await callback.message.edit_text(t('no_menu', lang), reply_markup=back_keyboard(lang))
        return

    categories = list(dict.fromkeys(i.get("category", "Прочее") for i in available))
    await callback.message.edit_text(t('choose_category', lang), reply_markup=categories_keyboard(categories, lang))


async def _show_menu_for_staff(message: Message, state: FSMContext, api_url: str, venue_id: str, lang: str):
    await state.set_state(None)
    data = await state.get_data()
    effective_venue = data.get('order_venue_id') or venue_id

    try:
        async with bot_client() as client:
            resp = await client.get(f"{api_url}/api/bot/menu", params={"venue_id": effective_venue}, timeout=5.0)
            items = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error("Menu fetch error: %s", e)
        items = []

    available = [i for i in items if i.get("is_available")]
    categories = list(dict.fromkeys(i.get("category", "Прочее") for i in available))
    await message.answer(t('choose_category', lang), reply_markup=categories_keyboard(categories, lang))


@router.callback_query(F.data == "confirm_staff_order")
async def confirm_staff_order(
    callback: CallbackQuery,
    state: FSMContext,
    staff_user: dict | None,
    api_url: str,
    venue_id: str,
    lang: str,
):
    if not staff_user:
        await callback.answer("Требуется авторизация", show_alert=True)
        return

    data = await state.get_data()
    cart: list = data.get("cart", [])
    effective_venue = data.get("order_venue_id") or staff_user.get("venue_id") or venue_id
    table_number = data.get("staff_table")
    guest_phone = data.get("staff_guest_phone")
    notes = data.get("order_notes") or None

    if not cart:
        await callback.answer(t('cart_empty', lang), show_alert=True)
        return

    order_items = [{"menu_item_id": e["id"], "quantity": e["qty"], "comment": e.get("comment")} for e in cart]
    try:
        async with bot_client() as client:
            resp = await client.post(
                f"{api_url}/api/bot/staff/order",
                params={"telegram_id": callback.from_user.id},
                json={
                    "venue_id": effective_venue,
                    "items": order_items,
                    "table_number": table_number,
                    "notes": notes,
                    "guest_phone": guest_phone,
                },
                timeout=10.0,
            )
        if resp.status_code == 200:
            order = resp.json()
            short_id = order["id"][:8].upper()
            await state.update_data(cart=[], order_notes="", staff_table=None)
            await callback.message.edit_text(
                f"✅ Заказ #{short_id} принят!\n"
                f"Стол: {order.get('table_number') or '—'}\n"
                f"Сумма: {float(order['total_amount']):.0f} ₸",
                reply_markup=staff_menu_keyboard(lang),
            )
        else:
            err = resp.json().get("detail", "Ошибка") if resp.content else "Ошибка"
            await callback.message.edit_text(t('order_error', lang, err=err), reply_markup=back_keyboard(lang))
    except Exception as e:
        logger.error("Staff order error: %s", e)
        await callback.message.edit_text(t('conn_error', lang), reply_markup=back_keyboard(lang))


class StaffFindGuestStates(StatesGroup):
    waiting_phone = State()


@router.callback_query(F.data == "staff_find_guest")
async def staff_find_guest_start(callback: CallbackQuery, state: FSMContext, staff_user: dict | None, lang: str):
    if not staff_user:
        await callback.answer("Требуется авторизация", show_alert=True)
        return
    await callback.message.edit_text(
        "🔍 Введите номер телефона гостя:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Назад", callback_data="back_staff")],
        ]),
    )
    await state.set_state(StaffFindGuestStates.waiting_phone)


@router.message(StaffFindGuestStates.waiting_phone)
async def staff_find_guest_search(message: Message, state: FSMContext, api_url: str, lang: str, network_id: str):
    phone = message.text.strip() if message.text else ""
    await state.clear()
    if not phone:
        await message.answer("❌ Введите номер телефона", reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Назад", callback_data="back_staff")],
        ]))
        return
    try:
        async with bot_client(timeout=5.0) as client:
            resp = await client.get(f"{api_url}/api/bot/guest-search", params={"phone": phone, "network_id": network_id})
        if resp.status_code == 200:
            g = resp.json()
            name = g.get("name") or "—"
            pts = g.get("total_points", 0)
            visits = g.get("total_visits", 0)
            await message.answer(
                f"👤 <b>{name}</b>\n📞 {phone}\n⭐ Баллы: {pts} · Визиты: {visits}",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀ Назад", callback_data="back_staff")],
                ]),
            )
        else:
            await message.answer(
                f"❌ Гость с номером {phone} не найден",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="◀ Назад", callback_data="back_staff")],
                ]),
            )
    except Exception as e:
        logger.error("Staff find guest error: %s", e)
        await message.answer(t('conn_error', lang), reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="◀ Назад", callback_data="back_staff")],
        ]))
