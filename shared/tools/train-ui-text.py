"""Update the fixed Setup pair grammar; normal builds do not invoke this tool."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re


def replace_pair(row, pair, token):
    result, at = [], 0
    while at < len(row):
        if tuple(row[at:at+2]) == pair:
            result.append(token)
            at += 2
        else:
            result.append(row[at])
            at += 1
    return result


def train(manifest):
    rows = [list(bytes.fromhex(row['hex'])) for port in manifest['ports'].values()
            for row in port['strings'].values() if row['compress']]
    pairs, depths = [], [0] * 128
    for token in range(128, 256):
        counts = Counter(pair for row in rows for pair in zip(row, row[1:])
                         if max(depths[pair[0]], depths[pair[1]]) < 32)
        pair = min(counts, key=lambda p: (-counts[p], p))
        pairs.append(pair)
        depths.append(1 + max(depths[pair[0]], depths[pair[1]]))
        rows = [replace_pair(row, pair, token) for row in rows]
    return pairs


def packed(plain, pairs):
    if plain[:1] == b'\x01':
        raise ValueError('Leading01 is reserved for compiled Setup text')
    literal = plain+b'\0'
    if any(value < 2 or value >= 128 for value in plain):
        return literal
    row = list(plain)
    for index, pair in enumerate(pairs):
        row = replace_pair(row, pair, 128+index)
    encoded = bytes([1]+row+[0])
    return encoded if len(encoded) < len(literal) else literal


def cache_entries(root, manifest):
    # The source declaration remains authoritative; this is derived metadata.
    pattern = re.compile(r'''(?m)^(\w+):\n[ \t]+ui_string[ \t]+('[^'\r\n]*'|"[^"\r\n]*")(?:[ \t]*,[ \t]*\w+)?[ \t]*$''')
    files = {name for port in manifest['ports'].values() for name in port.get('source_sha256', {})}
    entries = {}
    for name in sorted(files):
        for match in pattern.finditer((root/name).read_text(encoding='utf-8')):
            literal = match[2]
            entries.setdefault(match[1], {})[literal[1:-1].encode('utf-8')] = literal
    return entries


if __name__ == '__main__':
    root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, default=root/'shared/tests/fixtures/ui-text-p0.json')
    parser.add_argument('--output', type=Path, default=root/'shared/src/setup/ui-text-pairs.inc')
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text())
    pairs = train(manifest)
    lines = ['; Fixed Setup grammar. Regenerate only with shared/tools/train-ui-text.py.']
    for index, (a, b) in enumerate(pairs):
        lines += [f'%assign UI_PAIR_A{index} {a}', f'%assign UI_PAIR_B{index} {b}']
    lines.append('%define UI_TEXT_PAIRS ' + ','.join(str(v) for pair in pairs for v in pair))
    lines += ['', '; Derived compile-time cache. Exact full source text must match.']
    for label, variants in sorted(cache_entries(root,manifest).items()):
        lines.append(f'%macro UI_TEXT_CACHE_{label} 1.nolist')
        for index, (plain, literal) in enumerate(sorted(variants.items())):
            lines += [f'%{"ifidn" if index == 0 else "elifidn"} %1,{literal}',
                      '    %xdefine UI_STRING_BYTES '+','.join(str(value) for value in packed(plain,pairs))]
        lines += ['%else', '    ui_encode %1', '%endif', '%endmacro']
    args.output.write_text('\n'.join(lines)+'\n')
