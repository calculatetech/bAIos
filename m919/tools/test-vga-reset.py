"""Execute real reset entries with retained VGA state and no usable BIOS video call."""
import argparse
import json
from pathlib import Path
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--baseline', type=Path)
    arguments = parser.parse_args()
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
