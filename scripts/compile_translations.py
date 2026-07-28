"""Extract {{ _("...") }} message ids from every template and compile a
gettext catalog (.po + .mo) for every supported locale, reusing whatever
translations already exist in each locale's messages.po. Run from the repo
root after adding or editing a translatable string:

    python scripts/compile_translations.py

Message ids are the Russian source text, so the base locale ("ru") needs no
catalog — gettext falls back to the id. For every other locale, a new string
with no translation yet is left blank in that locale's .po (and printed as
MISSING below); gettext falls back to the Russian source at runtime, so
nothing breaks — just fill it in and re-run.

Requires `pip install babel` (dev-only dependency, see requirements-dev.txt).
"""
import glob
import os
import re

from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po, write_po

PATTERN = re.compile(
    r'_\(\s*"((?:[^"\\]|\\.)*)"\s*(?:\|\s*tojson\s*)?\)'
    r'|_\(\s*\'((?:[^\'\\]|\\.)*)\'\s*(?:\|\s*tojson\s*)?\)'
)

# "ru" is the source language (msgid == translation) so it needs no catalog.
TARGET_LOCALES = ("en", "uk", "sk", "hu", "cs")


def extract_msgids() -> list[str]:
    strings = []
    for path in sorted(glob.glob("app/templates/**/*.html", recursive=True)):
        text = open(path, encoding="utf-8").read()
        for m in PATTERN.finditer(text):
            strings.append(m.group(1) if m.group(1) is not None else m.group(2))
    # Plan-builder module labels/descriptions are rendered dynamically via
    # _(m.label) — not statically visible above — so pull them in explicitly.
    try:
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from app.services.plan_builder import MODULES
        for m in MODULES.values():
            strings.append(m["label"])
            strings.append(m["desc"])
    except Exception:
        pass
    # The abbreviated-money filter (app/templates_env.py:_money) localizes these
    # suffixes at runtime, but they aren't visible to the template scan above.
    strings.extend(["млн", "тыс"])
    return sorted(set(strings))


def compile_locale(locale: str, msgids: list[str]) -> int:
    po_path = f"locales/{locale}/LC_MESSAGES/messages.po"
    mo_path = f"locales/{locale}/LC_MESSAGES/messages.mo"
    os.makedirs(os.path.dirname(po_path), exist_ok=True)

    try:
        with open(po_path, "rb") as f:
            existing = read_po(f)
    except FileNotFoundError:
        existing = Catalog(locale=locale)

    catalog = Catalog(locale=locale)
    missing = 0
    for msgid in msgids:
        existing_msg = existing.get(msgid)
        translation = existing_msg.string if existing_msg and existing_msg.string else ""
        if not translation:
            missing += 1
        catalog.add(msgid, translation)

    with open(po_path, "wb") as f:
        write_po(f, catalog)
    with open(mo_path, "wb") as f:
        write_mo(f, catalog)
    return missing


def main() -> None:
    msgids = extract_msgids()
    print(f"Extracted {len(msgids)} translatable strings from templates.\n")
    for locale in TARGET_LOCALES:
        missing = compile_locale(locale, msgids)
        done = len(msgids) - missing
        flag = "" if not missing else f"  ⚠ {missing} untranslated (fall back to Russian)"
        print(f"  {locale}: {done}/{len(msgids)} translated{flag}")


if __name__ == "__main__":
    main()
