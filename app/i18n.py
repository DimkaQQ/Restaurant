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

from app.config import settings

LOCALES_DIR = Path(__file__).parent.parent / "locales"
SUPPORTED_LOCALES = ("ru", "en", "uk", "sk", "hu", "cs")
DEFAULT_LOCALE = settings.DEFAULT_LOCALE if settings.DEFAULT_LOCALE in ("ru", "en", "uk", "sk", "hu", "cs") else "en"

# Native names for the Settings language picker (value -> label shown to user).
LOCALE_NAMES = {
    "ru": "Русский",
    "en": "English",
    "uk": "Українська",
    "sk": "Slovenčina",
    "hu": "Magyar",
    "cs": "Čeština",
}

# Only these (pre-auth) surfaces may switch language via ?lang= — a visitor
# with no account needs a way to read the funnel in their language. Inside the
# app the language is a persisted Settings choice, so the query param is
# ignored there (no URL backdoor around the setting).
_PUBLIC_LANG_PREFIXES = ("/auth/", "/legal/")

_catalogs: dict[str, gettext.NullTranslations] = {}


def _load(locale: str) -> gettext.NullTranslations:
    if locale not in _catalogs:
        try:
            _catalogs[locale] = gettext.translation("messages", localedir=str(LOCALES_DIR), languages=[locale])
        except FileNotFoundError:
            _catalogs[locale] = gettext.NullTranslations()
    return _catalogs[locale]


def _is_public_lang_path(path: str) -> bool:
    return path == "/" or path.startswith(_PUBLIC_LANG_PREFIXES)


def get_locale(request: Request) -> str:
    # No Accept-Language auto-detection (unlike the guest-facing online-order
    # page) — owners/staff often run an English-locale OS but expect Russian by
    # default. Language is a persisted Settings choice carried in the `lang`
    # cookie; ?lang= is honored only on the pre-auth funnel (landing/auth/legal)
    # so a logged-in user can't bypass their setting via the URL.
    if _is_public_lang_path(request.url.path):
        q = request.query_params.get("lang")
        if q in SUPPORTED_LOCALES:
            return q
    cookie = request.cookies.get("lang")
    if cookie in SUPPORTED_LOCALES:
        return cookie
    return DEFAULT_LOCALE


def get_translator(request: Request):
    """Returns (gettext_fn, locale) for the current request — pass the fn
    into the template context as `_` and call `{{ _("Russian source text") }}`."""
    locale = get_locale(request)
    return _load(locale).gettext, locale
