"""Build and check the read-only DOS snapshot against independent state and PCI seams."""
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.ram_proof import constants


def check(raw, state, *, clock=1, revision=0x0D, identity=0x673A1060,
          enabled=1, usable=1, bdf=0x91, ebda=0x9D00, size=8, protected=False, interrupt_flag=True):
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x100000)
    program = 0x10000
    u.mem_write(program+0x100, raw)
    for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
        u.reg_write(reg, program >> 4)
    u.reg_write(x.UC_X86_REG_CR0, 0x11 if protected else 0x10)
    u.reg_write(x.UC_X86_REG_EFLAGS, (0x202 if interrupt_flag else 2) | (0x23000 if protected else 0))
    assert bool(u.reg_read(x.UC_X86_REG_CR0) & 1) == protected
    assert bool(u.reg_read(x.UC_X86_REG_EFLAGS) & 0x20000) == protected
    u.mem_write(0x40E, struct.pack('<H', ebda))
    base = ebda << 4
    u.mem_write(base, bytes((size,)))
    for offset, value in ((state['C_CHIP']+21, clock), (0xA00, enabled),
                          (0x1039, usable), (state['S_PIO_BLOCKED'], 2)):
        u.mem_write(base+offset, bytes((value,)))
    u.mem_write(base+0x1034, struct.pack('<H', bdf))
    for position, present, packet, request, limit, effective, status in (
            (0,1,0,0,4,0,0x50), (1,0,0,5,3,2,0x41),
            (2,0,1,4,3,3,0x40), (3,1,0,2,2,1,0x51)):
        for key, value in (('S_PRESENT',present),('S_ATAPI',packet),('S_PIO_REQUEST',request),
                           ('S_PIO_LIMIT',limit),('S_PIO_MODE',effective),('S_STATUS',status)):
            u.mem_write(base+position*512+state[key], bytes((value,)))
    original_state = bytes(u.mem_read(base, 0x2000))
    original_bda = bytes(u.mem_read(0x400, 256))
    selection = [0xDEADBEEF]
    reads, writes, output = [], [], []
    selected = 0x80000000 | bdf << 8
    config = {selected: identity, selected | 8: 0xABCD1200,
              (selected & 0xFFFFF8FF) | 8: revision}
    def inp(cpu, port, size, _):
        assert size == 4 and port in (0xCF8, 0xCFC), (port, size)
        assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        if port == 0xCF8:
            return selection[0]
        reads.append(selection[0])
        assert selection[0] in config, hex(selection[0])
        return config[selection[0]]
    def out(cpu, port, size, value, _):
        assert port == 0xCF8 and size == 4, 'Unexpected config-data or ATA write'
        assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        selection[0] = value
        writes.append(value)
    def memory(cpu, access, address, size, value, _):
        assert program <= address and address+size <= program+0x10000, hex(address)
    def intr(cpu, number, _):
        assert number == 0x21
        assert bool(cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200) == interrupt_flag
        ah = cpu.reg_read(x.UC_X86_REG_AH)
        if ah == 2:
            output.append(chr(cpu.reg_read(x.UC_X86_REG_DL)))
        elif ah == 0x4C:
            cpu.emu_stop()
        else:
            raise AssertionError(ah)
    u.hook_add(UC_HOOK_INSN, inp, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, out, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_MEM_WRITE, memory)
    u.hook_add(UC_HOOK_INTR, intr)
    u.emu_start(program+0x100, program+0x100+len(raw), count=30000)
    text = ''.join(output)
    invalid = not 0x8000 <= ebda <= 0x9E00 or size != 8
    if protected:
        assert text == 'N0 plain DOS required\r\n' and not reads and not writes
    elif invalid:
        assert text == 'N1 invalid bAIos state\r\n' and not reads and not writes
    else:
        reason = '2' if enabled != 1 or usable != 1 or bdf & 7 != 1 or identity != 0x673A1060 else '0'
        reported_id, ide_rev, sibling_rev = (0xFFFFFFFF,0xFF,0xFF) if bdf == 0xFFFF else (identity,0,revision)
        expected = f'P{reason} I{reported_id:08X} V{ide_rev:02X}/{sibling_rev:02X} B{bdf:04X} U{enabled:X}{usable:X} X2 0R0L4E0S50D 2R4L3E3S40C 3R2L2E1S51D\r\n'
        assert text == expected, (text, expected)
        assert reads == ([] if bdf == 0xFFFF else [selected, selected | 8, (selected & 0xFFFFF8FF) | 8])
        if bdf != 0xFFFF:
            assert writes[-1] == 0xDEADBEEF
    assert selection[0] == 0xDEADBEEF
    assert bytes(u.mem_read(base, 0x2000)) == original_state
    assert bytes(u.mem_read(0x400, 256)) == original_bda
    return dict(output=text.strip(), reads=[f'{v:08X}' for v in reads], read_only=True)


def main():
    folder = PORT/'build/diagnostics'
    folder.mkdir(parents=True, exist_ok=True)
    source = PORT/'diagnostics/pio-state.asm'
    for name in ('HW_IDE_BDF', 'HW_IDE_USABLE'):
        actual = re.search(r'^%define '+name+r'\s+(\S+)', (PORT/'src/hardware/board-definition.inc').read_text(), re.M)[1]
        assert f'%define {name} {actual}' in source.read_text()
    size = json.loads((PORT/'port.json').read_text())['platform']['state_kib']
    assert size == 8
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    image = folder/'PIOSTATE.COM'
    subprocess.run([nasm, '-w+error', '-f', 'bin', f'-DSTATE_KIB={size}',
                    '-I'+str(PORT.parent/'shared/src')+'/', '-o', str(image), str(source)], check=True)
    state = constants(PORT.parent/'shared/src/pc/state.inc')
    for key in ('S_PRESENT', 'S_STATUS'):
        offset = re.search(r'^%define '+key+r'\s+STATE_BASE\s*\+\s*(\d+)',
                           (PORT.parent/'shared/src/pc/state.inc').read_text(), re.M)[1]
        state[key] = state['STATE_BASE'] + int(offset)
    rows = [check(image.read_bytes(), state, **options) for options in (
        {}, {'clock':0}, {'revision':12}, {'revision':14}, {'identity':0x673B1060}, {'usable':0},
        {'enabled':0}, {'bdf':0x1A9}, {'bdf':0xFFFF}, {'ebda':0x9000}, {'ebda':0x7F00},
        {'ebda':0x9F00}, {'size':1}, {'protected':True}, {'interrupt_flag':False})]
    output = PORT/'build/tests/pio-state/result.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2)+'\n')
    print(f'PIOSTATE: {len(rows)} snapshot/guard/read-only cases PASS')


if __name__ == '__main__':
    main()
