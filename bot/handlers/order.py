import logging

import httpx
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery

from bot.keyboards.main import (
    categories_keyboard, menu_items_keyboard, quantity_keyboard, cart_keyboard, back_keyboard,
    main_menu_keyboard, cities_keyboard, venues_keyboard,
)
from bot.locales import t

router = Router()
logger = logging.getLogger(__name__)


async def fetch_menu(api_url: str, venue_id: str) -> list[dict]:
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"{api_url}/api/bot/menu", params={"venue_id": venue_id}, timeout=5.0)
            return resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error("Fetch menu error: %s", e)
        return []


def format_cart(cart: list, menu_map: dict, lang: str = 'ru') -> str:
    if not cart:
        return t('cart_empty', lang)
    lines = []
    total = 0
    for entry in cart:
        item = menu_map.get(entry["id"])
        if not item:
            continue
        subtotal = float(item["price"]) * entry["qty"]
        total += subtotal
        lines.append(f"• {item['name']} × {entry['qty']} = {subtotal:.0f} ₸")
    lines.append(f"\n💰 <b>{t('total', lang)}: {total:.0f} ₸</b>")
    return "\n".join(lines)


async def show_categories(callback: CallbackQuery, api_url: str, venue_id: str, lang: str):
    items = await fetch_menu(api_url, venue_id)
    available = [i for i in items if i.get("is_available")]
    if not available:
        await callback.message.edit_text(t('no_menu', lang), reply_markup=back_keyboard(lang))
        return
    categories = list(dict.fromkeys(i.get("category", "Прочее") for i in available))
    await callback.message.edit_text(
        t('choose_category', lang),
        reply_markup=categories_keyboard(categories, lang),
    )


@router.callback_query(F.data == "order")
async def start_order(
    callback: CallbackQuery,
    state: FSMContext,
    guest: dict | None,
    api_url: str,
    venue_id: str,
    network_id: str,
    lang: str,
):
    preferred_venue_id = guest.get('preferred_venue_id') if guest else None
    effective_venue = preferred_venue_id or venue_id

    if not preferred_venue_id:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{api_url}/api/bot/venues",
                    params={"network_id": network_id},
                    timeout=5.0,
                )
                venues = resp.json() if resp.status_code == 200 else []
        except Exception as e:
            logger.error("Venues fetch error: %s", e)
            venues = []

        if len(venues) > 1:
            cities = list(dict.fromkeys(v.get('city') or '' for v in venues if v.get('city')))
            await state.update_data(order_flow=True)
            if cities:
                await callback.message.edit_text(
                    t('choose_city', lang),
                    reply_markup=cities_keyboard(cities, lang, prefix="order_city"),
                )
            else:
                await callback.message.edit_text(
                    t('choose_venue', lang),
                    reply_markup=venues_keyboard(venues, lang, prefix="venue_order"),
                )
            return

    await state.update_data(order_venue_id=effective_venue)
    await show_categories(callback, api_url, effective_venue, lang)


@router.callback_query(F.data.startswith("venue_order:"))
async def venue_order_selected(
    callback: CallbackQuery,
    state: FSMContext,
    api_url: str,
    lang: str,
):
    venue_id = callback.data.split(":", 1)[1]
    await state.update_data(order_venue_id=venue_id, order_flow=False)
    await show_categories(callback, api_url, venue_id, lang)


@router.callback_query(F.data.startswith("order_city:"))
async def order_city_selected(
    callback: CallbackQuery,
    state: FSMContext,
    api_url: str,
    network_id: str,
    lang: str,
):
    city = callback.data.split(":", 1)[1]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{api_url}/api/bot/venues",
                params={"network_id": network_id},
                timeout=5.0,
            )
            venues = resp.json() if resp.status_code == 200 else []
    except Exception as e:
        logger.error("Venues fetch error: %s", e)
        venues = []

    city_venues = [v for v in venues if v.get('city') == city]
    if not city_venues:
        await callback.message.edit_text(t('no_venues', lang), reply_markup=back_keyboard(lang))
        return

    await callback.message.edit_text(
        t('choose_venue', lang),
        reply_markup=venues_keyboard(city_venues, lang, prefix="venue_order"),
    )


@router.callback_query(F.data.startswith("cat:"))
async def show_category(callback: CallbackQuery, state: FSMContext, api_url: str, venue_id: str, lang: str):
    category = callback.data.split(":", 1)[1]
    data = await state.get_data()
    effective_venue = data.get('order_venue_id') or venue_id

    items = await fetch_menu(api_url, effective_venue)
    cat_items = [i for i in items if i.get("category") == category and i.get("is_available")]

    if not cat_items:
        await callback.answer(t('no_menu', lang), show_alert=True)
        return

    text = f"<b>{category}</b>\n\n" + "\n".join(
        f"• {i['name']} — {float(i['price']):.0f} ₸"
        + (f"\n  <i>{i['description']}</i>" if i.get('description') else "")
        for i in cat_items
    )
    await callback.message.edit_text(
        text,
        reply_markup=menu_items_keyboard(cat_items, category, lang),
    )


@router.callback_query(F.data.startswith("item:"))
async def choose_item(callback: CallbackQuery, state: FSMContext, api_url: str, venue_id: str, lang: str):
    item_id = callback.data.split(":", 1)[1]
    data = await state.get_data()
    effective_venue = data.get('order_venue_id') or venue_id

    items = await fetch_menu(api_url, effective_venue)
    item = next((i for i in items if i["id"] == item_id), None)
    if not item:
        await callback.answer(t('no_menu', lang), show_alert=True)
        return
    desc_line = f"\n{item['description']}" if item.get('description') else ""
    await callback.message.edit_text(
        f"<b>{item['name']}</b>{desc_line}\n{t('price', lang, price=f\"{float(item['price']):.0f}\")}\n\n{t('choose_qty', lang)}",
        reply_markup=quantity_keyboard(item_id, lang),
    )


@router.callback_query(F.data.startswith("qty:"))
async def add_to_cart(callback: CallbackQuery, state: FSMContext, api_url: str, venue_id: str, lang: str):
    parts = callback.data.split(":", 2)
    if len(parts) != 3:
        await callback.answer(t('order_error', lang, err='invalid'), show_alert=True)
        return
    _, item_id, qty_str = parts
    try:
        qty = int(qty_str)
    except ValueError:
        await callback.answer(t('order_error', lang, err='invalid qty'), show_alert=True)
        return

    data = await state.get_data()
    cart: list = data.get("cart", [])
    effective_venue = data.get('order_venue_id') or venue_id

    existing = next((e for e in cart if e["id"] == item_id), None)
    if existing:
        existing["qty"] += qty
    else:
        cart.append({"id": item_id, "qty": qty})
    await state.update_data(cart=cart)

    items = await fetch_menu(api_url, effective_venue)
    menu_map = {i["id"]: i for i in items}
    text = f"{t('cart_title', lang)}\n\n" + format_cart(cart, menu_map, lang)
    await callback.message.edit_text(text, reply_markup=cart_keyboard(lang))


@router.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery, state: FSMContext, lang: str):
    await state.update_data(cart=[])
    await callback.message.edit_text(t('cart_empty', lang), reply_markup=back_keyboard(lang))


@router.callback_query(F.data == "confirm_order")
async def confirm_order(
    callback: CallbackQuery,
    state: FSMContext,
    guest: dict | None,
    api_url: str,
    venue_id: str,
    lang: str,
):
    if not guest:
        await callback.answer(t('register_first', lang), show_alert=True)
        return

    data = await state.get_data()
    cart: list = data.get("cart", [])
    effective_venue = data.get('order_venue_id') or venue_id

    if not cart:
        await callback.answer(t('cart_empty', lang), show_alert=True)
        return

    order_items = [{"menu_item_id": e["id"], "quantity": e["qty"]} for e in cart]
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{api_url}/api/orders/",
                params={"telegram_id": guest["telegram_id"]},
                json={"venue_id": effective_venue, "items": order_items},
                timeout=10.0,
            )
        if resp.status_code in (200, 201):
            order = resp.json()
            short_id = order["id"][:8].upper()
            await state.update_data(cart=[])
            await callback.message.edit_text(
                t('order_ok', lang,
                  short_id=short_id,
                  amount=f"{float(order['total_amount']):.0f}",
                  points=order['points_earned']),
                reply_markup=main_menu_keyboard(lang),
            )
        else:
            try:
                err = resp.json().get("detail", "Ошибка")
            except Exception:
                err = "Ошибка"
            await callback.message.edit_text(
                t('order_error', lang, err=err),
                reply_markup=back_keyboard(lang),
            )
    except Exception as e:
        logger.error("Order creation error: %s", e)
        await callback.message.edit_text(t('conn_error', lang), reply_markup=back_keyboard(lang))


