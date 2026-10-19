"""Run a real ATAPI DOS driver and MSCDEX, then copy verified CD data to HDD."""
import argparse
from contextlib import nullcontext
import importlib
import lzma
import os
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import zipfile

floppy = importlib.import_module('floppy-matrix')
Fat16 = importlib.import_module('memory-fixture').Fat16


def driver_bytes(path):
    if path.suffix.lower() == '.zip':
        with zipfile.ZipFile(path) as archive:
            return archive.read('VIDE-CDD.SYS')
    if path.suffix.lower() != '.xz':
        return path.read_bytes()
    # Read the original Mitsumi installation disk without mounting or altering it.
    image = lzma.decompress(path.read_bytes())
    bps = struct.unpack_from('<H', image, 11)[0]
    spc, fats = image[13], image[16]
    reserved, entries, spf = (struct.unpack_from('<H', image, n)[0] for n in (14, 17, 22))
    root = (reserved + fats * spf) * bps
    data = root + ((entries * 32 + bps - 1) // bps) * bps
    entry = next(image[n:n + 32] for n in range(root, root + entries * 32, 32)
                 if image[n:n + 11] == b'MTMCDAI SYS')
    cluster, size = struct.unpack_from('<H', entry, 26)[0], struct.unpack_from('<I', entry, 28)[0]
    result, seen = bytearray(), set()
    while 2 <= cluster < 0xFF8:
        assert cluster not in seen, 'Invalid FAT12 chain'
        seen.add(cluster)
        offset = data + (cluster - 2) * spc * bps
        result.extend(image[offset:offset + spc * bps])
        packed = struct.unpack_from('<H', image, reserved * bps + cluster * 3 // 2)[0]
        cluster = packed >> 4 if cluster & 1 else packed & 0xFFF
    assert len(result) >= size
    return bytes(result[:size])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('driver', type=Path, help='VIDE ZIP, Mitsumi installation IMG.XZ, or SYS')
    parser.add_argument('--keep-artifacts', action='store_true')
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--no-emm', action='store_true')
    args = parser.parse_args()
    scratch = floppy.BUILD / 'tmp'
    scratch.mkdir(exist_ok=True)
    keep = args.keep_artifacts or args.preview
    directory = tempfile.mkdtemp(prefix='cdrom-dos-', dir=scratch) if keep else tempfile.TemporaryDirectory(prefix='cdrom-dos-', dir=scratch)
    with (nullcontext(directory) if keep else directory) as name:
        run(args, Path(name))


def run(args, vm):
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    exe = shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA']) /
        'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    guest = vm / 'guest.com'
    floppy.run_hidden([nasm, '-f', 'bin', '-o', str(guest), str(floppy.ROOT / 'tests/cdrom-dos-test.asm')], check=True)
    disk = vm / 'dos.vhd'
    shutil.copyfile(args.backup, disk)
    fat = Fat16(disk)
    try:
        fat.vhd.file.seek(-512, 2)
        footer = fat.vhd.file.read(512)
        geometry = (footer[59], footer[58], struct.unpack_from('>H', footer, 56)[0])
        config = ('SHELL=C:\\DOS\\COMMAND.COM /P /E:1536\r\nSTACKS=9,256\r\n'
                  'DEVICE=C:\\DOS\\HIMEM.SYS\r\n')
        if not args.no_emm:
            config += 'DEVICE=C:\\DOS\\EMM386.EXE NOEMS X=F000-F5FF\r\nDOS=HIGH,UMB\r\n'
        config += 'DEVICEHIGH=C:\\CDDRIVER.SYS /D:SHSU-CD\r\nFILES=40\r\nBUFFERS=20\r\nLASTDRIVE=Z\r\n'
        batch = ('@ECHO OFF\r\nLH C:\\WINDOWS\\MSCDEX.EXE /S /D:SHSU-CD /M:12 /L:D >C:\\MSCDEX.LOG\r\n'
                 'DIR D: >C:\\CDDIR.LOG\r\n')
        if not args.preview:
            batch += 'C:\\CDTEST.COM\r\n'
        with disk.open('r+b', buffering=0) as out:
            fat.replace(out, 'CONFIG.SYS', config.encode('ascii'))
            fat.replace(out, 'AUTOEXEC.BAT', batch.encode('ascii'))
            fat.replace(out, 'COMMAND.COM', driver_bytes(args.driver), b'CDDRIVERSYS')
            fat.replace(out, 'CONFIG.B~K', guest.read_bytes(), b'CDTEST  COM')
    finally:
        fat.vhd.close()
    media = vm / 'disc'
    media.mkdir()
    payload = bytes(range(256)) * 256
    (media / 'PROBE.BIN').write_bytes(payload)
    roms = floppy.config(vm, disk, 0, 0, vm / 'a.img', vm / 'b.img', geometry)
    cfg = vm / '86box.cfg'
    settings = cfg.read_text().replace('[Floppy and CD-ROM drives]',
        '[Floppy and CD-ROM drives]\ncdrom_01_parameters = 1, atapi\n'
        'cdrom_01_ide_channel = 0:1\ncdrom_01_type = 86cd\n'
        f'cdrom_01_image_path = {media.resolve().as_posix()}\n')
    cfg.write_text(settings)
    production = (floppy.BUILD / 'baios-presario800.bin').read_bytes()
    wrapper = roms / 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    assert wrapper.read_bytes() == production, 'Close other test/preview owners first'
    if args.preview:
        process = subprocess.Popen([exe, '-P', str(vm), '-R', str(roms), '-N'])
        print(f'Interactive production ROM: PID {process.pid}, profile {vm}', flush=True)
        return
    system = vm / 'test.rom'
    floppy.run_hidden([nasm, '-f', 'bin', '-DVGA_BIOS_141', '-DEMULATOR_POST_SUMMARY_TEST',
                       '-I', str(floppy.ROOT / 'src') + '/', '-o', str(system),
                       str(floppy.ROOT / 'src/bios.asm')], check=True)
    data = bytearray(system.read_bytes())
    assert len(data) == 65536
    data[-1] = -sum(data[:-1]) & 255
    wrapper.write_bytes(production[:65536] + data)
    print(f'START {args.driver.name}, EMM386={not args.no_emm}: {vm}', flush=True)
    try:
        result = floppy.run_hidden([exe, '-P', str(vm), '-R', str(roms), '-L', str(vm / '86box.log'), '-N'], timeout=60)
        fat = Fat16(disk)
        try:
            for log in ('MSCDEX.LOG', 'CDDIR.LOG'):
                try:
                    print(log + ': ' + fat.read(log).decode('cp437'), flush=True)
                except StopIteration:
                    print(log + ': not created', flush=True)
            assert result.returncode == 0x67, f'CD read check exited {result.returncode:#x}'
            assert fat.read('CDCOPY.BIN') == payload, 'CD/HDD copy differs'
        finally:
            fat.vhd.close()
    finally:
        wrapper.write_bytes(production)
        assert wrapper.read_bytes() == production
    print('PASS: DOS driver/MSCDEX, directory, 64KiB checked CD reads interleaved with HDD writes', flush=True)


if __name__ == '__main__':
    main()
