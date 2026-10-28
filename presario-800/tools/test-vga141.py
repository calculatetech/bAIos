"""Build both VGA variants, boot real ROMs, and compare fixed-1-MiB registers."""
import argparse
import hashlib
import importlib
import json
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT / 'build/review/vga141'
floppy = importlib.import_module('floppy-matrix')
MODES = [0, 3, 0x503, 0x603, 0x12, 0x13, 0x101, 0x102, 0x103,
         0x104, 0x105, 0x106, 0x111, 0x112]
LABELS = ['POST text', 'Mode 03h', '80x50 text', '80x25 restored',
          '640x480x4', '320x200x8', '640x480x8', '800x600x4', '800x600x8',
          '1024x768x4', '1024x768x8', '1280x1024x4', '640x480x16', '640x480x24']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest().upper()


def ps(script, *args, reject=False):
    result = floppy.run_hidden([shutil.which('pwsh') or 'powershell', '-NoProfile',
                               '-File', str(ROOT / 'tools' / script), *args],
                              capture_output=True, text=True, errors='replace')
    log = WORK / ('commands.log')
    with log.open('a', encoding='utf-8') as output:
        output.write(f'COMMAND {script} {args}\n{result.stdout}{result.stderr}\nEXIT {result.returncode}\n')
    if reject:
        assert result.returncode != 0 and 'separate output directory' in result.stderr, result.stderr
    else:
        assert result.returncode == 0, result.stdout + result.stderr
    print(f'{script} {" ".join(args)}: {"REJECTED as required" if reject else "PASS"}', flush=True)


def integrity():
    retained = ROOT / 'reference/COMPAQ_PROLINEA_MT_05-02-94.BIN'
    new = ROOT / 'reference/gd5428_1-41.bin'
    bus07 = ROOT / 'reference/baios-presario800-vga141-bus07.bin'
    main = ROOT / 'build/baios-presario800.bin'
    system_main = ROOT / 'build/baios-presario800-system.rom'
    before = {str(p): digest(p) for p in (retained, new, bus07, main, system_main)}
    ps('build.ps1', '-Vga141')
    ps('verify-rom.ps1', '-Vga141', '-SelfTest')
    ps('build.ps1', '-Vga141', '-OutputDirectory', str(ROOT / 'build/../build'), reject=True)
    ps('build.ps1', '-Vga141', '-OutputDirectory', str(ROOT / 'build') + '/', reject=True)
    ps('build.ps1')
    ps('verify-rom.ps1', '-SelfTest')
    for variant, directory, name, entry in (
            (False, ROOT / 'build', 'baios-presario800.bin', 0x2897),
            (True, WORK, 'baios-presario800-vga141.bin', 0x2897)):
        image = (directory / name).read_bytes()
        system = (directory / 'baios-presario800-system.rom').read_bytes()
        assert len(image) == 131072 and len(system) == 65536 and sum(system) % 256 == 0
        assert image[65536:] == system and system[0xFFF0:0xFFF5] == bytes.fromhex('ea000000f0')
        assert image[:32768] == (new.read_bytes() if variant else bus07.read_bytes()[:32768])
        assert image[32768:65536] == retained.read_bytes()[32768:65536]
        assert system[0xF06A:0xF06F] == b'\xea' + struct.pack('<HH', entry, 0xC000)
        assert bytes.fromhex('26c7060801') + struct.pack('<H', entry + 1) in system
        jump = 0x28E9
        assert bytes.fromhex('813e0300') + struct.pack('<H', jump) in system
    assert before == {str(Path(p)): digest(Path(p)) for p in before}, 'Main image or supplied inputs changed'
    print('B1/S1: separate variant, root-output rejection, exact layout, checksum, reset, inputs and default reproducibility PASS', flush=True)


def snapshots(variant):
    directory = WORK if variant else ROOT / 'build'
    disk = directory / 'tests/86box/vm/boot-test-8g.img'
    result = []
    with disk.open('rb') as source:
        source.seek(31 * 512)
        info = source.read(512)
        assert info[:4] == b'VESA' and struct.unpack_from('<H', info, 18)[0] == 16
        for mode, label in zip(MODES, LABELS):
            raw = source.read(512)
            assert raw[:4] == b'VGAR' and struct.unpack_from('<H', raw, 4)[0] == mode, (label, raw[:8].hex())
            result.append(dict(label=label, mode=mode, vbe_version=struct.unpack_from('<H', raw, 6)[0],
                               misc=raw[8], dac=raw[9], bda=list(raw[10:16]),
                               seq=list(raw[16:48]), crtc=list(raw[48:88]),
                               gfx=list(raw[88:152]), attr=list(raw[152:173]),
                               int10=list(struct.unpack_from('<HH', raw, 174)),
                               int42=list(struct.unpack_from('<HH', raw, 178)), rom_header=raw[182:188].hex()))
    path = WORK / ('registers-141.json' if variant else 'registers-bus07.json')
    path.write_text(json.dumps(result, indent=2) + '\n')
    # Remove only the owned disposable 8 GiB disk after bounded records are saved.
    assert disk.resolve().parent == (directory / 'tests/86box/vm').resolve()
    disk.unlink()
    return result


def timing(state):
    sr, cr = state['seq'], state['crtc']
    clock = (state['misc'] >> 2) & 3
    numerator, denominator = sr[0x0B + clock] & 127, sr[0x1B + clock]
    divisor = ((denominator & 62) >> 1) * (2 if denominator & 1 else 1)
    vclk = 14.31818 * numerator / divisor if divisor else None
    # Report synthesizer output separately from packed-pixel and SR1 divide modes.
    mclk = 14.31818 * (sr[0x1F] & 63) / 8
    htotal = (cr[0] + 5) * (8 if sr[1] & 1 else 9)
    vtotal = cr[6] + ((cr[7] & 1) << 8) + ((cr[7] & 32) << 4) + 2
    return dict(vclk_mhz=round(vclk, 5) if vclk else None,
                mclk_mhz=round(mclk, 5), htotal=htotal, vtotal=vtotal,
                interlaced=bool(cr[0x1A] & 1), sr7_format=sr[7] & 6,
                clock_div2=bool(sr[1] & 8))


def comparison(old, new):
    rows = []
    for a, b in zip(old, new):
        assert a['mode'] == b['mode'] and a['label'] == b['label']
        changed = {}
        for group in ('seq', 'crtc', 'gfx', 'attr'):
            for index, (x, y) in enumerate(zip(a[group], b[group])):
                if x != y:
                    changed[f'{group}{index:02X}'] = f'{x:02X}->{y:02X}'
        for key in ('misc', 'dac'):
            if a[key] != b[key]:
                changed[key] = f'{a[key]:02X}->{b[key]:02X}'
        rows.append(dict(label=a['label'], changes=changed, bus07=timing(a), vga141=timing(b)))
    assert len(rows) == len(MODES)
    (WORK / 'register-comparison.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(rows, indent=2), flush=True)
    print('B6/S6: all 14 paired mode/register records and nominal timing calculations PASS', flush=True)


def emulator(transitions_only=False):
    saved = {str(p): digest(p) for p in (ROOT / 'build/baios-presario800.bin',
                                       ROOT / 'reference/gd5428_1-41.bin')}
    records = []
    chipset = importlib.import_module('test-chipset')
    for variant in (False, True):
        args = ['-Vga141'] if variant else []
        if not transitions_only:
            ps('run-86box.ps1', *args, '-VgaRegisterTest', '-KeepArtifacts', '-TimeoutSeconds', '60')
            records.append(snapshots(variant))
            print(f'B2/S2, B4/S4, B5/S5: {"1.41" if variant else "bus07 release"} actual init/INT42, VGA pixels/banks/retrace/IRQ, 1 MiB and upper-half VRAM PASS', flush=True)
        ps('run-86box.ps1', *args, '-SetupTest', '-TimeoutSeconds', '60')
        ps('run-86box.ps1', *args, '-KeyboardTest', '-TimeoutSeconds', '120')
        print(f'B3/S3: {"1.41" if variant else "bus07 release"} real Setup/summary 80x50->80x25, graphics->CtrlAltDel->warm visible text PASS', flush=True)
        chipset.emulator(only=['categories', 'post-summary'], vga141=variant)
    if not transitions_only:
        comparison(*records)
    assert saved == {p: digest(Path(p)) for p in saved}, 'Main image or input changed'
    print('Emulator selected variants and main image/input preservation PASS', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--integrity', action='store_true')
    parser.add_argument('--emulator', action='store_true')
    parser.add_argument('--transitions', action='store_true', help='Only native text/Setup/warm sequences and captures')
    args = parser.parse_args()
    WORK.mkdir(parents=True, exist_ok=True)
    if args.integrity or not (args.emulator or args.transitions):
        integrity()
    if args.emulator or args.transitions:
        emulator(transitions_only=args.transitions)


if __name__ == '__main__':
    main()
