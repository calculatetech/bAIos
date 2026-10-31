"""Execute real reset entries with retained VGA state and no usable BIOS video call."""
import argparse
import json
from pathlib import Path
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR
from unicorn import x86_const as x

REPOSITORY = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY))
from shared.tools.ram_proof import Listing


def check(image, entry, selected, clock, resume=0):
    listing = Listing(image.with_suffix('.lst'))
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x200000)
    u.mem_write(0xE0000, image.read_bytes())
    # Glyphs and text survive a warm CPU reset. Neither is this fix's owner.
    video = bytes(range(256)) * 512
    u.mem_write(0xA0000, video)
    u.mem_write(0x467, bytes.fromhex('00050000'))
    seq = {1: clock, selected: 0xA5} if selected != 1 else {1: clock}
    initial = dict(seq)
    index = selected
    rtc = 0
    writes = []
    terminal = []

    def incoming(cpu, port, size, user):
        if port == 0x3C4:
            return index
        if port == 0x3C5:
            return seq.get(index, 0)
        if port == 0x64:
            return 4 if resume else 0
        if port == 0x71:
            return resume if rtc & 127 == 15 else 0
        if port == 0x92:
            return 0x80  # Fast A20 begins closed, unrelated bits must survive.
        return 0

    def outgoing(cpu, port, size, value, user):
        nonlocal index, rtc
        writes.append((port, size, value))
        if port == 0x3C4:
            index = value
        elif port == 0x3C5:
            seq[index] = value
        elif port == 0x70:
            rtc = value
        elif port == 0x64 and value == 0xFE:
            assert seq[1] == clock | 0x20, 'Reset reached with retained display active'
            terminal.append('reset')
            cpu.emu_stop()

    boundary = 0xF0000 + listing.symbol('chipset_initialize')

    def observe(cpu, address, size, user):
        if address == boundary:
            assert seq[1] == clock | 0x20, 'Chipset teardown reached with display active'
            assert cpu.reg_read(x.UC_X86_REG_ESP) == 0x04F0, 'Early blank damaged saved CPU identity'
            terminal.append('chipset')
            cpu.emu_stop()
        elif address == 0x500:
            terminal.append('resume')
            cpu.emu_stop()

    u.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_CODE, observe)
    for reg, value in ((x.UC_X86_REG_CS, 0xF000), (x.UC_X86_REG_SS, 0),
                       (x.UC_X86_REG_SP, 0x7000), (x.UC_X86_REG_EDX, 0x04F0),
                       (x.UC_X86_REG_CR0, 0x10), (x.UC_X86_REG_EFLAGS, 0x247)):
        u.reg_write(reg, value)
    u.emu_start(0xF0000 + listing.symbol(entry), 0x100000, count=10000)
    expected = 'resume' if resume else 'chipset' if entry == 'startup' else 'reset'
    assert terminal == [expected], (entry, terminal)
    assert index == selected, 'Sequencer selector changed'
    assert seq == initial if resume else seq == {**initial, 1: clock | 0x20}
    assert bytes(u.mem_read(0xA0000, len(video))) == video, 'Text/font memory changed'
    assert not u.reg_read(x.UC_X86_REG_EFLAGS) & 0x200, 'Reset must keep interrupts masked'
    if resume:
        assert ((0x20,1,0x20) in writes)==(resume==5), 'Wrong service-resume EOI branch'
    if entry == 'warm_reset':
        assert bytes(u.mem_read(0x472, 2)) == b'\x34\x12'
        assert (0x92, 1, 0x82) in writes, 'Reset lost fast-A20 restoration'
    return dict(entry=entry, selector=selected, clock=clock, service_resume=resume,
                terminal=expected, video_bytes_unchanged=True)


def warm_mode(image, virtual=False, shutdown=0, busy_after=None):
    """Run the actual entry with CR0.PE/VM, not a substituted SMSW result."""
    listing = Listing(image.with_suffix('.lst'))
    halt_address = 0xF0000 + listing.symbol('keyboard_halt')
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x200000)
    u.mem_write(0xE0000, image.read_bytes())
    rtc_index, rtc_value = 0, shutdown
    kbc, writes, privileged, terminal = [], [], [], []
    seq_index, seq_value = 0x15, 1
    timer, timer_high, latched_timer = 0xFFFF, False, 0xFFFF
    status_reads = 0

    def incoming(cpu, port, size, user):
        nonlocal timer_high, status_reads
        if port == 0x3C4: return seq_index
        if port == 0x3C5: return seq_value
        if port == 0x71: return rtc_value if rtc_index & 127 == 15 else 0
        if port == 0x92: return 0x80
        if port == 0x64:
            status_reads += 1
            return 2 if busy_after is not None and len(kbc) >= busy_after else 0
        if port == 0x40:
            value = latched_timer >> 8 if timer_high else latched_timer & 255
            timer_high = not timer_high
            return value
        return 0

    def outgoing(cpu, port, size, value, user):
        nonlocal rtc_index, rtc_value, seq_index, seq_value, timer, timer_high, latched_timer
        writes.append((port, size, value))
        if port == 0x43 and value == 0:
            latched_timer = timer
            timer = (timer - 0x1000) & 0xFFFF
            timer_high = False
        if port == 0x3C4: seq_index = value
        if port == 0x3C5: seq_value = value
        if port == 0x70: rtc_index = value
        if port == 0x71 and rtc_index & 127 == 15: rtc_value = value
        if port in (0x60, 0x64): kbc.append((port, value))
        if port == 0x64 and value == 0xFE:
            terminal.append('reset')
            cpu.emu_stop()

    def observe(cpu, address, size, user):
        opcode = bytes(cpu.mem_read(address, min(size, 4)))
        if opcode.startswith((b'\x0f\x09', b'\x0f\x08', b'\x0f\x20', b'\x0f\x22')):
            privileged.append(opcode.hex())
            # Intel specifies #GP for WBINVD in V86. Unicorn is not the oracle
            # for that exception; reject the instruction before it executes.
            assert not virtual, 'Protected/V86 reset reached a privileged cache/CR instruction'
        if address == halt_address:
            assert cpu.reg_read(x.UC_X86_REG_AL) == 0xEE
            terminal.append('failed')
            cpu.emu_stop()

    def exception(cpu, vector, user):
        raise AssertionError(('CPU exception before reset', vector, hex(cpu.reg_read(x.UC_X86_REG_IP))))

    u.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_CODE, observe)
    u.hook_add(UC_HOOK_INTR, exception)
    for reg, value in ((x.UC_X86_REG_CS, 0xF000), (x.UC_X86_REG_SS, 0),
                       (x.UC_X86_REG_SP, 0x7000), (x.UC_X86_REG_DS, 0),
                       (x.UC_X86_REG_CR0, 0x11 if virtual else 0x10),
                       (x.UC_X86_REG_EFLAGS, 0x23202 if virtual else 0x202)):
        u.reg_write(reg, value)
    assert bool(u.reg_read(x.UC_X86_REG_CR0) & 1) == virtual
    assert bool(u.reg_read(x.UC_X86_REG_EFLAGS) & 0x20000) == virtual
    u.emu_start(0xF0000 + listing.symbol('warm_reset'), 0x100000, timeout=3000000, count=300000)
    assert terminal == ['reset' if busy_after is None else 'failed'], (terminal, hex(u.reg_read(x.UC_X86_REG_IP)), status_reads, kbc, writes[-12:])
    assert bytes(u.mem_read(0x472, 2)) == b'\x34\x12'
    assert rtc_value == 0, ('Deliberate reboot retained shutdown service', rtc_value)
    assert (0x70, 1, 0x8F) in writes and (0x71, 1, 0) in writes
    assert not u.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
    assert u.reg_read(x.UC_X86_REG_CR0) == (0x11 if virtual else 0x10)
    assert seq_index == 0x15 and seq_value == 0x21
    expected = [(0x64, 0xD1), (0x60, 0xDF), (0x64, 0xFE)] if virtual else [(0x64, 0xFE)]
    assert kbc == (expected if busy_after is None else expected[:busy_after]), kbc
    if busy_after is not None:
        assert status_reads == busy_after + 100, status_reads
    assert not any(port == 0x64 and value in (0xA8, 0xA9, 0xD3, 0xD4) for port, value in kbc)
    if virtual:
        assert privileged == []
        assert not any(port == 0x92 for port, _, _ in writes)
    else:
        assert privileged == ['0f09']
        assert (0x92, 1, 0x82) in writes
    print('warm reset', 'V86' if virtual else 'real', shutdown, busy_after, 'PASS', flush=True)
    # The clear precedes the output-port transaction and final reset pulse.
    first_kbc = next((i for i, row in enumerate(writes) if row[0] in (0x60, 0x64)), len(writes))
    assert writes.index((0x71, 1, 0)) < first_kbc
    return dict(mode='V86' if virtual else 'real', shutdown=shutdown, busy_after=busy_after,
                terminal=terminal[0], privileged=privileged, kbc=kbc, cr0_unchanged=True,
                no_aux=True, shutdown_cleared=True, status_reads=status_reads,
                delay_seam=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--warm-mode', action='store_true')
    parser.add_argument('--baseline-mode', type=Path)
    parser.add_argument('--warm-timeouts-only', action='store_true')
    arguments = parser.parse_args()
    if arguments.warm_mode:
        if arguments.baseline_mode:
            try:
                warm_mode(arguments.baseline_mode, virtual=True)
            except AssertionError as error:
                assert str(error) == 'Protected/V86 reset reached a privileged cache/CR instruction', error
            else:
                raise AssertionError('Baseline did not reach the claimed privileged instruction seam')
        rows = [] if arguments.warm_timeouts_only else [warm_mode(arguments.image, virtual, shutdown)
                for virtual in (False, True) for shutdown in (0, 5, 0x0A)]
        rows += [warm_mode(arguments.image, True, 5, busy_after) for busy_after in (0, 1, 2)]
        rows += [warm_mode(arguments.image, False, 0x0A, 0)]
        output = arguments.image.parent.parent / 'warm-mode.json'
        output.write_text(json.dumps({'baseline_reproduced':bool(arguments.baseline_mode),
                                    'cases':rows, 'limits':'Direct V86 with IOPL3; explicit privileged-op oracle. No loaded EMM386 claim.'}, indent=2) + '\n')
        print(f'PASS {len(rows)} real/V86 reset/timeout cases; {output}', flush=True)
        return
    if arguments.baseline:
        try:
            check(arguments.baseline, 'startup', 0x15, 1)
        except AssertionError as error:
            assert str(error) == 'Chipset teardown reached with display active', error
            print('Baseline reproduces missing blank before chipset teardown', flush=True)
        else:
            raise AssertionError('Baseline did not reproduce the missing reset blank')
    rows = [check(arguments.image, entry, selector, clock)
            for entry in ('startup', 'warm_reset', 'controlled_defaults_restart')
            for selector in (0, 1, 0x15)
            for clock in (0, 1, 0x29, 0xDF)]
    rows.extend(check(arguments.image, 'startup', 0x15, 1, resume=code) for code in (5,0x0A))
    output = arguments.image.parent.parent / 'reset.json'
    output.write_text(json.dumps(rows, indent=2) + '\n')
    print(f'PASS {len(rows)} reset/clock/index/service-resume cases; {output}', flush=True)


if __name__ == '__main__':
    main()
