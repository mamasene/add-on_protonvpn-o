"""Package addon/ into a .nvda-addon archive.

Shared by build_simple.ps1 and sconstruct so both entry points produce the same
package. Exclusion patterns come from buildVars.excludedFiles, which is the only
place they are declared.

Prints the output path to stdout.
"""

import fnmatch
import os
import sys
import zipfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import buildVars  # noqa: E402

ADDON_DIR = os.path.join(REPO_ROOT, 'addon')

# Files kept outside addon/ but shipped inside the package.
# The GPL v2 text must travel with the add-on it applies to.
EXTRA_FILES = ('COPYING',)


def is_excluded(relpath):
    """True if any path component matches an exclusion pattern."""
    parts = relpath.replace(os.sep, '/').split('/')
    return any(
        fnmatch.fnmatch(part, pattern)
        for pattern in buildVars.excludedFiles
        for part in parts
    )


def collect_files():
    """Return sorted (absolute_path, archive_name) pairs to package."""
    entries = []

    for dirpath, dirnames, filenames in os.walk(ADDON_DIR):
        # Prune excluded directories so we do not descend into __pycache__.
        dirnames[:] = [
            d for d in dirnames
            if not is_excluded(os.path.relpath(os.path.join(dirpath, d), ADDON_DIR))
        ]
        for filename in filenames:
            full = os.path.join(dirpath, filename)
            arcname = os.path.relpath(full, ADDON_DIR)
            if is_excluded(arcname):
                continue
            entries.append((full, arcname.replace(os.sep, '/')))

    for extra in EXTRA_FILES:
        full = os.path.join(REPO_ROOT, extra)
        if not os.path.isfile(full):
            raise SystemExit(f"Missing file required in the package: {extra}")
        entries.append((full, extra))

    # Sorted so repeated builds of the same sources produce the same archive.
    return sorted(entries, key=lambda pair: pair[1])


def build(output_path=None):
    info = buildVars.addon_info
    if output_path is None:
        output_path = os.path.join(
            REPO_ROOT,
            f"{info['addon_name']}-{info['addon_version']}.nvda-addon",
        )

    manifest = os.path.join(ADDON_DIR, 'manifest.ini')
    if not os.path.isfile(manifest):
        raise SystemExit(
            "addon/manifest.ini is missing. Run tools/generate_manifest.py first."
        )

    entries = collect_files()

    if os.path.exists(output_path):
        os.remove(output_path)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for full, arcname in entries:
            zf.write(full, arcname)

    print(f"Packaged {len(entries)} files", file=sys.stderr)
    return output_path


if __name__ == '__main__':
    print(build())
