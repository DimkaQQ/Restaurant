from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton

from bot.locales import t


def lang_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🇷🇺 Русский", callback_data="lang:ru"),
            InlineKeyboardButton(text="🇰🇿 Қазақша", callback_data="lang:kz"),
            InlineKeyboardButton(text="🇬🇧 English", callback_data="lang:en"),
        ]
    ])


def main_menu_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=t('btn_menu', lang), callback_data="menu"),
            InlineKeyboardButton(text=t('btn_order', lang), callback_data="order"),
        ],
        [
            InlineKeyboardButton(text=t('btn_points', lang), callback_data="points"),
            InlineKeyboardButton(text=t('btn_history', lang), callback_data="history"),
        ],
        [
            InlineKeyboardButton(text=t('btn_favorites', lang), callback_data="favorites"),
            InlineKeyboardButton(text=t('btn_language', lang), callback_data="lang_select"),
        ],
        [
            InlineKeyboardButton(text=t('btn_venue', lang), callback_data="venue_select"),
        ],
    ])


def phone_request_keyboard(lang: str = 'ru') -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=t('share_phone_btn', lang), request_contact=True)]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def cities_keyboard(cities: list[str], lang: str = 'ru', prefix: str = "city") -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=city, callback_data=f"{prefix}:{city}")] for city in cities]
    buttons.append([InlineKeyboardButton(text=t('btn_back', lang), callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def venues_keyboard(venues: list[dict], lang: str = 'ru', prefix: str = "venue_set") -> InlineKeyboardMarkup:
    buttons = [
        [InlineKeyboardButton(text=v['name'], callback_data=f"{prefix}:{v['id']}")]
        for v in venues
    ]
    buttons.append([InlineKeyboardButton(text=t('btn_back', lang), callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def categories_keyboard(categories: list[str], lang: str = 'ru') -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text=cat, callback_data=f"cat:{cat}")] for cat in categories]
    buttons.append([InlineKeyboardButton(text=t('btn_back', lang), callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def menu_items_keyboard(items: list, category: str, lang: str = 'ru') -> InlineKeyboardMarkup:
    buttons = []
    for item in items:
        buttons.append([InlineKeyboardButton(
            text=f"{item['name']} — {item['price']} ₸",
            callback_data=f"item:{item['id']}",
        )])
    buttons.append([InlineKeyboardButton(text=t('btn_back', lang), callback_data="order")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def quantity_keyboard(item_id: str, lang: str = 'ru') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="1", callback_data=f"qty:{item_id}:1"),
            InlineKeyboardButton(text="2", callback_data=f"qty:{item_id}:2"),
            InlineKeyboardButton(text="3", callback_data=f"qty:{item_id}:3"),
        ],
        [InlineKeyboardButton(text=t('btn_back', lang), callback_data="order")],
    ])


def cart_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t('btn_confirm_order', lang), callback_data="confirm_order")],
        [InlineKeyboardButton(text=t('btn_clear_cart', lang), callback_data="clear_cart")],
        [InlineKeyboardButton(text=t('btn_add_more', lang), callback_data="order")],
    ])


def back_keyboard(lang: str = 'ru') -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t('btn_back', lang), callback_data="back_main")],
    ])


def rating_keyboard(order_id: str) -> InlineKeyboardMarkup:
    """5 star buttons for review."""
    stars = ["⭐", "⭐⭐", "⭐⭐⭐", "⭐⭐⭐⭐", "⭐⭐⭐⭐⭐"]
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=stars[i], callback_data=f"rate:{order_id}:{i+1}") for i in range(5)]
    ])


def gis_keyboard(gis_url: str, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t('review_gis', lang), url=gis_url)],
        [InlineKeyboardButton(text=t('btn_back', lang), callback_data="back_main")],
    ])


def skip_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t('btn_skip', lang), callback_data="skip_review")],
    ])
