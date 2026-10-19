"""Real POST keyboard/error owners with an external KBC and no keyboard peer.

This is a deterministic device seam, not an 86Box detached-keyboard claim.
The existing POST owners run in their normal order. Only the controller, PIT,
RTC and external VGA provider are modeled; no absence/error flag is injected.
"""
import re
import struct
from pathlib import Path


def check(port, build, nvram):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_CODE
    from unicorn import x86_const as x
    image = build(port, 'build/full-core/keyboard-absent')
    raw = Path(image['path']).read_bytes()
    lines = Path(image['path']).with_suffix('.lst').read_text().splitlines()

    def symbol(name):
        row = next(i for i, s in enumerate(lines) if re.search(r'(?<![\w.])' + name + r':\s*$', s))
        return next(int(m[1], 16) for s in lines[row + 1:]
                    if (m := re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]', s)))

    def call_site(name):
        row = next(s for s in lines if re.search(r'\bcall\s+' + name + r'\s*$', s))
        return int(re.match(r'\s*\d+\s+([0-9A-F]{8})', row)[1], 16)
    start = call_site('init_keyboard')
    successor = call_site('post_keyboard_presence') + 3

    results = []
    for halt, title in ((0, 'All Errors'), (1, 'No Errors'), (2, 'All Except Keyboard')):
        cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        cpu.mem_map(0, 2 * 1024 * 1024)
        cpu.mem_write(0xF0000, raw[65536:])
        cpu.mem_write(0x40E, struct.pack('<H', 0x9E00))
        cpu.mem_write(0x41A, struct.pack('<HH', 0x1E, 0x1E))
        cpu.mem_write(0x480, struct.pack('<HH', 0x1E, 0x3E))
        cmos = nvram()
        cmos[0x3B] = (cmos[0x3B] & ~0x18) | (halt << 3)
        cmos[0x3D] = (-sum(cmos[0x38:0x3D]) - cmos[0x10] - cmos[0x3E]) & 255
        queue, controller_commands, device_commands, text, notes, speaker = [], [], [], [], [], []
        command_byte, target, rtc_index, counter, latch, phase = 0x5C, None, 0, 0xFFFF, 0xFFFF, 0
        gate, note_low, speaker_on, ticks, waiting = 0, None, False, 0, False
        visited = []
        sequence = ('init_keyboard', 'arm_keyboard_runtime', 'board_a20_handoff',
                    'post_ui_begin', 'settings_load', 'post_numlock_apply', 'post_keyboard_presence')
        entries = {0xF0000 + symbol(name): name for name in sequence}

        def incoming(uc, address, size, context):
            nonlocal phase
            if address == 0x64:
                return int(bool(queue))
            if address == 0x60:
                return queue.pop(0) if queue else 0
            if address == 0x40:
                result = (latch >> (8 * phase)) & 255
                phase ^= 1
                return result
            if address == 0x71:
                return cmos[rtc_index]
            if address == 0x61:
                return gate
            if address in (0x21, 0xA1):
                return 0xFC if address == 0x21 else 0xFF
            return 0

        def outgoing(uc, address, size, value, context):
            nonlocal command_byte, target, rtc_index, counter, latch, phase, gate, note_low, speaker_on
            if address == 0x64:
                controller_commands.append(value)
                if value == 0xAA:
                    queue.append(0x55)
                elif value == 0x20:
                    queue.append(command_byte)
                elif value in (0x60, 0xD1):
                    target = value
                elif value == 0xAD:
                    command_byte |= 0x10
                elif value == 0xAE:
                    command_byte &= ~0x10
            elif address == 0x60:
                if target == 0x60:
                    command_byte = value
                elif target is None:
                    device_commands.append(value)  # No physical keyboard: no ACK/BAT.
                target = None
            elif address == 0x43 and value == 0:
                counter = (counter - 3000) & 65535
                latch, phase = counter, 0
            elif address == 0x42:
                if note_low is None:
                    note_low = value
                else:
                    notes.append(note_low | value << 8)
                    note_low = None
            elif address == 0x61:
                gate = value
                speaker_on = bool(value & 3)
                speaker.append(value & 3)
            elif address == 0x70:
                rtc_index = value & 127
            elif address == 0x71:
                cmos[rtc_index] = value

        def dispatch(uc, number, next_ip=None):
            sp = uc.reg_read(x.UC_X86_REG_SP)
            for value in (uc.reg_read(x.UC_X86_REG_EFLAGS), uc.reg_read(x.UC_X86_REG_CS),
                          uc.reg_read(x.UC_X86_REG_IP) if next_ip is None else next_ip):
                sp -= 2
                uc.mem_write(sp, struct.pack('<H', value & 65535))
            ip, cs = struct.unpack('<HH', uc.mem_read(number * 4, 4))
            uc.reg_write(x.UC_X86_REG_SP, sp)
            uc.reg_write(x.UC_X86_REG_EFLAGS, uc.reg_read(x.UC_X86_REG_EFLAGS) & ~0x300)
            uc.reg_write(x.UC_X86_REG_CS, cs)
            uc.reg_write(x.UC_X86_REG_IP, ip)

        def interrupt(uc, number, context):
            if number == 0x10:
                ax = uc.reg_read(x.UC_X86_REG_AX)
                if ax >> 8 == 0x0E:
                    text.append(chr(ax & 255))
                else:
                    assert ax in (0x1202, 3, 0x1114, 0x1003, 0x500) or ax >> 8 == 2, hex(ax)
            else:
                assert number in (9, 0x15, 0x16, 0x1C), number
                dispatch(uc, number)

        def instruction(uc, address, size, context):
            nonlocal ticks, waiting
            if address in entries:
                visited.append(entries[address])
            if bytes(uc.mem_read(address, 1)) != b'\xF4':
                return
            assert uc.reg_read(x.UC_X86_REG_EFLAGS) & 0x200, 'Uninterruptible halt'
            if not speaker_on:
                assert symbol('post_notice_wait') <= address - 0xF0000 < symbol('setup_post_gate')
                waiting = True
                uc.emu_stop()
            else:
                ticks += 1
                dispatch(uc, 8, (uc.reg_read(x.UC_X86_REG_IP) + 1) & 65535)

        for vector, name in ((8, 'int08'), (9, 'int09'), (0x15, 'int15'), (0x16, 'int16'), (0x1C, 'default_iret')):
            cpu.mem_write(vector * 4, struct.pack('<HH', symbol(name), 0xF000))
        cpu.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
        cpu.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
        cpu.hook_add(UC_HOOK_INTR, interrupt)
        cpu.hook_add(UC_HOOK_CODE, instruction)

        # Enter the assembled startup CALL, then follow its unchanged continuation.
        # RAM/PIC/VGA initialization precedes this boundary and is covered natively.
        for register, value in ((x.UC_X86_REG_CS, 0xF000), (x.UC_X86_REG_FS, 0x9E00),
                                (x.UC_X86_REG_DS, 0), (x.UC_X86_REG_ES, 0), (x.UC_X86_REG_SS, 0),
                                (x.UC_X86_REG_SP, 0x7000), (x.UC_X86_REG_EFLAGS, 0x202)):
            cpu.reg_write(register, value)
        cpu.emu_start(0xF0000 + start, 0xF0000 + successor, count=3000000)
        assert cpu.reg_read(x.UC_X86_REG_IP) == successor or waiting
        assert visited == list(sequence), visited
        base = 0x9E000
        assert cpu.mem_read(0x49F, 1) == b'\x01', 'Production keyboard reset did not mark absence'
        assert cpu.mem_read(base + 0x174, 1) == b'\x01', 'Actual CMOS load failed'
        assert cpu.mem_read(base + 0x17F, 1) == bytes((halt,))
        assert cpu.mem_read(base + 0x175, 1) == b'\x08', 'Presence owner did not publish keyboard error'
        assert 0xFF in device_commands and 0xAA in controller_commands
        output = ''.join(text)
        assert 'Keyboard not detected.' in output, output
        if halt == 0:
            assert waiting and notes == [2712, 3419, 4571] and ticks == 7, (notes, ticks, waiting)
            assert speaker[-1] == 0 and 'Press any key to continue or Delete for Setup.' in output
        else:
            assert not waiting and not notes and 'Press any key' not in output
        results.append({'name': title, 'rom_sha256': image['sha256'], 'production_sequence': visited,
                        'entry': f'assembled startup CALL at F000:{start:04X}',
                        'returned_successor': f'F000:{successor:04X}' if not waiting else None,
                        'keyboard_absent': 1, 'POST_error': 8, 'CMOS_halt_policy': halt,
                        'warning': output, 'beep_divisors': notes, 'IRQ0_beep_ticks': ticks,
                        'terminal': 'real notice wait, empty keyboard queue' if waiting else 'policy permits return',
                        'device_seam': 'KBC self-test replies; keyboard peer never replies; real timer IRQ/VGA provider'})
    print('Absent keyboard: real init/presence/CMOS policy; HaltAll beep/wait versus exemptions: PASS', flush=True)
    return results
