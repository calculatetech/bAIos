"""Execute WAKECHK with real INT1A/int70 firmware and external DOS/RTC/PIC seams."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import (Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN,
                     UC_HOOK_INTR, UC_HOOK_MEM_WRITE)
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.ram_proof import Listing, constants

DAY = 0x1800B0
PROGRAM = 0x10000


def bcd(value):
    return (value // 10 << 4) | value % 10


def check(raw, rom, symbols, status_offset, state_kib, nmi_policy, name, **options):
    board = options.get('board')
    u = board.u if board else Uc(UC_ARCH_X86, UC_MODE_16)
    if not board:
        u.mem_map(0, 0x200000)
        u.mem_write(0xE0000, rom)
    u.mem_write(PROGRAM + 0x100, raw)
    idle = options.get('idle', False)
    if idle:
        u.mem_write(PROGRAM+0x80, b'\x02 K\r' if options.get('keyboard') else b'\0\r')
    protected = options.get('protected', False)
    flags = 0x202 if options.get('interrupts', True) else 2
    for reg in ('CS', 'DS', 'ES', 'SS'):
        u.reg_write(getattr(x, 'UC_X86_REG_' + reg), PROGRAM >> 4)
    u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
    u.reg_write(x.UC_X86_REG_CR0, 0x11 if protected else 0x10)
    u.reg_write(x.UC_X86_REG_EFLAGS, flags | (0x23000 if protected else 0))
    ebda = options.get('ebda', 0x9E00)
    u.mem_write(0x40E, struct.pack('<H', ebda))
    u.mem_write(ebda * 16, bytes([options.get('size', state_kib)]))
    u.mem_write(ebda * 16 + status_offset, bytes([options.get('status', 1)]))
    if options.get('header') is False:
        u.mem_write(0xE0014, b'OTHERROM')
    prior_vector = struct.pack('<HH', 0x1234, 0x8765)
    u.mem_write(0x4A * 4, prior_vector)
    state_before = bytes(u.mem_read(ebda * 16, state_kib * 1024))
    rtc = bytearray(128)
    rtc[1], rtc[3], rtc[5] = options.get('alarms', (0xC7, 0xD5, 0xEF))
    rtc[0xA], rtc[0xB], rtc[0xD] = options.get('rtc_a', 0x26), options.get('rtc_b', 2), options.get('rtc_d', 0x80)
    rtc[0xC] = options.get('stale', 0)
    native_before = bytes(rtc[i] for i in (1, 3, 5, 0xA, 0xB))
    masks = [options.get('master', 0xB8), options.get('slave', 0xEF)]
    masks_before = masks[:]
    ticks = options.get('ticks', 12345)
    u.mem_write(0x46C, struct.pack('<I', ticks))
    start_time = options.get('time', 12 * 3600 + 34 * 60 + 56)
    elapsed_ticks = 0
    selection, pic_selector = nmi_policy | 0x0D, options.get('pic_selector', 0x0A)
    irr, isr = options.get('pending', 0), options.get('in_service', 0)
    master_irr, master_isr = (4 if irr else 0), (4 if isr else 0)
    steps, action, exited = 0, None, False
    calls, events, writes, output = [], [], [], []
    arm_time, alarm_values, callback_count = None, None, 0
    cancelling, drained_pending, other_sent = False, False, False
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    decoded = {}
    control_before = tuple(u.reg_read(reg) for reg in (x.UC_X86_REG_CR0, x.UC_X86_REG_CR3))

    def clock_fields():
        now = (start_time + elapsed_ticks // 18) % 86400
        hour, remainder = divmod(now, 3600)
        minute, second = divmod(remainder, 60)
        if not rtc[0xB] & 2:
            hour = (hour % 12 or 12) | (0x80 if hour >= 12 else 0)
            hour = hour if rtc[0xB] & 4 else bcd(hour & 0x7F) | (hour & 0x80)
        elif not rtc[0xB] & 4:
            hour = bcd(hour)
        if not rtc[0xB] & 4:
            minute, second = bcd(minute), bcd(second)
        return second, minute, hour

    def dispatch(segment, offset):
        saved = [u.reg_read(x.UC_X86_REG_EFLAGS), u.reg_read(x.UC_X86_REG_CS), u.reg_read(x.UC_X86_REG_IP)]
        sp, ss = u.reg_read(x.UC_X86_REG_SP), u.reg_read(x.UC_X86_REG_SS)
        for value in saved:
            sp = (sp - 2) & 0xFFFF
            u.mem_write((ss << 4) + sp, struct.pack('<H', value & 0xFFFF))
        u.reg_write(x.UC_X86_REG_SP, sp)
        u.reg_write(x.UC_X86_REG_EFLAGS, saved[0] & ~0x300)
        u.reg_write(x.UC_X86_REG_CS, segment)
        u.reg_write(x.UC_X86_REG_IP, offset)

    def inp(cpu, port, size, _):
        nonlocal selection, rtc
        assert size == 1 and port in (0x20,0x21, 0xA1, 0xA0, 0x71, 0x84), ('unexpected input', hex(port), size)
        if port==0x20:
            return master_isr if pic_selector==0x0B else master_irr
        if port == 0x21:
            return masks[0]
        if port == 0xA1:
            return masks[1]
        if port == 0xA0:
            return isr if pic_selector == 0x0B else irr
        if port == 0x84:
            return 0
        index = selection & 0x7F
        if index == 0 and options.get('bad_time'):
            return 0x7A
        if index in (0, 2, 4):
            return clock_fields()[index // 2]
        if index == 0xC:
            value = rtc[index]
            rtc[index] = 0
            events.append(('read-C', value, cancelling))
            return value
        if index == 0xA and options.get('arm_reject') and calls and calls[-1] == 6:
            return rtc[index] | 0x80
        return rtc[index]

    def out(cpu, port, size, value, _):
        nonlocal selection, pic_selector, isr, master_isr, arm_time, alarm_values
        assert size == 1 and port in (0x21, 0xA1, 0xA0, 0x20, 0x70, 0x71), ('unexpected output', hex(port), size, value)
        writes.append((port, value))
        if port == 0x70:
            selection = value
        elif port == 0x71:
            index = selection & 0x7F
            assert index in (1, 3, 5, 0xB), ('RTC mutation outside alarm', index, value)
            old = rtc[index]
            rtc[index] = value
            if index == 0xB and value & 0x20 and not old & 0x20:
                arm_time = elapsed_ticks
                alarm_values = tuple(rtc[i] for i in (1, 3, 5))
                events.append(('arm', alarm_values))
                if options.get('expire_after_arm'):
                    clock_latch()
        elif port in (0x21, 0xA1):
            masks[port == 0xA1] = value
        elif port in (0x20,0xA0) and value in (0x0A,0x0B):
            pic_selector=value
        elif port == 0xA0:
            if value in (0x0A, 0x0B):
                pic_selector = value
            else:
                assert value == 0x60
                isr &= ~1
                events.append(('slave-EOI', cancelling))
        else:
            assert port == 0x20 and value == 0x62
            master_isr &= ~4
            events.append(('master-EOI', cancelling))

    def intr(cpu, number, _):
        nonlocal action, exited, cancelling, irr, master_irr, callback_count
        if number == 0x15 and idle:
            action = ('bios', symbols['int15'])
            cpu.emu_stop()
        elif number == 0x16 and idle:
            assert cpu.reg_read(x.UC_X86_REG_AH) == 1
            cpu.reg_write(x.UC_X86_REG_EFLAGS,cpu.reg_read(x.UC_X86_REG_EFLAGS)|0x40)
        elif number == 0x1A:
            command = cpu.reg_read(x.UC_X86_REG_AH)
            assert command in (2, 6, 7)
            calls.append(command)
            if command == 7:
                cancelling = True
                if options.get('pending_cancel'):
                    irr |= 1
                    master_irr |= 4
                    rtc[0xC] = 0xA0
            action = ('bios', symbols['RTC_INTERRUPT_LABEL'])
            cpu.emu_stop()
        elif number == 0x4A:
            callback_count += 1
            offset, segment = struct.unpack('<HH', bytes(cpu.mem_read(0x4A * 4, 4)))
            assert segment == PROGRAM >> 4
            action = ('callback', (segment, offset))
            cpu.emu_stop()
        else:
            assert number == 0x21
            ah = cpu.reg_read(x.UC_X86_REG_AH)
            if ah == 0x35:
                assert cpu.reg_read(x.UC_X86_REG_AL) == 0x4A
                offset, segment = struct.unpack('<HH', bytes(cpu.mem_read(0x4A * 4, 4)))
                cpu.reg_write(x.UC_X86_REG_BX, offset)
                cpu.reg_write(x.UC_X86_REG_ES, segment)
            elif ah == 0x25:
                assert cpu.reg_read(x.UC_X86_REG_AL) == 0x4A
                cpu.mem_write(0x4A * 4, struct.pack('<HH', cpu.reg_read(x.UC_X86_REG_DX), cpu.reg_read(x.UC_X86_REG_DS)))
                events.append(('vector', bytes(cpu.mem_read(0x4A * 4, 4)).hex()))
            elif ah == 9:
                address = cpu.reg_read(x.UC_X86_REG_DS) * 16 + cpu.reg_read(x.UC_X86_REG_DX)
                output.append(bytes(cpu.mem_read(address, 64 if idle else 8)).split(b'$')[0].decode())
            else:
                assert ah == 0x4C
                assert bool(cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200) == bool(flags & 0x200)
                exited = True
                cpu.emu_stop()

    def step(cpu, address, size, _):
        nonlocal steps, elapsed_ticks, irr, isr, master_irr, master_isr, action, other_sent, drained_pending
        if address not in decoded:
            decoded[address] = next(decoder.disasm(bytes(cpu.mem_read(address, size)), address))
        ins = decoded[address]
        if not board:
            assert ins.mnemonic not in ('invd', 'wbinvd', 'wrmsr', 'clts', 'lmsw', 'rsm', 'hlt'), ins.mnemonic
            assert not (ins.mnemonic == 'mov' and ins.op_str.startswith('cr')), ins.op_str
        steps += 1
        if steps % 160 == 0:
            elapsed_ticks += 1
            if not idle or not masks[0] & 1:
                cpu.mem_write(0x46C, struct.pack('<I', (ticks + elapsed_ticks) % DAY))
            if arm_time is not None and not cancelling:
                if options.get('cause') and not other_sent:
                    rtc[0xC] = options['cause']
                    irr |= 1
                    master_irr |= 4
                    other_sent = True
                if not options.get('no_alarm') and elapsed_ticks % 18 == 0 and clock_fields() == alarm_values:
                    rtc[0xC] = 0xA0
                    irr |= 1
                    master_irr |= 4
        if irr & 1 and not masks[1] & 1 and not masks[0] & 4 and cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200 and not (idle and board.action=='irq'):
            if options.get('stuck_drain') and cancelling:
                return
            irr &= ~1
            isr |= 1
            master_irr &= ~4
            master_isr |= 4
            events.append(('IRQ8', cancelling))
            drained_pending |= cancelling
            action = ('bios', symbols['int70'])
            cpu.emu_stop()

    def memory(cpu, access, address, size, value, _):
        if board and board.smm:
            return
        if idle and ebda*16+0x27A <= address and address+size <= ebda*16+0x27D:
            return
        if idle and address == ebda*16+status_offset+5 and size == 1:
            return
        assert PROGRAM <= address and address + size <= PROGRAM + 0x10000, ('write outside DOS process', hex(address))

    if board:
        board.rtc_in, board.rtc_out = inp, out
        def clock_latch():
            nonlocal irr, master_irr, elapsed_ticks
            assert arm_time is not None and rtc[0xB] & 0x20
            elapsed_ticks = 36
            rtc[0xC] = 0xA0
            irr |= 1
            master_irr |= 4
        board.clock_latch = clock_latch
    else:
        u.hook_add(UC_HOOK_INSN, inp, None, 1, 0, x.UC_X86_INS_IN)
        u.hook_add(UC_HOOK_INSN, out, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_INTR, intr)
    u.hook_add(UC_HOOK_CODE, step)
    u.hook_add(UC_HOOK_MEM_WRITE, memory)
    address = PROGRAM + 0x100
    for _ in range(40):
        action = None
        u.emu_start(address, 0x200000, count=2_000_000)
        if exited:
            break
        if idle and board.action == 'irq':
            board.wake_pending=False
            board.wakes+=1
            if options.get('keyboard'):
                if options.get('key_missing'):
                    pass       # Watchdog IRQ8 was already latched inside the request.
                else:
                    u.mem_write(0x41C,b'\x22\0')
            u.reg_write(x.UC_X86_REG_IP,u.reg_read(x.UC_X86_REG_IP)+1)
            board.action=None
            address=u.reg_read(x.UC_X86_REG_CS)*16+u.reg_read(x.UC_X86_REG_IP)
            continue
        if board and board.action in ('enter', 'resume'):
            if board.action == 'enter':
                board.enter()
            else:
                board.resume()
            board.action = None
            address = u.reg_read(x.UC_X86_REG_CS) * 16 + u.reg_read(x.UC_X86_REG_IP)
            continue
        assert action is not None, ('execution budget', name, hex(u.reg_read(x.UC_X86_REG_IP)))
        if action[0] == 'bios':
            dispatch(0xF000, action[1])
        else:
            dispatch(*action[1])
        address = u.reg_read(x.UC_X86_REG_CS) * 16 + u.reg_read(x.UC_X86_REG_IP)
    assert exited, name
    expected = options.get('expected', 'W0')
    if idle and options.get('keyboard'):
        assert output.pop(0)=='Press a key within two seconds.\r\n'
    assert output == [expected + '\r\n'], (name, output, expected, calls, events[-12:])
    assert tuple(rtc[i] for i in (1, 3, 5, 0xA, 0xB)) == tuple(native_before), (name, list(rtc), list(native_before))
    assert masks == masks_before, (name, masks, masks_before)
    assert tuple(u.reg_read(reg) for reg in (x.UC_X86_REG_CR0, x.UC_X86_REG_CR3)) == control_before
    assert bytes(u.mem_read(0x4A * 4, 4)) == prior_vector
    state_after=bytearray(u.mem_read(ebda * 16, state_kib * 1024))
    if idle:
        state_after[status_offset+5]=state_before[status_offset+5]
    assert bytes(state_after) == state_before
    if expected[1:] not in ('X', '1') and options.get('interrupts', True):
        assert selection == nmi_policy | 0x0D, (name, selection)
    if expected[1:] in ('X', '1', '2') and arm_time is None:
        assert not calls and not any(p == 0x71 for p, _ in writes)
        assert not any(e[0] == 'vector' for e in events)
    if name in ('bad-divider', 'no-power', 'invalid-time'):
        assert calls == ([2] if name == 'invalid-time' else [])
        assert not any(p == 0x71 for p, _ in writes)
        assert not any(e[0] == 'vector' for e in events)
    if expected[1:] in ('0', '6'):
        assert calls == [2, 6, 7] and callback_count == (int(options.get('key_missing',False)) if idle else 1)
        wanted = (start_time + 2) % 86400
        hour, rem = divmod(wanted, 3600)
        minute, second = divmod(rem, 60)
        if not native_before[-1] & 2:
            hour = (hour % 12 or 12) | (0x80 if hour >= 12 else 0)
            hour = hour if native_before[-1] & 4 else bcd(hour & 127) | (hour & 128)
        elif not native_before[-1] & 4:
            hour = bcd(hour)
        if not native_before[-1] & 4:
            second, minute = bcd(second), bcd(minute)
        assert alarm_values == (second, minute, hour), (name, alarm_values, (second, minute, hour))
    if options.get('stale'):
        assert events.index(('read-C', options['stale'], False)) < next(i for i, event in enumerate(events) if event[0] == 'arm')
    if arm_time is not None and expected[1:] != '5':
        assert irr == isr == master_irr == master_isr == 0
        assert pic_selector == 0x0A
    if options.get('pending_cancel') and expected[1:] != '5':
        assert drained_pending
        assert ('read-C', 0xA0, True) in events
        assert ('slave-EOI', True) in events and ('master-EOI', True) in events
    boundaries = ['B15', 'B18']
    if arm_time is not None:
        boundaries.append('B16')
    if 7 in calls:
        boundaries.append('B17')
    return dict(name=name, output=expected, boundaries=boundaries, calls=calls,
                events=events, callback_count=callback_count, elapsed_ticks=elapsed_ticks,
                configuration_restored=True, pending_irq8=irr, in_service_irq8=isr,
                master_pending=master_irr, master_in_service=master_isr, steps=steps)


def main():
    rom_path = PORT / 'build/baios-m919.bin'
    rom = rom_path.read_bytes()
    before = hashlib.sha256(rom).hexdigest()
    config = json.loads((PORT / 'port.json').read_text())['platform']
    status = constants(PORT / 'src/hardware/board-definition.inc')['HW_SMM_STATUS']
    listing = Listing(rom_path.with_suffix('.lst'))
    symbols = {key: listing.symbol(key) for key in ('RTC_INTERRUPT_LABEL', 'int70')}
    output = PORT / 'build/tests/wake-check'
    output.mkdir(parents=True, exist_ok=True)
    image = PORT / 'build/diagnostics/WAKECHK.COM'
    image.parent.mkdir(parents=True, exist_ok=True)
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    subprocess.run([nasm, '-w+error', '-f', 'bin', f'-DSMM_STATUS={status}',
                    f'-DSTATE_KIB={config["state_kib"]}', f'-DNMI_POLICY={config["rtc_nmi_mask"]}',
                    '-l', str(output / 'wake-check.lst'), '-o', str(image),
                    str(PORT / 'diagnostics/wake-check.asm')], check=True)
    cases = [('scheduled', {}), ('stale-alarm', {'stale': 0xA0}),
             ('binary-24', {'rtc_b': 6}), ('BCD-12-PM', {'rtc_b': 0}),
             ('binary-12', {'rtc_b': 4}), ('minute-rollover', {'time': 12*3600+59}),
             ('midnight', {'time': 86399}), ('deadline-wrap', {'ticks': DAY-10, 'no_alarm': True, 'expected': 'W4'}),
             ('periodic-only', {'cause': 0xC0, 'no_alarm': True, 'expected': 'W4'}),
             ('update-only', {'cause': 0x90, 'no_alarm': True, 'expected': 'W4'}),
             ('no-alarm', {'no_alarm': True, 'expected': 'W4'}),
             ('pending-cancel', {'pending_cancel': True}),
             ('stuck-drain', {'pending_cancel': True, 'stuck_drain': True, 'expected': 'W5'}),
             ('arm-rejected', {'arm_reject': True, 'expected': 'W3'}),
             ('protected', {'protected': True, 'expected': 'WX'}),
             ('IF-clear', {'interrupts': False, 'expected': 'W2'}),
             ('bad-header', {'header': False, 'expected': 'W1'}),
             ('low-EBDA', {'ebda': 0x7F00, 'expected': 'W1'}),
             ('high-EBDA', {'ebda': 0x9F00, 'expected': 'W1'}),
             ('wrong-size', {'size': 1, 'expected': 'W1'}),
             ('IRQ0-masked', {'master': 0xB9, 'expected': 'W2'}),
             ('bad-divider', {'rtc_a': 0x36, 'expected': 'W3'}),
             ('no-power', {'rtc_d': 0, 'expected': 'W3'}),
             ('invalid-time', {'bad_time': True, 'expected': 'W3'}),
             ('initial-IRQ8-request', {'pending': 1, 'expected': 'W2'}),
             ('initial-IRQ8-in-service', {'in_service': 1, 'expected': 'W2'}),
             ('both-IRQs-masked', {'master': 0xFC, 'slave': 0xFF, 'alarms': (0x13, 0x45, 0x21)})]
    cases += [(f'SMM-stage-{value}', {'status': value, 'expected': 'W1'}) for value in (0, 2, 3, 4)]
    cases += [(f'RTC-busy-{bit:02X}', {'rtc_b': 2 | bit, 'expected': 'W2'}) for bit in (0x10, 0x20, 0x40, 0x80)]
    rows = [check(image.read_bytes(), rom, symbols, status, config['state_kib'], config['rtc_nmi_mask'], name, **opts)
            for name, opts in cases]
    assert rom_path.read_bytes() == rom
    result = dict(cases=rows, image=dict(path='m919/build/diagnostics/WAKECHK.COM', size=image.stat().st_size,
                                       SUM32=f'{sum(image.read_bytes()):08X}'),
                  firmware=dict(sha256=before, SUM32=f'{sum(rom):08X}', unchanged=True),
                  physical_validation=False, electrical_StopGrant_validation=False)
    (output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(f'WAKECHK: {len(rows)} composed diagnostic/RTC/restoration cases PASS')
    print(f'{image.name}: {image.stat().st_size} bytes SUM32 {sum(image.read_bytes()):08X}; ROM unchanged')


if __name__ == '__main__':
    main()
