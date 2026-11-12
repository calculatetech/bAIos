"""Exercise the assembled boot router with independently supplied disk sectors."""
import argparse
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.tools.ram_proof import Listing, constants


def sector(code=b"\xF4", fill=0, signed=True):
    raw = bytearray(bytes((fill,)) * 512)
    raw[:len(code)] = code
    # A disk signature and partition table alone must not count as boot code.
    raw[440:446] = b"\x12\x34\x56\x78\0\0"
    raw[446:462] = struct.pack("<BBBBBBBBII", 0x80, 1, 1, 0, 0x0C, 254, 255, 255, 63, 100000)
    raw[510:512] = b"\x55\xAA" if signed else b"\0\0"
    return bytes(raw)


def check(image, hard_disk, expected, *, read_error=False, floppy=True):
    raw = image.read_bytes()
    listing = Listing(image.with_suffix(".lst"))
    state = constants(ROOT / "shared/src/pc/state.inc")
    state.update(constants(ROOT / "shared/src/pc/rom-state.inc"))
    cpu = Uc(UC_ARCH_X86, UC_MODE_16)
    cpu.mem_map(0, 0x100000)
    cpu.mem_write(0xF0000, raw[-65536:])
    base = 0x90000
    cpu.mem_write(0x40E, struct.pack("<H", base >> 4))
    cpu.mem_write(0x475, b"\x01")
    cpu.mem_write(base, b"\x10")
    for name, value in (("C_BOOT", 2), ("C_BOOT_SECOND", 1), ("C_BOOT_THIRD", 0),
                        ("C_BOOT_FOURTH", 0), ("F_TYPES", 4), ("B_ACTIVE", 0xA5)):
        cpu.mem_write(base + state[name], bytes((value,)))
    cpu.mem_write(base + state["C_PORTS"] + state["P_FLOPPY"], b"\x01")
    good_floppy = sector()
    cpu.mem_write(0x7C00, good_floppy)  # Signed stale data before a failed read.
    reads, handoffs, terminals = [], [], []

    def interrupt(u, number, unused):
        if number == 0x18:
            u.reg_write(x.UC_X86_REG_CS, 0xF000)
            u.reg_write(x.UC_X86_REG_IP, listing.symbol("int18"))
            u.reg_write(x.UC_X86_REG_EFLAGS, u.reg_read(x.UC_X86_REG_EFLAGS) & ~0x200)
            return
        assert number == 0x13, (number, hex(u.reg_read(x.UC_X86_REG_IP)))
        function = u.reg_read(x.UC_X86_REG_AH)
        drive = u.reg_read(x.UC_X86_REG_DL)
        assert function in (0, 2), function
        failed = False
        if function == 2:
            assert u.reg_read(x.UC_X86_REG_CX) == 1
            assert u.reg_read(x.UC_X86_REG_DH) == 0
            assert u.reg_read(x.UC_X86_REG_AL) == 1
            reads.append(drive)
            failed = read_error if drive == 0x80 else not floppy
            if not failed:
                address = (u.reg_read(x.UC_X86_REG_ES) << 4) + u.reg_read(x.UC_X86_REG_BX)
                u.mem_write(address, hard_disk if drive == 0x80 else good_floppy)
        u.reg_write(x.UC_X86_REG_AH, 0x20 if failed else 0)
        flags = u.reg_read(x.UC_X86_REG_EFLAGS)
        u.reg_write(x.UC_X86_REG_EFLAGS, flags | 1 if failed else flags & ~1)

    def instruction(u, address, length, unused):
        if address == 0x7C00:
            drive = u.reg_read(x.UC_X86_REG_DL)
            handoffs.append(drive)
            # INT18 is a real continuation from an MBR with no active partition.
            if drive == 0x80 and hard_disk[:2] == b"\xCD\x18":
                return
            terminals.append(drive)
            assert bytes(u.mem_read(address, 512)) == (hard_disk if drive == 0x80 else good_floppy)
            u.emu_stop()
        elif address == 0xF0000 + listing.symbol("boot_retry"):
            terminals.append("retry")
            u.emu_stop()

    cpu.hook_add(UC_HOOK_INTR, interrupt)
    cpu.hook_add(UC_HOOK_CODE, instruction)
    # The fixture supplies the installed public INT18 vector as startup does.
    cpu.mem_write(0x60, struct.pack("<HH", listing.symbol("int18"), 0xF000))
    for name, value in dict(CS=0xF000, DS=0, ES=0, SS=0, SP=0x7000, EFLAGS=0x202).items():
        cpu.reg_write(getattr(x, "UC_X86_REG_" + name), value)
    # Enter the resident candidate selector after the board's reset/KBC owners.
    cpu.emu_start(0xF0000 + listing.symbol("boot_candidate"), 0xFFFFF, count=100000)
    assert terminals == [expected], (terminals, handoffs, reads)
    assert reads == ([0x80] if expected == 0x80 else [0x80, 0]), reads
    return {"reads": reads, "handoffs": handoffs, "terminal": expected}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    args = parser.parse_args()
    cases = (
        ("unsigned", sector(signed=False), 0, {}),
        ("empty bootstrap", sector(code=b""), 0, {}),
        ("erased bootstrap", sector(code=b"", fill=255), 0, {}),
        ("read error with stale signed buffer", sector(), 0, {"read_error": True}),
        ("valid MBR", sector(), 0x80, {}),
        ("MBR INT18 continuation", sector(code=b"\xCD\x18\xF4"), 0, {}),
        ("all sources exhausted", sector(code=b""), "retry", {"floppy": False}),
    )
    for name, raw, expected, options in cases:
        print("PASS", name, check(args.image.resolve(), raw, expected, **options), flush=True)


if __name__ == "__main__":
    main()
