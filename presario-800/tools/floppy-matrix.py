"""Exercise the production BIOS with disposable blank 86F disks, one VM at a time."""
import argparse
from contextlib import nullcontext
import hashlib
import importlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / os.environ.get("BAIOS_BUILD_DIRECTORY", "build")
sys.path.insert(0, str(ROOT.parent))
from shared.tools.floppy import TYPES, GEOMETRY, blank_86f


def run_hidden(args, **kwargs):
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = 0
    return subprocess.run(args, startupinfo=startup, **kwargs)


def config(vm, disk, a, b, fa, fb, geometry=(32, 4, 1024), turbo=False, protected=False, boot=2, seek=True):
    s, h, c = geometry
    roms = BUILD / "tests/86box/roms"
    nvr = vm / "nvr"
    nvr.mkdir()
    cmos = bytearray(256)
    cmos[0x0A] = 0x26
    cmos[0x0B] = 2
    cmos[0x0D] = 0x80
    cmos[4] = 0x12
    cmos[6:10] = bytes((5, 1, 1, 0x26))  # Thursday, 2026-01-01; no POST clock warning.
    cmos[0x32] = 0x20
    cmos[0x10] = (a << 4) | b
    cmos[0x38:0x3F] = bytes((66, 56, 1, 1, boot, -(66 + 56 + 1 + 1 + boot + cmos[0x10]) & 255,
                             0x5A if seek else 0xA5))
    (nvr / "d824.nvr").write_bytes(cmos)
    (vm / "86box.cfg").write_text(f"""[General]
vid_renderer = qt_software
[Machine]
machine = d824
cpu_family = i486dx
cpu_speed = 25000000
cpu_multi = 1
fpu_type = internal
cpu_use_dynarec = 0
fpu_softfloat = 0
time_sync = disabled
mem_size = 4096
[Video]
gfxcard = internal
[Input devices]
mouse_type = none
[Sound]
sndcard = none
[Network]
net_01_card = none
[Storage controllers]
hdc_1 = ide_isa
[Hard disks]
hdd_01_parameters = {s}, {h}, {c}, 0, ide
hdd_01_fn = {disk.as_posix()}
hdd_01_speed = ramdisk
hdd_01_ide_channel = 0:0
[Floppy and CD-ROM drives]
fdd_01_type = {TYPES[a]}
fdd_01_fn = {fa.as_posix()}
fdd_01_writeprot = {int(protected)}
fdd_01_turbo = {int(turbo)}
fdd_02_type = {TYPES[b]}
fdd_02_fn = {fb.as_posix()}
fdd_02_writeprot = {int(protected)}
fdd_02_turbo = {int(turbo)}
[Other peripherals]
postcard_enabled = 1
unittester_enabled = 1
[86Box Unit Tester]
exit_enabled = 1
""", encoding="utf-8")
    return roms


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", action="append", help="A-type:B-type:A-media:B-media (1..5; 0 absent with --dos-backup)")
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("--raw", action="store_true", help="Use raw-sector fixtures for emulator comparison")
    parser.add_argument("--read-only", action="store_true", help="Read preformatted F6-filled sector images without formatting or writing")
    parser.add_argument("--turbo", action="store_true", help="Accelerate emulated drives; default tests normal timing")
    parser.add_argument("--diagnostic-log", action="store_true", help="Require a successful diagnostic ROM POST report")
    parser.add_argument("--write-protected", action="store_true", help="Require format rejection without changing either image")
    parser.add_argument("--dos-backup", type=Path, help="Copy this DOS VHD and exercise its FORMAT.COM")
    parser.add_argument("--memory-managers", action="store_true", help="Load HIMEM/EMM386 in the disposable DOS fixture")
    parser.add_argument("--trace", action="store_true", help="Record the last failed floppy INT13 call in a DOS fixture")
    parser.add_argument("--keep-artifacts", action="store_true", help="Retain disposable VMs for diagnosis")
    parser.add_argument('--swap', action='store_true', help='Report whether native Swap On validation is available')
    args = parser.parse_args()
    if args.swap:
        parser.error('Native Swap On validation is unavailable on the installed d824 FDC37C651 model (no CR3). Physical FDC37C661 transfer validation is pending.')
    if args.read_only:
        if args.dos_backup or args.write_protected:
            parser.error("--read-only requires the BIOS guest without --write-protected")
        args.raw = True
    if args.diagnostic_log and args.dos_backup:
        parser.error("--diagnostic-log requires the raw BIOS guest")
    if args.memory_managers and not args.dos_backup:
        parser.error("--memory-managers requires --dos-backup")
    if args.write_protected and args.dos_backup:
        parser.error("--write-protected requires the raw BIOS guest")
    if args.trace and not args.dos_backup:
        parser.error("--trace requires --dos-backup")
    cases = args.case or ["1:3:1:3", "3:1:3:1", "2:4:2:4", "4:2:4:2",
                          "5:5:5:5", "2:4:1:3", "4:2:3:1"]
    nasm = shutil.which("nasm") or str(Path(os.environ["LOCALAPPDATA"]) / "bin/NASM/nasm.exe")
    exe = shutil.which("86Box.exe") or str(Path(os.environ["LOCALAPPDATA"]) /
        "Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe")
    wrapper = BUILD / 'tests/86box/roms/machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    production = wrapper.read_bytes()
    (BUILD / 'tmp').mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='floppy-rom-', dir=BUILD / 'tmp') as name:
            system = Path(name) / 'test.rom'
            defines = ['-DVGA_BIOS_141', '-DEMULATOR_POST_SUMMARY_TEST']
            if args.diagnostic_log:
                defines.append('-DFLOPPY_DIAGNOSTIC')
            run_hidden([nasm, '-f', 'bin', *defines, '-I', str(ROOT / 'src') + '/',
                        '-o', str(system), str(ROOT / 'src/bios.asm')], check=True)
            data = bytearray(system.read_bytes())
            assert len(data) == 65536
            data[-1] = -sum(data[:-1]) & 255
            wrapper.write_bytes(production[:65536] + data)
            for case in cases:
                run_case(args, case, nasm, exe)
    finally:
        wrapper.write_bytes(production)


def run_case(args, case, nasm, exe):
    a, b, ma, mb = map(int, case.split(":"))
    if any(t not in TYPES for t in (a, b)) or any(t not in GEOMETRY for t in (ma, mb) if t):
        raise ValueError("Drive and media codes must be 0..5")
    if not all((drive == 0) == (medium == 0) for drive, medium in ((a, ma), (b, mb))):
        raise ValueError("Absent drives must have media code 0")
    if (not a or not b) and not args.dos_backup:
        raise ValueError("Absent-drive cases require the real DOS guest")
    scratch = (BUILD / "tmp").resolve()
    if scratch.parent != BUILD.resolve():
        raise ValueError("Temporary VMs must stay inside the system build directory")
    scratch.mkdir(exist_ok=True)
    factory = tempfile.mkdtemp if args.keep_artifacts else tempfile.TemporaryDirectory
    directory = factory(prefix=f"floppy-{a}{b}-{ma}{mb}-", dir=scratch)
    with (nullcontext(directory) if args.keep_artifacts else directory) as name:
        vm = Path(name)
        guest = vm / ("guest.com" if args.dos_backup else "guest.bin")
        defines = ["-DWRITE_PROTECTED"] if args.write_protected else []
        if args.read_only:
            defines.append("-DREAD_ONLY")
        if args.memory_managers:
            defines.append("-DMEMORY_MANAGERS")
        if args.trace:
            defines.append("-DTRACE_FLOPPY")
        run_hidden([nasm, *defines, "-f", "bin", f"-DTYPE_A={a}", f"-DTYPE_B={b}",
                    f"-DMEDIA_A={ma}", f"-DMEDIA_B={mb}", "-o", str(guest),
                    str(ROOT / "tests" / ("floppy-dos-test.asm" if args.dos_backup else "floppy-test.asm"))], check=True)
        geometry = (32, 4, 1024)
        if args.dos_backup:
            disk = vm / "dos.vhd"
            shutil.copyfile(args.dos_backup, disk)
            fat = importlib.import_module("memory-fixture").Fat16(disk)
            try:
                fat.vhd.file.seek(-512, 2)
                footer = fat.vhd.file.read(512)
                geometry = (footer[59], footer[58], struct.unpack_from(">H", footer, 56)[0])
                capacities = {1: "360", 2: "1.2", 3: "720", 4: "1.44", 5: "2.88"}
                batch = "@ECHO OFF\r\n"
                if args.trace:
                    batch += "C:\\FDTEST.COM INSTALL\r\n"
                for letter, medium in (("A", ma), ("B", mb)):
                    if not medium:
                        continue
                    batch += (f"C:\\DOS\\FORMAT.COM {letter}: /U /F:{capacities[medium]} /V:TEST{letter} "
                              f"<C:\\FDIN.TXT >C:\\FMT{letter}.LOG\r\n"
                              "IF ERRORLEVEL 1 GOTO FAIL\r\n"
                              f"ECHO FLOPPY_OK>{letter}:\\PROBE.TXT\r\n")
                batch += "C:\\FDTEST.COM\r\n:FAIL\r\nC:\\FDTEST.COM FAIL\r\n"
                startup = "SHELL=C:\\DOS\\COMMAND.COM /P /E:1536\r\nFILES=30\r\nBUFFERS=10\r\n"
                if args.memory_managers:
                    startup += ("DEVICE=C:\\DOS\\HIMEM.SYS /V\r\n"
                                "DEVICE=C:\\DOS\\EMM386.EXE NOEMS x=F000-F5FF /V\r\n"
                                "DOS=HIGH,UMB\r\n")
                with disk.open("r+b", buffering=0) as out:
                    fat.replace(out, "CONFIG.SYS", startup.encode("ascii"))
                    fat.replace(out, "AUTOEXEC.BAT", batch.encode("ascii"))
                    fat.replace(out, "CONFIG.B~K", guest.read_bytes(), b"FDTEST  COM")
                    fat.replace(out, "AUTOEXEC.B~K", b"\r\nN\r\n", b"FDIN    TXT")
            finally:
                fat.vhd.close()
        else:
            disk = vm / "test.img"
            with disk.open("xb") as out:
                out.write(guest.read_bytes())
                # ISA IDE in 86Box reports LBA capacity only at >=1024 cylinders.
                out.truncate(64 * 1024 * 1024)
        extension = "img" if args.raw else "86f"
        fa, fb = vm / f"a.{extension}", vm / f"b.{extension}"
        for path, medium in ((fa, ma), (fb, mb)):
            if not medium:
                continue
            if args.raw:
                tracks, sectors, *_ = GEOMETRY[medium]
                path.write_bytes(bytes([0xF6 if args.read_only else 0]) * (tracks * 2 * sectors * 512))
            else:
                blank_86f(path, medium)
        image_paths = [path for path, medium in ((fa, ma), (fb, mb)) if medium]
        original_disks = [hashlib.sha256(path.read_bytes()).digest() for path in image_paths]
        roms = config(vm, disk, a, b, fa, fb, geometry, args.turbo, args.write_protected or args.read_only)
        print(f"START {case} turbo={args.turbo} {vm}", flush=True)
        result = run_hidden([exe, "-P", str(vm), "-R", str(roms), "-L", str(vm / "86box.log"), "-N"], timeout=args.timeout)
        if args.dos_backup:
            fat = importlib.import_module("memory-fixture").Fat16(disk)
            try:
                for letter in "AB":
                    if not (a if letter == "A" else b):
                        continue
                    try:
                        log = fat.read(f"FMT{letter}.LOG").decode("cp437")
                        print("\n".join(line.strip() for line in log.splitlines()
                                        if line.strip() and "percent completed" not in line), flush=True)
                        if result.returncode == 0x68 and "Format complete." not in log:
                            raise RuntimeError(f"{letter}: missing FORMAT completion in {vm}")
                    except StopIteration:
                        print(f"No FMT{letter}.LOG in {vm}", flush=True)
                        if result.returncode == 0x68:
                            raise RuntimeError(f"Missing FORMAT completion log in {vm}")
                if result.returncode != 0x68:
                    try:
                        print("FDC state: " + fat.read("FDSTATE.BIN").hex(" "), flush=True)
                    except StopIteration:
                        print("No FDSTATE.BIN", flush=True)
                if args.trace:
                    print("Last failed AX/CX/DX/BX/ES, output AX, FDC state: " +
                          fat.read("FDTRACE.BIN").hex(" "), flush=True)
            finally:
                fat.vhd.close()
        if result.returncode != 0x68:
            with disk.open("rb") as inp:
                inp.seek(30 * 512)
                report = inp.read(64)
            raise RuntimeError(f"{case}: exit {result.returncode:#x}; state+AX/step/drive: {report.hex(' ')}; {vm}")
        if args.diagnostic_log:
            with disk.open("rb") as inp:
                inp.seek(32 * 512)
                screen = inp.read(4000)[::2].decode("cp437")
            lines = [screen[i:i + 80].rstrip() for i in range(0, 2000, 80)]
            print("\n".join(line for line in lines if line), flush=True)
            reports = [line for line in lines if line.startswith("Drive ")]
            if len(reports) != 7 or any("BIOS=00" not in line for line in reports):
                raise RuntimeError(f"Diagnostic POST did not report seven successful operations: {vm}")
            if "FDC probe complete; no sectors written." not in lines:
                raise RuntimeError(f"Diagnostic POST did not finish: {vm}")
            if args.read_only:
                probes = [line for line in lines if line.startswith("Probe ")]
                if len(probes) != 4 or any(" ID=00/" not in line or " RD=00/" not in line for line in probes):
                    raise RuntimeError(f"Diagnostic ID/read failed on preformatted media: {vm}")
            elif args.write_protected and not args.raw:
                probes = [line for line in lines if line.startswith("Probe ")]
                if len(probes) != 4 or any(" ID=04/" not in line or " RD=04/" not in line for line in probes):
                    raise RuntimeError(f"Diagnostic did not report unreadable blank media: {vm}")
        if args.write_protected or args.read_only:
            if original_disks != [hashlib.sha256(path.read_bytes()).digest() for path in image_paths]:
                raise RuntimeError(f"Write-protected floppy image changed: {vm}")
            description = ("all tracks/heads read from independent preformatted images; image hashes unchanged"
                           if args.read_only else "write-protected format rejected on A/B; image hashes unchanged")
        else:
            description = "actual DOS FORMAT and file reads on each configured drive" if args.dos_backup else "all tracks formatted; both heads/edge tracks read, written, verified; A/B revisit; head crossing; DMA bound"
        print(f"PASS {case}: {description}", flush=True)


if __name__ == "__main__":
    main()
