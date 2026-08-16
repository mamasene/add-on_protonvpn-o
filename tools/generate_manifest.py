"""Generate addon/manifest.ini from manifest.ini.tpl and buildVars.py.

buildVars.py is the single source of truth for the add-on metadata. No other
file in the tree should hardcode the version: build scripts read it from here.

Writes the manifest, then prints the version to stdout so shell build scripts
can name the package. Progress messages go to stderr to keep stdout parseable.
"""

import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import buildVars  # noqa: E402

TEMPLATE = os.path.join(REPO_ROOT, 'manifest.ini.tpl')
OUTPUT = os.path.join(REPO_ROOT, 'addon', 'manifest.ini')

# NVDA validates manifest.ini against a fixed schema; keys outside it are not
# accepted. License information belongs in the Add-on Store submission and in
# the COPYING file shipped with the package, not here.
IGNORED_KEYS = ('addon_license', 'addon_licenseURL', 'addon_sourceURL')


def generate(template_path=TEMPLATE, output_path=OUTPUT):
    with open(template_path, encoding='utf-8') as f:
        template = f.read()

    fields = {k: v for k, v in buildVars.addon_info.items() if k not in IGNORED_KEYS}

    try:
        manifest = template.format(**fields)
    except KeyError as e:
        raise SystemExit(
            f"{template_path}: placeholder {e} has no matching key in "
            f"buildVars.addon_info"
        )

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(manifest)

    return manifest


if __name__ == '__main__':
    generate()
    print(f"Generated {OUTPUT}", file=sys.stderr)
    print(buildVars.addon_info['addon_version'])
