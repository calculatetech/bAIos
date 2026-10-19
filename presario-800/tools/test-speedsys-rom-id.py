"""Run Speedsys 4.78's original BIOS-ID scan against actual ROM bytes."""
import hashlib
import os
from pathlib import Path

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE
from unicorn import x86_const as x


ROOT = Path(__file__).resolve().parents[1]


def scan(code, rom):
    machine = Uc(UC_ARCH_X86, UC_MODE_16)
    machine.mem_map(0, 0x100000)
    machine.mem_write(0x30000, code)
    machine.mem_write(0xF0000, rom[-65536:])
    for name, value in (('CS', 0x3000), ('DS', 0x2000), ('ES', 0x2000),
                        ('SS', 0x7000), ('SP', 0xF000), ('EFLAGS', 2)):
        machine.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
    reached = []

    def stop(uc, address, size, unused):
        if address == 0x313C8:
            reached.append(address)
            uc.emu_stop()

    machine.hook_add(UC_HOOK_CODE, stop)
    machine.emu_start(0x31348, 0xFFFFF, count=1000000)
    assert reached, 'BIOS-ID scan did not finish'
    return (machine.reg_read(x.UC_X86_REG_DS), machine.reg_read(x.UC_X86_REG_SP))


def main():
    code = (ROOT.parent / 'reference/software/speedsys/4.78/SPEEDSYS-code.bin').read_bytes()
    assert hashlib.sha256(code).hexdigest() == 'b43f9ed7f8efa0f11561b3213b82c9727571fafd2fec1695b8cbfd0fe816eee0'
    candidate = (ROOT / os.environ.get('BAIOS_BUILD_DIRECTORY', 'build') / 'baios-presario800-system.rom').read_bytes()
    reference = (ROOT / 'reference/COMPAQ_PROLINEA_MT_05-02-94.BIN').read_bytes()
    # The exhausted search leaks DS=F000 and one stack word. Confirm that the
    # smallest application-side repair (route via its existing POP DS) fixes it.
    empty = bytes([0xFF]) * 65536
    assert scan(code, empty) == (0xF000, 0xEFFE)
    repaired = bytearray(code)
    assert repaired[0x136F:0x1371] == b'\xEB\x57'
    repaired[0x1370] = 0x2B
    assert scan(bytes(repaired), empty) == (0x2000, 0xF000)
    assert scan(code, reference) == (0x2000, 0xF000), 'OEM scan failed'
    actual = scan(code, candidate)
    assert actual == (0x2000, 0xF000), f'Candidate leaks DS/stack: {actual!r}'
    marker = b'1999, BAIOS'
    assert candidate.count(marker) == 1
    # Other valid identity strings may also satisfy the original scan.
    # The empty-ROM contrast above establishes its failure behavior.
    print('PASS: original scan preserves DS/stack with OEM and candidate; empty ROM reproduces the leak; compatibility token retained.')


if __name__ == '__main__':
    main()
