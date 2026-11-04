"""Build S3STATE; exercise byte-read whitelist, lock cleanup, and DOS failures."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INTR, UC_HOOK_INSN, UC_HOOK_CODE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
CR = [0x2D, 0x2E, 0x2F, *range(0x30, 0x3D), *range(0x40, 0x44),
      *range(0x50, 0x56), 0x58, 0x59, 0x5A, 0x5D, 0x5E, 0x60, *range(0x65, 0x6D)]
SR = [8, 9, 0x0A, 0x0B, 0x0D, 0x10, 0x11, 0x12, 0x13, 0x14, 0x15, 0x18]


def check(raw, case):
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x100000)
    u.mem_write(0x20100, raw)
    for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
        u.reg_write(reg, 0x2000)
    u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
    u.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
    if case == 'protected':
        address = 0x20100 + raw.index(b'\x0f\x01\xe0')

        def status(m, address, size, _):
            m.reg_write(x.UC_X86_REG_AX, 1)
            m.reg_write(x.UC_X86_REG_IP, (address & 0xFFFF) + size)

        u.hook_add(UC_HOOK_CODE, status, None, address, address)
    rom = bytearray((i*13+29) & 255 for i in range(65536 if case == '64k-rom' else 32768))
    rom[:3] = b'\x55\xaa' + bytes([len(rom)//512])
    if case == 'bad-rom':
        rom[2] = 129
    u.mem_write(0xC0000, bytes(rom))
    output, exits, modes, pci_reads, reads, writes = bytearray(), [], [], [], [], []
    old_mode = 7 if case == 'mono' else (0x12 if case == 'graphics' else 3)
    current_mode = old_mode
    cr, sr, index_cr, index_sr = {}, {}, 0, 0
    expected_cr, expected_sr = {}, {}
    snapshots = []
    stage = 0
    gc, index_gc, planar_done = {5: 0x40, 6: 5}, 0, False
    saved_indices = (0x17, 4)

    def install(mode):
        nonlocal cr, sr, index_cr, index_sr, expected_cr, expected_sr, saved_indices, planar_done
        cr = {i: (i*7+mode*5) & 255 for i in CR}
        sr = {i: (i*11+mode*3) & 255 for i in SR}
        cr.update({0x2D: 0x88, 0x2E: 0x11})
        cr.update({0x14: 0x40, 0x17: 0xA3})
        sr.update({2: 0x0F, 4: 0x0E})
        if case == 'wrong-cr' or (case == 'changed-card' and mode == 0x13):
            cr[0x2E] = 0x10
        cr[0x38], cr[0x39], sr[8] = ((0x48, 0xA5, 6) if case == 'unlocked' else
                                     (0xA9, 0x31, 0xE2) if mode == 0x13 else (0, 0, 0x90))
        index_cr, index_sr = 0x17, 4
        saved_indices, planar_done = (0x17, 4), False
        expected_cr, expected_sr = cr.copy(), sr.copy()

    install(old_mode)

    def clean(m):
        assert cr == expected_cr and sr == expected_sr, (case, cr, sr)
        assert (index_cr, index_sr) == saved_indices, (case, index_cr, index_sr)
        assert m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200, case

    def incoming(m, port, size, _):
        assert size == 1, (port, size)
        assert not (m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200), (case, port)
        base = 0x3B4 if current_mode == 7 else 0x3D4
        if port == 0x3CC:
            return 0 if current_mode == 7 else 1
        if port == base:
            return index_cr
        if port == 0x3C4:
            return index_sr
        if port == base+1:
            if stage == 3 and not planar_done and index_cr in (0x14, 0x17):
                return cr[index_cr]
            assert index_cr in CR, ('forbidden CR read', index_cr)
            if index_cr != 0x38:
                assert cr[0x38] == 0x48
            if index_cr not in (0x38, 0x39):
                assert cr[0x39] == 0xA5
            reads.append((stage, 'CR', index_cr))
            return cr[index_cr]
        if port == 0x3C5:
            if stage == 3 and not planar_done and index_sr == 4:
                return sr[4]
            assert index_sr in SR, ('forbidden SR read', index_sr)
            if index_sr != 8:
                assert sr[8] & 15 == 6
            reads.append((stage, 'SR', index_sr))
            return sr[index_sr]
        if port == 0x3CF:
            assert stage == 3 and not planar_done and index_gc in (5, 6)
            return gc[index_gc]
        raise AssertionError(('unexpected IN', hex(port)))

    def outgoing(m, port, size, value, _):
        nonlocal index_cr, index_sr, index_gc, planar_done, saved_indices
        assert not (m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200)
        if size == 2:
            assert port == 0x3C4 and value == 0x0F02 and stage == 3 and not planar_done
            index_sr = 2
            sr[2] = expected_sr[2] = 0x0F
            return
        assert size == 1
        base = 0x3B4 if current_mode == 7 else 0x3D4
        if port == base:
            index_cr = value
        elif port == 0x3C4:
            index_sr = value
        elif port == base+1:
            if stage == 3 and not planar_done and index_cr in (0x14, 0x17):
                assert value == (0 if index_cr == 0x14 else 0xE3)
                cr[index_cr] = expected_cr[index_cr] = value
                return
            assert index_cr in (0x38, 0x39), ('changed CR control', index_cr, value)
            if index_cr == 0x39:
                assert cr[0x38] == 0x48
            writes.append((stage, 'CR', index_cr, value))
            cr[index_cr] = value
        elif port == 0x3C5:
            if stage == 3 and not planar_done and index_sr == 4:
                assert value == 6
                sr[4] = expected_sr[4] = value
                return
            assert index_sr == 8, ('changed SR control', index_sr, value)
            writes.append((stage, 'SR', index_sr, value))
            sr[index_sr] = value
        elif port == 0x3CE:
            assert stage == 3 and not planar_done and value in (4, 5, 6)
            index_gc = value
            if value == 4:
                assert (cr[0x14], cr[0x17], sr[2], sr[4], gc[5], gc[6]) == (0, 0xE3, 15, 6, 0x40, 5)
                assert bytes(m.mem_read(0xA0000, 65536)) == bytes(65536)
                planar_done = True
                saved_indices = (0x17, 2)
        elif port == 0x3CF:
            assert stage == 3 and not planar_done
            assert value == (0x40 if index_gc == 5 else 5) and index_gc in (5, 6)
            gc[index_gc] = value
        else:
            raise AssertionError(('unexpected OUT', hex(port), value))

    def interrupt(m, number, _):
        nonlocal current_mode, stage
        ax = m.reg_read(x.UC_X86_REG_AX)
        flags = m.reg_read(x.UC_X86_REG_EFLAGS) & ~1
        clean(m)
        if number == 0x1A:
            assert not reads, 'PCI access after private capture'
            if ax == 0xB101:
                m.reg_write(x.UC_X86_REG_EDX, 0x20494350)
                m.reg_write(x.UC_X86_REG_AX, 1 if case != 'no-pci' else 0x8101)
                if case == 'no-pci': flags |= 1
            elif ax == 0xB103:
                assert m.reg_read(x.UC_X86_REG_ECX) == 0x030000
                m.reg_write(x.UC_X86_REG_BX, 0x60)
                m.reg_write(x.UC_X86_REG_AX, 3)
            else:
                assert ax == 0xB108
                assert m.reg_read(x.UC_X86_REG_BX) == 0x60
                off = m.reg_read(x.UC_X86_REG_DI)
                pci_reads.append(off)
                assert 0 <= off < 5
                identity = bytes.fromhex('33 53 11 88 03')
                if case == 'wrong-pci': identity = bytes.fromhex('33 53 11 89 03')
                if case == 'io-off': identity = identity[:4]+b'\x02'
                m.reg_write(x.UC_X86_REG_CL, identity[off])
                m.reg_write(x.UC_X86_REG_AX, 8 if case != 'read-error' else 0x8708)
        elif number == 0x10:
            if ax >> 8 == 0x0F:
                m.reg_write(x.UC_X86_REG_AX, 0x5000 | current_mode)
            else:
                assert ax >> 8 == 0
                new_mode = ax & 255
                assert new_mode in (0x13, old_mode)
                if new_mode == 0x13:
                    assert b'Mode13 capture;' in output
                snapshots.append((stage, expected_cr.copy(), expected_sr.copy()))
                current_mode = new_mode
                modes.append(new_mode)
                stage += 1
                install(new_mode)
                if stage == 3:
                    m.mem_write(0xA0000, bytes([0xA5])*65536)
        elif number == 0x21:
            assert current_mode == old_mode, 'DOS output/exit in graphics mode'
            if ax >> 8 == 0x40:
                count = m.reg_read(x.UC_X86_REG_CX)
                pointer = (m.reg_read(x.UC_X86_REG_DS) << 4)+m.reg_read(x.UC_X86_REG_DX)
                assert m.reg_read(x.UC_X86_REG_BX) == 1
                output.extend(m.mem_read(pointer, count))
                m.reg_write(x.UC_X86_REG_AX, count-int(case == 'short-output'))
                if case == 'late-output-error' and modes:
                    flags |= 1
            else:
                assert ax >> 8 == 0x4C, hex(ax)
                exits.append(ax & 255)
                m.emu_stop()
        else:
            raise AssertionError(number)
        m.reg_write(x.UC_X86_REG_EFLAGS, flags)

    u.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_INTR, interrupt)
    u.emu_start(0x20100, 0x30000, count=1000000)
    clean(u)
    rejected = ('protected', 'no-pci', 'wrong-pci', 'io-off', 'wrong-cr', 'changed-card', 'graphics', 'read-error')
    expected = 2 if case in rejected else 1 if case in ('short-output', 'late-output-error') else 0
    assert exits == [expected], (case, exits, output)
    if expected == 0:
        assert modes == [0x13, old_mode, 0x13, old_mode]
        assert output.endswith(b'S0 Complete. Text mode and register locks restored.\r\n')
        sections = re.findall(rb'CR index=value\r\n(.*?)SR index=value\r\n(.*?)(?=Mode13|DOOM planar|S0)', output, re.S)
        assert len(sections) == 3, output
        for (cr_text, sr_text), (phase, cr_expected, sr_expected) in zip(sections, [snapshots[i] for i in (0, 1, 3)]):
            for text, registers, values in ((cr_text, CR, cr_expected), (sr_text, SR, sr_expected)):
                found = [(int(a, 16), int(b, 16)) for a, b in re.findall(rb'([0-9A-F]{2})=([0-9A-F]{2})', text)]
                assert found == [(i, values[i]) for i in registers], (case, phase, found)
        if case == 'bad-rom':
            assert b'Live ROM bytes / FNV1a32: unknown\r\n' in output
        else:
            digest = 0x811C9DC5
            for v in rom: digest = ((digest ^ v)*0x01000193) & 0xFFFFFFFF
            assert f'{len(rom):08X} {digest:08X}'.encode() in output
    elif case == 'changed-card':
        assert modes == [0x13, old_mode]
    elif case in ('wrong-cr',):
        assert writes and not modes
    elif case not in ('late-output-error',):
        assert not reads and not writes and not modes
    return {'case': case, 'exit': exits[0], 'mode_calls': modes, 'reads': len(reads),
            'lock_writes': len(writes), 'output_bytes': len(output)}


def main():
    folder = PORT/'build/diagnostics'
    folder.mkdir(parents=True, exist_ok=True)
    image = folder/'S3STATE.COM'
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    subprocess.run([nasm, '-w+error', '-f', 'bin', '-o', str(image), str(PORT/'diagnostics/s3-state.asm')], check=True)
    raw = image.read_bytes()
    cases = [check(raw, case) for case in ('capture', 'mono', 'unlocked', '64k-rom', 'bad-rom',
             'protected', 'no-pci', 'wrong-pci', 'io-off', 'wrong-cr', 'changed-card', 'graphics',
             'read-error', 'short-output', 'late-output-error')]
    report = {'size': len(raw), 'sum32': f'{sum(raw) & 0xffffffff:08X}',
              'sha256': hashlib.sha256(raw).hexdigest(), 'cases': cases,
              'limit': 'Diagnostic execution with external PCI/VGA/DOS seams; no physical compatibility or speed claim.'}
    target = PORT/'build/tests/pci-performance'
    target.mkdir(parents=True, exist_ok=True)
    (target/'s3-state.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
