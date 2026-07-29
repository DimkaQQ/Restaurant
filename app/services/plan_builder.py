"""Build-your-own subscription: the modules a network can add to a base plan,
their monthly prices, and price computation. All prices live here so they're
trivial to adjust — nothing else hardcodes a number.

Base plan (always included): POS/касса, кухня (KDS), официант, меню, столы,
склад, смены, QR-меню и гости — plus 1 venue and up to 3 staff.
"""
CURRENCY = "$"
BASE_PRICE = 19          # per month — core product + 1 venue + 3 staff
EXTRA_VENUE_PRICE = 9    # per additional venue

# module key -> price + copy. Keys must match the feature names checked by
# app.services.plan_limits.network_has_feature (analytics/finance/api/whitelabel)
# so toggling a module directly controls access; "marketing" and
# "unlimited_staff" are additional gated capabilities.
MODULES = {
    "analytics":       {"price": 12, "label": "Аналитика и NPS",
                        "desc": "Графики продаж, популярные позиции, оценки гостей (NPS)."},
    "finance":         {"price": 12, "label": "Финансы и P&L",
                        "desc": "Расходы, прибыль, P&L и выгрузка для бухгалтерии."},
    "marketing":       {"price": 9,  "label": "Маркетинг",
                        "desc": "Промокоды и рассылки гостям в QR-меню."},
    "unlimited_staff": {"price": 9,  "label": "Безлимит сотрудников",
                        "desc": "Снять лимит в 3 сотрудника — сколько угодно ролей."},
    "api":             {"price": 15, "label": "API и веб-хуки",
                        "desc": "REST API и веб-хуки заказов для интеграций."},
    "whitelabel":      {"price": 19, "label": "White-label оформление",
                        "desc": "Своя тема и цвет на каждом экране заведения."},
}

MODULE_ORDER = ["analytics", "finance", "marketing", "unlimited_staff", "api", "whitelabel"]


def compute_price(features: list[str], extra_venues: int) -> int:
    """Monthly price in whole currency units for the chosen modules + venues."""
    total = BASE_PRICE + EXTRA_VENUE_PRICE * max(0, int(extra_venues or 0))
    for f in features or []:
        m = MODULES.get(f)
        if m:
            total += m["price"]
    return total


def sanitize_features(features) -> list[str]:
    """Keep only known module keys, de-duplicated, in canonical order."""
    chosen = set(f for f in (features or []) if f in MODULES)
    return [k for k in MODULE_ORDER if k in chosen]
