"""Build the MP386 system ROM and both programmer lanes."""
import argparse
import json
from pathlib import Path
import sys

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.rom import build, verify


def validate(image):
    image = Path(image)
    result = verify(PORT, image)
    raw = image.read_bytes()
    lanes = [image.with_name('baios-mp386-' + name + '.bin')
             for name in ('even', 'odd')]
    parts = [path.read_bytes() for path in lanes]
    if any(len(part) != 32768 for part in parts):
        raise ValueError('Each MP386 programmer lane must contain 32768 bytes')
    merged = bytearray(65536)
    merged[::2], merged[1::2] = parts
    if merged != raw:
        raise ValueError('MP386 even/odd lanes do not reproduce the physical image')
    result['programmer_checksum_sum32'] = f'{sum(raw):08X}'
    result['lanes'] = [dict(path=str(path), size=len(part),
                           programmer_checksum_sum32=f'{sum(part):08X}')
                       for path, part in zip(lanes, parts)]
    return result


def run(output='build', defines=()):
    result = build(PORT, output, defines)
    image = Path(result['path'])
    raw = image.read_bytes()
    for offset, name in enumerate(('even', 'odd')):
        image.with_name('baios-mp386-' + name + '.bin').write_bytes(raw[offset::2])
    result.update(validate(image))
    image.with_name('rom-checksums.json').write_text(json.dumps(result, indent=2)+'\n')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', default='build')
    args = parser.parse_args()
    result = run(args.output)
    result.pop('sha256', None)
    print(json.dumps(result, indent=2))
