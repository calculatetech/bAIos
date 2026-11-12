"""Build the resource reader and verify that card configuration stays unchanged."""
import copy
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.isa_pnp_proof import Bus, Card, serial


def check(raw, stream, expected, exit_code=0, arguments=b'', policy=None):
    card = Card(serial(b"\x16\x73\x18\x68", 1), stream)
    card.csn = 1
    card.state = "wait"
    card.registers[0] = {0x30: 1, 0x60: 2, 0x61: 0}
    before = copy.deepcopy(card.registers)
    bus = Bus([card])
    bus.read_port = 0x203
    cpu = Uc(UC_ARCH_X86, UC_MODE_16)
    cpu.mem_map(0, 0x100000)
    cpu.mem_write(0x10100, raw)
    cpu.mem_write(0x10080, bytes((len(arguments),)) + arguments + b'\r')
    cpu.mem_write(0x4FB, b"\x01\x03\x02")
    if policy is not None:
        assert len(policy) == 15
        cpu.mem_write(0x40E, struct.pack('<H',0x9E00))
        cpu.mem_write(0x9E300, policy)
    output, exits = [], []

    def incoming(u, port, size, unused):
        value = bus.input(port, size)
        assert value is not None, hex(port)
        return value

    def outgoing(u, port, size, value, unused):
        assert bus.output(port, size, value), hex(port)

    def interrupt(u, number, unused):
        assert number == 0x21
        function = u.reg_read(x.UC_X86_REG_AH)
        if function == 2:
            output.append(chr(u.reg_read(x.UC_X86_REG_DL)))
        else:
            assert function == 0x4C
            exits.append(u.reg_read(x.UC_X86_REG_AL))
            u.emu_stop()

    def write(u, access, address, size, value, unused):
        assert 0x10000 <= address and address + size <= 0x20000, hex(address)

    cpu.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
    cpu.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    cpu.hook_add(UC_HOOK_INTR, interrupt)
    cpu.hook_add(UC_HOOK_MEM_WRITE, write)
    for name, value in dict(CS=0x1000, DS=0x1000, ES=0x1000, SS=0x1000, SP=0xFFFE, EFLAGS=0x202).items():
        cpu.reg_write(getattr(x, "UC_X86_REG_" + name), value)
    cpu.emu_start(0x10100, 0x20000, count=3000000)
    actual = "".join(output)
    assert exits == [exit_code] and actual.splitlines() == expected, (exits, actual)
    assert card.registers == before and card.csn == 1 and card.state == "wait"
    assert all(event[0] != "write" or event[1] in (2, 3, 7) for event in bus.transactions), bus.transactions
    return actual.strip()


def main():
    folder = PORT / "build/diagnostics"
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / "PNPGAME.COM"
    nasm = shutil.which("nasm") or str(Path(os.environ["LOCALAPPDATA"]) / "bin/NASM/nasm.exe")
    subprocess.run([nasm, "-w+error", "-f", "bin", "-o", str(image), str(PORT / "diagnostics/pnp-gameport.asm")], check=True)
    header = b"\x0A\x10\0\x82\x03\0ESS\x15\x41\xD0\xB0\x2F\0"
    fixed = lambda base: b"\x4B" + struct.pack("<HB", base, 1)
    range_io = b"\x47\x01" + struct.pack("<HHBB", 0x200, 0x207, 1, 1)
    prefix = "G C01 L00 V0200 E01 "
    tests = (
        ("range", header + range_io + b"\x79\0", [prefix + "AFF P01 R0200-0207 S01 N01"]),
        ("preferred", header + b"\x31\0" + fixed(0x201) + b"\x31\x01" + fixed(0x200) + b"\x38\x79\0",
         [prefix + "A00 P00 R0201-0201 S01 N01", prefix + "A01 P01 R0200-0200 S01 N01"]),
        ("compatible", header[:9] + b"\x15\x16\x73\x12\x34\0\x1C\x41\xD0\xB0\x2F" + range_io + b"\x79\0",
         [prefix + "AFF P01 R0200-0207 S01 N01"]),
        ("metadata", header + b"\x84\x01\x01" + bytes(257) + range_io + b"\x79\0",
         [prefix + "AFF P01 R0200-0207 S01 N01"]),
        ("other device", header[:9] + b"\x15\x16\x73\x12\x34\0" + range_io + b"\x79\0",
         ["G3 No gameport I/O descriptor found."]),
    )
    for name, stream, expected in tests:
        print("PASS", name, check(image.read_bytes(), stream, expected), flush=True)
    line = prefix + "AFF P01 R0200-0207 S01 N01"
    complete = header + range_io + b"\x79"
    checksum = bytes(((-sum(complete)) & 255,))
    print("PASS checksum", check(image.read_bytes(), complete + checksum, [line]))
    for name, stream in (("truncated", header + range_io), ("bad checksum", complete + b"\x01")):
        print("PASS", name, check(image.read_bytes(), stream, [line, "G2 Resource read incomplete."], exit_code=2))
    for name, stream, status in (("full dump", complete + checksum, 0),
                                 ("truncated dump", header + range_io, 2)):
        identity = serial(b'\x16\x73\x18\x68', 1)[:8] + b'\xA5'
        data = identity + stream
        lines = ['R C01 ' + data[at:at+16].hex().upper() for at in range(0, len(data), 16)]
        if status:
            lines.append('G2 Resource read incomplete.')
        print('PASS', name, check(image.read_bytes(), stream, lines, exit_code=status, arguments=b' /D'))
    policy=bytes.fromhex('000000010201003003020000000000')
    stream=complete+checksum
    data=serial(b'\x16\x73\x18\x68',1)[:8]+b'\xA5'+stream
    lines=['P '+policy.hex().upper()]+['R C01 '+data[at:at+16].hex().upper() for at in range(0,len(data),16)]
    print('PASS saved reservations',check(image.read_bytes(),stream,lines,arguments=b' /D',policy=policy))
    print("PASS configuration unchanged;", image)


if __name__ == "__main__":
    main()
