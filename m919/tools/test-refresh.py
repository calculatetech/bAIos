"""Build REFRESH; execute its counter-latch protocol against independent timers."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]


def check(raw, case):
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x100000)
    u.mem_write(0x20100, raw)
    for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
        u.reg_write(reg, 0x2000)
    u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
    u.reg_write(x.UC_X86_REG_EFLAGS, 2 if case == 'irq-off' else 0x202)
    initial_cr0 = u.reg_read(x.UC_X86_REG_CR0)
    if case == 'protected':
        location = 0x20100 + raw.index(b'\x0F\x01\xE0')

        def protected(m, address, size, _):
            m.reg_write(x.UC_X86_REG_AX, 1)
            m.reg_write(x.UC_X86_REG_IP, address - 0x20000 + size)

        u.hook_add(UC_HOOK_CODE, protected, None, location, location)
    mode2 = case == 'mode2'
    period = 36 if case == 'slow-refresh' else 18
    status = [0x34 if mode2 else 0x36, 0x14]
    if case == 'wrong-pit0': status[0] = 0x30
    if case == 'null-pit1': status[1] = 0x54
    if case == 'invalid-access': status[1] = 0x04
    if case == 'word-access': status[1] = 0x34
    if case == 'high-access': status[1] = 0x24
    pending = {0x40: [], 0x41: []}
    tick, reads61 = 30000, 0
    values1, count0, output, exits, writes = [], [], bytearray(), [], []
    status_reads = []

    def incoming(m, port, size, _):
        nonlocal tick, reads61
        tick += 1
        assert size == 1 and not m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        if port == 0x61:
            reads61 += 1
            if case == 'stuck-refresh' or (case == 'late-stuck' and reads61 > 4000):
                return 0x0C
            return 0x0C | (((tick // period) & 1) << 4)
        assert port in pending and pending[port], ('unlatched read', hex(port))
        return pending[port].pop(0)

    def outgoing(m, port, size, value, _):
        nonlocal tick
        tick += 1
        assert size == 1 and not m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        assert port == 0x43 and value in (0xE2, 0xE4, 0, 0x40), ('hardware write', port, value)
        writes.append(value)
        channel = 0 if value in (0xE2, 0) else 1
        port = 0x40 + channel
        assert not pending[port], ('unconsumed latch', port, pending[port])
        if value in (0xE2, 0xE4):
            assert output.startswith(b'REFRESH 1'), 'heading must precede access'
            pending[port] = [status[channel] | 0x80]
            status_reads.append(channel)
        elif channel == 0:
            count = 50000 if case == 'frozen-pit0' else (-tick * (1 if mode2 else 2)) & 0xFFFF
            count0.append(count)
            pending[port] = [count & 255, count >> 8]
        else:
            count = period - tick % period
            access = status[1] & 0x30
            if access == 0x20:
                # Exercise high-byte reads independently of the refresh toggle.
                count <<= 8
            values1.append(count)
            pending[port] = ([count & 255] if access == 0x10 else [count >> 8] if access == 0x20
                             else [count & 255, count >> 8])

    def interrupt(m, number, _):
        assert number == 0x21
        assert bool(m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200) == (case != 'irq-off')
        ax = m.reg_read(x.UC_X86_REG_AX)
        if ax >> 8 == 0x4C:
            exits.append(ax & 255)
            m.emu_stop()
            return
        assert ax >> 8 == 0x40 and m.reg_read(x.UC_X86_REG_BX) == 1
        length = m.reg_read(x.UC_X86_REG_CX)
        pointer = m.reg_read(x.UC_X86_REG_DS) * 16 + m.reg_read(x.UC_X86_REG_DX)
        data = bytes(m.mem_read(pointer, length))
        fail = case in ('short-output', 'output-error') or (case == 'late-output-error' and output)
        if fail:
            m.reg_write(x.UC_X86_REG_AX, length - 1)
            if case != 'short-output':
                m.reg_write(x.UC_X86_REG_EFLAGS, m.reg_read(x.UC_X86_REG_EFLAGS) | 1)
        else:
            output.extend(data)
            m.reg_write(x.UC_X86_REG_AX, length)
            m.reg_write(x.UC_X86_REG_EFLAGS, m.reg_read(x.UC_X86_REG_EFLAGS) & ~1)

    u.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_INTR, interrupt)
    u.emu_start(0x20100, 0x30000, count=3000000)
    refusal = case in ('protected', 'irq-off')
    failure = case in ('wrong-pit0', 'null-pit1', 'invalid-access', 'stuck-refresh', 'late-stuck', 'frozen-pit0')
    expected = 2 if refusal else 3 if failure else 1 if 'output' in case else 0
    assert exits == [expected], (case, exits, output)
    assert u.reg_read(x.UC_X86_REG_CR0) == initial_cr0
    assert bool(u.reg_read(x.UC_X86_REG_EFLAGS) & 0x200) == (case != 'irq-off')
    assert not any(pending.values())
    if expected in (0, 3):
        assert status_reads == [0, 1]
        numbers = [int(n, 16) for n in re.findall(rb'\b[0-9A-F]{8}\b', output)]
        assert numbers[:2] == status
        if values1:
            assert len(values1) == 256
            assert numbers[2:4] == [min(values1), max(values1)]
        if expected == 0:
            scale = 1 if mode2 else 2
            pairs = list(zip(count0[::2], count0[1::2]))
            accepted = [a - b for a, b in pairs if a > b]
            assert len(accepted) == 64
            assert numbers[4] == sum(accepted) // scale
            # The timer model advances continuously, independent of guest labels.
            # Polling phase contributes at most three PIT ticks per 32-edge window.
            assert abs(numbers[4] - 2048 * period) <= 64 * 3, (case, numbers[4])
        assert output.endswith(b'tick total).\r\n') and f'R{expected} '.encode() in output
    if refusal or case in ('short-output', 'output-error'):
        assert not writes
    return {'case': case, 'exit': exits[0], 'port61_reads': reads61,
            'counter0_samples': len(count0), 'counter1_samples': len(values1),
            'output': output.decode()}


def main():
    folder = PORT / 'build/diagnostics'
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / 'REFRESH.COM'
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    subprocess.run([nasm, '-w+error', '-f', 'bin', '-o', str(image),
                    str(PORT / 'diagnostics/refresh.asm')], check=True)
    raw = image.read_bytes()
    cases = [check(raw, case) for case in ('normal', 'mode2', 'slow-refresh', 'word-access', 'high-access',
             'protected', 'irq-off', 'wrong-pit0', 'null-pit1', 'invalid-access', 'stuck-refresh',
             'late-stuck', 'frozen-pit0', 'short-output', 'output-error', 'late-output-error')]
    report = {'size': len(raw), 'sum32': f'{sum(raw):08X}', 'sha256': hashlib.sha256(raw).hexdigest(),
              'cases': cases, 'limit': 'Assembled COM with synthetic running timers; no physical refresh or throughput proof.'}
    target = PORT / 'build/tests/pci-performance'
    target.mkdir(parents=True, exist_ok=True)
    (target / 'refresh.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({**{k: v for k, v in report.items() if k != 'cases'}, 'cases_passed': len(cases)}, indent=2))


if __name__ == '__main__':
    main()
