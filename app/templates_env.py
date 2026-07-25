from fastapi.templating import Jinja2Templates

from app.config import settings
from app.i18n import get_translator


def _i18n_context(request):
    gettext_fn, locale = get_translator(request)
    return {"_": gettext_fn, "locale": locale, "support_url": settings.SUPPORT_URL}


templates = Jinja2Templates(directory="app/templates", context_processors=[_i18n_context])


def _money(value) -> str:
    if value is None:
        return "—"
    value = float(value)
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн"
    if value >= 1_000:
        return f"{value / 1_000:.0f} тыс"
    return f"{value:.0f}"


templates.env.filters["money"] = _money
