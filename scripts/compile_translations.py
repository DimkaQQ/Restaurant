"""Extract {{ _("...") }} message ids from every template and compile
locales/en/LC_MESSAGES/messages.mo, reusing existing translations from
messages.po. Run from the repo root after adding or editing a translatable
string:

    python scripts/compile_translations.py

New strings with no translation yet are left untranslated in the .po (and
print as MISSING below) — gettext falls back to the Russian source text for
those at runtime, so nothing breaks; just fill them in and re-run.

Requires `pip install babel` (dev-only dependency, see requirements-dev.txt).
"""
import glob
import re

from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.messages.pofile import read_po, write_po

PATTERN = re.compile(
    r'_\(\s*"((?:[^"\\]|\\.)*)"\s*(?:\|\s*tojson\s*)?\)'
    r'|_\(\s*\'((?:[^\'\\]|\\.)*)\'\s*(?:\|\s*tojson\s*)?\)'
)
PO_PATH = "locales/en/LC_MESSAGES/messages.po"
MO_PATH = "locales/en/LC_MESSAGES/messages.mo"


def extract_msgids() -> list[str]:
    strings = []
    for path in sorted(glob.glob("app/templates/**/*.html", recursive=True)):
        text = open(path, encoding="utf-8").read()
        for m in PATTERN.finditer(text):
            strings.append(m.group(1) if m.group(1) is not None else m.group(2))
    return sorted(set(strings))


def main() -> None:
    msgids = extract_msgids()

    try:
        with open(PO_PATH, "rb") as f:
            existing = read_po(f)
    except FileNotFoundError:
        existing = Catalog(locale="en")

    catalog = Catalog(locale="en")
    missing = []
    for msgid in msgids:
        existing_msg = existing.get(msgid)
        translation = existing_msg.string if existing_msg and existing_msg.string else ""
        if not translation:
            missing.append(msgid)
        catalog.add(msgid, translation)

    with open(PO_PATH, "wb") as f:
        write_po(f, catalog)
    with open(MO_PATH, "wb") as f:
        write_mo(f, catalog)

    print(f"Compiled {len(msgids)} strings ({len(missing)} untranslated).")
    if missing:
        print("\nMISSING TRANSLATIONS (fall back to Russian until filled in):")
        for m in missing:
            print(f"  {m!r}")


if __name__ == "__main__":
    main()
