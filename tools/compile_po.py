"""
Compile all .po files in addon/locale/*/LC_MESSAGES/ to binary .mo files.
Uses only Python standard library — no external gettext tools required.

Singular and plural entries are both supported. In a .mo file a plural entry is
stored as a single pair whose key is "msgid\\0msgid_plural" and whose value is
the translated forms joined by the same NUL; gettext splits them back out and
picks one using the Plural-Forms expression of the header. Without this, a
msgid_plural entry would be silently dropped and the string would come out
untranslated.

GNU .mo binary format reference:
  https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html
"""

import gettext
import re
import struct
import os


# Minimal header used when a .po file carries no metadata entry of its own.
# Without it, gettext falls back to ASCII and fails to decode accented translations.
DEFAULT_HEADER = "Content-Type: text/plain; charset=UTF-8\nContent-Transfer-Encoding: 8bit\n"

ESCAPES = {'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\'}

# Séparateur imposé par le format .mo entre singulier et pluriel.
PLURAL_SEPARATOR = '\x00'

MSGSTR_INDEXED_RE = re.compile(r'^msgstr\[(\d+)\]\s+"(.*)"$')


def unescape(s):
    """Decode gettext escape sequences inside a quoted string value.

    Scanned left to right rather than by chained replaces: replacing "\\n"
    before "\\\\" would turn a literal backslash followed by n into a newline.
    """
    out = []
    i = 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            out.append(ESCAPES.get(s[i + 1], '\\' + s[i + 1]))
            i += 2
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


class _Entry:
    """Une entrée du catalogue, singulier ou pluriel."""

    def __init__(self, msgid):
        self.msgid = msgid
        self.msgid_plural = None
        self.forms = {}

    def key(self):
        if self.msgid_plural is None:
            return self.msgid
        return self.msgid + PLURAL_SEPARATOR + self.msgid_plural

    def value(self):
        if self.msgid_plural is None:
            return self.forms.get(0, '')
        ordered = [self.forms[index] for index in sorted(self.forms)]
        return PLURAL_SEPARATOR.join(ordered)

    def is_complete(self):
        if not self.forms:
            return False
        if self.msgid_plural is None:
            return 0 in self.forms
        # Une forme manquante produirait une traduction vide pour ce cas précis.
        return sorted(self.forms) == list(range(len(self.forms)))


def parse_po(po_path):
    """Parse a .po file and return {key: value} ready for the .mo writer.

    For a plural entry the key and the value carry every form, joined by NUL.
    The metadata entry (empty msgid) is kept: gettext reads the charset from it.
    """
    messages = {}
    entry = None
    target = None  # ('msgid' | 'msgid_plural' | index) de la chaîne en cours

    def flush():
        if entry is not None and entry.is_complete():
            messages[entry.key()] = entry.value()

    with open(po_path, encoding='utf-8') as f:
        for raw_line in f:
            line = raw_line.rstrip('\n').rstrip()

            if line.startswith('msgid "'):
                flush()
                entry = _Entry(unescape(line[7:-1]))
                target = 'msgid'

            elif line.startswith('msgid_plural "') and entry is not None:
                entry.msgid_plural = unescape(line[14:-1])
                target = 'msgid_plural'

            elif line.startswith('msgstr "') and entry is not None:
                entry.forms[0] = unescape(line[8:-1])
                target = 0

            elif line.startswith('msgstr[') and entry is not None:
                match = MSGSTR_INDEXED_RE.match(line)
                if match:
                    index = int(match.group(1))
                    entry.forms[index] = unescape(match.group(2))
                    target = index

            elif line.startswith('"') and line.endswith('"') and entry is not None:
                value = unescape(line[1:-1])
                if target == 'msgid':
                    entry.msgid += value
                elif target == 'msgid_plural':
                    entry.msgid_plural = (entry.msgid_plural or '') + value
                elif isinstance(target, int):
                    entry.forms[target] = entry.forms.get(target, '') + value

            elif line == '' or line.startswith('#'):
                target = None

    flush()

    if not messages.get(''):
        messages[''] = DEFAULT_HEADER

    return messages


def write_mo(messages, mo_path):
    """Write a GNU .mo binary file from a dict of {msgid: msgstr}."""
    keys = sorted(messages.keys())
    N = len(keys)

    # Offsets layout:
    # [0..27]   : header (7 x 4-byte ints)
    # [28..28+N*8-1]       : original strings table  (N x length+offset pairs)
    # [28+N*8..28+N*16-1]  : translated strings table
    # [28+N*16..]          : string data (NUL-terminated UTF-8)

    HEADER = 28
    orig_table_offset = HEADER
    trans_table_offset = HEADER + N * 8
    strings_start = HEADER + N * 16

    orig_offsets = []
    trans_offsets = []
    strings_blob = b''
    pos = strings_start

    for key in keys:
        enc = key.encode('utf-8')
        orig_offsets.append((len(enc), pos))
        strings_blob += enc + b'\x00'
        pos += len(enc) + 1

    for key in keys:
        enc = messages[key].encode('utf-8')
        trans_offsets.append((len(enc), pos))
        strings_blob += enc + b'\x00'
        pos += len(enc) + 1

    # Pack header
    mo = struct.pack('<IIIIIII',
        0x950412de,        # magic (little-endian)
        0,                 # file format revision
        N,                 # number of strings
        orig_table_offset, # offset of original strings table
        trans_table_offset,# offset of translated strings table
        0,                 # hash table size (unused)
        0,                 # hash table offset (unused)
    )

    for length, offset in orig_offsets:
        mo += struct.pack('<II', length, offset)
    for length, offset in trans_offsets:
        mo += struct.pack('<II', length, offset)
    mo += strings_blob

    os.makedirs(os.path.dirname(mo_path), exist_ok=True)
    with open(mo_path, 'wb') as f:
        f.write(mo)


def verify_mo(mo_path, messages):
    """Load the generated .mo through gettext to prove NVDA will be able to read it.

    A catalog without a metadata entry loads as ASCII and blows up on the first
    accented translation, so this check must run on every build. Plural entries
    are replayed through ngettext with the catalog's own Plural-Forms rule: a
    form stored at the wrong index would otherwise only show up to a user.
    """
    with open(mo_path, 'rb') as f:
        catalog = gettext.GNUTranslations(f)

    # Règle de pluriel déclarée par le catalogue lui-même : la vérification ne
    # suppose donc rien de la langue compilée.
    plural_rule = getattr(catalog, 'plural', None)

    for key, expected in messages.items():
        if not key:
            continue

        if PLURAL_SEPARATOR not in key:
            actual = catalog.gettext(key)
            if actual != expected:
                raise ValueError(
                    f"{mo_path}: round-trip mismatch for {key!r}: "
                    f"got {actual!r}, expected {expected!r}"
                )
            continue

        singular, plural = key.split(PLURAL_SEPARATOR, 1)
        forms = expected.split(PLURAL_SEPARATOR)

        for count in (0, 1, 2, 5, 21):
            actual = catalog.ngettext(singular, plural, count)
            if plural_rule is not None:
                index = min(plural_rule(count), len(forms) - 1)
                if actual != forms[index]:
                    raise ValueError(
                        f"{mo_path}: plural mismatch for {singular!r} at n={count}: "
                        f"got {actual!r}, expected {forms[index]!r}"
                    )
            elif actual not in forms:
                raise ValueError(
                    f"{mo_path}: plural form missing for {singular!r} at n={count}: "
                    f"got {actual!r}"
                )


def compile_all(addon_dir):
    locale_dir = os.path.join(addon_dir, 'locale')
    if not os.path.isdir(locale_dir):
        print(f"No locale directory found at {locale_dir}")
        return

    compiled = 0
    for lang in os.listdir(locale_dir):
        lc_dir = os.path.join(locale_dir, lang, 'LC_MESSAGES')
        po_path = os.path.join(lc_dir, 'nvda.po')
        mo_path = os.path.join(lc_dir, 'nvda.mo')

        if not os.path.isfile(po_path):
            continue

        messages = parse_po(po_path)
        write_mo(messages, mo_path)
        verify_mo(mo_path, messages)
        # The metadata entry is not a translatable string, do not count it.
        print(f"  [{lang}] {len(messages) - 1} messages -> {mo_path}")
        compiled += 1

    if compiled == 0:
        print("No .po files found.")
    else:
        print(f"Done: {compiled} catalog(s) compiled and verified.")


if __name__ == '__main__':
    # Called from repo root or from tools/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    addon_dir = os.path.join(repo_root, 'addon')
    compile_all(addon_dir)
