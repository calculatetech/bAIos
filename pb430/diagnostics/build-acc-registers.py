"""Build the PB430 DOS register reader and check its actual machine code."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_INTR
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
REGISTERS = list(range(0x14)) + [0x14, 0x16, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x25, 0x26, 0x37]


def check(raw, cmos=False):
    registers = list(range(0x10, 0x80))*2 if cmos else REGISTERS
    assert {0x01, 0x02, 0x04, 0x0B, 0x12, 0x14, 0x16, 0x18, 0x19} <= set(REGISTERS)
    results = []
    cases = [("enabled", 0x10, 0x202, None),
             ("disabled", 0x60000010, 0x202, None),
             ("interrupts-off", 0x10, 2, None),
             ("virtual-8086", 0x11, 0x23202, None),
             ("short-write", 0x10, 0x202, "short"),
             ("output-error", 0x10, 0x202, "error")]
    for name, cr0, flags, failure in cases:
        u = Uc(UC_ARCH_X86, UC_MODE_16)
        u.mem_map(0, 0x100000)
        u.mem_write(0x20100, raw)
        for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
            u.reg_write(reg, 0x2000)
        u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
        u.reg_write(x.UC_X86_REG_EFLAGS, flags)
        u.reg_write(x.UC_X86_REG_CR0, cr0)
        values = bytes((i * 37 + 0x19) & 255 for i in range(256))
        selector = 0xA7
        io = []
        output = bytearray()
        exits = []

        def input_port(machine, port, size, _):
            assert not machine.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            assert size == 1
            assert port in ((0xF2, 0x78, 0x92, 0x71, 0x84) if cmos else (0xF2, 0xF3, 0x78, 0x92)), hex(port)
            value = {0xF2: selector, 0xF3: values[selector], 0x78: 0xFD, 0x92: 2, 0x71: values[selector], 0x84: 0}[port]
            io.append(("in", port, value))
            return value

        def output_port(machine, port, size, value, _):
            nonlocal selector
            assert not machine.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            assert size == 1 and port in ((0x70,) if cmos else (0xF2, 0xED)), (port, size, value)
            io.append(("out", port, value))
            if port == (0x70 if cmos else 0xF2):
                selector = value

        def interrupt(machine, number, _):
            assert number == 0x21, (name, number)
            assert machine.reg_read(x.UC_X86_REG_EFLAGS) & 0x200 == flags & 0x200
            ax = machine.reg_read(x.UC_X86_REG_AX)
            if ax >> 8 == 0x40:
                assert machine.reg_read(x.UC_X86_REG_BX) == 1
                count = machine.reg_read(x.UC_X86_REG_CX)
                address = (machine.reg_read(x.UC_X86_REG_DS) << 4) + machine.reg_read(x.UC_X86_REG_DX)
                output.extend(machine.mem_read(address, count))
                machine.reg_write(x.UC_X86_REG_AX, 5 if failure == "error" else count - (failure == "short"))
                machine.reg_write(x.UC_X86_REG_EFLAGS,
                                  (machine.reg_read(x.UC_X86_REG_EFLAGS) & ~1) | (failure == "error"))
            else:
                assert ax >> 8 == 0x4C, hex(ax)
                exits.append(ax & 255)
                machine.emu_stop()

        u.hook_add(UC_HOOK_INSN, input_port, None, 1, 0, x.UC_X86_INS_IN)
        u.hook_add(UC_HOOK_INSN, output_port, None, 1, 0, x.UC_X86_INS_OUT)
        u.hook_add(UC_HOOK_INTR, interrupt)
        u.emu_start(0x20100, 0x30000, count=100000)
        assert exits == [2 if cr0 & 1 else 1 if failure else 0], (name, exits)
        assert u.reg_read(x.UC_X86_REG_CR0) == cr0
        assert selector == (0 if cmos and not cr0 & 1 else 0xA7)
        if cr0 & 1:
            assert not io
            name_bytes = b'ACCCMOS' if cmos else b'ACCDUMP'
            assert output == b'Boot plain DOS without EMM386 or Windows, then run ' + name_bytes + b'.\r\n'
        else:
            expected_io = [("in", 0xF2, 0xA7), ("in", 0x78, 0xFD), ("in", 0x92, 2)]
            for index in registers:
                value = values[index]
                expected_io.extend([("out", 0x70, index), ("in", 0x84, 0), ("in", 0x71, value)] if cmos else [("out", 0xF2, index), ("out", 0xED, index), ("in", 0xF3, value), ("out", 0xED, value)])
            expected_io.extend([("out", 0x70, 0)] if cmos else [("out", 0xF2, 0xA7), ("out", 0xED, 0xA7)])
            assert io == expected_io, name
            expected = ('PB430 CMOS snapshot - two reads of 10-7F; no data writes\r\n' if cmos else 'ACC chipset snapshot - PB430 only; no configuration writes\r\n')
            expected += f'CR0={cr0:08X}  P78=FD  P92=02\r\n'
            for offset in range(0, len(registers), 8):
                expected += ''.join(f'{i:02X}={values[i]:02X} ' for i in registers[offset:offset+8]) + '\r\n'
            if len(registers) % 8 == 0: expected += '\r\n'
            assert output == expected.encode('ascii'), (name, output)
        results.append({"case": name, "exit": exits[0], "io_operations": len(io)})
    return results


def main():
    cmos = "--cmos" in sys.argv
    output = PORT / "build/diagnostics"
    output.mkdir(parents=True, exist_ok=True)
    nasm = shutil.which("nasm") or str(Path(os.environ["LOCALAPPDATA"]) / "bin/NASM/nasm.exe")
    image = output / ("ACCCMOS.COM" if cmos else "ACCDUMP.COM")
    subprocess.run([nasm, "-w+error", "-f", "bin", *(["-DACC_CMOS"] if cmos else []), "-o", str(image),
                    str(PORT / "diagnostics/acc-registers.asm")], check=True)
    raw = image.read_bytes()
    checks = check(raw, cmos)
    result = {"path": str(image), "size": len(raw), "sum32": f"{sum(raw):08X}",
              "sha256": hashlib.sha256(raw).hexdigest(), "checks": checks}
    (output / ("acc-cmos-checks.json" if cmos else "acc-registers-checks.json")).write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"{image}: {len(raw)} bytes, SUM32 {result['sum32']}; {len(checks)} machine-code checks passed")


if __name__ == "__main__":
    main()
