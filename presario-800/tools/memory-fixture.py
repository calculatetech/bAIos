"""Build a disposable DOS memory-manager fixture from the user's dynamic VHD."""
import argparse
import sys
import shutil
import struct
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.tools.fat16 import Fat16
from shared.tools.inspect_vhd import Vhd


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", type=Path)
    parser.add_argument("--read")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--guest", type=Path)
    parser.add_argument("--drivers", choices=("DOS", "WINDOWS"), default="DOS")
    parser.add_argument("--no-emm", action="store_true")
    parser.add_argument("--loadhigh", action="store_true")
    args = parser.parse_args()
    if args.read:
        fat = Fat16(args.image)
        try:
            print(fat.read(args.read).decode("cp437"))
        finally:
            fat.vhd.close()
        return
    if not args.output or not args.guest:
        parser.error("--output and --guest are required to build a fixture")
    if args.loadhigh and args.no_emm:
        parser.error("--loadhigh requires EMM386")
    output = args.output.resolve()
    build = Path(__file__).resolve().parents[1] / "build"
    if not output.is_relative_to(build) or output == args.image.resolve() or output.exists():
        raise ValueError("Use a new disposable output inside presario-800/build")
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(args.image, output)
    fat = Fat16(output)
    try:
        with output.open("r+b", buffering=0) as disk:
            config = "SHELL=C:\\DOS\\COMMAND.COM /P /E:1536\r\nSTACKS=9,256\r\n"
            config += f"DEVICE=C:\\{args.drivers}\\HIMEM.SYS /V\r\n"
            if not args.no_emm:
                config += f"DEVICE=C:\\{args.drivers}\\EMM386.EXE NOEMS x=F000-F5FF /V\r\n"
            config += "DOS=UMB,HIGH\r\nBUFFERS=20\r\nLASTDRIVE=Z\r\nFILES=40\r\n"
            fat.replace(disk, "CONFIG.SYS", config.encode("ascii"))
            launch = "LH " if args.loadhigh else ""
            fat.replace(disk, "AUTOEXEC.BAT", f"@ECHO OFF\r\n{launch}C:\\XMSTEST.COM\r\n".encode("ascii"))
            fat.replace(disk, "CONFIG.B~K", args.guest.read_bytes(), b"XMSTEST COM")
    finally:
        fat.vhd.close()
    print(output)


if __name__ == "__main__":
    main()
