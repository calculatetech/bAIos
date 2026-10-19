"""Test PS/2 BIOS services and the user's Logitech DOS driver on a VHD copy."""
import argparse
from contextlib import nullcontext
import importlib
import os
from pathlib import Path
import shutil
import struct
import tempfile

floppy = importlib.import_module("floppy-matrix")
Fat16 = importlib.import_module("memory-fixture").Fat16


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("backup", type=Path)
    parser.add_argument("--no-mouse", action="store_true")
    parser.add_argument("--edit", action="store_true", help="Run the backup's EDIT and save typed text")
    parser.add_argument("--keep-artifacts", action="store_true", help="Retain the disposable VM for diagnosis")
    args = parser.parse_args()
    scratch = (floppy.BUILD / "tmp").resolve()
    if scratch.parent != floppy.BUILD.resolve():
        raise ValueError("Temporary VMs must stay inside the system build directory")
    scratch.mkdir(exist_ok=True)
    factory = tempfile.mkdtemp if args.keep_artifacts else tempfile.TemporaryDirectory
    directory = factory(prefix="mouse-", dir=scratch)
    with (nullcontext(directory) if args.keep_artifacts else directory) as name:
        run(args, Path(name))


def run(args, vm):
    guest = vm / "guest.com"
    nasm = shutil.which("nasm") or str(Path(os.environ["LOCALAPPDATA"]) / "bin/NASM/nasm.exe")
    defines = ["-DNO_MOUSE"] if args.no_mouse else []
    floppy.run_hidden([nasm, *defines, "-f", "bin", "-o", str(guest),
                       str(floppy.ROOT / "tests" / ("edit-test.asm" if args.edit else "mouse-test.asm"))], check=True)
    disk = vm / "dos.vhd"
    shutil.copyfile(args.backup, disk)
    fat = Fat16(disk)
    try:
        fat.vhd.file.seek(-512, 2)
        footer = fat.vhd.file.read(512)
        geometry = (footer[59], footer[58], struct.unpack_from(">H", footer, 56)[0])
        config = ("SHELL=C:\\DOS\\COMMAND.COM /P /E:1536\r\n"
                  "DEVICE=C:\\DOS\\HIMEM.SYS /V\r\n"
                  "DEVICE=C:\\DOS\\EMM386.EXE NOEMS x=F000-F5FF /V\r\n"
                  "DOS=HIGH,UMB\r\nFILES=30\r\nBUFFERS=10\r\n")
        batch = ("@ECHO OFF\r\nC:\\MTEST.COM\r\n"
                 "LH C:\\MOUSE\\MOUSE.COM >C:\\MOUSE.LOG\r\nC:\\MTEST.COM DRIVER\r\n")
        if args.edit:
            batch = "@ECHO OFF\r\nSET PATH=C:\\DOS;C:\\MOUSE\r\n"
            if not args.no_mouse:
                batch += "LH C:\\MOUSE\\MOUSE.COM >C:\\MOUSE.LOG\r\n"
            batch += "C:\\MTEST.COM\r\n"
        with disk.open("r+b", buffering=0) as out:
            fat.replace(out, "CONFIG.SYS", config.encode("ascii"))
            fat.replace(out, "AUTOEXEC.BAT", batch.encode("ascii"))
            fat.replace(out, "CONFIG.B~K", guest.read_bytes(), b"MTEST   COM")
            if args.edit:
                fat.replace(out, "AUTOEXEC.B~K", b"ORIGINAL\r\n", b"EDITTESTTXT")
    finally:
        fat.vhd.close()
    # Reuse the existing disposable VM configuration; no floppy media needed.
    roms = floppy.config(vm, disk, 4, 2, vm / "a.img", vm / "b.img", geometry)
    config_path = vm / "86box.cfg"
    settings = config_path.read_text()
    settings = "\n".join(line for line in settings.splitlines() if not line.startswith(("fdd_01_fn", "fdd_02_fn")))
    if not args.no_mouse:
        settings = settings.replace("mouse_type = none", "mouse_type = ps2")
    config_path.write_text(settings + "\n")
    exe = shutil.which("86Box.exe") or str(Path(os.environ["LOCALAPPDATA"]) /
        "Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe")
    print(f"START mouse absent={args.no_mouse} {vm}", flush=True)
    result = floppy.run_hidden([exe, "-P", str(vm), "-R", str(roms), "-L", str(vm / "86box.log"), "-N"], timeout=120)
    fat = Fat16(disk)
    try:
        if args.edit:
            edited = fat.read("EDITTEST.TXT")
            if result.returncode == 0x7A:
                screen = fat.vhd.sectors(32, 8)[:4000:2].decode("cp437")
                print("\n".join(screen[i:i+80].rstrip() for i in range(0,2000,80)).encode("ascii", "replace").decode(), flush=True)
                debug = fat.vhd.sectors(40, 2)
                counts = struct.unpack_from("<256H", debug, 256)
                print("INT16 counts:", [(hex(i),n) for i,n in enumerate(counts) if n], flush=True)
                print("Last AX/IP/CS, KBC/PIC, injected keys:", debug[768:778].hex(" "), flush=True)
                print("BDA:", debug[:64].hex(" "), flush=True)
                print("IRQ09 count/head/tail:", debug[778:784].hex(" "), flush=True)
                print("IRQ09 raw scans:", debug[784:817].hex(" "), flush=True)
                print("IRQ09 entry status:", debug[817:818].hex(), flush=True)
                print("BDA keyboard tail:", debug[0x90:0xA0].hex(" "), flush=True)
            print(f"Editor file: {edited!r}", flush=True)
            if result.returncode == 0x69 and edited != b"testORIGINAL\r\n":
                raise RuntimeError("EDIT did not save the expected typed text")
        try:
            print(fat.read("MOUSE.LOG").decode("cp437"), flush=True)
        except StopIteration:
            pass
        if result.returncode != 0x69:
            try:
                print("Guest failure AX/FLAGS:", fat.read("MFAIL.BIN").hex(" "), flush=True)
            except StopIteration:
                pass
    finally:
        fat.vhd.close()
    if result.returncode != 0x69:
        raise RuntimeError(f"Mouse check exited {result.returncode:#x}: {vm}")
    print("PASS: actual EDIT startup, keyboard typing, save and exit" if args.edit else
          "PASS: bounded absence + keyboard" if args.no_mouse else
          "PASS: BIOS commands/IRQ12 packet callback, Logitech driver load, movement/buttons and keyboard with HIMEM/EMM386", flush=True)


if __name__ == "__main__":
    main()
