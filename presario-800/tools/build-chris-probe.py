"""Build a separate startup probe from the supplied, exact Chris benchmark."""
import argparse
import hashlib
import importlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_HASH = "7106fe7e66c6b3a1086365b3bdb950b32fe8f9875046b62ac30069241391d789"


def normalize_vesa(original):
    """Keep the full benchmark; encode its same DOS buffer with offset < 16."""
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32
    from unicorn import x86_const as x
    # Original: load __tb; DI=low16(__tb); ES=(__tb>>4)&F000.
    old = bytes.fromhex('a1dc660d00 66a310660d00 c1e804 662500f0 66a332660d00')
    # ROR puts address bits 4..19 in AX and bits 0..3 in bits 28..31.
    # Only EAX/flags differ after this block; both are dead before DPMI INT31.
    new = bytes.fromhex('a1dc660d00 c1c804 66a332660d00 c1e81c 66a310660d00 90')
    assert len(old) == len(new) == 24
    patched = bytearray(original)
    for site in (0x8BCF, 0x8D39, 0x8EB0):
        offset = site - 0x800
        assert original[offset:offset + 24] == old
        patched[offset:offset + 24] = new
        for buffer in (0xF760, 0xFF00, 0xFF40, 0xFFF0, 0x10000, 0x10630, 0x7FF40, 0x9F000):
            cpu = Uc(UC_ARCH_X86, UC_MODE_32)
            cpu.mem_map(0, 0x200000)
            cpu.mem_write(0x1000, bytes(patched[0x800:]))
            cpu.mem_write(0xD66DC, struct.pack('<I', buffer))
            cpu.mem_write(0xD6610, b'\xa5' * 0x34)
            cpu.reg_write(x.UC_X86_REG_ESP, 0x180000)
            preserved = (x.UC_X86_REG_EBX, x.UC_X86_REG_ECX, x.UC_X86_REG_EDX,
                         x.UC_X86_REG_ESI, x.UC_X86_REG_EDI, x.UC_X86_REG_EBP)
            for reg in preserved:
                cpu.reg_write(reg, 0x76543210)
            cpu.emu_start(site, site + 24, count=16)
            assert cpu.reg_read(x.UC_X86_REG_EIP) == site + 24
            expected = bytearray(b'\xa5' * 0x34)
            struct.pack_into('<H', expected, 0, buffer & 15)
            struct.pack_into('<H', expected, 0x22, buffer >> 4)
            assert cpu.mem_read(0xD6610, 0x34) == expected
            assert all(cpu.reg_read(reg) == 0x76543210 for reg in preserved)
            assert cpu.reg_read(x.UC_X86_REG_ESP) == 0x180000
    return patched


def post_only(original, no_port=False):
    """Redirect calls through register/flags-preserving POST-only tail thunks.

    These exact-image caves are alignment NOPs after RET, not live frame code.
    Neither COFF layout nor the loader, arguments, return PCs, or fallback changes.
    """
    hooks = (
        (0x3E3B, 0x2C0C, 0x5DDA, 0xD1),  # Model load.
        (0x3E51, 0xDA08, 0x5DFA, 0xD3),  # Delay (model returned).
        (0x3E56, 0x5F48, 0x5E2C, 0xD4),  # Allegro initialization.
        (0x3E6E, 0x6598, 0x5E7C, 0xD6),  # First graphics-mode attempt.
        (0x3E8A, 0x6598, 0x5ED9, 0xD8),  # Fallback graphics-mode attempt.
        (0x3EBC, 0xF21C, 0x611A, 0xD9),  # Graphics succeeded; start clock.
        (0x3F3C, 0xF370, 0x615B, 0xDA),  # First trigonometric calculation.
        (0x4370, 0x30EC, 0x64CB, 0xDB),  # Model normal calculation.
        (0x5C75, 0x8688, 0x685B, 0xDC),  # Frame blit (each frame).
        (0x5CA2, 0xF21C, 0x6AAB, 0xDD),  # All frames done; end clock.
        (0x5CB3, 0x60F8, 0x6E1A, 0xDE),  # Original graphics cleanup.
    )
    patched = bytearray(original)
    allowed = set()
    for site, target, cave, code in hooks:
        offset, spare = site - 0x800, cave - 0x800
        assert original[offset:offset + 5] == b'\xe8' + struct.pack('<i', target - site - 5)
        assert original[spare - 4:spare] == bytes.fromhex('89ec5dc3')
        assert original[spare:spare + 11] == b'\x90' * 11
        # PUSH EAX; MOV AL,stage; OUT 80h,AL; POP EAX; JMP original callee.
        port_instruction = (0x90, 0x90) if no_port else (0xE6, 0x80)
        thunk = bytes((0x50, 0xB0, code, *port_instruction, 0x58, 0xE9))
        thunk += struct.pack('<i', target - cave - 11)
        patched[spare:spare + 11] = thunk
        patched[offset:offset + 5] = b'\xe8' + struct.pack('<i', cave - site - 5)
        allowed.update(range(offset, offset + 5))
        allowed.update(range(spare, spare + 11))
    assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(original, patched)))
    check_post_hooks(original, patched, hooks, no_port)
    return patched


def check_post_hooks(original, patched, hooks, no_port=False):
    """Execute both paths to the real callee; compare stack, registers and flags."""
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_INSN
    from unicorn import x86_const as x
    registers = [x.UC_X86_REG_EAX, x.UC_X86_REG_EBX, x.UC_X86_REG_ECX,
                 x.UC_X86_REG_EDX, x.UC_X86_REG_ESI, x.UC_X86_REG_EDI,
                 x.UC_X86_REG_EBP, x.UC_X86_REG_ESP, x.UC_X86_REG_EFLAGS]
    for site, target, _, code in hooks:
        for flags in (0x202, 0xED7):
            results = []
            for executable in (original, patched):
                cpu = Uc(UC_ARCH_X86, UC_MODE_32)
                cpu.mem_map(0, 0x200000)
                cpu.mem_write(0x1000, bytes(executable[0x800:]))
                for i, register in enumerate(registers[:-2]):
                    cpu.reg_write(register, 0x12345678 + i)
                cpu.reg_write(x.UC_X86_REG_ESP, 0x180000)
                cpu.reg_write(x.UC_X86_REG_EFLAGS, flags)
                ports = []
                cpu.hook_add(UC_HOOK_INSN, lambda uc, port, size, value, data:
                             ports.append((port, size, value)), None, 1, 0, x.UC_X86_INS_OUT)
                cpu.emu_start(site, target, count=16)
                assert cpu.reg_read(x.UC_X86_REG_EIP) == target
                results.append(([cpu.reg_read(r) for r in registers],
                                bytes(cpu.mem_read(0x17FFFC, 8)), ports))
            assert results[0][:2] == results[1][:2]
            assert results[0][2] == []
            assert results[1][2] == ([] if no_port else [(0x80, 1, code)])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--emulator", action="store_true")
    parser.add_argument("--post-only", action="store_true",
                        help="Keep the full benchmark; add only POST-card call markers")
    parser.add_argument("--no-port", action="store_true",
                        help="With --post-only, replace only OUT instructions with equal-size NOPs")
    parser.add_argument("--normalize-vesa", action="store_true",
                        help="Keep full benchmark; normalize only three VESA buffer pointers")
    parser.add_argument("--support-image", type=Path,
                        help="Also package the matching DPMI host and model from this backup")
    args = parser.parse_args()
    if args.post_only and args.emulator:
        parser.error("The full benchmark has no emulator-only termination patch")
    if args.no_port and not args.post_only:
        parser.error("--no-port requires --post-only")
    if args.normalize_vesa and (args.post_only or args.emulator or args.no_port):
        parser.error("--normalize-vesa is a standalone full-benchmark comparison")
    original = args.source.read_bytes()
    if hashlib.sha256(original).hexdigest() != SOURCE_HASH:
        raise ValueError("This probe requires the exact supplied SVGABNCH.EXE")
    folder = ROOT / "build" / "diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    output = folder / ("CHRBOUND.EXE" if args.normalize_vesa else
                       "CHRNOPS.EXE" if args.no_port else "CHRPOST.EXE" if args.post_only else
                       "chris-emu.exe" if args.emulator else "CHRISDBG.EXE")
    if output.resolve() == args.source.resolve():
        raise ValueError("Do not overwrite the original benchmark")
    if args.normalize_vesa:
        patched = normalize_vesa(original)
    elif args.post_only:
        patched = post_only(original, args.no_port)
        if args.no_port:
            with_port = post_only(original)
            changed = [i for i, (a, b) in enumerate(zip(with_port, patched)) if a != b]
            assert len(changed) == 22
            for start in changed[::2]:
                assert with_port[start:start + 2] == b'\xe6\x80'
                assert patched[start:start + 2] == b'\x90\x90'
    else:
        patched = startup_probe(original, folder, args.emulator)
    assert len(patched) == len(original)
    output.write_bytes(patched)
    print(output)
    print(len(patched), hashlib.sha256(patched).hexdigest())
    if args.support_image:
        package_support(args, output, patched)


def startup_probe(original, folder, emulator):
    stub_path = folder / "chris-probe.bin"
    nasm = shutil.which("nasm") or str(Path(os.environ["LOCALAPPDATA"]) / "bin/NASM/nasm.exe")
    command = [nasm, "-f", "bin", "-o", str(stub_path)]
    if emulator:
        command += ["-D", "EMULATOR_TEST"]
    command += [str(ROOT / "tests/chris-probe.asm")]
    try:
        subprocess.run(command, check=True)
        stub = stub_path.read_bytes()
    finally:
        stub_path.unlink(missing_ok=True)
    # Exact executable: COFF .text maps virtual addresses to file offset VA-800h.
    assert len(stub) < 0x3B7  # Preserve main's separate LoadObject error target.
    patched = bytearray(original)
    patched[0x5200:0x5200 + len(stub)] = stub
    sites = (0x3E3B, 0x3E51, 0x3E56, 0x3E6E, 0x3E73)
    for i, (site, target) in enumerate(zip(sites, struct.unpack_from("<5I", stub))):
        offset = site - 0x800
        if i < 4:
            assert original[offset] == 0xE8
        else:
            assert original[offset:offset + 5] == bytes.fromhex("83c41885c0")
        patched[offset:offset + 5] = bytes([0xE8 if i < 4 else 0xE9]) + struct.pack("<i", target - site - 5)
    video_sites = (0x65BF, 0x8BEE, 0x8D5F, 0x8ED6, 0x9597, 0x9617)
    hooks = []
    for i, (site, target) in enumerate(zip(video_sites, struct.unpack_from("<6I", stub, 20))):
        offset = site - 0x800
        assert original[offset:offset + 5] == b'\xe8' + struct.pack('<i', 0x10524 - site - 5)
        patched[offset:offset + 5] = b'\xe8' + struct.pack('<i', target - site - 5)
        hooks.append((site, 0x10524, target, 0xE0 + i))
    check_post_hooks(original, patched, hooks)
    return patched


def package_support(args, output, patched):
    if args.emulator:
        raise ValueError("Do not package the emulator-only diagnostic")
    sys.path.insert(0, str(ROOT / "tools"))
    disk = importlib.import_module("memory-fixture").Fat16(args.support_image)
    try:
        base = "DOSBENCH/MARKS/CHRISB/"
        if hashlib.sha256(disk.read(base + "SVGABNCH.EXE")).hexdigest() != SOURCE_HASH:
            raise ValueError("Support image does not contain the matching original benchmark")
        support = {name: disk.read(base + name) for name in ("CWSDPMI.EXE", "HTOR.3DR")}
    finally:
        disk.vhd.close()
    package = output.with_suffix(".zip")
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(output.name, patched)
        for name, data in support.items():
            archive.writestr(name, data)
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert archive.read(output.name) == patched
        assert all(archive.read(name) == data for name, data in support.items())
    print(package)


if __name__ == "__main__":
    main()
