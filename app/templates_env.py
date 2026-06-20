from fastapi.templating import Jinja2Templates

templates = Jinja2Templates(directory="app/templates")


def _money(value: float) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f} млн"
    if value >= 1_000:
        return f"{value / 1_000:.0f} тыс"
    return f"{value:.0f}"


templates.env.filters["money"] = _money
