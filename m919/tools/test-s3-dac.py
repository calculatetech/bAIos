"""Build S3DAC/S3WAIT; execute guards, masked writes and mode-change cleanup."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INTR, UC_HOOK_INSN, UC_HOOK_CODE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]


def check(raw, argument=' T', initial=0xEF, case='normal', wait=False):
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x100000)
    u.mem_write(0x20100, raw)
    tail = argument.encode('ascii')
    u.mem_write(0x20080, bytes([len(tail)]) + tail + b'\r')
    for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
        u.reg_write(reg, 0x2000)
    u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
    saved_if = 0 if case == 'if-clear' else 0x200
    u.reg_write(x.UC_X86_REG_EFLAGS, 2 | saved_if)
    if case == 'protected':
        address = 0x20100 + raw.index(b'\x0f\x01\xe0')

        def status(m, address, size, _):
            m.reg_write(x.UC_X86_REG_AX, 1)
            m.reg_write(x.UC_X86_REG_IP, (address & 0xFFFF) + size)

        u.hook_add(UC_HOOK_CODE, status, None, address, address)

    cr = {0x2D: 0x88, 0x2E: 0x11, 0x36: 0x9D, 0x37: initial, 0x38: 0, 0x39: 0}
    masks = {0x37: 0x10}
    if wait:
        cr.update({0x37: 0xBF, 0x40: initial >> 8, 0x58: initial & 255})
        masks = {0x58: 0x08, 0x40: 0x10}
    if case == 'wrong-id-high': cr[0x2D] = 0x89
    if case == 'wrong-id-low': cr[0x2E] = 0x10
    if case.startswith('bus-'): cr[0x36] = 0x9C | int(case[-1])
    if case == 'unlocked': cr[0x38], cr[0x39] = 0x48, 0xA5
    expected = cr.copy()
    original = {r: cr[r] & mask for r, mask in masks.items()}
    peer_bits = {r: cr[r] & (mask ^ 255) for r, mask in masks.items()}
    index = saved_index = 0x17
    old_mode = 7 if case == 'mono' else 0x12 if case == 'graphics' else 3
    mode = old_mode
    modes, writes, reads, exits, output = [], [], [], [], bytearray()
    choice = argument.strip().upper()
    wanted = ({0x58: 8 if choice == '1' else 0, 0x40: 0x10} if wait else
              {0x37: (initial ^ 0x10) & 0x10 if choice == 'T' else 0x10 if choice == '1' else 0})
    invalid = choice not in (('', '1', '2') if wait else ('', '0', '1', 'T'))
    prefix = 'W' if wait else 'D'
    write_count = 0
    base = lambda: 0x3B4 if mode == 7 else 0x3D4

    def clean(m):
        assert cr == expected, (case, choice, cr, expected)
        assert index == saved_index, (case, index, saved_index)
        assert m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200 == saved_if

    def incoming(m, port, size, _):
        assert size == 1
        assert not m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        if port == 0x3CC: return int(mode != 7)
        if port == base(): return index
        assert port == base()+1, ('unexpected IN', hex(port))
        assert index in cr, ('unexpected CRTC read', index)
        if index != 0x38: assert cr[0x38] == 0x48
        if index not in (0x38, 0x39): assert cr[0x39] == 0xA5
        reads.append(index)
        return cr[index]

    def outgoing(m, port, size, value, _):
        nonlocal index, write_count
        assert size == 1
        assert not m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        if port == base():
            index = value
            return
        assert port == base()+1, ('unexpected OUT', hex(port))
        assert index in (*masks, 0x38, 0x39), ('unexpected CRTC write', index)
        writes.append((index, value))
        if index in masks:
            assert cr[0x38] == 0x48 and cr[0x39] == 0xA5
            assert cr[0x2D] == 0x88 and cr[0x2E] == 0x11 and cr[0x36] & 3 == 1
            write_count += 1
            assert value & (masks[index] ^ 255) == peer_bits[index], ('peer bits changed', case, value)
            if case == 'write-reject' or (case == 'final-reject' and len(modes) == 2):
                return
            if case == 'second-reject' and index == 0x40:
                return
            if case in ('write-corrupt', 'rollback-fails') and write_count == 1:
                cr[index] = value ^ 0x20
                if case == 'rollback-fails': expected[index] = cr[index]
                return
            if case == 'rollback-fails':
                # The attempted rollback restores the saved byte, not the damaged peer.
                return
            expected[index] = value
            if case == 'cross-write' and write_count == 2:
                cr[0x58] ^= 0x20  # The final write must not hide damage to its peer.
        cr[index] = value

    def interrupt(m, number, _):
        nonlocal mode, saved_index, index, peer_bits
        clean(m)
        ax = m.reg_read(x.UC_X86_REG_AX)
        flags = m.reg_read(x.UC_X86_REG_EFLAGS) & ~1
        if number == 0x10:
            if ax >> 8 == 0x0F:
                m.reg_write(x.UC_X86_REG_AX, 0x5000 | mode)
            else:
                assert ax >> 8 == 0 and ax & 255 in (0x13, old_mode)
                mode = ax & 255
                modes.append(mode)
                if mode == 0x13:
                    for r, mask in masks.items():
                        assert cr[r] & mask == wanted[r]
                        cr[r] ^= 0x80  # BIOS is allowed to change the other fields.
                    if case == 'mode-reject':
                        first = next(iter(masks))
                        cr[first] ^= masks[first]
                    if case == 'graphics-id': cr[0x2E] = 0x10
                    cr[0x38], cr[0x39] = 0x19, 0x81
                    index = saved_index = 0x0F
                else:
                    for r in masks:
                        cr[r] ^= 0x40
                    if case in ('text-revert', 'final-reject'):
                        for r, mask in masks.items():
                            cr[r] = (cr[r] & (mask ^ 255)) | original[r]
                    cr[0x2E] = 0x10 if case == 'text-id' else 0x11
                    cr[0x38], cr[0x39] = 0x28, 0x01
                    index = saved_index = 0x11
                expected.update(cr)
                peer_bits = {r: cr[r] & (mask ^ 255) for r, mask in masks.items()}
        elif number == 0x21:
            assert mode == old_mode, 'DOS reached before text mode was restored'
            if ax >> 8 == 0x40:
                count = m.reg_read(x.UC_X86_REG_CX)
                pointer = (m.reg_read(x.UC_X86_REG_DS) << 4) + m.reg_read(x.UC_X86_REG_DX)
                assert m.reg_read(x.UC_X86_REG_BX) == 1
                output.extend(m.mem_read(pointer, count))
                m.reg_write(x.UC_X86_REG_AX, count - int(case == 'short-output'))
                if case == 'output-error': flags |= 1
            else:
                assert ax >> 8 == 0x4C
                exits.append(ax & 255)
                m.emu_stop()
        else:
            raise AssertionError(('unexpected INT', number))
        m.reg_write(x.UC_X86_REG_EFLAGS, flags)

    u.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_INTR, interrupt)
    u.emu_start(0x20100, 0x30000, count=20000)
    clean(u)
    rejected = invalid or case in ('graphics', 'wrong-id-high', 'wrong-id-low', 'bus-0', 'bus-2', 'bus-3')
    code = (2 if rejected else 1 if case in ('protected', 'short-output', 'output-error') else
            3 if case in ('write-reject', 'write-corrupt', 'final-reject', 'second-reject', 'cross-write') else
            4 if case in ('mode-reject', 'graphics-id') else
            5 if case in ('rollback-fails', 'text-id') else 0)
    assert exits == [code], (case, argument, exits, output)
    def display(values):
        if wait:
            return 0 if not values[0x40] else 1 if values[0x58] else 2
        return values[0x37] >> 4
    if code == 0:
        if choice:
            assert modes == [0x13, old_mode]
            assert all(cr[r] & mask == wanted[r] for r, mask in masks.items())
            assert output == f'{prefix}0 {display(original)}>{display(wanted)} Mode13 retained. Run Doom with sound effects.\r\n'.encode()
        else:
            assert not modes and not any(i in masks for i, v in writes)
            assert output.startswith(f'{prefix}0 current={display(original)}'.encode())
    elif code in (3, 4):
        assert all(cr[r] & mask == original[r] for r, mask in masks.items())
        assert output.startswith(f'{prefix}{code} '.encode())
    elif code == 2 or case == 'protected':
        assert not modes and not any(i in masks for i, v in writes)
        if invalid or case in ('graphics', 'protected'): assert not writes and not reads
    if case in ('second-reject', 'cross-write'):
        assert [r for r, v in writes if r in masks] == [0x58, 0x40, 0x40, 0x58]
    return {'case': case, 'argument': argument, 'initial': initial, 'exit': code,
            'mode_calls': modes, 'control_writes': write_count, 'output': output.decode('ascii').strip()}


def build(wait):
    stem = 's3-wait' if wait else 's3-dac'
    image = PORT/('build/diagnostics/S3WAIT.COM' if wait else 'build/diagnostics/S3DAC.COM')
    image.parent.mkdir(parents=True, exist_ok=True)
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    subprocess.run([nasm, '-w+error', '-f', 'bin', '-I', str(PORT/'diagnostics')+os.sep,
                    '-o', str(image), str(PORT/f'diagnostics/{stem}.asm')], check=True)
    raw = image.read_bytes()
    masked = [check(raw, arg, (value << 8) | (value ^ 0xA5) if wait else value, wait=wait)
              for value in range(256) for arg in (('', ' 1', ' 2') if wait else ('', ' T', ' 0', ' 1'))]
    initial = 0x20A0 if wait else 0xEF
    argument = ' 1' if wait else ' T'
    cases = [check(raw, argument, initial, case, wait) for case in ('mono', 'unlocked', 'if-clear', 'protected', 'graphics',
             'wrong-id-high', 'wrong-id-low', 'bus-0', 'bus-2', 'bus-3', 'write-reject', 'write-corrupt',
             'rollback-fails', 'mode-reject', 'graphics-id', 'text-id', 'text-revert', 'final-reject',
             'short-output', 'output-error')]
    cases += [check(raw, arg, initial, wait=wait) for arg in ('  t\t ', '   ', ' X', ' T 1', ' 01', ' /T', ' 1x')]
    if wait:
        cases += [check(raw, ' 1', initial, case, True) for case in ('second-reject', 'cross-write')]
    report = {'size': len(raw), 'sum32': f'{sum(raw) & 0xffffffff:08X}',
              'sha256': hashlib.sha256(raw).hexdigest(), 'masked_cases': len(masked), 'cases': cases,
              'limit': 'Executed COM with VGA/BIOS/DOS mocks; not a physical palette, DMA or sound test.'}
    target = PORT/f'build/tests/pci-performance/{stem}.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, indent=2))
    print(f'{len(cases)} guard, rollback, mode-change and output cases passed.')


def main():
    build(False)
    build(True)


if __name__ == '__main__':
    main()
