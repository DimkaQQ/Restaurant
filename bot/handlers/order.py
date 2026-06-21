import logging

import httpx
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.main import (
    categories_keyboard, quantity_keyboard, cart_keyboard, back_keyboard, main_menu_keyboard
)

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


def format_cart(cart: list, menu_map: dict) -> str:
    if not cart:
        return "Корзина пуста."
    lines = []
    total = 0
    for entry in cart:
        item = menu_map.get(entry["id"])
        if not item:
            continue
        subtotal = float(item["price"]) * entry["qty"]
        total += subtotal
        lines.append(f"• {item['name']} × {entry['qty']} = {subtotal:.0f} ₸")
    lines.append(f"\n💰 *Итого: {total:.0f} ₸*")
    return "\n".join(lines)


@router.callback_query(F.data == "order")
async def start_order(callback: CallbackQuery, state: FSMContext, api_url: str, venue_id: str):
    items = await fetch_menu(api_url, venue_id)
    available = [i for i in items if i.get("is_available")]
    if not available:
        await callback.message.edit_text("Меню недоступно.", reply_markup=back_keyboard())
        return
    categories = list(dict.fromkeys(i.get("category", "Прочее") for i in available))
    await callback.message.edit_text(
        "🛒 *Заказ*\nВыберите категорию:",
        parse_mode="Markdown",
        reply_markup=categories_keyboard(categories),
    )


@router.callback_query(F.data.startswith("item:"))
async def choose_item(callback: CallbackQuery, api_url: str, venue_id: str):
    item_id = callback.data.split(":", 1)[1]
    items = await fetch_menu(api_url, venue_id)
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        await callback.answer("Позиция не найдена", show_alert=True)
        return
    await callback.message.edit_text(
        f"*{item['name']}*\n{item.get('description', '')}\nЦена: {item['price']} ₸\n\nСколько?",
        parse_mode="Markdown",
        reply_markup=quantity_keyboard(item_id),
    )


@router.callback_query(F.data.startswith("qty:"))
async def add_to_cart(callback: CallbackQuery, state: FSMContext, api_url: str, venue_id: str):
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer("Ошибка", show_alert=True)
        return
    _, item_id, qty_str = parts
    try:
        qty = int(qty_str)
    except ValueError:
        await callback.answer("Ошибка", show_alert=True)
        return

    data = await state.get_data()
    cart: list = data.get("cart", [])

    existing = next((e for e in cart if e["id"] == item_id), None)
    if existing:
        existing["qty"] += qty
    else:
        cart.append({"id": item_id, "qty": qty})
    await state.update_data(cart=cart)

    items = await fetch_menu(api_url, venue_id)
    menu_map = {i["id"]: i for i in items}
    text = "🛒 *Корзина*\n\n" + format_cart(cart, menu_map)
    await callback.message.edit_text(text, parse_mode="Markdown", reply_markup=cart_keyboard())


@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery, state: FSMContext):
    await state.update_data(cart=[])
    await callback.message.edit_text("Корзина очищена.", reply_markup=back_keyboard())


@router.callback_query(F.data == "confirm_order")
async def confirm_order(callback: CallbackQuery, state: FSMContext, guest: dict | None, api_url: str, venue_id: str):
    if not guest:
        await callback.answer("Сначала зарегистрируйтесь через /start", show_alert=True)
        return

    data = await state.get_data()
    cart: list = data.get("cart", [])
    if not cart:
        await callback.answer("Корзина пуста", show_alert=True)
        return

    order_items = [{"menu_item_id": e["id"], "quantity": e["qty"]} for e in cart]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{api_url}/api/orders/",
                params={"telegram_id": guest["telegram_id"]},
                json={"venue_id": venue_id, "items": order_items},
                timeout=10.0,
            )
        if resp.status_code in (200, 201):
            order = resp.json()
            short_id = order["id"][:8].upper()
            await state.update_data(cart=[])
            await callback.message.edit_text(
                f"✅ *Заказ #{short_id} принят!*\n\n"
                f"Сумма: {float(order['total_amount']):.0f} ₸\n"
                f"Начислено баллов: +{order['points_earned']}\n\n"
                f"⏱ Ожидайте ~15 минут.",
                parse_mode="Markdown",
                reply_markup=main_menu_keyboard(),
            )
        else:
            try:
                err = resp.json().get("detail", "Ошибка")
            except Exception:
                err = "Ошибка"
            await callback.message.edit_text(f"❌ Ошибка: {err}", reply_markup=back_keyboard())
    except Exception as e:
        logger.error("Order creation error: %s", e)
        await callback.message.edit_text("❌ Ошибка соединения. Попробуйте позже.", reply_markup=back_keyboard())
