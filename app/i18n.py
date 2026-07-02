"""Minimal gettext-based i18n. Message ids are the Russian source text, so a
missing/未compiled catalog (or the default "ru" locale) just returns the
original string unchanged — nothing breaks if a template isn't wired up yet.

Currently translated: landing page, login/register/forgot/reset-password,
Terms of Service, Privacy Policy. The rest of the app (dashboard, settings,
analytics, etc.) is still Russian-only — see the launch-readiness audit for
the full picture; this covers what a prospective non-Russian-speaking
customer sees before signing up.
"""
import gettext
from pathlib import Path

from fastapi import Request

LOCALES_DIR = Path(__file__).parent.parent / "locales"
SUPPORTED_LOCALES = ("ru", "en")
DEFAULT_LOCALE = "ru"

_catalogs: dict[str, gettext.NullTranslations] = {}


def _load(locale: str) -> gettext.NullTranslations:
    if locale not in _catalogs:
        try:
            _catalogs[locale] = gettext.translation("messages", localedir=str(LOCALES_DIR), languages=[locale])
        except FileNotFoundError:
            _catalogs[locale] = gettext.NullTranslations()
    return _catalogs[locale]


def get_locale(request: Request) -> str:
    q = request.query_params.get("lang")
    if q in SUPPORTED_LOCALES:
        return q
    cookie = request.cookies.get("lang")
    if cookie in SUPPORTED_LOCALES:
        return cookie
    accept = request.headers.get("accept-language", "")
    if accept.lower().startswith("en"):
        return "en"
    return DEFAULT_LOCALE


def get_translator(request: Request):
    """Returns (gettext_fn, locale) for the current request — pass the fn
    into the template context as `_` and call `{{ _("Russian source text") }}`."""
    locale = get_locale(request)
    return _load(locale).gettext, locale
