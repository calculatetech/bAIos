"""Build and check a read-only DOS host-bridge register dump for a PCI port."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INTR
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.tools.rom import configuration, definitions


def check(raw, device, name):
    results = []
    for failure in (None, 'signature', 'read', 'short-write'):
        u = Uc(UC_ARCH_X86, UC_MODE_16)
        u.mem_map(0, 0x100000)
        u.mem_write(0x20100, raw)
        for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
            u.reg_write(reg, 0x2000)
        u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
        u.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
        output = bytearray()
        reads = []
        exits = []
        values = bytes((i * 37 + 0x19) & 255 for i in range(256))

        def interrupt(machine, number, _):
            ax = machine.reg_read(x.UC_X86_REG_AX)
            flags = machine.reg_read(x.UC_X86_REG_EFLAGS) & ~1
            if number == 0x1A:
                assert ax in (0xB101, 0xB108, 0xB109, 0xB10A), hex(ax)
                if ax == 0xB101:
                    machine.reg_write(x.UC_X86_REG_AX, 1)
                    machine.reg_write(x.UC_X86_REG_EDX, 0 if failure == 'signature' else 0x20494350)
                else:
                    assert machine.reg_read(x.UC_X86_REG_BX) == device << 3
                    offset = machine.reg_read(x.UC_X86_REG_DI)
                    reads.append(offset)
                    width = {8: 1, 9: 2, 10: 4}[ax & 255]
                    if offset % width or offset + width > 256 or (failure == 'read' and offset == 0x61):
                        flags |= 1
                        machine.reg_write(x.UC_X86_REG_AX, 0x8700 | (ax & 255))
                    else:
                        machine.reg_write(x.UC_X86_REG_AX, ax & 255)
                        mask = (1 << (width * 8)) - 1
                        prior = machine.reg_read(x.UC_X86_REG_ECX)
                        value = int.from_bytes(values[offset:offset+width], 'little')
                        machine.reg_write(x.UC_X86_REG_ECX, (prior & ~mask) | value)
            elif number == 0x21:
                if ax >> 8 == 0x40:
                    assert machine.reg_read(x.UC_X86_REG_BX) == 1
                    count = machine.reg_read(x.UC_X86_REG_CX)
                    address = (machine.reg_read(x.UC_X86_REG_DS) << 4) + machine.reg_read(x.UC_X86_REG_DX)
                    output.extend(machine.mem_read(address, count))
                    machine.reg_write(x.UC_X86_REG_AX, count - (failure == 'short-write'))
                else:
                    assert ax >> 8 == 0x4C, hex(ax)
                    exits.append(ax & 255)
                    machine.emu_stop()
            else:
                raise AssertionError(number)
            machine.reg_write(x.UC_X86_REG_EFLAGS, flags)

        u.hook_add(UC_HOOK_INTR, interrupt)
        u.emu_start(0x20100, 0x30000, count=100000)
        expected_exit = 0 if failure is None else 1 if failure == 'short-write' else 2
        assert exits == [expected_exit], (failure, exits)
        if failure is None:
            expected = name + ' host PCI configuration (read only)\r\n'
            expected += ''.join(f'{offset:02X}: ' + ''.join(f'{value:02X} ' for value in values[offset:offset+16]) + '\r\n'
                                for offset in range(0, 256, 16))
            assert output == expected.encode('ascii'), output
        elif failure == 'read':
            assert output == b'PCI read failed at 61 status 87\r\n', output
        assert reads == list(range(0 if failure == 'signature' else 0x62 if failure == 'read' else 256))
        results.append({'case': failure or 'all-registers', 'exit': expected_exit, 'reads': len(reads)})
    return results


def main():
    port, data = configuration(sys.argv[1])
    output = port / 'build/diagnostics'
    output.mkdir(parents=True, exist_ok=True)
    (output / 'configuration.inc').write_text(definitions(data), encoding='utf-8')
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    image = output / 'PCIDUMP.COM'
    subprocess.run([nasm, '-w+error', '-f', 'bin', '-I', str(output) + '/', '-o', str(image),
                    str(ROOT / 'shared/tools/pci-registers.asm')], check=True)
    raw = image.read_bytes()
    tests = check(raw, data['platform']['host_pci_device'], data['platform']['host_bridge'])
    result = {'path': str(image), 'size': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'checks': tests}
    (output / 'pci-registers-checks.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
