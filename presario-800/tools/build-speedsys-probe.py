"""Build a read-only DOS graphics probe from the supplied Speedsys 4.78 code."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("code", type=Path, help="Unpacked 64 KiB code segment")
    parser.add_argument("output", type=Path)
    parser.add_argument("--emulator", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = args.output.resolve()
    if not output.is_relative_to(root / "build"):
        parser.error("Output must be inside the system build directory")
    code = args.code.read_bytes()
    expected = "b43f9ed7f8efa0f11561b3213b82c9727571fafd2fec1695b8cbfd0fe816eee0"
    if len(code) != 65536 or hashlib.sha256(code).hexdigest() != expected:
        parser.error("Input is not the verified Speedsys 4.78 code segment")
    nasm = shutil.which("nasm") or str(Path(os.environ["LOCALAPPDATA"]) / "bin/NASM/nasm.exe")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="speedraw-", dir=root / "build/tmp") as temporary:
        stub = Path(temporary) / "stub.com"
        command = [nasm, "-f", "bin", "-I", str(root / "tests") + "/", "-o", str(stub)]
        if args.emulator:
            command += ["-D", "EMULATOR_TEST"]
        subprocess.run(command + [str(root / "tests/speedsys-probe.asm")], check=True)
        image = bytearray(stub.read_bytes())
    ranges = ((0x5F41, 0x6032), (0xA340, 0xA34C), (0xA360, 0xA395),
              (0xA3A0, 0xA3BB), (0xA3BB, 0xA47F), (0xA640, 0xA7A2))
    for start, end in ranges:
        assert image[start - 0x100:end - 0x100] == bytes(end - start)
        image[start - 0x100:end - 0x100] = code[start:end]
    assert len(image) == 0xA6A2
    for start, end in ranges:
        assert image[start - 0x100:end - 0x100] == code[start:end]
    output.write_bytes(image)
    assert output.read_bytes() == image
    print(f"{output}: {len(image)} bytes, SHA256 {hashlib.sha256(image).hexdigest().upper()}")


if __name__ == "__main__":
    main()
