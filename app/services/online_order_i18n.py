"""Guest-facing translations for the QR/online-order page. Separate from
app/i18n.py (the staff RU/EN switcher, persisted via a cookie) because the
audience is different: an anonymous guest scanning a table QR code, with
no login and (until they submit an order with a phone number) no Guest
row to read a language preference from. Kazakh is included here since
guests are the actual KZ market audience — staff-facing screens are not.

Language is picked per-request (query param > cookie > browser
Accept-Language > ru) and, once a guest is identified (phone on submit),
written back to Guest.language so it's remembered for bot broadcasts too.
"""

SUPPORTED = ("ru", "kz", "en")
DEFAULT = "ru"

STRINGS = {
    "ru": {
        "online_menu": "Онлайн меню",
        "table": "Стол",
        "cart_empty": "Корзина пуста",
        "positions": "позиций",
        "cart": "Корзина",
        "total": "Итого",
        "name_optional": "Имя (необязательно)",
        "your_name": "Ваше имя",
        "phone_for_points": "Телефон (для бонусных баллов)",
        "order_comment": "Комментарий к заказу",
        "allergies_placeholder": "Аллергии, пожелания...",
        "place_order": "Заказать",
        "continue_browsing": "Продолжить выбор",
        "item_wishes": "Пожелания к блюду",
        "comment_placeholder": "Например: без лука, хорошо прожарить...",
        "save": "Сохранить",
        "skip": "Пропустить",
        "order_number": "Заказ #",
        "order_accepted": "Ваш заказ принят!",
        "preparing_now": "Мы готовим его прямо сейчас.",
        "points_earned": "бонусных баллов начислено!",
        "order_again": "Сделать ещё заказ",
        "placing_order": "Оформляем...",
        "order_error": "Ошибка при оформлении заказа",
        "connection_error": "Ошибка соединения",
        "venue_not_found": "Заведение не найдено",
        "cart_empty_error": "Корзина пуста",
        "other_category": "Прочее",
        "guest": "Гость",
        "online_guest": "Онлайн-гость",
    },
    "kz": {
        "online_menu": "Онлайн мәзір",
        "table": "Үстел",
        "cart_empty": "Себет бос",
        "positions": "позиция",
        "cart": "Себет",
        "total": "Барлығы",
        "name_optional": "Аты (міндетті емес)",
        "your_name": "Сіздің атыңыз",
        "phone_for_points": "Телефон (бонус ұпайлары үшін)",
        "order_comment": "Тапсырысқа түсініктеме",
        "allergies_placeholder": "Аллергия, тілектер...",
        "place_order": "Тапсырыс беру",
        "continue_browsing": "Таңдауды жалғастыру",
        "item_wishes": "Тағамға тілектер",
        "comment_placeholder": "Мысалы: пиязсыз, жақсылап қуырылған...",
        "save": "Сақтау",
        "skip": "Өткізіп жіберу",
        "order_number": "Тапсырыс #",
        "order_accepted": "Тапсырысыңыз қабылданды!",
        "preparing_now": "Біз оны дәл қазір дайындап жатырмыз.",
        "points_earned": "бонус ұпай есептелді!",
        "order_again": "Тағы тапсырыс беру",
        "placing_order": "Рәсімделуде...",
        "order_error": "Тапсырысты рәсімдеу кезінде қате пайда болды",
        "connection_error": "Байланыс қатесі",
        "venue_not_found": "Мекеме табылмады",
        "cart_empty_error": "Себет бос",
        "other_category": "Басқа",
        "guest": "Қонақ",
        "online_guest": "Онлайн-қонақ",
    },
    "en": {
        "online_menu": "Online Menu",
        "table": "Table",
        "cart_empty": "Cart is empty",
        "positions": "items",
        "cart": "Cart",
        "total": "Total",
        "name_optional": "Name (optional)",
        "your_name": "Your name",
        "phone_for_points": "Phone (for bonus points)",
        "order_comment": "Order comment",
        "allergies_placeholder": "Allergies, requests...",
        "place_order": "Place order",
        "continue_browsing": "Continue browsing",
        "item_wishes": "Notes for this dish",
        "comment_placeholder": "E.g.: no onions, well done...",
        "save": "Save",
        "skip": "Skip",
        "order_number": "Order #",
        "order_accepted": "Your order has been received!",
        "preparing_now": "We're preparing it right now.",
        "points_earned": "bonus points earned!",
        "order_again": "Place another order",
        "placing_order": "Placing order...",
        "order_error": "Failed to place order",
        "connection_error": "Connection error",
        "venue_not_found": "Venue not found",
        "cart_empty_error": "Cart is empty",
        "other_category": "Other",
        "guest": "Guest",
        "online_guest": "Online guest",
    },
}


def get_guest_lang(query_lang: str | None, cookie_lang: str | None, accept_language: str | None) -> str:
    if query_lang in SUPPORTED:
        return query_lang
    if cookie_lang in SUPPORTED:
        return cookie_lang
    if accept_language:
        head = accept_language.split(",")[0].strip().lower()[:2]
        if head == "kk":  # ISO 639-1 for Kazakh; guest.language/UI convention here uses "kz"
            return "kz"
        if head == "en":
            return "en"
    return DEFAULT


def t(lang: str) -> dict:
    return STRINGS.get(lang, STRINGS[DEFAULT])
