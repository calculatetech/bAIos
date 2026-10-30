"""Build and check DOS-owned partial writes and targeted moving inversions."""
import json
import os
from pathlib import Path
import shutil
import subprocess
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
FOLDER = PORT / 'build/diagnostics'


def check(raw, fault=0, cache=0xC3, allocation_ok=True, protected=False, l1_enabled=False, first=0x14000):
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x100000)
    program = 0x10000
    span = 0x8000 << (cache & 7)
    second = first + span
    u.mem_write(program + 0x100, raw)
    u.reg_write(x.UC_X86_REG_CR0, 0x10 if l1_enabled else 0x60000010)
    for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
        u.reg_write(reg, program >> 4)
    output, allocated, injected = [], [], []
    selection = [0x12345678]
    flushes, evictions = [0], [0]
    unaligned = [False]
    result = program + 0x100 + raw.index(b'I0 \r\n$')
    targets = (0x42B68, 0x48F7C, 0x88F7C)
    coverage = []
    def flip(address, mask=1):
        u.mem_write(address, bytes((u.mem_read(address, 1)[0] ^ mask,)))
        injected.append(address)
    def intr(cpu, number, _):
        assert number == 0x21, number
        ah = cpu.reg_read(x.UC_X86_REG_AH)
        flags = cpu.reg_read(x.UC_X86_REG_EFLAGS) & ~1
        if ah == 0x4A:
            assert cpu.reg_read(x.UC_X86_REG_BX) * 16 >= len(raw) + 0x100
        elif ah == 0x48:
            assert cpu.reg_read(x.UC_X86_REG_BX) == span * 2 // 16
            if allocation_ok:
                allocated.append((first, second + span))
                cpu.reg_write(x.UC_X86_REG_AX, first >> 4)
            else:
                flags |= 1
        elif ah == 0x49:
            assert cpu.reg_read(x.UC_X86_REG_ES) == first >> 4
            assert allocated
        elif ah == 9:
            address = (cpu.reg_read(x.UC_X86_REG_DS) << 4) + cpu.reg_read(x.UC_X86_REG_DX)
            output.append(bytes(cpu.mem_read(address, 24)).split(b'$')[0].decode())
        elif ah == 0x4C:
            cpu.emu_stop()
        else:
            raise AssertionError(hex(ah))
        cpu.reg_write(x.UC_X86_REG_EFLAGS, flags)
    def inp(cpu, port, size, _):
        assert port in (0xCF8, 0xCFC)
        return selection[0] if port == 0xCF8 else cache
    def out(cpu, port, size, value, _):
        assert port == 0xCF8, 'diagnostic wrote a chipset register'
        selection[0] = value
    def read(cpu, access, address, size, value, _):
        if injected:
            return
        if fault == 1 and address == first:
            flip(first + 1)
        elif fault == 4 and unaligned[0] and address == first + 12:
            flip(first + 12)
        elif fault == 7 and address == 0x48F7C and cpu.mem_read(result + 1, 1) == b'8' and bytes(cpu.mem_read(address, 4)) == b'\xfb'*4:
            flip(address + 2, 8)  # Observed FBFBFBFB -> FBF3FBFB, D19.
        elif fault == 8 and address == 0x42B68 and cpu.mem_read(result + 1, 1) == b'8' and bytes(cpu.mem_read(address, 4)) == b'\xfb'*4:
            flip(address + 3, 4)  # Observed FBFBFBFB -> FFFBFBFB, D26.
        elif fault == 9 and address == 0x42B68 and cpu.mem_read(result + 1, 1) == b'7' and bytes(cpu.mem_read(address, 4)) == b'\x08'*4:
            flip(address + 3, 4)  # Observed 08080808 -> 0C080808, D26.
        elif fault == 10 and address == 0x51B6C and cpu.mem_read(result + 1, 1) == b'8' and bytes(cpu.mem_read(address, 4)) == b'\xfb'*4:
            flip(address + 3, 2)  # Unknown-offset report must retain its full address.
        elif fault == 11 and address == 0x42B6A and cpu.mem_read(result + 1, 1) == b'1':
            flip(address + 1, 4)  # Upper-word D10 must report DWORD D26 at 42B68.
    def observe(cpu, access, address, size, value, _):
        stage = bytes(cpu.mem_read(result + 1, 1))
        if stage in (b'7', b'8'):
            assert address in targets and size == 4
            coverage.append((stage.decode(), address, bytes(cpu.mem_read(address, 4)).hex()))
    def write(cpu, access, address, size, value, _):
        assert program <= address and address + size <= program + len(raw) + 0x100 or any(
            a <= address and address + size <= b for a, b in allocated), ('out of DOS-owned RAM', hex(address))
        if address == first + 15 and size == 2:
            unaligned[0] = True
        if address == second:
            evictions[0] += 1
            if (fault == 3 and evictions[0] == 1) or (fault == 6 and evictions[0] == 2):
                flip(first + (1 if fault == 3 else 12))
    # Hook only the two flush opcodes; the remaining CPU code runs uninstrumented.
    def flush(cpu, address, size, _):
        flushes[0] += 1
        if (fault == 2 and flushes[0] == 1) or (fault == 5 and flushes[0] == 2):
            flip(first + (1 if fault == 2 else 12))
    for offset in range(len(raw) - 1):
        if raw[offset:offset + 2] == b'\x0f\x09':
            u.hook_add(UC_HOOK_CODE, flush, None, program + 0x100 + offset, program + 0x100 + offset)
    if protected:
        # Supply the virtual-DOS SMSW result without installing a DPMI host.
        offset = raw.index(b'\x0f\x01\xe0')
        def smsw(cpu, address, size, _):
            cpu.reg_write(x.UC_X86_REG_AX, 1)
            cpu.reg_write(x.UC_X86_REG_IP, address - program + 3)
        u.hook_add(UC_HOOK_CODE, smsw, None, program + 0x100 + offset, program + 0x100 + offset)
    u.hook_add(UC_HOOK_INTR, intr)
    u.hook_add(UC_HOOK_INSN, inp, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, out, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_MEM_WRITE, write)
    if fault in (1, 4, 7, 8, 9, 10, 11):
        u.hook_add(UC_HOOK_MEM_READ, read, None, first, first + span - 1)
    for target in targets:
        u.hook_add(UC_HOOK_MEM_READ, observe, None, target, target + 3)
    u.emu_start(program + 0x100, 0xFFFFF, count=30000000)
    expected = 'N0' if protected else 'N1' if not cache & 0x80 else 'N2' if (cache & 7) > 3 or not allocation_ok else 'N4' if first > min(targets) or first + span * 2 < max(targets) + 4 else f'I{fault}'
    expected += {7:'B', 8:'A', 9:'A'}.get(fault, ' ')
    if fault == 7:
        expected = 'I8B'
    if fault == 9:
        expected = 'I7A'
    if fault == 10:
        expected = 'I8X'
    if fault in (7, 8, 9):
        expected += ' ' + ('00080000' if fault == 7 else '04000000')
        expected += ' ' + ('00048F7C' if fault == 7 else '00042B68')
    if fault == 10:
        expected += ' 02000000 00051B6C'
    if fault in (1, 2, 3):
        expected = f'I{fault}X 00000100 {first:08X}'
    if fault in (4, 5, 6):
        expected = f'I{fault}X 00000001 {first+12:08X}'
    if fault == 11:
        expected = 'I1A 04000000 00042B68'
    assert output == [expected + '\r\n'], (output, expected, flushes, evictions)
    assert selection[0] == 0x12345678
    assert u.reg_read(x.UC_X86_REG_CR0) == (0x10 if l1_enabled else 0x60000010), 'CPU cache setting changed'
    if fault:
        assert injected, fault
    if expected == 'I0 ':
        assert len(coverage) == 48, len(coverage)
        for stage in ('7', '8'):
            for target in targets:
                values = [v for s, a, v in coverage if s == stage and a == target]
                wanted = [(bytes((1 << bit,))*4 if stage == '7' else bytes((255 ^ (1 << bit),))*4).hex() for bit in range(8)]
                assert values == wanted, (stage, hex(target), values)
        assert flushes[0] == 2, 'moving inversions must not flush between read/write passes'
    return dict(fault=fault, cache=hex(cache), allocation_ok=allocation_ok, protected=protected, l1_enabled=l1_enabled, output=expected, target_coverage=coverage)


def main():
    FOLDER.mkdir(parents=True, exist_ok=True)
    device = json.loads((PORT / 'port.json').read_text())['platform']['host_pci_device']
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    image = FOLDER / 'L2CHECK.COM'
    subprocess.run([nasm, '-w+error', '-f', 'bin', f'-DHOST_PCI_DEVICE={device}',
                    '-o', str(image), str(PORT / 'diagnostics/cache-data.asm')], check=True)
    raw = image.read_bytes()
    rows = [check(raw, fault) for fault in range(12)]
    rows += [check(raw, cache=0x83), check(raw, cache=0), check(raw, cache=0xC5),
             check(raw, allocation_ok=False), check(raw, protected=True), check(raw, l1_enabled=True), check(raw, first=0x50000),
             check(raw, fault=8, l1_enabled=True)]
    folder = PORT / 'build/tests/cache-data'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'result.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(f'DOS memory diagnostic: {len(rows)} pass/fault/guard cases PASS')


if __name__ == '__main__':
    main()
