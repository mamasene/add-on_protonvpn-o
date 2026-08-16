"""Generate addon/locale/<lang>/manifest.ini for every translated locale.

The Add-on Store reads the summary, description and changelog from these files
when NVDA runs in that language; without them the store falls back to English.

The English strings come from buildVars.py and the translations from each
locale's compiled catalog, so the two can never drift apart silently: a msgid
that does not match buildVars.py word for word is reported as untranslated.

Run tools/compile_po.py first: this reads the .mo catalogs, not the .po sources.
"""

import gettext
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import buildVars  # noqa: E402

TEMPLATE = os.path.join(REPO_ROOT, 'manifest-translated.ini.tpl')
LOCALE_DIR = os.path.join(REPO_ROOT, 'addon', 'locale')

# Fields the translated manifest carries. NVDA accepts no others here.
TRANSLATED_FIELDS = ('addon_summary', 'addon_description', 'addon_changelog')


def generate_for_locale(lang, template):
    mo_path = os.path.join(LOCALE_DIR, lang, 'LC_MESSAGES', 'nvda.mo')
    if not os.path.isfile(mo_path):
        return None

    with open(mo_path, 'rb') as f:
        catalog = gettext.GNUTranslations(f)

    fields = {}
    untranslated = []
    for key in TRANSLATED_FIELDS:
        source = buildVars.addon_info[key]
        translated = catalog.gettext(source)
        if translated == source:
            untranslated.append(key)
        fields[key] = translated

    if untranslated:
        print(
            f"  [{lang}] WARNING: no translation found for "
            f"{', '.join(untranslated)} -- English will be shown in the store. "
            f"Check that the msgid in nvda.po matches buildVars.py exactly.",
            file=sys.stderr,
        )

    output_path = os.path.join(LOCALE_DIR, lang, 'manifest.ini')
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(template.format(**fields))

    return output_path, len(TRANSLATED_FIELDS) - len(untranslated)


def generate_all():
    if not os.path.isdir(LOCALE_DIR):
        print("No locale directory found.", file=sys.stderr)
        return

    with open(TEMPLATE, encoding='utf-8') as f:
        template = f.read()

    generated = 0
    for lang in sorted(os.listdir(LOCALE_DIR)):
        if not os.path.isdir(os.path.join(LOCALE_DIR, lang)):
            continue
        result = generate_for_locale(lang, template)
        if result is None:
            continue
        output_path, translated_count = result
        print(
            f"  [{lang}] {translated_count}/{len(TRANSLATED_FIELDS)} fields "
            f"-> {output_path}",
            file=sys.stderr,
        )
        generated += 1

    if generated == 0:
        print("No compiled catalogs found.", file=sys.stderr)
    else:
        print(f"Done: {generated} translated manifest(s).", file=sys.stderr)


if __name__ == '__main__':
    generate_all()
