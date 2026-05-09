"""
Compile all .po files in addon/locale/*/LC_MESSAGES/ to binary .mo files.
Uses only Python standard library — no external gettext tools required.

GNU .mo binary format reference:
  https://www.gnu.org/software/gettext/manual/html_node/MO-Files.html
"""

import struct
import os
import sys
import re


def parse_po(po_path):
    """Parse a .po file and return a dict of {msgid: msgstr}."""
    messages = {}
    current_msgid = None
    current_msgstr = None
    in_msgid = False
    in_msgstr = False

    def unescape(s):
        """Decode gettext escape sequences inside a quoted string value."""
        return s.replace('\\n', '\n').replace('\\t', '\t').replace('\\"', '"').replace('\\\\', '\\')

    with open(po_path, encoding='utf-8') as f:
        for line in f:
            line = line.rstrip('\n')

            if line.startswith('msgid "'):
                # Save previous pair
                if current_msgid is not None and current_msgstr is not None:
                    if current_msgid:  # skip the header (empty msgid)
                        messages[current_msgid] = current_msgstr
                current_msgid = unescape(line[7:-1])
                current_msgstr = None
                in_msgid = True
                in_msgstr = False

            elif line.startswith('msgstr "'):
                current_msgstr = unescape(line[8:-1])
                in_msgid = False
                in_msgstr = True

            elif line.startswith('"') and line.endswith('"'):
                val = unescape(line[1:-1])
                if in_msgid and current_msgid is not None:
                    current_msgid += val
                elif in_msgstr and current_msgstr is not None:
                    current_msgstr += val

            elif line == '' or line.startswith('#'):
                in_msgid = False
                in_msgstr = False

    # Save the last pair
    if current_msgid is not None and current_msgstr is not None and current_msgid:
        messages[current_msgid] = current_msgstr

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
        print(f"  [{lang}] {len(messages)} messages -> {mo_path}")
        compiled += 1

    if compiled == 0:
        print("No .po files found.")
    else:
        print(f"Done: {compiled} catalog(s) compiled.")


if __name__ == '__main__':
    # Called from repo root or from tools/
    script_dir = os.path.dirname(os.path.abspath(__file__))
    repo_root = os.path.dirname(script_dir)
    addon_dir = os.path.join(repo_root, 'addon')
    compile_all(addon_dir)
