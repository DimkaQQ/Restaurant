"""Per-venue, per-surface appearance resolution. A surface is one screen
type (kitchen/pos/inventory/dashboard/waiter). The venue stores an optional
{theme, accent} per surface; screens apply it server-side (pre-paint) so a
physical kitchen/register tied to a venue looks the way the owner set it,
independent of any single device."""

SURFACES = ("dashboard", "pos", "kitchen", "inventory", "waiter")
_THEMES = ("dark", "black", "light")


def _valid_accent(a: str | None) -> str | None:
    if not a or not isinstance(a, str):
        return None
    a = a.strip()
    if len(a) == 7 and a[0] == "#" and all(c in "0123456789abcdefABCDEF" for c in a[1:]):
        return a
    return None


def surface_appearance(venue, surface: str) -> dict:
    """Return {theme, accent, on_accent} for a venue's surface, or {} if the
    owner hasn't set one (screen then uses its own default / device theme)."""
    if venue is None or not getattr(venue, "appearance", None):
        return {}
    conf = venue.appearance.get(surface) if isinstance(venue.appearance, dict) else None
    if not isinstance(conf, dict):
        return {}
    theme = conf.get("theme")
    accent = _valid_accent(conf.get("accent"))
    out = {}
    if theme in _THEMES:
        out["theme"] = theme
    if accent:
        out["accent"] = accent
        r, g, b = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
        # WCAG-ish luminance → readable text color on the accent
        out["on_accent"] = "#0D0D0D" if (0.2126 * r + 0.7152 * g + 0.0722 * b) > 150 else "#FFFFFF"
    return out
