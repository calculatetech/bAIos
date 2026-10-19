"""Check coexisting VGA outputs and the real build purge with independent file oracles."""
import argparse
import ast
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / 'build'
WRAPPER = 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
FLASH = ('baios-presario800-system.rom', 'baios-presario800-vga50.bin',
         'baios-presario800-vga60.bin', 'baios-presario800.bin')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ps(script, *args, reject=None):
    result = subprocess.run([shutil.which('pwsh') or 'powershell', '-NoProfile', '-File',
                             str(ROOT / 'tools' / script), *map(str, args)],
                            capture_output=True, text=True, errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW)
    output = result.stdout + result.stderr
    if reject:
        assert result.returncode != 0 and reject in output, output
    else:
        assert result.returncode == 0, output
    return output


def retained_roms():
    return {str(folder / name): digest(folder / name)
            for folder in (BUILD,) for name in FLASH}


def build():
    before = retained_roms()
    scratch = BUILD / 'tmp'
    scratch.mkdir(exist_ok=True)
    for order in ((50, 60), (60, 50)):
        with tempfile.TemporaryDirectory(prefix='build-paths-', dir=scratch) as work:
            out = Path(work).resolve()
            assert out.is_relative_to(BUILD.resolve())
            previous = None
            for index, clock in enumerate(order):
                ps('build.ps1', '-OutputDirectory', out, '-VgaClockMHz', clock)
                physical = out / f'baios-presario800-vga{clock}.bin'
                assert len(physical.read_bytes()) == 131072
                ps('verify-rom.ps1', '-BuildDirectory', out, '-VgaClockMHz', clock, '-SelfTest')
                if index == 0:
                    assert not (out / f'baios-presario800-vga{order[1]}.bin').exists()
                    previous = digest(physical)
                else:
                    assert digest(out / f'baios-presario800-vga{order[0]}.bin') == previous
            images = {clock: (out / f'baios-presario800-vga{clock}.bin').read_bytes() for clock in order}
            system = (out / FLASH[0]).read_bytes()
            assert len(system) == 65536 and sum(system) & 255 == 0
            assert system[0xFFF0:0xFFF5] == bytes.fromhex('ea000000f0')
            assert images[50][65536:] == images[60][65536:] == system
            differences = [i for i in range(131072) if images[50][i] != images[60][i]]
            assert differences == [0x08E7, 32767], differences
            generic = out / '86box/roms' / WRAPPER
            assert (out / FLASH[3]).read_bytes() == generic.read_bytes() == images[order[-1]]
            for clock in order:
                assert (out / f'86box/vga{clock}/roms' / WRAPPER).read_bytes() == images[clock]
                ps('verify-rom.ps1', '-BuildDirectory', out, '-VgaClockMHz', clock, '-SelfTest')
            print(f'PASS sole first build and coexistence {order}: both verifiers, retained sibling, common system, latest alias/wrapper', flush=True)
            # Synthetic local contrasts: only the named artifact is substituted.
            if order[-1] == 60:  # S4 keeps the valid 60 MHz shared alias constant.
                selected = out / FLASH[1]
                try:
                    selected.write_bytes(images[60])
                    ps('verify-rom.ps1', '-BuildDirectory', out, '-VgaClockMHz', 50,
                       reject='Retained region differs')
                finally:
                    selected.write_bytes(images[50])
            try:
                generic.write_bytes(images[order[0]])
                ps('verify-rom.ps1', '-BuildDirectory', out, '-VgaClockMHz', order[-1],
                   reject='generic 86Box wrapper differs')
            finally:
                generic.write_bytes(images[order[-1]])
            print('PASS selected-clock substitution and generic-wrapper/alias mismatch rejected', flush=True)
    assert before == retained_roms(), 'Proof build changed an approved image'


def inventory():
    # Include empty directories; hash small files and record large-media metadata.
    return {str(p.relative_to(BUILD)): (p.stat().st_size, p.stat().st_mtime_ns,
                                       digest(p) if p.stat().st_size < 4 * 1024 * 1024 else None)
            if p.is_file() else ('directory',) for p in BUILD.rglob('*')}


def cleanup():
    # Independent obsolete inputs, including duplicate prefixes and a later archive.
    obsolete = [BUILD / name for name in ('post-ui', 'post-ui-50', 'setup25', 'setup25-50',
                'modular', 'modular-50', 'apm-50', 'ram-presets', 'vga141',
                'baios-presario800-cache-detection.bin', 'baios-presario800-chipset.bin',
                'baios-presario800-chipset-final.bin', 'archive', 'research',
                'm919-shared-check', 'shared-tools-junction', 'shared-tools-junction-output',
                'shared-tools-native', 'emulator-test-system.rom')]
    scratch = BUILD / 'tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    obsolete += list(scratch.iterdir())
    provider = ROOT.parent / 'reference/software/speedsys/4.78/SPEEDSYS-code.bin'
    assert digest(provider) == 'b43f9ed7f8efa0f11561b3213b82c9727571fafd2fec1695b8cbfd0fe816eee0'
    obsolete += [BUILD / '86box' / name for name in ('card-vm', 'cmos-review', 'diagnostic',
                'ide-review', 'oem-probe', 'setup-review', 'unit-smoke', 'vector-dump', 'vm',
                'official-d824.bin', 'unit-smoke.png')]
    obsolete += [BUILD / 'apm', BUILD / 'cdboot', BUILD / 'mouse']
    existing = [p for p in obsolete if p.exists()]
    if not existing:
        # Synthetic local generated outputs, not archives of any real artifact.
        obsolete.append(BUILD / 'tmp/generated-purge-proof')
        for path in obsolete:
            assert path.resolve().is_relative_to(BUILD.resolve())
            if path.suffix:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b'Synthetic obsolete output')
            else:
                path.mkdir(parents=True)
                (path / 'purge-proof.txt').write_text('Synthetic obsolete output\n')
    else:
        obsolete = existing
    review_roots = [BUILD / name for name in ('chipset-review', 'chipset-review/vga50', 'cd-review', 'review/cd-review')]
    review_controls, created_reviews = [], []
    pending = BUILD / 'review'
    if not pending.exists():
        pending.mkdir()
        created_reviews.append(pending)
    control = tempfile.TemporaryDirectory(prefix='build-paths-pending-', dir=pending)
    assert Path(control.name).resolve().is_relative_to(BUILD.resolve())
    for name in FLASH:
        (Path(control.name) / name).write_bytes(b'Synthetic pending image: ' + name.encode())
    review_controls.append(control)
    for review in review_roots:
        if not review.exists():
            review.mkdir()
            created_reviews.append(review)
        if review.name == 'cd-review':
            marker = review / 'preview.pid'
            if not marker.exists():
                marker.write_text('0\n')
            obsolete.append(marker)
        vm = Path(tempfile.mkdtemp(prefix='build-paths-vm-', dir=review))
        assert vm.resolve().is_relative_to(BUILD.resolve())
        (vm / '86box.cfg').write_text('Synthetic completed VM\n')
        (vm / 'disposable.img').write_bytes(b'Synthetic disposable media')
        control = tempfile.TemporaryDirectory(prefix='build-paths-review-', dir=review)
        assert Path(control.name).resolve().is_relative_to(BUILD.resolve())
        (Path(control.name) / 'review.txt').write_text('Synthetic current review evidence\n')
        review_controls.append(control)
    # Include native captures already present, as well as the newly seeded VMs.
    obsolete += [vm for review in review_roots for vm in review.iterdir()
                 if vm.is_dir() and (vm / '86box.cfg').is_file()]
    # Real screenshot producers must save current evidence outside old archives.
    for source, expected, screenshot in (('test-setup.py', 'chipset-review/setup', 'setup-standard.png'),
                                         ('test-ports.py', 'chipset-review/serial-addresses', 'devices.png')):
        producer = ast.parse((ROOT / 'tools' / source).read_text())
        producer_body = next(n for n in producer.body if isinstance(n, ast.FunctionDef) and n.name == 'run_86box')
        evidence_paths = [n.value.right.value for n in ast.walk(producer_body)
                          if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'evidence' for t in n.targets)
                          and isinstance(n.value, ast.BinOp) and isinstance(n.value.right, ast.Constant)]
        assert evidence_paths == [expected]
        evidence_review = BUILD / expected
        if not evidence_review.exists():
            evidence_review.mkdir()
            created_reviews.append(evidence_review)
        control = tempfile.TemporaryDirectory(prefix='evidence-', dir=evidence_review)
        assert Path(control.name).resolve().is_relative_to(BUILD.resolve())
        for name in (screenshot, 'screen.log', 'screen.nvr'):
            (Path(control.name) / name).write_bytes(b'Synthetic current review evidence')
        review_controls.append(control)
    card_capture = BUILD / 'card-boot.png'
    created_card_capture = not card_capture.exists()
    if created_card_capture:
        card_capture.write_bytes(b'Synthetic current card screenshot')
    before = inventory()
    record = ROOT.parent / '.agent/test-results'
    record.mkdir(parents=True, exist_ok=True)
    (record / 'build-paths-cleanup-before.json').write_text(json.dumps(before, sort_keys=True))
    outside = {str(p): digest(p) for folder in (ROOT / 'src', ROOT / 'reference', ROOT / 'docs')
               for p in folder.rglob('*') if p.is_file()}
    card_hash = digest(BUILD / 'presario800-card.vhd')
    roms = retained_roms()
    retained = {name: state for name, state in before.items()
                if not any((BUILD / name).is_relative_to(p) for p in obsolete)}
    output = ps('clean-build.ps1', '-WhatIf')
    assert before == inventory(), 'WhatIf changed build contents'
    assert not obsolete or 'Purge obsolete generated output' in output
    print('PASS WhatIf leaves the complete file inventory unchanged', flush=True)
    ps('clean-build.ps1')
    assert all(not p.exists() for p in obsolete), [str(p) for p in obsolete if p.exists()]
    assert scratch.is_dir() and not list(scratch.iterdir()), 'Cleanup must retain an empty scratch parent'
    after = inventory()
    (record / 'build-paths-cleanup-after.json').write_text(json.dumps(after, sort_keys=True))
    assert retained == after, ('Unexpected retention/deletion', set(retained) ^ set(after))
    assert roms == retained_roms() and card_hash == digest(BUILD / 'presario800-card.vhd')
    assert outside == {p: digest(Path(p)) for p in outside}
    print('PASS pending review pair and shared system survive cleanup unchanged', flush=True)
    assert not (BUILD / 'archive').exists()
    for folder in (BUILD,):
        for clock in (50, 60):
            ps('verify-rom.ps1', '-BuildDirectory', folder, '-VgaClockMHz', clock, '-SelfTest')
    subprocess.run([sys.executable, '-B', str(ROOT / 'tools/test-speedsys-rom-id.py')],
                   check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    print('PASS exact retained SpeedSys fixture and original BIOS-ID scanner after cleanup', flush=True)
    print(f'PASS full obsolete set purged ({len(obsolete)} targets), approved/dependencies/card/source/evidence preserved, two selected ROM checks', flush=True)
    ps('clean-build.ps1')
    assert after == inventory(), 'Repeated cleanup changed the retained tree'
    assert not (BUILD / 'archive').exists()
    print('PASS empty obsolete set on repeated cleanup: no new history or file changes', flush=True)
    for control in review_controls:
        control.cleanup()  # Owned synthetic retained controls, after terminal oracles.
    for review in reversed(created_reviews):
        review.rmdir()
    if created_card_capture:
        card_capture.unlink()  # Remove only the owned synthetic screenshot.


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', action='store_true')
    parser.add_argument('--cleanup', action='store_true')
    args = parser.parse_args()
    if args.build or not args.cleanup:
        build()
    if args.cleanup:
        cleanup()
