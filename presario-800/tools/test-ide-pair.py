"""Test both primary IDE positions in86Box, with disposable images only."""
import importlib
import argparse
from contextlib import nullcontext
import os
import re
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

floppy = importlib.import_module('floppy-matrix')
ROOT, BUILD = floppy.ROOT, floppy.BUILD


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preview', action='store_true', help='Open the production ROM with an ATA master and ATAPI slave')
    parser.add_argument('--invalid-cmos', action='store_true', help='Preview CMOS recovery with disposable invalid settings and date')
    parser.add_argument('--setup-entry', action='store_true', help='Hold the preview at CMOS recovery for untimed Delete entry')
    args = parser.parse_args()
    preview = args.preview or args.invalid_cmos or args.setup_entry
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    exe = shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA']) /
        'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    roms = BUILD / 'tests/86box/roms'
    wrapper = roms / 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    production = (BUILD / 'baios-presario800.bin').read_bytes()
    (BUILD / 'tmp').mkdir(parents=True, exist_ok=True)
    if preview:
        work = BUILD / ('tests/86box/cmos-review' if args.invalid_cmos else 'tests/86box/ide-review')
        work.mkdir(exist_ok=True)
    try:
        with (nullcontext(work) if preview else tempfile.TemporaryDirectory(prefix='ide-pair-', dir=BUILD / 'tmp')) as name:
            work = Path(name)
            if not preview:
                system = work / 'test.rom'
                floppy.run_hidden([nasm, '-f', 'bin', '-DVGA_BIOS_141', '-DEMULATOR_POST_SUMMARY_TEST', '-I', str(ROOT / 'src') + '/',
                                   '-o', str(system), str(ROOT / 'src/bios.asm')], check=True)
                data = bytearray(system.read_bytes())
                assert len(data) == 65536
                data[-1] = -sum(data[:-1]) & 255
                wrapper.write_bytes(production[:65536] + data)
            pairs = (('ata', 'packet'),) if preview else (('ata', 'ata'), ('ata', 'packet'), ('packet', 'ata'), ('absent', 'ata'))
            for master, slave in pairs:
                vm = work / (master + '-' + slave)
                if preview and (vm / '86box.cfg').exists():
                    break  # Keep the user's interactive settings on subsequent previews.
                vm.mkdir()
                guest = vm / 'guest.bin'
                defines = [f'-DMASTER_ATA={int(master == "ata")}', f'-DMASTER_PACKET={int(master == "packet")}',
                           f'-DSLAVE_ATA={int(slave == "ata")}', f'-DSLAVE_PACKET={int(slave == "packet")}']
                if preview:
                    defines.append('-DINTERACTIVE_GUEST')
                floppy.run_hidden([nasm, '-f', 'bin', *defines, '-o', str(guest),
                                   str(ROOT / 'tests/ide-pair-test.asm')], check=True)
                images = [vm / 'master.img', vm / 'slave.img']
                for unit, image in enumerate(images):
                    with image.open('xb') as out:
                        out.write(guest.read_bytes())
                        out.write(struct.pack('<H', 0xA001 + unit) + bytes(510))
                        out.truncate((64 + unit * 32) * 1024 * 1024)
                floppy.config(vm, images[0], 4 if args.invalid_cmos else 0,
                              2 if args.invalid_cmos else 0, vm / 'a.img', vm / 'b.img')
                if args.invalid_cmos:
                    nvram = vm / 'nvr/d824.nvr'
                    cmos = bytearray(nvram.read_bytes())
                    cmos[0x38] = 0
                    cmos[8] = 0
                    nvram.write_bytes(cmos)
                cfg = (vm / '86box.cfg').read_text()
                cfg = cfg.replace('[Floppy and CD-ROM drives]',
                    ('hdd_02_parameters = 32, 6, 1024, 0, ide\n'
                     f'hdd_02_fn = {images[1].as_posix()}\nhdd_02_speed = ramdisk\nhdd_02_ide_channel = 0:1\n'
                     '[Floppy and CD-ROM drives]') if slave == 'ata' else '[Floppy and CD-ROM drives]')
                if master != 'ata':
                    cfg = re.sub(r'(?m)^hdd_01_.*\n', '', cfg)
                if 'packet' in (master, slave):
                    channel = '0:0' if master == 'packet' else '0:1'
                    cfg = cfg.replace('[Floppy and CD-ROM drives]',
                        '[Floppy and CD-ROM drives]\ncdrom_01_parameters = 1, atapi\n'
                        f'cdrom_01_ide_channel = {channel}\ncdrom_01_type = 86cd')
                (vm / '86box.cfg').write_text(cfg)
                if preview:
                    break
                result = floppy.run_hidden([exe, '-P', str(vm), '-R', str(roms), '-L', str(vm / '86box.log'), '-N'], timeout=60)
                assert result.returncode == 0x67, (master, slave, hex(result.returncode))
                print(f'86Box primary {master}/{slave}: detection, summary, legacy R/W, EDD capacity/read and reset PASS', flush=True)
            if args.setup_entry:
                nvram = vm / 'nvr/d824.nvr'
                previous = nvram.read_bytes()
                backup = vm / 'nvr/setup-entry-backup.nvr'
                if not backup.exists():
                    backup.write_bytes(previous)
                cmos = bytearray(previous)
                cmos[0x38] = 0  # Production recovery notice waits for Delete.
                nvram.write_bytes(cmos)
    finally:
        wrapper.write_bytes(production)
    assert wrapper.read_bytes() == production
    if preview:
        process = subprocess.Popen([exe, '-P', str(vm), '-R', str(roms), '-N'])
        print(f'Interactive production ROM: PID {process.pid}, profile {vm}', flush=True)


if __name__ == '__main__':
    main()
