"""Check PCI BIOS caller state and Intel's post-IRET word copy."""
from pathlib import Path
import importlib.util
import struct
import sys

from unicorn import UC_HOOK_CODE

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('pnp', ROOT / 'shared/tests/test-pnp.py')
pnp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pnp)
pnp.OUTPUT = 'build'


class Caller(pnp.Caller):
    def __init__(self):
        self.pci_active = False
        super().__init__('m919')
        self.pci_active = True
        self.read_value = 0xA1B2C3D4
        self.address = None
        self.accesses = []
        self.cpu.mem_write(0x44A, struct.pack('<H', 80))
        self.cpu.mem_write(0x484, bytes([24]))
        self.cpu.mem_write(0x463, struct.pack('<H', 0x3D4))

    def inp(self, cpu, port, size, unused):
        if self.pci_active and 0xCFC <= port <= 0xCFF:
            assert not cpu.reg_read(pnp.x.UC_X86_REG_EFLAGS) & 0x200
            self.accesses.append(('read', self.address, port, size))
            return (self.read_value >> (8 * (port - 0xCFC))) & ((1 << (8 * size)) - 1)
        return super().inp(cpu, port, size, unused)

    def out(self, cpu, port, size, value, unused):
        if self.pci_active and port == 0xCF8:
            self.address = value
            return
        if self.pci_active and 0xCFC <= port <= 0xCFF:
            assert not cpu.reg_read(pnp.x.UC_X86_REG_EFLAGS) & 0x200
            self.accesses.append(('write', self.address, port, size, value))
            return
        return super().out(cpu, port, size, value, unused)


    def interrupt(self, cpu, vector, unused):
        if vector == 0x1A:
            self.inject('pci_int1a', cpu.reg_read(pnp.x.UC_X86_REG_IP))
            return
        return super().interrupt(cpu, vector, unused)


def intel_word_checks():
    raw = (ROOT / 'tools/deps/intel-pnp/extracted/DWCFGMG.SYS').read_bytes()
    cases = 0
    for stack, vendor, target in ((s, v, t) for s in (0, 0x80, 0x7080, 0xFFF0)
                                  for v in (0xC3D4, 0x10B7) for t in (0x2D1D, 0xBC58)):
        caller = Caller()
        caller.read_value = 0xA1B20000 | vendor
        cpu = caller.cpu
        cpu.mem_write(0x20000, raw)
        cpu.ctl_remove_cache(0x20000, 0x2FFFF)
        cpu.mem_write(0x203FA, struct.pack('<H', 8))
        expected = bytes(cpu.mem_read(0x20000, len(raw)))
        # Repeat the same PCI word read to exercise repeated register access.
        stub = bytearray()
        for repeat in range(2):
            args = (0x5000, 0x200 + repeat * 2, 1, 0, 0x68, 0) if target == 0x2D1D else (0x68, 0)
            for value in args:
                stub += b'\x68' + struct.pack('<H', value)
            stub += b'\xE8' + struct.pack('<H', (target - (0xFE00 + len(stub) + 3)) & 0xFFFF)
            stub += b'\x83\xC4' + bytes([len(args) * 2])
        stub += b'\xF4'
        cpu.mem_write(0x2FE00, bytes(stub))
        values = dict(CS=0x2000, DS=0x2000, ES=0x5000, SS=0x3000,
                      ESP=0xABCD0000 | stack, EAX=0x12345678, EBX=0x87654321,
                      ECX=0x11223344, EDX=0x76543210, ESI=0x24681357,
                      EDI=0x13572468, EBP=0x19283746, EFLAGS=0x202)
        for name, value in values.items():
            cpu.reg_write(getattr(pnp.x, 'UC_X86_REG_' + name), value)
        stopped = []
        end = 0x2FE00 + len(stub) - 1
        hook = cpu.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (stopped.append(a), u.emu_stop()), None, end, end)
        caller.io.clear()
        cpu.emu_start(0x2FE00, 0x30000, count=200000)
        cpu.hook_del(hook)
        assert stopped, hex(stack)
        if target == 0x2D1D:
            assert bytes(cpu.mem_read(0x50200, 4)) == vendor.to_bytes(2, 'little') * 2
        else:
            assert cpu.reg_read(pnp.x.UC_X86_REG_AX) == 1
        state = {name: cpu.reg_read(getattr(pnp.x, 'UC_X86_REG_' + name)) for name in values}
        assert state['ESP'] == values['ESP']
        assert bytes(cpu.mem_read(0x20000, len(raw))) == expected
        cases += 1
    return cases


def main():
    caller = Caller()
    cpu = caller.cpu
    cases = 0
    for function in range(8, 14):
        width = (1, 2, 4)[(function - 8) % 3]
        offset = {1: 1, 2: 2, 4: 4}[width]
        for data, crtc, columns, row in ((0, 0x3D4, 80, 24), (0x11223344, 0x3D4, 80, 24),
                                         (0x11223344, 0x3B4, 132, 49)):
            cpu.mem_write(0x44A, struct.pack('<H', columns))
            cpu.mem_write(0x484, bytes([row]))
            cpu.mem_write(0x463, struct.pack('<H', crtc))
            values = dict(CS=0x1000, SS=0x3000, ESP=0x7000, DS=0x2000, ES=0x2000,
                          EAX=0xCDEFB100 | function, EBX=0x12340060, ECX=data,
                          EDX=0xABCD1234, ESI=0x87654321, EDI=0xCAFE0000 | offset,
                          EBP=0x19283746, EFLAGS=0xED7)
            for name, value in values.items():
                cpu.reg_write(getattr(pnp.x, 'UC_X86_REG_' + name), value)
            caller.accesses.clear()
            caller.io.clear()
            caller.inject('pci_int1a', 0x200)
            stopped = []
            hook = cpu.hook_add(UC_HOOK_CODE, lambda u, a, z, _: (stopped.append(a), u.emu_stop()), None, 0x10200, 0x10200)
            cpu.emu_start(0xF0000 + caller.listing.symbol('pci_int1a'), 0x100000, count=10000)
            cpu.hook_del(hook)
            assert stopped and len(caller.accesses) == 1
            access = caller.accesses[0]
            assert access[1:4] == (0x80006000 | (offset & ~3), 0xCFC + (offset & 3), width), access
            for name, original in values.items():
                expected = original
                if name == 'EAX':
                    expected &= ~0xFF00
                elif name == 'ECX' and function < 11:
                    mask = (1 << (8 * width)) - 1
                    expected = (original & ~mask) | ((0xA1B2C3D4 >> (8 * (offset & 3))) & mask)
                elif name == 'EFLAGS':
                    expected &= ~1
                assert cpu.reg_read(getattr(pnp.x, 'UC_X86_REG_' + name)) == expected, (function, name)
            if function >= 11:
                assert access[4] == data & ((1 << (8 * width)) - 1)
            cases += 1
    for name in ('pci_read', 'pci_write', 'pci_command_write'):
        caller.accesses.clear()
        caller.call(name, EAX=0x80006000, ECX=0x11223344)
        assert len(caller.accesses) == 1
        cases += 1
    result = {'cases': cases, 'Intel_word_wrapper_cases': intel_word_checks(),
              'public_registers_flags_widths_and_lane': 'PASS',
              'scope': 'Caller-state fixture'}
    print(result)


if __name__ == '__main__':
    main()
