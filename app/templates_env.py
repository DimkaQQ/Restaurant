from fastapi.templating import Jinja2Templates
from jinja2 import pass_context

from app.config import settings
from app.i18n import get_translator, LOCALE_NAMES


def _i18n_context(request):
    gettext_fn, locale = get_translator(request)
    return {"_": gettext_fn, "locale": locale, "support_url": settings.SUPPORT_URL,
            "currency": settings.CURRENCY, "locale_names": LOCALE_NAMES}


templates = Jinja2Templates(directory="app/templates", context_processors=[_i18n_context])


@pass_context
def _money(context, value) -> str:
    """Abbreviated money label. The "млн"/"тыс" suffixes are localized via the
    request's translator (pulled from the template context) so the label
    switches with the interface language instead of staying Russian."""
    if value is None:
        return "—"
    _ = context.get("_") or (lambda s: s)
    value = float(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} {_('млн')}"
    if value >= 1_000:
        return f"{value / 1_000:.0f} {_('тыс')}"
    return f"{value:.0f}"


templates.env.filters["money"] = _money
