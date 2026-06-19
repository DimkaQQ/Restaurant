from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton


def main_menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="📋 Меню", callback_data="menu"),
            InlineKeyboardButton(text="🛒 Заказать", callback_data="order"),
        ],
        [
            InlineKeyboardButton(text="⭐ Мои баллы", callback_data="points"),
            InlineKeyboardButton(text="📜 История", callback_data="history"),
        ],
    ])


def phone_request_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="📱 Поделиться номером", request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def categories_keyboard(categories: list[str]) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}")] for cat in categories]
    buttons.append([InlineKeyboardButton(text="◀ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def menu_items_keyboard(items: list, category: str) -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        buttons.append([InlineKeyboardButton(
            text=f"{item['name']} — {item['price']} ₸",
            callback_data=f"item:{item['id']}",
        )])
    buttons.append([InlineKeyboardButton(text="◀ Категории", callback_data="order")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def quantity_keyboard(item_id: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data=f"qty:{item_id}:1"),
            InlineKeyboardButton(text="2", callback_data=f"qty:{item_id}:2"),
            InlineKeyboardButton(text="3", callback_data=f"qty:{item_id}:3"),
        ],
        [InlineKeyboardButton(text="◀ Назад", callback_data="order")],
    ])


def cart_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Подтвердить заказ", callback_data="confirm_order")],
        [InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")],
        [InlineKeyboardButton(text="➕ Добавить ещё", callback_data="order")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="◀ Главное меню", callback_data="back_main")],
    ])
