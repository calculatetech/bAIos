"""Build PCISTATE and check bounded PCI BIOS reads without direct hardware I/O."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INTR, UC_HOOK_INSN, UC_HOOK_CODE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
ROOT = PORT.parent
sys.path.insert(0, str(ROOT))
from shared.tools.rom import configuration, definitions

TITLE = b'PCISTATE 3 - PCI BIOS byte reads; PM/IDE startup snapshot\r\n'
IBC_INDICES = [0x70,0x71,0x72,0x73,0x74,0x76,0x80,0x81,0x82,0x83,
               0x90,0x91,0x92,0x93,0xA0,0xA2,0xA3,0xA4,0xA7,0xA8]
IDE_INDICES = list(range(4,16)) + [0x3C] + list(range(0x40,0x5A))


def check(raw, host, isa, case='capture'):
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x100000)
    u.mem_write(0x20100, raw)
    for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
        u.reg_write(reg, 0x2000)
    u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
    u.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
    if case == 'protected':
        # Model SMSW status, without adding a protected DOS monitor to this fixture.
        address = 0x20100 + raw.index(b'\x0f\x01\xe0')

        def status(machine, address, size, _):
            machine.reg_write(x.UC_X86_REG_AX, 1)
            machine.reg_write(x.UC_X86_REG_IP, (address & 0xFFFF) + size)

        u.hook_add(UC_HOOK_CODE, status, None, address, address)
    vga = 0x68
    ide = isa | 1
    functions = {bdf: bytearray((bdf + i*29) & 255 for i in range(256))
                 for bdf in (host, isa, ide, vga)}
    functions[isa][:4] = (0 if case == 'other-bridge' else 0x886A1060).to_bytes(4,'little')
    ide_id = 0xFFFFFFFF if case == 'no-ide' else 0x12341060 if case == 'other-ide' else 0x673A1060
    functions[ide][:4] = ide_id.to_bytes(4,'little')
    ibc_valid = case != 'other-bridge'
    ide_valid = case not in ('no-ide','other-ide')
    snapshot_reads = ([(isa,i) for i in range(4)] +
                      ([(isa,i) for i in IBC_INDICES] if ibc_valid else []) +
                      [(ide,i) for i in range(4)] +
                      ([(ide,i) for i in IDE_INDICES] if ide_valid else []))
    output, calls, reads, exits = bytearray(), [], [], []

    def incoming(machine, port, size, _):
        raise AssertionError(('direct IN', port, size))

    def outgoing(machine, port, size, value, _):
        raise AssertionError(('direct OUT', port, size, value))

    def interrupt(machine, number, _):
        ax = machine.reg_read(x.UC_X86_REG_AX)
        flags = machine.reg_read(x.UC_X86_REG_EFLAGS) & ~1
        if number == 0x1A:
            calls.append(ax)
            assert ax in (0xB101, 0xB103, 0xB108), hex(ax)
            if ax == 0xB101:
                machine.reg_write(x.UC_X86_REG_AX, 1 if case != 'unavailable' else 0x8101)
                machine.reg_write(x.UC_X86_REG_EDX, 0 if case == 'signature' else 0x20494350)
                if case == 'unavailable':
                    flags |= 1
            elif ax == 0xB103:
                assert machine.reg_read(x.UC_X86_REG_ECX) == 0x030000
                assert machine.reg_read(x.UC_X86_REG_SI) == 0
                machine.reg_write(x.UC_X86_REG_BX, vga)
                machine.reg_write(x.UC_X86_REG_AX, 0x8603 if case == 'no-vga' else 3)
                if case == 'no-vga':
                    flags |= 1
            else:
                bdf = machine.reg_read(x.UC_X86_REG_BX)
                offset = machine.reg_read(x.UC_X86_REG_DI)
                assert bdf in functions, (bdf, offset)
                assert (bdf == host and offset < 0x64 or
                        bdf == isa and (offset < 0x58 or offset in IBC_INDICES) or
                        bdf == ide and (offset < 4 or offset in IDE_INDICES) or
                        bdf == vga and offset < 0x40), (bdf, offset)
                if len(reads) < len(snapshot_reads):
                    assert (bdf,offset) == snapshot_reads[len(reads)]
                    # No DOS/file output between any PM/IDE observations.
                    assert not output, output
                elif offset % 16 == 0 or offset == 0xA4:
                    assert output.endswith(f'{offset:02X}: '.encode()), output[-60:]
                reads.append((bdf, offset))
                fail = (case in ('read-carry', 'read-status') and bdf == host and offset == 0x61 or
                        case == 'pm-read-error' and bdf == isa and offset == 0xA2 or
                        case == 'ide-read-error' and bdf == ide and offset == 0x44)
                machine.reg_write(x.UC_X86_REG_AX, 0x8708 if fail else 8)
                machine.reg_write(x.UC_X86_REG_CL, functions[bdf][offset])
                if fail and case != 'read-status':
                    flags |= 1
        elif number == 0x21:
            if ax >> 8 == 0x40:
                assert machine.reg_read(x.UC_X86_REG_BX) == 1
                count = machine.reg_read(x.UC_X86_REG_CX)
                pointer = (machine.reg_read(x.UC_X86_REG_DS) << 4) + machine.reg_read(x.UC_X86_REG_DX)
                output.extend(machine.mem_read(pointer, count))
                machine.reg_write(x.UC_X86_REG_AX, count - int(case == 'short-output'))
                if case == 'output-error':
                    flags |= 1
            else:
                assert ax >> 8 == 0x4C, hex(ax)
                exits.append(ax & 255)
                machine.emu_stop()
        else:
            raise AssertionError(number)
        machine.reg_write(x.UC_X86_REG_EFLAGS, flags)

    u.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_INTR, interrupt)
    u.emu_start(0x20100, 0x30000, count=300000)
    expected_exit = (1 if case in ('short-output', 'output-error') else
                     2 if case in ('protected', 'unavailable', 'signature', 'read-carry', 'read-status',
                                   'pm-read-error', 'ide-read-error') else 0)
    assert exits == [expected_exit], (case, exits)
    expected_reads = (snapshot_reads + [(host, i) for i in range(0x64)] +
                      [(isa, i) for i in range(0x58)] + [(isa, 0xA4)] +
                      ([(vga, i) for i in range(0x40)] if case != 'no-vga' else []))
    if case in ('capture', 'no-vga', 'other-bridge', 'no-ide', 'other-ide'):
        assert reads == expected_reads
        text = output.decode('ascii')
        expected = TITLE.decode('ascii')

        def heading(bdf):
            return f'PCI {bdf >> 8:02X}:{(bdf >> 3) & 31:02X}.{bdf & 7:X}\r\n'

        def dump(bdf, start, count):
            return ''.join(f'{offset:02X}: ' + ''.join(f'{v:02X} ' for v in functions[bdf][offset:min(offset+16, start+count)]) + '\r\n'
                           for offset in range(start, start+count, 16))

        expected += heading(host) + dump(host, 0, 0x64)
        expected += heading(isa) + dump(isa, 0, 0x58) + dump(isa, 0xA4, 1)
        expected += 'VGA lookup\r\n'
        expected += ('VGA lookup unavailable; bridge capture retained.\r\n' if case == 'no-vga' else
                     heading(vga) + dump(vga, 0, 0x40))

        def pairs(bdf, indices):
            return ''.join(''.join(f'{i:02X}={functions[bdf][i]:02X} ' for i in indices[n:n+8])+'\r\n'
                           for n in range(0,len(indices),8))

        expected += heading(isa) + 'Startup snapshot (offset=value): \r\n'
        expected += (pairs(isa,IBC_INDICES) if ibc_valid else
                     'UM8886BF ID not matched; extra bridge reads skipped.\r\n')
        expected += heading(ide) + f'Startup snapshot (offset=value): \r\n{ide_id:08X}\r\n'
        expected += (pairs(ide,IDE_INDICES) if ide_valid else
                     'UM8886BF IDE ID not matched; private IDE reads skipped.\r\n')
        expected += 'Complete.\r\n'
        assert text == expected, text
    elif case in ('read-carry', 'read-status'):
        assert reads == snapshot_reads + [(host, i) for i in range(0x62)]
        assert output.endswith(b'PCI read failed at 61 status 87\r\n')
    elif case in ('pm-read-error', 'ide-read-error'):
        stop = (isa,0xA2) if case == 'pm-read-error' else (ide,0x44)
        assert reads == snapshot_reads[:snapshot_reads.index(stop)+1]
        assert output.endswith(f'PCI read failed at {stop[1]:02X} status 87\r\n'.encode())
    elif case in ('short-output', 'output-error'):
        assert reads == snapshot_reads
    else:
        assert not reads
    if case == 'protected':
        assert not calls
    return {'case': case, 'exit': exits[0], 'pci_byte_reads': len(reads),
            'direct_io': False, 'bytes': len(output)}


def main():
    _, config = configuration('m919')
    folder = PORT/'build/diagnostics'
    folder.mkdir(parents=True, exist_ok=True)
    (folder/'configuration.inc').write_text(definitions(config), encoding='utf-8')
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    image = folder/'PCISTATE.COM'
    subprocess.run([nasm, '-w+error', '-f', 'bin', '-I', str(folder)+'/', '-o', str(image),
                    str(PORT/'diagnostics/pci-state.asm')], check=True)
    raw = image.read_bytes()
    host, isa = [config['platform'][key] << 3 for key in ('host_pci_device', 'isa_pci_device')]
    cases = [check(raw, host, isa, case) for case in ('capture', 'no-vga', 'protected', 'unavailable',
             'signature', 'read-carry', 'read-status', 'short-output', 'output-error',
             'other-bridge', 'no-ide', 'other-ide', 'pm-read-error', 'ide-read-error')]
    result = {'version': 3, 'size': len(raw), 'sum32': f'{sum(raw) & 0xffffffff:08X}',
              'sha256': hashlib.sha256(raw).hexdigest(), 'cases': cases}
    target = PORT/'build/tests/pci-performance'
    target.mkdir(parents=True, exist_ok=True)
    (target/'pci-state.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
