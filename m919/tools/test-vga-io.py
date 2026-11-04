"""Build VGAIO and check actual transfer ranges, PIT arithmetic, and cleanup."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.rom import configuration, definitions


def symbols(path):
    lines = path.read_text().splitlines()
    names = ('measure', 'empty_kernel', 'word_kernel', 'read_kernel', 'byte_kernel', 'column_kernel', 'planar', 'buffer')
    found = {}
    for name in names:
        index = next(i for i, line in enumerate(lines) if re.search(r'\b'+name+r'(?:\s+times|:)', line))
        for line in lines[index:]:
            match = re.match(r'\s*\d+\s+([0-9A-F]{8})\s+', line)
            if match:
                found[name] = int(match[1], 16)+0x100
                break
    return found


def check(raw, addresses, case, ide_bdf):
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x100000)
    u.mem_write(0x20100, raw)
    u.mem_write(0xC0000, b'\x55\xAA'+bytes(4094))
    u.mem_write(0x413, (632).to_bytes(2, 'little'))
    u.mem_write(0x40E, (0x9E00).to_bytes(2, 'little'))
    trial = case.startswith('ide-')
    tail = b' i ' if case == 'ide-peer-bits' else b' I' if trial else b' IX' if case == 'bad-argument' else b''
    u.mem_write(0x20080, bytes([len(tail)])+tail+b'\r')
    pci = bytearray(256)
    pci[:4] = (0 if case == 'ide-wrong-id' else 0x673A1060).to_bytes(4,'little')
    pci[4] = 5 if case == 'ide-bus-master' else 1
    pci[0x40] = 1 if case == 'ide-fifo' else 0
    pci[0x41] = 0xC0 if case == 'ide-no-change' else 0xDD if case == 'ide-peer-bits' else 0xC9
    pci[0x58] = int(case == 'ide-count-low')
    pci[0x59] = int(case == 'ide-count-high')
    original_pci = bytes(pci)
    pci_calls, pci_writes, fast_phases, console = [], [], [], bytearray()
    fast = trial and case != 'ide-normal' or case == 'bad-argument'
    for reg in (x.UC_X86_REG_CS, x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_SS):
        u.reg_write(reg, 0x2000)
    u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
    u.reg_write(x.UC_X86_REG_EFLAGS, 2 if case == 'irq-off' else 0x202)
    initial_cr0 = u.reg_read(x.UC_X86_REG_CR0)
    if case == 'protected':
        location = 0x20100+raw.index(b'\x0F\x01\xE0')

        def protected(m, address, size, _):
            m.reg_write(x.UC_X86_REG_AX, 1)
            m.reg_write(x.UC_X86_REG_IP, address-0x20000+size)

        u.hook_add(UC_HOOK_CODE, protected, None, location, location)
    if case == 'no-rom':
        u.mem_write(0xC0000, b'\0\0')
    current_mode = 7 if case == 'wrong-mode' else 3
    modes, output, exits = [], bytearray(), []
    registers = {0x3C4: {2: 15, 4: 14}, 0x3CE: {5: 0x40, 6: 5}, 0x3D4: {0x14: 0x40, 0x17: 0xA3}}
    indices = {p: 0 for p in registers}
    phase, latched, byte_index, status_pending, active = 0, 0, 0, False, False
    samples, memory_bytes = [0]*6, [0]*6
    deltas = [16, 40, 300, 4000, 5000, 7000]
    mode2 = case == 'mode2-wrap'
    wrap_done = False

    def state(m):
        bx, es = m.reg_read(x.UC_X86_REG_BX), m.reg_read(x.UC_X86_REG_ES)
        if bx == addresses['empty_kernel']: return 0
        if bx == addresses['word_kernel']: return 1 if es == 0x2000 else 3
        if bx == addresses['read_kernel']: return 2
        if bx == addresses['byte_kernel']: return 4
        assert bx == addresses['column_kernel']
        return 5

    def incoming(m, port, size, _):
        nonlocal status_pending, byte_index
        assert size == 1 and not m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        if port == 0x40:
            if status_pending:
                status_pending = False
                return 0x30 if case == 'wrong-pit' else 0x34 if mode2 else 0x36
            value = (latched >> (byte_index*8)) & 255
            byte_index ^= 1
            return value
        assert port-1 in registers
        return registers[port-1][indices[port-1]]

    def outgoing(m, port, size, value, _):
        nonlocal phase, latched, byte_index, status_pending, active, wrap_done
        assert not m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        if port == 0x43:
            assert size == 1 and value in (0, 0xE2), ('timer reprogrammed', value)
            if value == 0xE2:
                status_pending = True
                return
            phase = state(m)
            byte_index = 0
            active = samples[phase] % 2 == 0
            latched = 50000
            if not active:
                frozen = case == 'frozen' or (case == 'late-frozen' and phase == 4)
                if not frozen:
                    latched -= deltas[phase]
                if mode2 and phase == 3 and not wrap_done:
                    latched = 60000
                    wrap_done = True
            samples[phase] += 1
            return
        assert current_mode == 0x13
        if size == 2:
            assert port == 0x3C4 and value == 0x0102
            indices[port], registers[port][2] = 2, 1
        elif port in registers:
            assert size == 1
            indices[port] = value
        else:
            assert size == 1 and port-1 in registers
            registers[port-1][indices[port-1]] = value

    def memory(m, access, address, size, value, _):
        if not active:
            return
        ranges = ((0, 0), (0x20000+addresses['buffer'], 3840), (0xC0000, 3840),
                  (0xB80A0, 3840), (0xA0000, 3840), (0xA0000, 15300))
        lower, length = ranges[phase]
        if not lower <= address < lower+length:
            # Stack and harness state are expected; any other VGA access is not.
            assert not 0xA0000 <= address < 0xC0000, (case, phase, hex(address))
            return
        assert not m.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        assert address+size <= lower+length
        assert size == (1 if phase >= 4 else 2)
        if phase == 5:
            assert (address-lower) % 80 < 20
        memory_bytes[phase] += size

    def interrupt(m, number, _):
        nonlocal current_mode
        ax, flags = m.reg_read(x.UC_X86_REG_AX), m.reg_read(x.UC_X86_REG_EFLAGS)
        if number == 0x10:
            if ax >> 8 == 0x0E:
                console.append(ax & 255)
                return
            if ax >> 8 == 0x0F:
                m.reg_write(x.UC_X86_REG_AX, 0x5000 | current_mode)
                return
            assert flags & 0x200
            assert ax in (3, 0x13)
            modes.append(ax)
            current_mode = ax
            # A real option ROM may disturb segment/scratch registers.
            for reg in (x.UC_X86_REG_DS, x.UC_X86_REG_ES, x.UC_X86_REG_FS, x.UC_X86_REG_GS):
                m.reg_write(reg, 0x1234)
            for reg in (x.UC_X86_REG_EBX, x.UC_X86_REG_ESI, x.UC_X86_REG_EDI):
                m.reg_write(reg, 0xDEADBEEF)
            m.reg_write(x.UC_X86_REG_EFLAGS, flags | 0x400)
        elif number == 0x21:
            assert bytes(pci) == original_pci, 'DOS called before IDE restoration'
            assert current_mode != 0x13, 'DOS called before restoring video'
            if ax >> 8 == 0x40:
                count = m.reg_read(x.UC_X86_REG_CX)
                pointer = (m.reg_read(x.UC_X86_REG_DS) << 4)+m.reg_read(x.UC_X86_REG_DX)
                output.extend(m.mem_read(pointer, count))
                m.reg_write(x.UC_X86_REG_AX, count-int(case in ('short-output','ide-short-output')))
                m.reg_write(x.UC_X86_REG_EFLAGS, flags & ~1)
            else:
                assert ax >> 8 == 0x4C
                exits.append(ax & 255)
                m.emu_stop()
        elif number == 0x1A:
            pci_calls.append(ax)
            assert trial and ax in (0xB101,0xB108,0xB10B)
            flags &= ~1
            status = 0
            if ax == 0xB101:
                m.reg_write(x.UC_X86_REG_EDX,0 if case == 'ide-no-bios' else 0x20494350)
            else:
                assert m.reg_read(x.UC_X86_REG_BX) == ide_bdf
                index = m.reg_read(x.UC_X86_REG_DI)
                if ax == 0xB108:
                    assert index in (0,1,2,3,4,0x40,0x41,0x58,0x59)
                    status = 0x87 if (case == 'ide-read-error' and index == 0x58 or
                                     case == 'ide-restore-read-error' and len(pci_writes) == 2) else 0
                    m.reg_write(x.UC_X86_REG_CL,pci[index])
                else:
                    assert index == 0x41
                    value = m.reg_read(x.UC_X86_REG_CL)
                    pci_writes.append((index,value))
                    assert value == (original_pci[0x41] & ~9 if len(pci_writes)==1 else original_pci[0x41])
                    assert len(pci_writes) <= 2
                    ignored = (case == 'ide-write-ignored' and len(pci_writes)==1 or
                               case == 'ide-restore-fails' and len(pci_writes)==2)
                    if not ignored:
                        pci[index] = value
                    if case == 'ide-write-error' and len(pci_writes)==1:
                        status = 0x87  # The write happened despite failed completion.
            m.reg_write(x.UC_X86_REG_AX,(status << 8) | (ax & 255))
            m.reg_write(x.UC_X86_REG_EFLAGS,flags | int(bool(status)))
        else:
            raise AssertionError(('unexpected interrupt', number))

    def enter_measure(m,address,size,_):
        if trial:
            assert pci[0x41] == original_pci[0x41] & ~9
        if not fast:
            return
        phase = state(m)
        fast_phases.append(phase)
        m.reg_write(x.UC_X86_REG_EAX,deltas[phase]*128)
        flags = m.reg_read(x.UC_X86_REG_EFLAGS) & ~1
        m.reg_write(x.UC_X86_REG_EFLAGS,flags | int(case == 'ide-late-frozen' and phase == 4))
        sp = m.reg_read(x.UC_X86_REG_SP)
        ret = int.from_bytes(m.mem_read(0x20000+sp,2),'little')
        m.reg_write(x.UC_X86_REG_SP,sp+2)
        m.reg_write(x.UC_X86_REG_IP,ret)

    u.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_INTR, interrupt)
    u.hook_add(UC_HOOK_MEM_WRITE | UC_HOOK_MEM_READ, memory)
    entry = 0x20000+addresses['measure']
    u.hook_add(UC_HOOK_CODE,enter_measure,None,entry,entry)
    u.emu_start(0x20100, 0x30000, count=20000000)
    refused = case in ('protected', 'irq-off', 'no-rom', 'wrong-mode', 'wrong-pit','bad-argument')
    failed_timer = case in ('frozen', 'late-frozen','ide-late-frozen')
    failed_ide = case in ('ide-wrong-id','ide-bus-master','ide-fifo','ide-count-low','ide-count-high',
                         'ide-no-change','ide-read-error','ide-write-error','ide-write-ignored','ide-no-bios')
    failed_restore = case in ('ide-restore-fails','ide-restore-read-error')
    expected = (5 if failed_restore else 4 if failed_ide else 2 if refused else 3 if failed_timer else
                1 if case in ('short-output','ide-short-output') else 0)
    assert exits == ([] if failed_restore else [expected]), (case, exits, output)
    assert u.reg_read(x.UC_X86_REG_CR0) == initial_cr0
    assert bool(u.reg_read(x.UC_X86_REG_EFLAGS) & 0x200) == (case != 'irq-off' and not failed_restore)
    if failed_restore:
        assert not output and b'V5 IDE restore not confirmed.' in console
    elif not refused and not failed_timer and not failed_ide:
        assert modes == [0x13, 3]
        parsed = [int(n, 16) for n in re.findall(rb'^(?:Empty|RAM W16|ROM R16|TextW16|VGA W8|Doom W8) +([0-9A-F]{8})', output, re.M)]
        assert parsed == [d*256//(1 if mode2 else 2) for d in deltas], (case, parsed)
        if fast:
            assert fast_phases == list(range(6))
        else:
            assert memory_bytes == [0, 983040, 983040, 983040+(3840 if mode2 else 0), 983040, 983040], memory_bytes
            assert samples == [512, 512, 512, 514 if mode2 else 512, 512, 512]
        assert b'00000278 00009E00' in output and output.endswith(b'changed.\r\n')
        assert registers[0x3C4][4] == 6 and registers[0x3C4][2] == 1
        assert registers[0x3CE][5] == 0x40 and registers[0x3CE][6] == 5
        assert registers[0x3D4][0x14] == 0 and registers[0x3D4][0x17] == 0xE3
    elif refused or failed_ide:
        assert not modes and not sum(memory_bytes)
    elif case == 'ide-late-frozen':
        assert modes == [0x13,3] and fast_phases == list(range(5))
    elif case == 'late-frozen':
        assert modes == [0x13, 3] and samples[4] == 2048
    else:
        assert not modes and samples[0] == 2048
    if not trial:
        assert not pci_calls and not pci_writes
    elif pci_writes:
        assert pci_writes == [(0x41,original_pci[0x41] & ~9),(0x41,original_pci[0x41])]
        if not failed_restore and not failed_ide and not failed_timer and expected == 0:
            field = f'{original_pci[0x41]:08X} {original_pci[0x41] & ~9:08X} {original_pci[0x41]:08X}'.encode()
            assert field in output
    return {'case': case, 'exit': expected, 'memory_bytes': memory_bytes, 'samples': samples,
            'pci_writes':pci_writes,'fast_control_fixture':fast}


def main():
    folder = PORT/'build/diagnostics'
    folder.mkdir(parents=True, exist_ok=True)
    _, config = configuration('m919')
    (folder/'configuration.inc').write_text(definitions(config),encoding='utf-8')
    ide_bdf = (config['platform']['isa_pci_device'] << 3) | 1
    image, listing = folder/'VGAIO.COM', folder/'VGAIO.lst'
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    subprocess.run([nasm, '-w+error', '-f', 'bin', '-I', str(folder)+'/', '-l', str(listing), '-o', str(image),
                    str(PORT/'diagnostics/vga-io.asm')], check=True)
    raw = image.read_bytes()
    addresses = symbols(listing)
    cases = []
    selected = ('normal','ide-normal','ide-peer-bits','ide-no-bios','ide-wrong-id','ide-bus-master','ide-fifo',
                'ide-count-low','ide-count-high','ide-no-change','ide-read-error','ide-write-error',
                'ide-write-ignored','ide-restore-fails','ide-restore-read-error','ide-late-frozen',
                'ide-short-output','bad-argument')
    if '--ide-only' not in sys.argv:
        selected += ('mode2-wrap','protected','irq-off','no-rom','wrong-mode','wrong-pit','frozen','late-frozen','short-output')
    for case in selected:
        cases.append(check(raw, addresses, case, ide_bdf))
        print(case+' passed', flush=True)
    report = {'version':2, 'size': len(raw), 'sum32': f'{sum(raw):08X}', 'sha256': hashlib.sha256(raw).hexdigest(),
              'cases': cases, 'limit': 'Actual COM with synthetic PIT/VGA/DOS; no physical throughput or stability proof.'}
    target = PORT/'build/tests/pci-performance'
    target.mkdir(parents=True, exist_ok=True)
    (target/'vga-io.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps({k: v for k, v in report.items() if k != 'cases'}, indent=2))


if __name__ == '__main__':
    main()
