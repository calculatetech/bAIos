"""Drive the production setup/IRQ1/RTC path; optionally retain real VGA in 86Box."""
import argparse
import datetime
import importlib
import os
import shutil
import struct
import tempfile
import re
import zlib
from pathlib import Path

from unicorn import UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

rtc = importlib.import_module('test-rtc')
legacy = importlib.import_module('test-legacy-disk')
ROOT = rtc.ROOT
EBDA = 0x9FC00
SCANS = {'0': 0x0B, '1': 2, '2': 3, '3': 4, '4': 5, '5': 6, '6': 7,
         '7': 8, '8': 9, '9': 10, '\t': 15, '\r': 28, '\x1b': 1,
         'a': 0x1E, 'p': 0x19, 'y': 21, 'n': 49}


class Setup(rtc.Clock):
    def __init__(self, binary=False, hour24=True, segment=0x9FC0):
        super().__init__(binary, hour24)
        self.segment = segment
        self.base = segment * 16
        self.cpu.mem_write(0x40E, struct.pack('<H', segment))
        self.cpu.mem_write(self.base + 0xD0, struct.pack('<H', 7168))
        self.cpu.mem_write(self.base + 0x80, bytes((4, 2)))
        self.cpu.mem_write(0x413, struct.pack('<H', 639))
        self.cpu.mem_write(0x484, b'\x18\x10\x00')  # Startup's normal text mode.
        self.cpu.mem_write(0x49E, b'\x01')
        self.cpu.mem_write(0x499, b'\xff')  # No lamp exchange in the opaque KBC.
        self.cpu.mem_write(0x49A, b'\x00')
        for vector, name in ((9, 'int09'), (0x15, 'int15'), (0x16, 'int16')):
            self.cpu.mem_write(vector * 4, struct.pack('<HH', rtc.symbol(name), 0xF000))
        self.cpu.mem_write(0x1C * 4, struct.pack('<HH', rtc.symbol('default_iret'), 0xF000))
        self.pending = []
        self.script = []
        self.vga = []
        self.vga_bx = []
        self.posts = []
        self.idles = 0
        self.observer = None
        self.warm = False
        self.console = ''
        self.speaker = 0xA0
        self.speaker_writes = []
        self.pit_writes = []
        self.pit_counter = 0xFFFF
        self.pit_byte = 0
        self.fdc_dor = 0
        self.fdc_fifo = []
        self.fdc_command = []
        self.fdc_log = []
        self.fdc_senses = []
        self.fdc_irq = False
        self.positions = [0, 0]
        self.track_zero = [None, None]  # None follows motion; bool is a stuck pin.
        self.recal_results = [[], []]
        self.fdc_timeout = None
        self.chipset_index = 0
        self.chipset = {1: 0x96, 2: 0x8D, 3: 0x88, 4: 0x56, 5: 0x10, 9: 0x30, 0x19: 0x33}
        self.cpu.mem_write(0x0E * 4, struct.pack('<HH', rtc.symbol('int0e'), 0xF000))
        self.warm_entry = 0xF0000 + rtc.symbol('.warm_start')
        self.setup_entries = 0
        self.cpu.hook_add(UC_HOOK_CODE, self.setup_entered,
                          begin=0xF0000+rtc.symbol('setup_main'),
                          end=0xF0000+rtc.symbol('setup_main'))
        self.code_hook = self.cpu.hook_add(UC_HOOK_CODE, self.code)
        settings_fixture(self)
        self.call('settings_load')

    def setup_entered(self, cpu, address, size, unused):
        self.setup_entries += 1

    def interrupt(self, cpu, vector, unused):
        if vector == 0x10:  # Opaque video model; --86box tests retained VGA itself.
            ax = cpu.reg_read(x.UC_X86_REG_AX)
            self.vga.append(ax)
            self.vga_bx.append(cpu.reg_read(x.UC_X86_REG_BX))
            if ax == 3:
                cpu.mem_write(0x449, b'\x03')
                cpu.mem_write(0x44A, struct.pack('<H', 80))
                cpu.mem_write(0x484, b'\x18\x10\x00')
            elif ax >> 8 == 2:
                cpu.mem_write(0x450,struct.pack('<H',cpu.reg_read(x.UC_X86_REG_DX)))
            elif ax == 0x1112:
                cpu.mem_write(0x484, b'\x31\x08\x00')
            elif ax == 0x1114:
                cpu.mem_write(0x484, b'\x18\x10\x00')
            elif ax >> 8 == 0x0E:
                self.console += chr(ax & 255)
            return
        if vector == 0x16 and cpu.reg_read(x.UC_X86_REG_AH) == 1:
            if self.observer:
                self.observer(self)
            if self.script and not self.pending:
                self.pending.append(self.script.pop(0))
        super().interrupt(cpu, vector, unused)

    def port_in(self, cpu, port, size, unused):
        if port == 0xED:
            return self.chipset.get(self.chipset_index, 0)
        if port == 0x40:
            value = (self.pit_counter >> (8 * self.pit_byte)) & 255
            self.pit_byte ^= 1
            return value
        if port == 0x3F4:
            return 0xC0 if self.fdc_fifo else 0x80
        if port == 0x3F5:
            assert self.fdc_fifo
            return self.fdc_fifo.pop(0)
        if port == 0x3F7:
            return 0
        if port == 0x64:
            return int(bool(self.pending))
        if port == 0x60:
            assert self.pending
            return self.pending.pop(0)
        if port == 0x20:
            return 2 if getattr(self, 'irq1_pending', False) else 0
        if port == 0x61:
            return self.speaker
        return super().port_in(cpu, port, size, unused)

    def port_out(self, cpu, port, size, value, unused):
        if port == 0x3F2:
            if value & 4 and not self.fdc_dor & 4:
                self.fdc_senses = [(0xC0 | i, 0) for i in range(4)]
                self.fdc_irq = True
            self.fdc_dor = value
        elif port == 0x3F5:
            self.fdc_command.append(value)
            command = self.fdc_command[0]
            length = {3: 3, 4: 2, 7: 2, 8: 1, 0x0F: 3, 0x12: 2, 0x13: 4, 0x4A: 2}[command]
            if len(self.fdc_command) == length:
                data = self.fdc_command
                self.fdc_command = []
                self.fdc_log.append(tuple(data))
                if command == 8:
                    assert self.fdc_senses
                    self.fdc_fifo.extend(self.fdc_senses.pop(0))
                elif command == 4:
                    unit = data[1] & 3
                    zero = self.track_zero[unit]
                    zero = self.positions[unit] == 0 if zero is None else zero
                    self.fdc_fifo.append(0x28 | unit | (0x10 if zero else 0))
                elif command in (7, 0x0F):
                    unit = data[1] & 3
                    status = (self.recal_results[unit].pop(0) if command == 7 and self.recal_results[unit]
                              else 0x20) | unit
                    target = 0 if command == 7 else data[2]
                    self.positions[unit] = target
                    if unit != self.fdc_timeout:
                        self.fdc_senses.append((status, target))
                        self.fdc_irq = True
                elif command == 0x4A:
                    # This external fixture has empty drives. Native cases supply media.
                    self.fdc_fifo.extend((0x40 | (data[1] & 3), 4, 0, 0, 0, 0, 2))
                    self.fdc_irq = True
        elif port == 0x0A:
            assert value == 6, 'idle floppy service must mask DMA channel2'
        elif port in (0x3F0, 0x3F1, 0x3F3, 0x3F7, 0xD6, 0xD2, 0xD4):
            pass  # Opaque SuperIO, rate input and DMA cascade.
        elif port == 0x64:
            assert value in (0xAD, 0xAE), hex(value)
        elif port == 0x60:
            assert value == 0xED or 0 <= value <= 7, hex(value)
            self.pending.insert(0, 0xFA)  # Opaque keyboard acknowledges LED writes.
        elif port == 0x80:
            self.posts.append(value)
        elif port in (0xF9, 0xFB, 0xED):
            pass  # Configuration gate/write owner is opaque.
        elif port == 0xEC:
            self.chipset_index = value
        elif port == 0x61:
            self.speaker = value
            self.speaker_writes.append(value)
        elif port in (0x42, 0x43):
            self.pit_writes.append((port, value))
            if port == 0x43 and value == 0:
                self.pit_counter = (self.pit_counter - 1024) & 0xFFFF
                self.pit_byte = 0
        else:
            super().port_out(cpu, port, size, value, unused)

    def code(self, cpu, address, size, unused):
        if address == self.warm_entry:
            self.warm = True
            cpu.emu_stop()
        if self.fdc_irq and cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200:
            self.fdc_irq = False
            rtc.Clock.interrupt(self, cpu, 0x0E, None)
            return
        if bytes(cpu.mem_read(address, 1)) == b'\xf4':
            self.idles += 1
            cpu.reg_write(x.UC_X86_REG_IP, (cpu.reg_read(x.UC_X86_REG_IP) + 1) & 0xFFFF)
            # Natural external clock/timer event, through the production IRQ0.
            decode = (lambda n: n) if self.cmos[0xB] & 4 else (lambda n: (n >> 4) * 10 + (n & 15))
            hour = decode(self.cmos[4] & 0x7F)
            if not self.cmos[0xB] & 2:
                hour = hour % 12 + (12 if self.cmos[4] & 0x80 else 0)
            try:
                now = datetime.datetime((self.cmos[0x32] >> 4) * 1000 + (self.cmos[0x32] & 15) * 100 + decode(self.cmos[9]),
                                        decode(self.cmos[8]), decode(self.cmos[7]), hour,
                                        decode(self.cmos[2]), decode(self.cmos[0])) + datetime.timedelta(seconds=1)
            except ValueError:
                now = None  # Invalid opaque RTC bytes remain invalid; IRQ0 still advances.
            if now:
                self.seed(now.hour, now.minute, now.second, now.year, now.month, now.day)
            super().interrupt(cpu, 8, None)

    def call(self, name, flags=0x202, count=50000000):
        cpu = self.cpu
        for reg, value in ((x.UC_X86_REG_CS, 0xF000), (x.UC_X86_REG_IP, rtc.symbol(name)),
                           (x.UC_X86_REG_DS, 0), (x.UC_X86_REG_ES, 0),
                           (x.UC_X86_REG_FS, self.segment), (x.UC_X86_REG_SS, 0),
                           (x.UC_X86_REG_SP, 0x6FFE), (x.UC_X86_REG_EFLAGS, flags)):
            cpu.reg_write(reg, value)
        cpu.mem_write(0x6FFE, b'\xff\xff')
        cpu.emu_start(0xF0000 + rtc.symbol(name), 0xFFFFF, count=count)
        assert (cpu.reg_read(x.UC_X86_REG_IP) == 0xFFFF or
                cpu.reg_read(x.UC_X86_REG_CS) * 16 + cpu.reg_read(x.UC_X86_REG_IP) == self.warm_entry or
                (getattr(self, 'post_done', False) and
                 cpu.reg_read(x.UC_X86_REG_CS) * 16 + cpu.reg_read(x.UC_X86_REG_IP) ==
                 getattr(self, 'post_terminal', -1))), 'setup did not reach terminal return'

    def scans(self, scans):
        for scan in scans:
            self.pending.append(scan)
            self.cpu.reg_write(x.UC_X86_REG_CS, 0x9000)
            self.cpu.reg_write(x.UC_X86_REG_IP, 0)
            self.cpu.reg_write(x.UC_X86_REG_SS, 0)
            self.cpu.reg_write(x.UC_X86_REG_SP, 0x7000)
            self.cpu.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
            self.cpu.mem_write(0x90000, b'\xcd\x09\x90')
            self.cpu.emu_start(0x90000, 0x90002, count=100000)
            if self.warm:
                break

    def text(self, row, col, length):
        return bytes(self.cpu.mem_read(0xB8000 + (row * 80 + col) * 2, length * 2))[::2].decode('ascii')

    def open(self, script):
        def visible_page(cpu, access, address, size, value, unused):
            assert address + size <= 0xB8000+4000, (hex(address), size, 'outside 80x25')
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, visible_page, begin=0xB8000, end=0xB8000+7999)
        self.scans([0xE0, 0x53])
        assert self.cpu.mem_read(self.base + 0xF4, 1) == b'\x01'
        self.script = script
        self.call('setup_post_gate')


def keys(text):
    return [SCANS[c] for c in text]


def post_entry():
    for scans, enters in (([0x45, 0xC5, 0x53], False),
                          ([0x1D, 0xE0, 0x53, 0x9D], False),
                          ([0xE0, 0x53], True),
                          ([0xE0, 0x53, 0xE0, 0x53], True)):
        terminal = Setup()
        terminal.scans(scans)
        terminal.script = [1, 28] if enters else []
        terminal.call('setup_post_gate')
        assert terminal.setup_entries == int(enters), (scans, 'wrong terminal entry count')
        assert terminal.cpu.mem_read(0x484, 3) == b'\x18\x10\x00'
    model = Setup()
    model.scans([0x45, 0xC5, 0x53])  # NumLock keypad decimal is ordinary text.
    assert model.cpu.mem_read(model.base + 0xF4, 1) == b'\x00'
    model.scans([0x1D, 0xE0, 0x53, 0x9D])
    assert model.cpu.mem_read(model.base + 0xF4, 1) == b'\x00'
    model.scans([0xE0, 0x53, 0xE0, 0x53])
    assert model.cpu.mem_read(model.base + 0xF4, 1) == b'\x01'
    model.cpu.mem_write(0x49E, b'\x00')
    model.cpu.mem_write(model.base + 0xF4, b'\x00')
    model.scans([0xE0, 0x53])
    assert model.cpu.mem_read(model.base + 0xF4, 1) == b'\x00'
    # There is no late window. Delete after the cutoff cannot latch setup.
    model = Setup()
    model.call('setup_post_gate')
    assert model.cpu.mem_read(0x49E, 1) == b'\x02'
    model.scans([0xE0, 0x53])
    assert model.cpu.mem_read(model.base + 0xF4, 1) == b'\x00'
    assert model.setup_entries == 0


def pause_entry():
    # Suspend arbitrary caller code inside IRQ1, with no POST wait call.
    # Nested timer events supply the E1 tail, release, ACK, then resume make.
    for state in (0, 1, 2):
        model = Setup()
        model.cpu.mem_write(0x4A8, bytes.fromhex('16 FC 00 C0'))
        model.cpu.mem_write(0x49E, bytes((state,)))
        model.cpu.mem_write(0x500, b'\0\0')
        events = [0x1D, 0x45, 0xE1, 0x9D, 0xC5, 0x9E, 0xFA, 0x1E]
        seen = []
        model.cpu.hook_del(model.code_hook)
        def interrupted(cpu, address, size, unused):
            if bytes(cpu.mem_read(address, 1)) == b'\xf4':
                assert cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
                assert bytes(cpu.mem_read(0x500, 2)) == b'\0\0'
                assert bytes(cpu.mem_read(0x4A6, 2)) == b'\x01\x01'
                assert cpu.mem_read(0x49E, 1)[0] == (state + 2 if state else 0)
                assert len(seen) < len(events), 'Pause failed to resume'
                model.pending.append(events[len(seen)])
                seen.append(address)
            model.code(cpu, address, size, unused)
        model.cpu.hook_add(UC_HOOK_CODE, interrupted)
        # Caller advances a marker only after the interrupted IRQ returns.
        model.cpu.mem_write(0x90000, b'\xcd\x09\xff\x06\x00\x05\x90')
        cpu = model.cpu
        for reg, value in ((x.UC_X86_REG_CS, 0x9000), (x.UC_X86_REG_IP, 0),
                           (x.UC_X86_REG_DS, 0), (x.UC_X86_REG_SS, 0),
                           (x.UC_X86_REG_SP, 0x7000), (x.UC_X86_REG_EFLAGS, 0x202)):
            cpu.reg_write(reg, value)
        model.pending.append(0xE1)
        cpu.emu_start(0x90000, 0x90006, count=1000000)
        assert len(seen) == 8
        assert bytes(cpu.mem_read(0x500, 2)) == b'\x01\0'
        assert bytes(cpu.mem_read(0x4A6, 2)) == b'\0\0'
        assert bytes(cpu.mem_read(0x4A8, 4)) == bytes.fromhex('16 FC 00 C0')
        assert cpu.mem_read(0x49E, 1)[0] == state
        assert cpu.reg_read(x.UC_X86_REG_SP) == 0x7000
        assert cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        assert bytes(cpu.mem_read(0x41A, 2)) == bytes(cpu.mem_read(0x41C, 2))
        assert cpu.mem_read(model.base + 0xF4, 1)[0] == 0
        model.scans([0xE0, 0x53])
        assert cpu.mem_read(model.base + 0xF4, 1)[0] == int(state == 1)


def text_ui():
    model = Setup()
    seen = []
    def observe(m):
        if not seen:
            assert m.cpu.mem_read(0x484, 3) == b'\x18\x10\x00'
            assert m.text(0, 3, 19) == 'Compaq Presario 800'
            assert m.text(0, 34, 11) == 'bAIos Setup'
            assert m.text(1, 3, 7) == 'Unknown'
            assert m.text(0, 58, 8) == 'Version:'
            assert m.text(0, 72, 5) == '0.1.0'
            assert m.text(1, 58, 10) == 'ROM build:'
            assert m.text(1, 69, 8) == '10/05/26'
            assert bytes(m.cpu.mem_read(0xB8000 + 320, 160))[::2] == b'\xcd' * 20 + b'\xd1' + b'\xcd' * 59
            assert all(a in (0x1B, 0x1F) for a in bytes(m.cpu.mem_read(0xB8000, 320))[1::2])
            assert m.text(15, 24, 47).strip() == ''
            for row, size in ((9, '8192'), (10, '639'), (11, '7168')):
                assert m.text(row, 49, len(size)) == size
                assert m.text(row, 59, 2) == 'KB'
            assert m.cpu.mem_read(0x49E, 1) == b'\x00'
            seen.append(True)
    model.observer = observe
    model.open([0x3B, 1, 0x50, 28, 15, 0x50, 28, 1, 1, 28])
    assert seen and model.vga[:3] == [0x1202, 3, 0x1114] and model.vga[-4:] == [0x1202, 3, 0x1114, 0x1003], model.vga
    assert model.cpu.mem_read(0x484, 3) == b'\x18\x10\x00'
    assert model.cpu.mem_read(model.base + 0xF4, 1) == b'\x00'
    for signature, name in ((0x0430, '486DX2'), (0x1532, 'Pentium P24T')):
        model = Setup()
        model.cpu.mem_write(model.base + 0xD4, struct.pack('<H', signature))
        seen_cpu = []
        def cpu_header(m):
            assert m.text(1, 3, len(name)) == name
            seen_cpu.append(True)
        model.observer = cpu_header
        model.open([1, 28])
        assert seen_cpu
    # Navigation must reach each real page and leave unimplemented items absent.
    for present in (False, True):
        model = Setup()
        model.cpu.mem_write(model.base + 0x20, bytes((int(present),)))
        model.cpu.mem_write(model.base + 0x140, b'FIXTURE IDE MASTER\0')
        model.cpu.mem_write(model.base + 0x2E, struct.pack('<I', 8 * 1024 * 2048))
        pages = set()
        def page_observer(m):
            page, focus = m.cpu.mem_read(m.base + 0xF5, 2)
            pages.add((page, focus))
            whole = bytes(m.cpu.mem_read(0xB8000, 4000))[::2].decode('cp437')
            assert not any(s in whole for s in ('Chipset Setup', 'Power Management'))
            if page == 1:
                assert m.text(3, 23, 20) == 'bAIos Setup > Drives'
                assert m.text(5, 49, 16).strip() == '1.44 MB, 3.5 in'
                assert m.text(6, 49, 16).strip() == '1.2 MB, 5.25 in'
                for row in (5, 6):
                    color = 0x1F if focus == 1 and row == 5 else 7
                    assert bytes(m.cpu.mem_read(0xB8000 + row * 160 + 49 * 2 + 1, 28))[::2] == bytes([color]) * 14
                assert m.text(9, 24, 17) == 'Primary IDE Slave'
                assert m.text(9, 49, 4) == 'Auto'
                for row in (8, 9):
                    assert m.cpu.mem_read(0xB8000 + row * 160 + 54 * 2, 2) == b'\x1a\x07'
                assert m.text(18, 24, 54).strip() == ''
            elif page == 2:
                assert m.text(5, 49, 6) == 'Floppy'
            elif page == 4:
                assert m.text(5, 24, 13) == 'Save and Exit'
                assert m.text(6, 24, 16) == 'Discard and Exit'
        model.observer = page_observer
        before = bytes(model.cpu.mem_read(model.base + 0x80, 2))
        model.open([0x50, 28, 1, 0x50, 28, 1, 0x50, 0x50, 0x50, 28, 0x50, 28, 28])
        assert {(0, 0), (1, 0), (1, 1), (2, 0), (3, 0), (4, 1)} <= pages, pages
        assert bytes(model.cpu.mem_read(model.base + 0x80, 2)) == before
        assert model.cpu.mem_read(0x484, 3) == b'\x18\x10\x00'


def context_help():
    # Each F1 follows the actual selection, and Esc dismisses it without edits.
    for prefix, title, detail in (
        ([], 'Standard Setup', 'System date, time, and detected memory.'),
        ([15], 'System Date', 'Calendar date: 1980-2099.'),
        ([15, 0x50], 'System Time', '12-hour clock:01:00:00-12:59:59. A/P selects AM/PM.'),
        ([15,0x50,0x50], 'Time Format', 'Choose12-hour AM/PM or24-hour display.'),
        ([15,0x50,0x50,0x4D,0x48], 'System Time', '24-hour clock:00:00:00-23:59:59.'),
        ([0x50], 'Drives', 'Floppy types and primary IDE device policy.'),
        ([0x50, 0x50], 'Boot', 'Used devices move to the selected position.'),
        ([0x50, 15], 'Floppy Drive A', 'Select the installed drive type, or None.'),
        ([0x50, 15, 0x50], 'Floppy Drive B', 'Select the installed drive type, or None.'),
        ([0x50, 15, 0x50, 0x50], 'Primary IDE Master', 'Auto identifies ATA disks and ATAPI devices at POST.'),
        ([0x50, 15, 0x50, 0x50, 0x50], 'Primary IDE Slave', 'Auto identifies ATA disks and ATAPI devices at POST.'),
        ([0x50, 0x50, 15], 'First Boot Device', 'Used devices move to the selected position.'),
        ([0x50,0x50,15]+[0x50]*3, 'Fourth Boot Device', 'Used devices move to the selected position.'),
        ([0x50,15]+[0x50]*6, 'Swap Floppy Drives', 'Physical B becomes A at boot; A becomes B.'),
        ([0x50,0x50,15]+[0x50]*5, 'Boot Num Lock', 'Set Num Lock after cold or warm POST.'),
        ([0x50,0x50,15]+[0x50]*6, 'Halt On', 'Choose which recoverable errors pause POST.'),
        ([0x50,0x50,15]+[0x50]*4, 'Floppy Seek', 'Check drives during POST. Default Enabled.'),
        ([0x50, 0x50, 0x50, 0x50, 0x50, 15], 'Save and Exit', 'Write drive and boot settings, then restart.'),
        ([0x50, 0x50, 0x50, 0x50, 0x50, 15, 0x50], 'Discard and Exit', 'Return without saving drive or boot edits.'),
        (keys('\t\r01012001'), 'System Date', 'Calendar date: 1980-2099.'),
    ):
        model = Setup()
        old = bytes(model.cmos)
        seen = []
        def observe(m):
            if m.text(18, 25, len(title)) == title and not seen:
                assert m.text(19, 25, len(detail)) == detail
                assert m.text(22, 25, 8).strip() == ''
                if m.cpu.mem_read(m.base + 0xF8, 1) != b'\x00':
                    assert bytes(m.cpu.mem_read(m.base + 0x100, 11)) == b'01/01/2001\x00'
                seen.append(bytes(m.cpu.mem_read(m.base + 0xF5, 4)))
            elif len(seen) == 1 and m.text(18, 25, len(title)).strip() == '':
                assert bytes(m.cpu.mem_read(m.base + 0xF5, 4)) == seen[0], 'help dismissal left the selection/editor'
                assert m.cpu.mem_read(0x484, 3) == b'\x18\x10\x00', 'help dismissal left setup'
                seen.append(True)
        model.observer = observe
        exits = ([1, 1, 1, 28] if prefix[:2] == [15, 28] else
                 ([1, 1, 28] if 15 in prefix else [1, 28]))
        model.open(prefix + [0x3B, 1] + exits)
        assert len(seen) == 2, (title, 'help did not return to the selected item')
        assert bytes(model.cmos) == old, 'help changed the clock'


def immediate_clock():
    for binary in (False, True):
        for hour24 in (False, True):
            model = Setup(binary, hour24)
            model.open(keys('\t\r02292028\r') + [0x50, 28] + keys('115958p\r') + [1, 1, 1, 1, 28])
            assert model.invoke(4)[1:3] == (0x2028, 0x0229)
            assert model.invoke(2)[1:3] == (0x2359, 0x5801)
            assert model.cmos[0xB] == 2 * hour24 + 4 * binary + 1
            model = Setup(binary, hour24)
            model.cmos[4] = 0xFF
            model.open([15, 0x50, 28] + keys('014559p\r') + [1, 1, 28])
            assert model.invoke(2)[1:3] == (0x1345, 0x5901), 'time repair cleared DST'
            assert model.cmos[0xB] == 2 * hour24 + 4 * binary + 1
    model = Setup()
    old = bytes(model.cmos)
    model.open(keys('\t\r13322099\r\x1b') + [1, 1, 28])
    assert bytes(model.cmos) == old, 'invalid date changed clock'
    model = Setup()
    old = bytes(model.cmos)
    model.open(keys('\t\r01012001\x1b') + [1, 1, 28])
    assert bytes(model.cmos) == old, 'canceled form changed clock'
    for form in ('246199\r\x1b', '010203\x1b'):
        model = Setup()
        old = bytes(model.cmos)
        model.open([15, 0x50, 28] + keys(form) + [1, 1, 28])
        assert bytes(model.cmos) == old, 'invalid/canceled time form changed clock'


def idle_clock():
    for confirm in (False, True):
        model = Setup()
        original_date = model.invoke(4)[1:3]
        entered = []
        phase = [0]
        def observe(m):
            if phase[0] == 0 and not m.script and not m.pending:
                assert m.cpu.mem_read(m.base+0xF8,1) == b'\x01'
                entered.extend((bytes(m.cpu.mem_read(m.base+0x100,11)),
                                m.text(6,49,8), m.cpu.mem_read(m.base+0xF9,1)[0],
                                bytes(m.cpu.mem_read(0xB8000,320))))
                phase[0] = 1  # No key: a natural modeled RTC second passes.
            elif phase[0] == 1 and m.idles:
                assert bytes(m.cpu.mem_read(m.base+0x100,11)) == entered[0]
                assert m.text(6,49,8) != entered[1]
                assert bytes(m.cpu.mem_read(0xB8000,320)) == entered[3]
                m.script = [0x3B,1]
                phase[0] = 2
            elif phase[0] == 2 and m.text(18,25,11) == 'System Date':
                assert bytes(m.cpu.mem_read(m.base+0x100,11)) == entered[0]
                assert m.cpu.mem_read(m.base+0xF9,1)[0] == entered[2]
                phase[0] = 3
            elif phase[0] == 3 and not m.script and not m.pending:
                assert m.text(19,24,10).encode('ascii') == entered[0][:10]
                assert m.cpu.mem_read(0xB8000+19*160+(24+entered[2])*2+1,1) == b'\x70'
                assert bytes(m.cpu.mem_read(0xB8000,320)) == entered[3]
                assert m.text(6,49,8) != entered[1]
                m.script = [28 if confirm else 1,1,1,28]
                m.observer = None
                phase[0] = 4
        model.observer = observe
        model.open(keys('\t\r01012001'))
        assert phase[0] == 4 and model.idles
        assert model.invoke(4)[1:3] == ((0x2001,0x0101) if confirm else original_date)


def clock_repair():
    model = Setup()
    model.cmos[0xD] = 0
    model.open(keys('\t\r02292028\r') + [0x50, 28] + keys('120000\r') + [1, 1, 28])
    assert not model.cmos[0xE] & 0x80
    assert model.invoke(4)[1:3] == (0x2028, 0x0229)


def partial_clock_repair():
    for binary in (False, True):
        for hour24 in (False, True):
            for date_first in (False, True):
                model = Setup(binary, hour24)
                model.cmos[0xD] = 0
                seen = []
                def observe(m):
                    repaired = m.cpu.mem_read(m.base + 0xD2, 1)[0]
                    if repaired == (2 if date_first else 1):
                        assert m.text(5, 49, 10) == ('10/01/2026' if date_first else '01/01/1980')
                        assert m.text(6, 49, 8) == ('12:00:00' if date_first else '01:45:59')
                        assert m.cmos[0xE] & 0x80, 'partial repair cleared power-loss warning'
                        seen.append(True)
                model.observer = observe
                date = keys('10012026\r')
                time = keys('014559p\r')
                script = keys('\t') + ([] if date_first else [0x50]) + [28]
                script += date if date_first else time
                # Cancel another edit: the last confirmed display must remain.
                script += [28, 1, 0x50 if date_first else 0x48, 28] + (time if date_first else date) + [1, 1, 28]
                model.open(script)
                assert seen, 'confirmed first domain was never observed'
                assert model.invoke(4)[1:3] == (0x2026, 0x1001)
                assert model.invoke(2)[1:3] == (0x1345, 0x5901)
                assert not model.cmos[0xE] & 0x80


def clock_defaults():
    clock_bytes = (0, 2, 4, 6, 7, 8, 9, 0x32)
    for bad_date, bad_time in ((True, False), (False, True), (True, True)):
        model = Setup()
        _, date_cx, date_dx, _ = model.invoke(4)
        _, time_cx, time_dx, _ = model.invoke(2)
        valid_date = f'{date_dx >> 8:02X}/{date_dx & 255:02X}/{date_cx:04X}'
        valid_time = f'{((time_cx >> 8)-0x12):02X}:{time_cx & 255:02X}:{time_dx >> 8:02X}'
        if bad_date:
            model.cmos[8] = 0
        if bad_time:
            model.cmos[4] = 0xFF
        old = tuple(model.cmos[i] for i in clock_bytes)
        seen = []
        def observe(m):
            if not seen:
                if bad_date:
                    assert m.text(5, 49, 10) == '01/01/1980'
                else:
                    assert m.text(5, 49, 10) == valid_date
                if bad_time:
                    assert m.text(6, 49, 8) == '12:00:00'
                else:
                    assert m.text(6, 49, 8) == valid_time
                seen.append(True)
            edit = m.cpu.mem_read(m.base + 0xF8, 1)[0]
            if edit == 1 and bad_date:
                assert bytes(m.cpu.mem_read(m.base + 0x100, 11)) == b'01/01/1980\x00'
            if edit == 2 and bad_time:
                assert bytes(m.cpu.mem_read(m.base + 0x100, 12)) == b'12:00:00 AM\x00'
        model.observer = observe
        model.open([15, 28, 1, 0x50, 28, 1, 1, 1, 28])
        assert seen and tuple(model.cmos[i] for i in clock_bytes) == old, 'unconfirmed defaults wrote the RTC'
    model = Setup()
    model.cmos[8] = 0
    model.cmos[4] = 0xFF
    model.open([15, 28, 28, 0x50, 28, 28, 1, 1, 28])
    assert model.invoke(4)[1:3] == (0x1980, 0x0101)
    assert model.invoke(2)[1:3] == (0x0000, 0x0001)
    model.call('post_clock_alert')
    assert not model.console and not model.speaker_writes, 'confirmed defaults still triggered the warning'


def clock_alert():
    for bad_date, bad_time in ((False, False), (True, False), (False, True), (True, True)):
        model = Setup()
        if bad_date:
            model.cmos[8] = 0
        if bad_time:
            model.cmos[4] = 0xFF
        # A real keyboard arrival while the tone waits must still reach IRQ1.
        def deliver(cpu, address, size, unused):
            if bytes(cpu.mem_read(address, 1)) == b'\xf4' and model.idles in (1, 2):
                model.pending.append(0xE0 if model.idles == 1 else 0x53)
        model.cpu.hook_add(UC_HOOK_CODE, deliver)
        model.call('post_clock_alert')
        if bad_date or bad_time:
            assert 'WARNING: CMOS date/time not set.' in model.console
            assert model.speaker_writes == [0xA3, 0xA3, 0xA3, 0xA0]
            assert model.pit_writes == [(port, value) for divisor in (2712, 3419, 4571)
                                        for port, value in ((0x43, 0xB6), (0x42, divisor & 255), (0x42, divisor >> 8))]
            assert model.idles >= 4 and model.cpu.mem_read(model.base + 0xF4, 1) == b'\x01'
        else:
            assert model.console == '' and not model.speaker_writes and not model.pit_writes
        assert not any(i in (0, 2, 4, 6, 7, 8, 9, 0x32) for i, _ in model.writes), 'alert wrote clock defaults'
    model = Setup()
    model.speaker = 0xA3  # Tone left by a reset during the previous POST.
    model.call('post_clock_alert')
    assert model.speaker == 0xA0 and model.speaker_writes == [0xA0]
    assert not model.console and not model.pit_writes
    for reboot in (False, True):
        model = Setup()
        model.cmos[8] = 0
        model.scans([28])      # Queued before the warning: must not dismiss it.
        scans = [0x1D, 0x38, 0xE0, 0x53] if reboot else [28]
        def delayed_key(cpu, address, size, unused):
            if bytes(cpu.mem_read(address, 1)) == b'\xf4' and model.idles >= 7 and scans:
                model.pending.append(scans.pop(0))
        model.cpu.hook_add(UC_HOOK_CODE, delayed_key)
        model.call('post_clock_alert')
        assert model.idles >= 7, 'POST warning did not wait for a fresh key'
        assert model.warm == reboot
        assert model.speaker == 0xA0, 'speaker left on during notice wait'
        if not reboot:
            assert model.cpu.mem_read(0x41A, 2) == model.cpu.mem_read(0x41C, 2), 'continuation key was not consumed'
    model = Setup()
    model.cmos[8] = 0
    supplied = False
    def paired_keys(cpu, address, size, unused):
        nonlocal supplied
        if bytes(cpu.mem_read(address, 1)) == b'\xf4' and model.idles >= 7 and not supplied:
            # Two distinct arrivals before notice consumes exactly one.
            model.pending.extend([28, 0x30])
            supplied = True
    model.cpu.hook_add(UC_HOOK_CODE, paired_keys)
    model.call('post_clock_alert')
    assert supplied
    head, tail = struct.unpack('<HH', model.cpu.mem_read(0x41A, 4))
    assert (tail - head) % 32 == 2, 'notice drained the later key'
    assert model.cpu.mem_read(0x400 + head, 2) == b'b\x30'


def clock_alert_delete():
    for segment in (0x9FC0, 0x8FC0):
        for incoming_fs in (0, 0x9FC0):
            model = Setup(segment=segment)
            model.cmos[8] = 0
            entry = 0xF0000 + rtc.symbol('post_clock_alert')
            scans = [0xE0, 0x53]
            def deliver(cpu, address, size, unused):
                if address == entry:
                    cpu.reg_write(x.UC_X86_REG_FS, incoming_fs)
                if bytes(cpu.mem_read(address, 1)) == b'\xf4':
                    assert model.idles < 12, 'Delete latched but clock notice still waiting'
                    if model.idles >= 7 and scans:
                        model.pending.append(scans.pop(0))
            model.cpu.hook_add(UC_HOOK_CODE, deliver)
            model.call('post_clock_alert')
            assert not scans and model.cpu.mem_read(model.base + 0xF4, 1) == b'\x01'
            assert model.cpu.reg_read(x.UC_X86_REG_FS) == incoming_fs
            # Only terminal fixture exit input follows; no extra notice key.
            model.script = [1, 28]
            model.call('setup_post_gate')
            assert model.setup_entries == 1 and 0x1114 in model.vga


def shared_state():
    for segment in (0x9FC0, 0x8FC0):
        model = Setup(segment=segment)
        model.cpu.mem_write(model.base + 0x20, bytes(range(64)))
        model.cpu.mem_write(model.base + 0x80, bytes((4, 2)) + bytes(range(2, 64)))
        opaque = bytes(model.cpu.mem_read(model.base + 0x20, 0xD4))
        model.open([1, 28])
        assert bytes(model.cpu.mem_read(model.base + 0x20, 0xD4)) == opaque
        assert model.cpu.mem_read(0x413, 2) == struct.pack('<H', 639)


def reset():
    model = Setup()
    model.open(keys('\t\r02292028\r') + [0x1D, 0x38, 0xE0, 0x53])
    assert model.warm and model.posts[-2:] == [0x90, 0x91]
    assert model.cpu.mem_read(0x472, 2) == b'\x34\x12'
    assert model.invoke(4)[1:3] == (0x2028, 0x0229)
    model = Setup()
    before = bytes(model.cmos)
    active = loaded(model)
    model.open(DRIVE_EDIT + [0x1D, 0x38, 0xE0, 0x53])
    assert model.warm and bytes(model.cmos[0x10:]) == before[0x10:] and not model.writes
    assert loaded(model) == active


def settings_fixture(model, types=0x42, hdd=1, boot=0, seek=0x5A):
    # Independent external CMOS fixture, never built by the candidate writer.
    model.cmos[0x10] = types
    model.cmos[0x38:0x3F] = bytes((ord('B'), ord('8'), 1, hdd, boot,
                                   -(ord('B') + ord('8') + 1 + types + hdd + boot) & 255, seek))


def loaded(model):
    return bytes(model.cpu.mem_read(model.base + 0x170, 4))


def settings_validity():
    fixtures = [(None, None, (0x42, 1, 1, 1)),
                (0x10, 0, (0, 1, 1, 0)), (0x3E, 0, (0x42, 1, 1, 1)),
                (0x3E, 0x5A, (0x42, 1, 1, 1)), (0x3E, 0xA5, (0x42, 1, 1, 0))]
    fixtures += [(i, value, (0x40 if i == 0x10 else 0x42, 1, 1, 1)) for i, value in
                 ((0x38, 0), (0x39, 0), (0x3A, 5), (0x3B, 2), (0x3C, 3),
                  (0x10, 0x62), (0x10, 0x46), (0x3D, 0))]
    for index, value, expected in fixtures:
        model = Setup()
        settings_fixture(model, seek=0xA5)
        if index is not None:
            model.cmos[index] = value
            if index < 0x3D:
                model.cmos[0x3D] = -(sum(model.cmos[0x38:0x3D]) + model.cmos[0x10]) & 255
        else:
            model.cmos[0x3E] = 0x5A
        before = bytes(model.cmos)
        model.writes.clear()
        model.call('settings_load')
        assert loaded(model) == bytes(expected), (index, loaded(model), expected)
        model.call('init_floppy')
        model.call('post_floppy_seek')
        mechanical = [c for c in model.fdc_log if c[0] in (4, 7, 15)]
        assert bool(mechanical) == (bool(expected[0]) and bool(expected[3])), (index, mechanical)
        assert bytes(model.cmos) == before and not model.writes
    for legacy_type, expected in ((0, 0x40), (0x24, 0x24), (0x60, 0x40)):
        model = Setup()
        model.cmos[0x38] = 0
        model.cmos[0x10] = legacy_type
        model.call('settings_load')
        assert loaded(model) == bytes((expected, 1, 1, 1))

    model = Setup()
    model.cmos[0x10] = model.cmos[0x38] = 0
    model.call('settings_load')
    assert loaded(model) == bytes((0x40, 1, 1, 1))
    model.call('init_floppy')
    model.call('post_floppy_seek')
    assert bytes(model.cpu.mem_read(model.base + 0x80, 2)) == b'\x04\x00'
    assert any(c[0] == 15 for c in model.fdc_log)
    assert not any(c[0] in (4, 7, 15) and c[1] & 3 for c in model.fdc_log)
    model.open([0x43, 28, 0x44, 28])  # Real F9/confirm, F10/confirm.
    model.call('settings_load')
    assert model.warm and loaded(model) == bytes((0x40, 1, 1, 1))
    assert model.cmos[0x10] == 0x40 and model.cmos[0x3C:0x3D] == b'\x01'
    assert model.cmos[0x3E] == 2


def cmos_recovery():
    # Keep the selected chipset policy across clock-only repair and Setup choice.
    for invalid_settings in (False, True):
        chipset = importlib.import_module('test-chipset')
        model, policy = chipset.recovery_model()
        if invalid_settings:
            model.cmos[0x38] ^= 0xFF
        else:
            model.cmos[8] = 0
        model.call('settings_load')
        saved_chipset = bytes(model.cmos[0x69:0x80] + model.cmos[0x33:0x36])
        model.writes.clear()
        model.script = [0xE0, 0x53] if invalid_settings else [28]
        model.call('post_clock_alert')
        assert not getattr(model, 'restarts', 0) and not model.cmos[0x36]
        assert model.record() == policy
        assert bytes(model.cmos[0x69:0x80] + model.cmos[0x33:0x36]) == saved_chipset
        assert model.chipset[1] == 0x54 and model.chipset[4] == 0x36
        assert (model.chipset[0x20], model.chipset[0x21], model.chipset[0x19]) == (4, 1, 0)
        assert model.cpu.mem_read(model.base+0xD0, 2) == struct.pack('<H', 1024)
        assert bytes(model.cmos[0x17:0x19]) == bytes(model.cmos[0x30:0x32]) == struct.pack('<H', 1024)
        assert (0x69, 0) not in model.writes and (0x36, 0x5A) not in model.writes
        assert 'RAM test failed' not in model.console
        assert model.cpu.mem_read(model.base+0xF4, 1) == bytes((invalid_settings,))
    print('Custom chipset policy survives clock-only repair and choosing Setup: PASS', flush=True)
    for bad_record, bad_clock, choice in ((record, clock, choice)
            for record in (None, 0x38, 0x3A, 0x3D, 0x10)
            for clock in (False, True) for choice in ('defaults', 'setup')):
        model = Setup()
        if bad_record is not None:
            model.cmos[bad_record] ^= 0xFF
        if bad_clock:
            model.cmos[8] = 0
        model.call('settings_load')
        before = bytes(model.cmos)
        active = loaded(model)
        model.scans([0x20])  # Queued D cannot accept defaults before the notice.
        model.script = [0x1E, 0x20] if choice == 'defaults' else [0xE0, 0x53]
        if bad_record is not None and choice == 'defaults':
            # Compose genuine warning/save/load with the same full ROM restart fixture.
            chipset = importlib.import_module('test-chipset')
            model = chipset.Chipset()
            policy = bytearray(model.record())
            policy[0], policy[1], policy[2] = 0x54, 0x96, 0xA7
            policy[10] |= 0x80
            policy[17:19] = bytes((4, 1))
            model.draft(policy)
            model.call('chipset_settings_save')
            model.chipset[2], model.chipset[3], model.chipset[4] = 0xCC, 0x88, 0x36
            model.cpu.mem_write(model.base+0x78, struct.pack('<H', 7168))
            model.cmos[bad_record] ^= 0xFF
            if bad_clock: model.cmos[8] = 0
            model.call('settings_load')
            model.call('chipset_apply', flags=2)
            model.call('publish_memory_cmos', flags=2)
            model.cmos[0x36] = 0
            model.scans([0x20])
            model.script = [0x1E, 0x20]
            model.startup(entry='post_clock_alert', through_visible=True)
            assert model.restarts == 1 and model.chipset[4] == 0x16
            assert model.record() == chipset.NORMAL and model.chipset[1] == 0x96
            assert model.cmos[0x69] == 0xC2 and bytes(model.cmos[0x6B:0x80]+model.cmos[0x33:0x36]) == chipset.NORMAL
            assert bytes(model.cmos[0x17:0x19]) == bytes(model.cmos[0x30:0x32]) == struct.pack('<H', 7168)
            assert not model.cmos[0x36] and 'RAM test failed' not in model.console
        else:
            model.call('post_clock_alert')
        if bad_record is None and not bad_clock:
            assert not model.console and not model.speaker_writes
            continue
        assert 'Enter/D: Load defaults and continue.  Delete: Setup.' in model.console
        if bad_record is not None and bad_clock:
            assert 'CMOS settings invalid; date/time not set.' in model.console
        else:
            assert ('CMOS settings invalid.' in model.console) == (bad_record is not None)
            assert ('CMOS date/time not set.' in model.console) == bad_clock
        assert model.idles >= 7 and not model.speaker & 3
        if not getattr(model, 'restarts', 0):
            assert model.speaker == 0xA0
        assert model.cpu.mem_read(model.base + 0xF4, 1) == bytes((choice == 'setup',))
        assert loaded(model) == (bytes((0x40, 1, 1, 1))
                                  if bad_record is not None and choice == 'defaults' else active)
        if choice == 'setup':
            assert bytes(model.cmos[0x10:]) == before[0x10:] and not model.writes
            assert model.cpu.mem_read(model.base + 0x174, 1) == bytes((bad_record is None,))
            continue
        assert model.cpu.mem_read(model.base + 0x174, 1) == b'\x01'
        assert model.invoke(4)[1:3] == ((0x1980, 0x0101) if bad_clock else (0x2026, 0x0228))
        # Fresh EBDA/keyboard state with only persisted CMOS carried over.
        reboot = Setup()
        reboot.cmos[:] = model.cmos
        reboot.call('settings_load')
        reboot.call('post_clock_alert')
        assert not reboot.console and not reboot.speaker_writes, 'reboot repeated CMOS warning'
        assert loaded(reboot) == loaded(model)
    # Preserve a valid time/date counterpart in all four native RTC formats.
    for binary in (False, True):
        for hour24 in (False, True):
            for bad_date, bad_time, lost in ((True, False, False), (False, True, False), (True, True, True)):
                model = Setup(binary, hour24)
                date = model.invoke(4)[1:3]
                time = model.invoke(2)[1:3]
                if bad_date:
                    model.cmos[8] = 0
                if bad_time:
                    model.cmos[4] = 0xFF
                if lost:
                    model.cmos[0xE] |= 0x80
                model.script = [28]
                model.call('post_clock_alert')
                assert not model.cpu.mem_read(model.base + 0xF4, 1)[0]
                assert model.invoke(4)[1:3] == ((0x1980, 0x0101) if bad_date else date)
                failed, cx, dx, _ = model.invoke(2)
                assert not failed, (binary, hour24, bad_date, bad_time, lost, model.console, model.writes)
                assert cx == (0 if bad_time else time[0])
                assert dx >> 8 <= (1 if bad_time else (time[1] >> 8) + 1)
                assert dx & 255 == time[1] & 255
                assert not model.cmos[0xE] & 0x80
    class FailedSave(Setup):
        def port_in(self, cpu, port, size, unused):
            value = super().port_in(cpu, port, size, unused)
            if port == 0x71 and self.index == 0x10 and (0x38, 66) in self.writes:
                return 0xFF
            return value
    model = FailedSave()
    model.cmos[0x38] = 0
    model.call('settings_load')
    model.script = [28]
    model.call('post_clock_alert')
    assert 'CMOS verification failed.' in model.console
    assert model.cpu.mem_read(model.base + 0xF4, 1) == b'\x01'


DRIVE_EDIT = [0x50, 28, 0x4D, 0x50, 0x4D, 0x50, 0x4D,
              1, 0x50, 28, 0x4D, 0x50,
              0x50, 0x50, 0x50, 0x4D]


def save_all():
    for action, accept in ((action, accept) for action in ('defaults', 'discard', 'save') for accept in (False, True)):
        model = Setup()
        before = bytes(model.cmos)
        seen = []
        def observe(m):
            seen.append(bytes(m.cpu.mem_read(m.base + 0x180, 4)))
        model.observer = observe
        if action == 'defaults':
            ending = [0x43, 28 if accept else 1, 1, 1, 28]
        elif action == 'discard':
            ending = [1, 1, 28] if accept else [1, 1, 1, 1, 28]
        else:
            ending = [0x44, 28] if accept else [0x44, 1, 1, 1, 28]
        model.open(DRIVE_EDIT + ending)
        assert bytes((0x53, 0, 2, 0)) in seen, (action, seen)
        assert model.warm == (action == 'save' and accept)
        if model.warm:
            assert model.cpu.mem_read(0x472, 2) == b'\x34\x12'
            assert model.posts[-2:] == [0x90, 0x91]
            model.call('settings_load')
            assert loaded(model) == bytes((0x53, 0, 2, 0))
        else:
            assert bytes(model.cmos) == before and not model.writes, action
        if action == 'defaults' and accept:
            assert bytes((0x40, 1, 1, 1)) in seen
    model = Setup()
    model.open(keys('\t\r02292028\r') + [1] + DRIVE_EDIT + [0x44, 28])
    model.call('settings_load')
    assert loaded(model) == bytes((0x53, 0, 2, 0)) and model.invoke(4)[1:3] == (0x2028, 0x0229)


def settings_save():
    model = Setup()
    model.open(DRIVE_EDIT + [0x44, 28])
    record = bytes(model.cmos[0x38:0x40])
    assert record == bytes((66, 56, 5, 0x31, 2, -(66 + 56 + 5 + 0x53 + 0x31 + 2 + 1) & 255, 1, 0))
    assert model.writes[0] == (0x38, 0) and model.writes[-1] == (0x38, 66)
    assert sum(model.cmos[0x38:0x40]) + model.cmos[0x10] & 255 == 0
    assert model.cmos[0x2E:0x30] == sum(model.cmos[0x10:0x2E]).to_bytes(2, 'big')
    model.call('publish_memory_cmos', flags=2)
    model.call('publish_disk_cmos', flags=2)
    assert bytes(model.cmos[0x38:0x40]) == record and model.cmos[0x10] == 0x53
    relocated = Setup(segment=0x8FC0)
    unrelated = bytes(relocated.cpu.mem_read(0x9FD70, 0x14))
    relocated.open(DRIVE_EDIT + [0x44, 28])
    relocated.call('settings_load')
    assert loaded(relocated) == bytes((0x53, 0, 2, 0))
    assert bytes(relocated.cmos[0x38:0x40]) == record
    assert bytes(relocated.cpu.mem_read(0x9FD70, 0x14)) == unrelated
    class Mismatch(Setup):
        def port_in(self, cpu, port, size, unused):
            value = super().port_in(cpu, port, size, unused)
            if port == 0x71 and self.index == 0x3E and (0x38, 66) in self.writes:
                return value ^ 255
            return value
    model = Mismatch()
    seen = []
    def error_observer(m):
        if 'CMOS verification failed.' in m.text(19, 23, 46):
            assert not m.warm and loaded(m) == bytes((0x42, 1, 1, 1))
            assert bytes(m.cpu.mem_read(m.base + 0x180, 4)) == bytes((0x53, 0, 2, 0))
            assert m.text(20, 49, 8) == '3E 01 FE'
            seen.append(True)
            m.observer = None
            m.script = [1, 1, 28]
    model.observer = error_observer
    model.open(DRIVE_EDIT + [0x44, 28])
    assert seen and not model.warm
    class Transient(Setup):
        missed = False
        def port_in(self, cpu, port, size, unused):
            value = super().port_in(cpu, port, size, unused)
            if port == 0x71 and self.index == 0x3E and (0x38, 66) in self.writes and not self.missed:
                self.missed = True
                return value ^ 255
            return value
    model = Transient(binary=True)
    model.open(DRIVE_EDIT + [0x44, 28])
    assert model.missed and model.warm, 'a transient read rejected persisted settings'
    model.call('settings_load')
    assert loaded(model) == bytes((0x53, 0, 2, 0))


class Policy(Setup, legacy.Disk):
    pass  # Reuse the ATA port model, not a replacement detection/publication path.


def hdd_policy():
    for hdd in (0, 1):
        model = Policy()
        settings_fixture(model, hdd=hdd)
        model.cmos[0x3F] = 0xA5  # Isolate the master policy; the absent slave is Disabled.
        model.call('settings_load')
        model.call('ata_identify', flags=2)
        assert (0xEC in model.commands) == bool(hdd)
        assert model.cpu.mem_read(model.base + 0x20, 1)[0] == hdd
        assert model.cpu.mem_read(0x475, 1)[0] == hdd
        assert bytes(model.cpu.mem_read(0x104, 4)) == (struct.pack('<HH', 0xE0, model.segment) if hdd else bytes(4))
        assert model.cmos[0x12] == (0xF0 if hdd else 0) and model.cmos[0x19] == (47 if hdd else 0)
        if not hdd:
            assert bytes(model.cpu.mem_read(model.base + 0x2E, 4)) == bytes(4)
            assert bytes(model.cpu.mem_read(model.base + 0x140, 1)) == b'\x00'
        published = bytes(model.cpu.mem_read(model.base + 0x20, 0xD4))
        model.open([0x50, 28, 0x50, 0x50, 0x4D, 1, 1, 28])
        assert bytes(model.cpu.mem_read(model.base + 0x20, 0xD4)) == published
        assert loaded(model)[1] == hdd


def floppy_policy():
    for types in (0, 0x40, 2, 0x42, 0x24, 0x44):
        model = Setup()
        settings_fixture(model, types=types)
        model.call('settings_load')
        model.call('init_floppy')
        a, b = types >> 4, types & 15
        assert bytes(model.cpu.mem_read(model.base + 0x80, 2)) == bytes((a, b))
        equipment = struct.unpack('<H', model.cpu.mem_read(0x410, 2))[0]
        span = 2 if b else int(bool(a))
        assert bool(equipment & 1) == bool(span)
        if span:
            assert (equipment >> 6 & 3) + 1 == span
        model.cpu.mem_write(0x13 * 4, struct.pack('<HH', rtc.symbol('int13'), 0xF000))
        for unit, kind in enumerate((a, b)):
            model.setup(ah=8, cx=0, dx=unit, flags=0x202)
            model.cpu.mem_write(0x90000, b'\xcd\x13\x90')
            model.cpu.emu_start(0x90000, 0x90002, count=100000)
            assert bool(model.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1) == (not kind)
            if kind:
                assert model.cpu.reg_read(x.UC_X86_REG_BL) == kind
                assert model.cpu.reg_read(x.UC_X86_REG_DL) == span


def post_seek_policy():
    for seek in (0x5A, 0xA5):
        model = Setup()
        settings_fixture(model, seek=seek)
        model.call('settings_load')
        before = bytes(model.cmos)
        # Inspect after Discard returns, retaining the opposite unsaved draft.
        model.open([0x50, 0x50, 28, 0x50, 0x50, 0x50, 0x50, 0x4D, 1, 1, 28])
        assert model.cpu.mem_read(model.base + 0x183, 1)[0] == (seek == 0xA5)
        assert loaded(model)[3] == (seek == 0x5A)
        model.call('init_floppy')
        model.call('post_floppy_seek')
        assert any(c[0] in (4, 7, 15) for c in model.fdc_log) == (seek == 0x5A)
        assert bytes(model.cmos) == before and not model.writes
    for base_valid in (False, True):
        model = Setup()
        settings_fixture(model, seek=0xA5)
        if not base_valid:
            model.cmos[0x3B] = 2
            model.cmos[0x3D] = -(sum(model.cmos[0x38:0x3D]) + model.cmos[0x10]) & 255
        model.writes.clear()
        model.call('settings_load')
        model.call('init_floppy')
        model.call('post_floppy_seek')
        assert any(c[0] in (7, 15, 4) for c in model.fdc_log) == (not base_valid)
        assert not model.writes
    model = Setup()
    model.open(DRIVE_EDIT + [0x44, 28])
    model.call('settings_load')
    model.call('init_floppy')
    model.call('post_floppy_seek')
    assert not any(c[0] in (7, 15, 4) for c in model.fdc_log), 'saved Off ignored'


def post_seek_mechanics():
    for stuck, retries, fail in ((None, [], False), (True, [], True), (False, [], True),
                                  (None, [0x70, 0x20], False), (None, [0x70, 0x70], True),
                                  (None, [0x40], True)):
        model = Setup()
        settings_fixture(model, types=0x40)
        model.track_zero[0] = stuck
        model.recal_results[0] = list(retries)
        model.script = [28]
        model.call('settings_load')
        model.call('init_floppy')
        model.call('post_floppy_seek')
        assert bool(model.cpu.mem_read(model.base + 0x176, 1)[0]) == fail, (stuck, retries)
        assert sum(c[0] == 7 for c in model.fdc_log) == max(1, len(retries))
        assert all(c[0] in (3, 4, 7, 8, 15, 0x12, 0x13) for c in model.fdc_log)
        if not fail:
            assert [c for c in model.fdc_log if c[0] == 15] == [(15, 0, n) for n in (48, *range(8, -1, -1))]
            assert bytes(model.cpu.mem_read(model.base + 0x178, 2)) == b'\x04\x00'
        assert model.fdc_dor == 0x0C and model.cpu.mem_read(model.base + 0x86, 1) == b'\x00'
        assert ('Floppy A seek error.' in model.console) == fail
    model = Setup()
    settings_fixture(model, types=0x40)
    model.fdc_timeout = 0
    model.script = [28]
    model.call('settings_load')
    model.call('init_floppy')
    model.call('post_floppy_seek')
    assert model.cpu.mem_read(model.base + 0x179, 1) == b'\x80'
    # Both drive widths use OEM's POST rate, without changing normal I/O timing.
    for kind in range(1, 6):
        model = Setup()
        settings_fixture(model, types=kind << 4)
        model.call('settings_load')
        model.call('init_floppy')
        rates = []
        model.cpu.hook_add(UC_HOOK_INSN, lambda c, p, s, v, u: rates.append(v) if p == 0x3F7 else None,
                           None, 1, 0, x.UC_X86_INS_OUT)
        model.call('post_floppy_seek')
        targets = (39 if kind == 1 else 48, *range(8, -1, -1))
        assert [c for c in model.fdc_log if c[0] == 15] == [(15, 0, n) for n in targets]
        assert rates[-1] == 2 and model.positions[0] == 0
        model.cpu.reg_write(x.UC_X86_REG_SI, 0)
        model.call('fdc_prepare')
        assert rates[-1] == (2, 0, 2, 0, 3)[kind - 1]


def post_seek_drives():
    for types, faults in ((0, (None, None)), (0x40, (None, None)), (4, (None, None)),
                          (0x44, (None, None)), (0x44, (None, True)), (0x44, (True, None))):
        model = Setup()
        settings_fixture(model, types=types)
        model.track_zero = list(faults)
        model.script = [28]
        model.call('settings_load')
        model.call('init_floppy')
        model.call('post_floppy_seek')
        units = [c[1] for c in model.fdc_log if c[0] == 7]
        assert units == ([0] if types >> 4 else []) + ([1] if types & 15 else [])
        assert ('Floppy A seek error.' in model.console) == bool(faults[0])
        assert ('Floppy B seek error.' in model.console) == bool(faults[1])


def post_tones():
    for choice in ('defaults', 'discard'):
        model = Setup()
        model.cmos[8] = 0
        model.script = [28] if choice == 'defaults' else [0xE0, 0x53]
        model.call('post_clock_alert')
        assert model.cpu.mem_read(model.base + 0x175, 1) == b'\x01'
        if choice == 'discard':
            model.script = [1, 28]
            model.call('setup_post_gate')
        previous = len(model.pit_writes)
        model.call('post_success_tone')
        assert len(model.pit_writes) == previous, 'clock error falsely sounded success'
    for error in (False, True):
        model = Setup()
        model.cpu.mem_write(model.base + 0x175, bytes((int(error),)))
        model.call('post_success_tone')
        if error:
            assert not model.pit_writes
            model.call('post_error_tone')
        notes = (2712, 3419, 4571) if error else (2281, 1810, 1522)
        assert model.pit_writes == [(p, v) for n in notes for p, v in ((0x43, 0xB6), (0x42, n & 255), (0x42, n >> 8))]
        assert model.idles == (7 if error else 6)
        assert model.speaker == 0xA0 and all(v & 0xFC == 0xA0 for v in model.speaker_writes)
    model = Setup()
    model.scans([0x1D, 0x38])
    scans = [0xE0, 0x53]
    def reset_during_note(cpu, address, size, unused):
        if model.speaker & 3 == 3 and scans and cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200:
            model.pending.append(scans.pop(0))
            rtc.Clock.interrupt(model, cpu, 9, None)
    model.cpu.hook_add(UC_HOOK_CODE, reset_during_note)
    model.call('post_success_tone')
    assert not scans and model.warm and model.speaker == 0xA0
    assert model.posts[-2:] == [0x90, 0x91]


def post_error_input():
    for event in ('ordinary', 'delete', 'pause-delete', 'cad'):
        model = Setup()
        settings_fixture(model, types=0x40)
        model.track_zero[0] = True
        model.call('settings_load')
        model.call('init_floppy')
        model.scans([28])  # Stale event before the notice.
        scans = {'ordinary': [28], 'delete': [0xE0, 0x53],
                 'pause-delete': [0xE1, 0x1D, 0x45, 0xE1, 0x9D, 0xC5, 0xE0, 0x53, 0xE0, 0x53],
                 'cad': [0x1D, 0x38, 0xE0, 0x53]}[event]
        def deliver(cpu, address, size, unused):
            if bytes(cpu.mem_read(address, 1)) == b'\xf4' and model.idles >= 10 and scans:
                assert model.fdc_dor == 0x0C and model.cpu.mem_read(model.base + 0x86, 1) == b'\x00'
                model.pending.append(scans.pop(0))
        model.cpu.hook_add(UC_HOOK_CODE, deliver)
        model.call('post_floppy_seek')
        assert not scans and model.idles >= 10
        assert model.warm == (event == 'cad')
        if event in ('delete', 'pause-delete'):
            model.script = [1, 28]
            model.call('setup_post_gate')
            assert model.setup_entries == 1
        if not model.warm:
            previous = len(model.pit_writes)
            model.call('post_success_tone')
            assert len(model.pit_writes) == previous, 'acknowledged error falsely sounded success'

    # Continue CAD in the same execution through full warm POST, not just
    # the decoder's warm-entry target. Ordinary input is the no-reset contrast.
    for phase in ('detection', 'notice'):
        for event in ('ordinary', 'cad'):
            model = production_post_model()
            schema2_fixture(model, types=0x40 if phase == 'notice' else 0,
                            flags=0x13, order=(2, 0, 0))
            if phase == 'notice': model.fdc_timeout = 0
            saved = bytes([model.cmos[0x10]]) + bytes(model.cmos[0x33:])
            hops, resets, delivered = [], [], []
            def boundary(m, name):
                hops.append(name)
                if phase == 'detection' and name == 'chipset_visible_ram_test' and not delivered:
                    m.pending.extend([0x1D, 0x38, 0xE0, 0x53] if event == 'cad' else [28])
                    delivered.append(True)
            def warm_entry(cpu, address, size, unused):
                resets.append(True)  # Observe only; execute the production hop.
            model.cpu.hook_add(UC_HOOK_CODE, warm_entry, None,
                               model.warm_entry, model.warm_entry)
            def deliver(m, address):
                if m.cpu.mem_read(address, 1) != b'\xf4': return
                if phase != 'notice': return
                target = 'post_notice_wait'
                if not delivered and hops and hops[-1] == target:
                    assert not m.boot_reads
                    m.pending.extend([0x1D, 0x38, 0xE0, 0x53] if event == 'cad' else [28])
                    delivered.append(True)
                elif phase == 'notice' and event == 'cad' and resets and hops[-1] == target and len(delivered) == 1:
                    m.pending.append(28)  # Acknowledge the same absent drive after warm POST.
                    delivered.append(True)
            model.startup_observer = boundary
            model.event_observer = deliver
            model.startup(reset=True, production_controls=True, through_boot=True)
            count = 2 if event == 'cad' else 1
            assert delivered and len(resets) == count - 1, (phase, event, hops)
            for name in ('init_memory', 'settings_load', 'chipset_visible_ram_test'):
                assert hops.count(name) == count, (phase, event, name, hops)
            assert hops.count('post_floppy_seek') == (count if phase == 'notice' else 1), hops
            assert hops.count('setup_post_gate') == 1, hops
            assert hops[-6:] == ['chipset_late_cache', 'init_external_cache',
                                 'option_rom_discovery', 'post_debug_summary',
                                 'int19', 'boot_sector'], hops
            assert model.cpu.mem_read(0x7C00, 4) == b'BOOT'
            assert model.cpu.mem_read(0x49E, 1) == b'\0'  # Runtime gate, no Setup request.
            assert model.cpu.mem_read(0x484, 3) == b'\x18\x10\0'
            assert bytes([model.cmos[0x10]]) + bytes(model.cmos[0x33:]) == saved
            assert model.cmos[0x36] == 0, 'CAD must not load recovery defaults'
            print(f'POST {phase}/{event}: actual warm continuation, retained policy and BOOT PASS')


def themes():
    import sys
    importlib.import_module('test-setup-themes').run(sys.modules[__name__])


CASES = {'themes': themes, 'post-entry': post_entry, 'pause-entry': pause_entry, 'text-ui': text_ui,
         'context-help': context_help,
         'immediate-clock': immediate_clock, 'clock-domain': immediate_clock,
         'clock-repair': clock_repair, 'idle-clock': idle_clock,
         'partial-clock-repair': partial_clock_repair,
         'clock-defaults': clock_defaults,
         'clock-alert': clock_alert,
         'clock-alert-delete': clock_alert_delete,
         'shared-state': shared_state, 'unsaved-reset': reset}
CASES.update({'settings-validity': settings_validity, 'save-all': save_all,
              'settings-save': settings_save, 'hdd-policy': hdd_policy,
              'floppy-policy': floppy_policy, 'post-seek-policy': post_seek_policy,
              'post-seek-mechanics': post_seek_mechanics, 'post-seek-drives': post_seek_drives,
              'post-tones': post_tones, 'post-error-input': post_error_input})


def choice_menus():
    for prefix, offset, initial, choices in (
        ([0x50, 15], 0x180, 4, ['Not installed', '360 KB, 5.25 in', '1.2 MB, 5.25 in',
                                     '720 KB, 3.5 in', '1.44 MB, 3.5 in', '2.88 MB, 3.5 in']),
        ([0x50, 15, 0x50], 0x180, 2, ['Not installed', '360 KB, 5.25 in', '1.2 MB, 5.25 in',
                                                   '720 KB, 3.5 in', '1.44 MB, 3.5 in', '2.88 MB, 3.5 in']),
        ([0x50, 15, 0x50, 0x50, 28], 0x181, 1, ['Disabled', 'Enabled']),
        ([0x50, 15, 0x50, 0x50, 0x50, 28], 0x184, 1, ['Disabled', 'Enabled']),
        ([0x50, 0x50, 15], 0x182, 1, ['Disabled', 'Floppy', 'Hard Disk', 'CD-ROM', 'Other']),
        ([0x50, 0x50, 15, 0x50, 0x50, 0x50, 0x50], 0x183, 1, ['Disabled', 'Enabled'])):
        for apply in (False, True):
            model = Setup()
            old = bytes(model.cmos)
            seen = []
            def observe(m):
                if m.text(8, 26, 12) == 'SELECT VALUE':
                    for index, text in enumerate(choices):
                        assert m.text(10 + index, 26, len(text)) == text
                    seen.append(True)
            model.observer = observe
            exit_keys = [1, 1, 1, 28] if offset in (0x181, 0x184) else [1, 1, 28]
            model.open(prefix + [28, 0x50, 28 if apply else 1] + exit_keys)
            assert seen and bytes(model.cmos) == old
            expected = ((initial + 1) % len(choices)) if apply else initial
            value = model.cpu.mem_read(model.base + offset, 1)[0]
            if offset == 0x180:
                value = value >> 4 if len(prefix) == 2 else value & 15
            assert value == expected, (prefix, apply, value, expected)
    # Slave extension is additive; a missing tag retains Auto.
    model = Setup(segment=0x8FC0)
    settings_fixture(model)
    model.cmos[0x3F] = 0xA5
    model.call('settings_load')
    assert model.cpu.mem_read(model.base + 0x177, 1) == b'\x00'
    model.open([1, 28])  # Production Setup initializes every additive draft.
    model.cpu.mem_write(model.base + 0x184, b'\x01')
    model.call('settings_save')
    assert not model.cmos[0x3B] & 0x40
    model.call('settings_load')
    assert model.cpu.mem_read(model.base + 0x177, 1) == b'\x01'


def summary_grid_limits():
    # Independent80x25 expected grids; reserved and neighboring cells are exact.
    for banks, indices, ports, warnings, mode in ((0x0004,'0',(0,)*7,0,0),
            (0x4444,'0 1 2 3',(0,)*7,0,0),
            (0x4444,'0 1 2 3',(0,)*7,0,0x20),
            (0x4444,'0 1 2 3',(0x3F8,0x2F8,0x3E8,0x2E8,0x378,0x3BC,0x278),31,0xA0),
            (0x4044,'0 1 3',(0,0x2F8,0,0,0,0x278,0),0,0x40)):
        m=Setup();m.chipset[2]=banks&255;m.chipset[3]=banks>>8;m.chipset[0x19]=3;m.chipset[4]=0x16|mode
        m.cpu.mem_write(m.base+0xD0,struct.pack('<H',64512))
        m.cpu.mem_write(0x413,struct.pack('<H',639));m.cpu.mem_write(0x410,b'\x02\0')
        m.cpu.mem_write(m.base+0x80,b'\x04\x02');m.cpu.mem_write(0x400,struct.pack('<7H',*ports))
        m.cpu.mem_write(m.base+0x175,bytes((warnings,)));m.cmos[0x36]=0x1A if warnings else 0
        m.cpu.mem_write(0x475,b'\x03')
        for offset,capacity in ((0,0x0FFFFFFF),(0x200,0x0FFFF7FF)):
            m.cpu.mem_write(m.base+offset+0x20,b'\x01')
            m.cpu.mem_write(m.base+offset+0x2E,struct.pack('<I',capacity))
            m.cpu.mem_write(m.base+offset+0x140,b'ABCDEFGHIJKLMN'+b'X'*26+b'\0')
            m.cpu.mem_write(m.base+offset+0xE0,struct.pack('<H',16383))
            m.cpu.mem_write(m.base+offset+0xE2,b'\xFF');m.cpu.mem_write(m.base+offset+0xEE,b'\x3F')
        grid=bytearray(b' \x07'*2000)
        def put(row,col,text,color=7):
            assert 0<=col and col+len(text)<80
            grid[(row*80+col)*2:(row*80+col+len(text))*2]=bytes(v for c in text for v in (ord(c),color))
        for col in range(80):grid[col*2:col*2+2]=b' \x1F'
        for row in range(1,12):
            grid[row*160:row*160+2]=b'\xBA\x0B';grid[row*160+158:row*160+160]=b'\xBA\x0B'
        for row in (1,5,8,11):
            grid[row*160:(row+1)*160]=b'\xCD\x0B'*80
            grid[row*160:row*160+2]=bytes((0xC8 if row==11 else 0xC9 if row==1 else 0xCC,11))
            grid[row*160+158:row*160+160]=bytes((0xBC if row==11 else 0xBB if row==1 else 0xB9,11))
        put(0,3,'Compaq Presario 800',27);put(0,37,'bAIos',31)
        put(0,58,'ROM build:',27);put(0,69,bytes(m.cpu.mem_read(0xFFFF5,8)).decode(),31)
        for row,left,right in ((2,'Processor','Base Memory'),(3,'FPU','Extended Memory'),
                              (4,'L2 cache','Memory Banks'),
                              (6,'Floppy Drive A','COM Ports'),(7,'Floppy Drive B','LPT Ports')):
            put(row,3,left,11);put(row,40,right,11)
        put(2,20,'Unknown');put(3,20,'Detected');put(4,20,'128');put(4,25,'KB')
        put(2,58,'639');put(2,64,'KB')
        put(3,58,'64512');put(3,64,'KB');put(4,58,indices+(', Interleaved' if mode else ''))
        put(6,20,'1.44 MB, 3.5 in');put(7,20,'1.2 MB, 5.25 in')
        put(6,58,' '.join(f'{v:04X}' for v in ports[:4] if v))
        put(7,58,' '.join(f'{v:04X}' for v in ports[4:] if v))
        for row,name,capacity in ((9,'Primary IDE Master','131071'),(10,'Primary IDE Slave','131070')):
            put(row,3,name,11);put(row,23,'ABCDEFGHIJKLMN'+'X'*26)
            put(row,64,f'[{capacity} MB PIO]')
            put(row,64,'[',11);put(row,78,']',11)
        if warnings:
            put(13,3,'POST warnings:',14)
            for col,label in ((18,'Clock'),(24,'Floppy'),(31,'Settings'),(40,'Keyboard'),(49,'ROM')):put(13,col,label,14)
            put(13,54,'RAM recovered',12)
        before=bytes(m.cpu.mem_read(m.base,0x400));saved=bytes(m.cmos);registers=dict(m.chipset)
        m.call('post_debug_summary')
        actual=bytes(m.cpu.mem_read(0xB8000,4000))
        assert actual==grid, [(i//160,(i%160)//2,actual[i:i+2],grid[i:i+2]) for i in range(0,4000,2) if actual[i:i+2]!=grid[i:i+2]][:12]
        assert bytes(m.cpu.mem_read(m.base,0x400))==before and bytes(m.cmos)==saved and m.chipset==registers
        assert m.cpu.mem_read(0x450,2)==bytes((0,14 if warnings else 13))
    print('post-summary exact80x25 grids:row0 header, blank below closed table, anchors, bounds, full/sparse ports/banks, maximum fields and all warnings PASS',flush=True)


def processor_summary():
    for signature,name in ((0x1531,'Pentium P24T'),(0x1532,'Pentium P24T'),
                           (0x0521,'Pentium'),(0x1544,'Pentium'),
                           (0x0430,'486DX2'),(0x0480,'486DX4'),
                           (0x0000,'Unknown'),(0x0630,'Unknown')):
        for cache,label in ((0,'Not detected'),(0x33,'128'),(0xB6,'1024')):
            model=Setup()
            model.cpu.mem_write(model.base+0xD4,struct.pack('<H',signature))
            model.chipset[0x19]=cache
            before=bytes(model.cpu.mem_read(model.base,0x400))
            model.call('post_debug_summary')
            assert model.text(2,20,len(name)) == name
            assert model.text(2,20+len(name),40-20-len(name)) == ' '*(40-20-len(name))
            assert model.text(4,20,len(label)) == label
            assert bytes(model.cpu.mem_read(model.base,0x400)) == before
    print('Processor/L2 summary: P24T63/83 signatures, other models unchanged, independent register19 size rendering PASS',flush=True)
    for signature, name in ((0x1532, 'Pentium P24T'), (0x0430, '486DX2'),
                            (0x0000, 'Unknown'), (0x0630, 'Unknown')):
        for cold in (False, True):
            post = production_post_model()
            schema2_fixture(post, types=0, flags=0x13, order=(2, 0, 0))
            post.cpu.mem_write(post.base+0xD4, struct.pack('<H', signature))
            post.cpu.reg_write(x.UC_X86_REG_EDX, signature)
            post.startup(reset=cold, production_controls=True, through_boot=True)
            assert bytes(post.cpu.mem_read(post.base+0xD4, 2)) == struct.pack('<H', signature)
            assert post.text(2, 20, len(name)) == name
            assert bytes(post.cpu.mem_read(0x7C00, 4)) == b'BOOT'
    print('Processor signature: real cold/warm POST through identity publication, summary and boot PASS', flush=True)


def post_summary():
    summary_grid_limits()
    # Normal output inherits the real cold-POST cursor, including a warning row.
    for missing_keyboard in (False,True):
        m=production_post_model()
        schema2_fixture(m,types=0,flags=0x13,order=(2,0,0))
        m.device_present=not missing_keyboard
        m.startup(reset=True,production_controls=True,through_boot=True)
        row=14 if missing_keyboard else 13
        assert m.cpu.mem_read(0x450,2)==bytes((0,row))
        assert m.cpu.mem_read(0xB8000+12*160,160)==b' \x07'*80
        message=bytes(m.cpu.mem_read(0xF0000,65536)).find(b'No boot device available\r\n\0')
        assert message>=0
        m.cpu.reg_write(x.UC_X86_REG_SI,message)
        m.call('print_string')
        assert m.text(row,0,24)=='No boot device available'
        assert m.cpu.mem_read(0x450,2)==bytes((0,row+1))
        if missing_keyboard: assert m.text(13,40,8)=='Keyboard'
    # Rendering reads active/published state and cannot consume or demand input.
    for segment in (0x9FC0, 0x8FC0):
        m = Setup(segment=segment)
        m.call('setup_post_gate')
        m.cpu.mem_write(m.base+0x180, b'\x53')  # Unsaved draft differs from logical4/2.
        m.cpu.mem_write(m.base+0x140, b'ATA MASTER FIXTURE\0')
        m.cpu.mem_write(m.base+0x20, b'\x01')
        m.cpu.mem_write(m.base+0x2E, struct.pack('<I', 3970048))
        m.cpu.mem_write(m.base+0xE0, struct.pack('<H', 984))
        m.cpu.mem_write(m.base+0xE2, b'\x40')
        m.cpu.mem_write(m.base+0xEE, b'\x3f')
        m.cpu.mem_write(m.base+0x369, b'\x01')
        m.cpu.mem_write(m.base+0x340, b'ATAPI SLAVE FIXTURE\0')
        m.cpu.mem_write(0x410, b'\x02\x00')
        m.cpu.mem_write(0x475, b'\x01')
        m.cpu.mem_write(0x400, struct.pack('<7H', 0x3F8, 0x2F8, 0x3E8, 0x2E8, 0x378, 0, 0))
        before = bytes(m.cpu.mem_read(m.base+0x170, 0x79))
        m.scans([0xE0, 0x53, 0x53])  # Both late Delete forms retain a closed gate.
        queued = bytes(m.cpu.mem_read(0x41A, 4))
        idle = m.idles
        m.call('post_debug_summary')
        assert m.idles == idle and not m.script, 'summary waited for input'
        assert m.cpu.mem_read(0x484, 3) == b'\x18\x10\0'
        assert m.text(0,37, 5) == 'bAIos'
        assert m.text(2,20, 7).strip() == 'Unknown'
        assert m.text(3,20, 8) == 'Detected'
        assert m.text(4,20, 10).strip() == '128  KB'
        assert m.text(2,58, 3) == '639' and m.text(3,58, 4) == '7168'
        assert m.text(6,20, len('1.44 MB, 3.5 in')) == '1.44 MB, 3.5 in'
        assert m.text(7,20, len('1.2 MB, 5.25 in')) == '1.2 MB, 5.25 in'
        assert m.text(6,58, 19) == '03F8 02F8 03E8 02E8'
        assert m.text(7,58, 4) == '0378' and m.text(7,62, 17) == ' '*17
        assert m.text(9,23, 18) == 'ATA MASTER FIXTURE'
        assert m.text(9,63,16) == ' [1938 MB PIO]  '
        assert m.text(10,23, 19) == 'ATAPI SLAVE FIXTURE'
        assert m.text(10,63,16) == ' [ATAPI PIO]    '
        assert bytes(m.cpu.mem_read(m.base+0x170, 0x79)) == before
        assert bytes(m.cpu.mem_read(0x41A, 4)) == queued
        assert m.cpu.mem_read(m.base+0xF4, 1) == b'\0' and m.cpu.mem_read(0x49E, 1) == b'\x02'
        screen = bytes(m.cpu.mem_read(0xB8000,4000))[::2].decode('cp437')
        for forbidden in ('Debug', 'register', 'CMOS', 'stage/status', 'Press any key', 'RAMSET', 'CPU L1 cache', 'Option ROM disks'):
            assert forbidden not in screen, forbidden
    for requested, code, text in ((0,0,'Disabled'),(1,0,'Not detected')):
        m=Setup()
        m.chipset[0x19]=code
        m.cpu.mem_write(m.base+0x69, bytes((0x30|requested,)))
        m.cmos[0x36]=0x1A
        m.cpu.mem_write(m.base+0x175,b'\x07')
        m.call('post_debug_summary')
        assert m.text(4,20,len(text))==text
        assert m.text(13,54,13)=='RAM recovered'
        assert m.text(13,18,5)=='Clock' and m.text(13,24,6)=='Floppy' and m.text(13,31,8)=='Settings'
    for code in range(1,7):
        m=Setup(); m.chipset[0x19]=0xB0|code
        m.call('post_debug_summary')
        assert m.text(4,20,len(str(16<<code)))==str(16<<code)
    # Actual detection distinguishes packet, absent and enabled ATA; geometry is effective.
    ide=importlib.import_module('test-ide-options')
    class SummaryDisk(ide.Disk):
        text=Setup.text
        def port_out(self,cpu,port,size,value,unused):
            if port in (0xF9,0xFB,0xEC,0xED): return Setup.port_out(self,cpu,port,size,value,unused)
            return super().port_out(cpu,port,size,value,unused)
        def port_in(self,cpu,port,size,unused):
            if port==0xED: return Setup.port_in(self,cpu,port,size,unused)
            return super().port_in(cpu,port,size,unused)
        def interrupt(self,cpu,vector,unused):
            if vector==0x10: return Setup.interrupt(self,cpu,vector,unused)
            return super().interrupt(cpu,vector,unused)
    m=SummaryDisk(('packet','absent')); m.vga=[]; m.vga_bx=[]; m.console=''; m.chipset_index=0; m.chipset={0x19:0}
    ide.detect(m)
    m.call('post_debug_summary')
    assert m.text(9,64,11)=='[ATAPI PIO]' and m.text(10,23,12)=='Not detected'
    for cold in (False,True):
        for action in ('none','discard','save','late-delete','late-decimal'):
            m=production_post_model()
            schema2_fixture(m,types=0,flags=0x13,order=(2,0,0))
            model_name=b'PRODUCTION ATA FIXTURE'.ljust(40,b' ')
            m.identify[54:94]=bytes(value for i in range(0,40,2) for value in model_name[i:i+2][::-1])
            seen=[]
            def observe(model,name):
                if name=='init_floppy' and action in ('discard','save') and not seen:
                    model.pending += [0xE0,0x53]
                    seen.append('delete')
                if name=='setup_main':
                    # Edit a draft and reach the real discard/F10 path.
                    model.script=([0x50,15,0x4D,1,1,28] if action=='discard' else
                                  [0x50,0x50,15]+[0x50]*5+[0x4B,0x44,28])
                    seen.append('setup')
                if name=='chipset_late_cache' and action=='late-delete' and 'prefix' not in seen:
                    seen.append('prefix'); model.pending.append(0xE0)
                    rtc.Clock.interrupt(model,model.cpu,9,None)
                if name=='post_debug_summary':
                    assert model.cpu.mem_read(0x49E,1)==b'\x02'
                    assert model.cpu.mem_read(0x484,3)==b'\x18\x10\0'
                    if action.startswith('late-') and 'late' not in seen:
                        seen.append('late'); model.pending.append(0x53)
                        rtc.Clock.interrupt(model,model.cpu,9,None)
                    assert model.cpu.mem_read(model.base+0xF4,1)==b'\0'
                if name=='int19':
                    assert model.text(0,37,5)=='bAIos'
                    assert model.text(6,20,13)=='Not installed'
                    assert model.text(9,23,14)=='PRODUCTION ATA'
                    assert model.text(3,20,8)=='Detected'
                    if action=='discard':
                        assert model.cpu.mem_read(model.base+0x180,1)==b'\x10'
                        assert model.cpu.mem_read(model.base+0x170,1)==b'\0'
                    assert model.text(10,23,12)=='Not detected'
                    assert model.text(9,63,16)==' [1938 MB PIO]  '
                    assert model.text(3,58,4)=='7168'
                    assert model.text(4,20,12)=='Not detected'
                    assert model.cpu.mem_read(0x484,3)==b'\x18\x10\0'
                    assert not model.script
                    seen.append('summary')
            m.startup_observer=observe
            m.startup(reset=cold,production_controls=True,through_boot=True)
            assert m.cpu.mem_read(0x7C00,4)==b'BOOT'
            assert seen.count('setup')==int(action in ('discard','save'))
            assert seen.count('summary')==1 and m.cpu.mem_read(0x49E,1)==b'\0'
            print(f'post-summary composed {"cold" if cold else "warm"}/{action}: PASS',flush=True)
    post_summary_causes()
    absent=production_post_model()
    schema2_fixture(absent,types=0,flags=0x13,order=(2,0,0))
    absent.device_present=False
    absent.startup(reset=True,production_controls=True,through_boot=True)
    assert absent.cpu.mem_read(absent.base+0x175,1)==b'\x08'
    assert absent.text(13,40,8)=='Keyboard' and absent.cpu.mem_read(0x7C00,4)==b'BOOT'
    assert 'Keyboard not detected' in absent.console and 'Press any key to continue' not in absent.console
    print('post-summary: active/draft, detected/absent/packet, effective geometry/cache/ports, no-input cold/warm boot and Setup/late input PASS',flush=True)


def post_summary_causes():
    # Publication and IDENTIFY owners remain in the composed production path.
    for master, slave in (('ata','absent'),('ata','packet'),('ata','ata'),('absent','ata'),('packet','ata')):
        for cold in (False, True):
            m = production_post_model(kinds=(master, slave), peripherals=True)
            schema2_fixture(m, types=0, flags=0x13, order=(2, 0, 0))
            m.startup(reset=cold, production_controls=True, through_boot=True)
            assert tuple(struct.unpack('<7H', m.cpu.mem_read(0x400, 14))) == (0x3F8, 0x2F8, 0x3E8, 0x2E8, 0x378, 0x3BC, 0x278)
            assert m.text(6,58, 19) == '03F8 02F8 03E8 02E8'
            assert m.text(7,58, 14) == '0378 03BC 0278'
            if master == 'ata':
                assert m.text(9,23,12) == 'FIXTURE ATA0'
                assert m.text(9,63,16) == ' [64 MB PIO]    '
                assert m.cpu.mem_read(m.base+0x20,1) == b'\x01'
                assert m.cpu.mem_read(m.base+0x2E,4) == struct.pack('<I',131072)
            elif master == 'packet':
                assert m.text(9,23,14) == 'FIXTURE PACKET'
                assert m.cpu.mem_read(m.base+0x20,1) == b'\0' and m.cpu.mem_read(m.base+0x169,1) == b'\x01'
                assert m.text(9,63,16) == ' [ATAPI PIO]    ' and (0,0xA1) in m.disk_device.selected_commands
            else:
                assert m.text(9,23,12) == 'Not detected' and m.text(9,40,39) == ' '*39
                assert m.cpu.mem_read(m.base+0x20,1) == b'\0' and m.cpu.mem_read(m.base+0x169,1) == b'\0'
            if slave == 'absent':
                assert m.text(10,23, 12) == 'Not detected'
                assert m.cpu.mem_read(m.base+0x220, 1) == b'\0'
                assert m.cpu.mem_read(m.base+0x369, 1) == b'\0'
            elif slave == 'packet':
                assert m.text(10,23, 14) == 'FIXTURE PACKET'
                assert m.text(10,63,16) == ' [ATAPI PIO]    '
                assert m.cpu.mem_read(m.base+0x220, 1) == b'\0'
                assert m.cpu.mem_read(m.base+0x369, 1) == b'\x01'
                assert (1, 0xA1) in m.disk_device.selected_commands
            else:
                assert m.text(10,23, 12) == 'FIXTURE ATA1'
                assert m.text(10,63,16) == ' [128 MB PIO]   '
                assert m.cpu.mem_read(m.base+0x220, 1) == b'\x01'
                assert m.cpu.mem_read(m.base+0x22E, 4) == struct.pack('<I', 262144)
            hops = m.startup_hops
            assert hops.index('init_peripherals') < hops.index('ata_detect_primary') < hops.index('setup_post_gate') < hops.index('chipset_late_cache') < hops.index('post_debug_summary') < hops.index('int19') < hops.index('boot_sector')
            assert m.cpu.mem_read(0x7C00, 4) == b'BOOT' and m.cpu.mem_read(0x49E, 1) == b'\0'
            assert m.cpu.mem_read(0x484, 3) == b'\x18\x10\0' and not m.script
            print(f'post-summary publication/detection {"cold" if cold else "warm"}/{master}+{slave}: PASS', flush=True)
    # Reuse the existing SRAM decoder; no cache decision or result is replaced.
    cache_module = importlib.import_module('test-external-cache')
    for broken, primary in ((False, True), (False, False), (True, False)):
        for cold in (False, True):
            m = production_post_model()
            schema2_fixture(m, types=0, flags=0x13, order=(2, 0, 0))
            policy = bytearray.fromhex('96160000883830000031285555555555aa00000000030003')
            if not primary: policy[4] &= ~8
            m.cmos[0x69:0x80] = bytes((0xC2, -(0xC2+sum(policy)) & 255)) + policy[:21]
            m.cmos[0x33:0x36] = policy[21:]
            cache = cache_module.Cache(128*1024, broken=broken)
            hooks = []
            def direct(cpu, access, address, size, value, unused):
                cache.external_cache = m.chipset.get(0x19, 0)
                if cache.external_cache & 7 == 7 and not 0xA0000 <= address < 0x100000:
                    cache.ramtmg, cache.miscset, cache.xctl = (m.chipset[r] for r in (1, 7, 0x24))
                    cache.memory(cpu, access, address, size, value, unused)
            def before_probe(model, name):
                if name == 'chipset_late_cache':
                    assert model.cpu.mem_read(model.base+0x69, 1) == b'\x31'
                    assert model.chipset[0x19] == 0 and model.cpu.mem_read(0x49E, 1) == b'\x02'
                    hooks.append(model.cpu.hook_add(cache_module.UC_HOOK_MEM_READ | cache_module.UC_HOOK_MEM_WRITE, direct, None, 0x10000, 0x200004))
                elif name == 'post_debug_summary':
                    assert model.text(3, 24, 8).strip() == ('Enabled' if primary else 'Disabled')
                    assert model.text(14, 24, 12).strip() == ('Not detected' if broken else 'Enabled, 128')
                    if not broken: assert model.text(14, 39, 2) == 'KB'
            m.startup_observer = before_probe
            try:
                m.startup(reset=cold, production_controls=True, through_boot=True)
                assert cache.direct_reads > 0 and m.record() == policy
                assert m.chipset[0x19] == (0 if broken else 0x33)
                assert m.cpu.mem_read(m.base+0x7A, 1) == bytes((0x14 if broken else 0x15,))
                assert bool(m.cpu.reg_read(x.UC_X86_REG_CR0) & 0x60000000) == (not primary)
                label = 'Enabled' if primary else 'Disabled'
                assert m.text(4,20, 12 if broken else 7) == ('Not detected' if broken else '128  KB')
                assert m.startup_hops.index('chipset_late_cache') < m.startup_hops.index('init_external_cache') < m.startup_hops.index('post_debug_summary') < m.startup_hops.index('int19')
                assert m.cpu.mem_read(0x7C00, 4) == b'BOOT' and m.cpu.mem_read(0x49E, 1) == b'\0'
                print(f'post-summary causal cache {"cold" if cold else "warm"}/L1={label}/128KiB broken={broken}: PASS', flush=True)
            finally:
                for hook in hooks: m.cpu.hook_del(hook)


# Retained chipset contract names this test entry point.
debug_summary = post_summary

CASES.update({'choice-menus': choice_menus, 'post-summary': post_summary,
              'cmos-recovery': cmos_recovery})


def run_86box(only=None):
    floppy = importlib.import_module('floppy-matrix')
    build = rtc.BUILD
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    exe = shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA']) /
        'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    roms = build / '86box/roms'
    wrapper = roms / 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    production = (build / 'baios-presario800.bin').read_bytes()
    scratch = build / 'tmp'
    scratch.mkdir(exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='setup-', dir=scratch) as name:
            work = Path(name)
            system = work / 'test.rom'
            if only is None or 'recovery' in only:
                floppy.run_hidden([nasm, '-f', 'bin', '-DVGA_BIOS_141', '-DEMULATOR_POST_SUMMARY_TEST', '-DEMULATOR_SETUP_TEST',
                    '-DEMULATOR_SETUP_RECOVERY', '-DEMULATOR_SETUP_BAD_CMOS',
                    '-I', str(ROOT / 'src') + '/', '-o', str(system),
                    str(ROOT / 'src/bios.asm')], check=True)
                data = bytearray(system.read_bytes())
                data[-1] = -sum(data[:-1]) & 255
                wrapper.write_bytes(production[:65536] + data)
                vm = work / 'recovery'
                vm.mkdir()
                disk = vm / 'scratch.img'
                with disk.open('xb') as out:
                    out.truncate(64 * 1024 * 1024)
                floppy.config(vm, disk, 4, 2, vm / 'a.img', vm / 'b.img')
                nvram = vm / 'nvr/d824.nvr'
                cmos = bytearray(nvram.read_bytes())
                cmos[0x38] = 0
                cmos[0xE] |= 0x80
                cmos[8], cmos[4] = 0, 0xFF
                nvram.write_bytes(cmos)
                for boot in ('recovery-and-warm-reset', 'cold-reload'):
                    result = floppy.run_hidden([exe, '-P', str(vm), '-R', str(roms),
                        '-L', str(vm / '86box.log'), '-N'], timeout=60)
                    assert result.returncode == 0x67, (boot, hex(result.returncode))
                    saved = nvram.read_bytes()
                    assert saved[0x10] == 0x40 and saved[0x38:0x3D] == b'B8\x04\x13\x01'
                    assert (sum(saved[0x38:0x40]) + saved[0x10]) & 255 == 0
                    assert saved[0x3E:0x40] == b'\x02\0' and not saved[0xE] & 0x80
                    assert saved[7:10] == bytes((1, 1, 0x80)) and saved[0x32] == 0x19
                    print('86Box CMOS defaults / ' + boot + ': PASS', flush=True)
            for absent, invalid_date, power_loss, bad_cmos in (
                    (False, False, False, False), (True, False, False, False),
                    (False, True, False, False), (False, True, True, False),
                    (False, False, False, True),
                    (False, False, False, 'clock24'), (False, False, False, 'ide-device'),
                    (False, False, False, 'ide-types'),
                    (False, False, False, 'ide-block'),
                    (False, False, False, 'ide-channel'),
                    (False, False, False, 'ide-submenu'),
                    (False, False, False, 'ide-none')):
                label = 'power-loss' if power_loss else ('invalid-date' if invalid_date else ('no-disk' if absent else 'hdd'))
                if bad_cmos is True:
                    label = 'invalid-settings'
                elif isinstance(bad_cmos, str):
                    label = bad_cmos
                if only is not None and label not in only:
                    continue
                defines = ['-DVGA_BIOS_141', '-DEMULATOR_POST_SUMMARY_TEST', '-DEMULATOR_SETUP_TEST']
                if invalid_date:
                    defines.append('-DEMULATOR_SETUP_INVALID_DATE')
                if power_loss:
                    defines.append('-DEMULATOR_SETUP_POWERLOSS')
                if bad_cmos is True:
                    defines.append('-DEMULATOR_SETUP_BAD_CMOS')
                if bad_cmos == 'clock24':
                    defines.append('-DEMULATOR_SETUP_CLOCK24')
                elif isinstance(bad_cmos, str):
                    screen = ('ide-device', 'ide-types', 'ide-block', 'ide-channel', 'ide-submenu', 'ide-none').index(bad_cmos) + 1
                    defines.append(f'-DEMULATOR_SETUP_IDE_SCREEN={screen}')
                floppy.run_hidden([nasm, '-f', 'bin'] + defines +
                                  ['-I', str(ROOT / 'src') + '/', '-o', str(system),
                                   str(ROOT / 'src/bios.asm')], check=True)
                data = bytearray(system.read_bytes())
                assert len(data) == 65536
                data[-1] = -sum(data[:-1]) & 255
                wrapper.write_bytes(production[:65536] + data)
                vm = work / label
                vm.mkdir()
                disk = vm / 'scratch.img'
                with disk.open('xb') as out:
                    out.truncate(64 * 1024 * 1024)
                floppy.config(vm, disk, 4, 2, vm / 'a.img', vm / 'b.img')
                cfg = vm / '86box.cfg'
                if absent:
                    cfg.write_text(re.sub(r'(?ms)^\[Hard disks\].*?(?=^\[)', '[Hard disks]\n', cfg.read_text()))
                nvram = vm / 'nvr/d824.nvr'
                cmos = bytearray(nvram.read_bytes())
                for index, value in ((0, 0), (2, 0), (4, 0x12), (7, 0x28), (8, 2), (9, 0x26), (0x32, 0x20)):
                    cmos[index] = value
                if invalid_date and not power_loss:
                    cmos[8] = 0
                if power_loss:
                    # 86Box synthesizes read-only VRT; seed the persisted AT
                    # power-loss diagnostic instead of writing register D.
                    cmos[0xE] |= 0x80
                if bad_cmos is True:
                    cmos[0x38] = 0

                if bad_cmos == 'clock24':
                    record = bytearray((66,56,4,0x93,1,0,2,0))
                    record[5] = -(sum(record)+cmos[0x10])&255
                    cmos[0x38:0x40] = record
                nvram.write_bytes(cmos)
                result = floppy.run_hidden([exe, '-P', str(vm), '-R', str(roms), '-L', str(vm / '86box.log'), '-N'], timeout=60)
                assert result.returncode == 0x67, ('retained VGA setup fixture', label, hex(result.returncode))
                if not absent:
                    evidence = build / 'chipset-review/setup'
                    evidence.mkdir(parents=True, exist_ok=True)
                    with disk.open('rb') as inp:
                        inp.seek(63 * 512)
                        width, height = struct.unpack('<HH', inp.read(4))
                        assert width in (640, 720) and height == 400
                        inp.seek(64 * 512)
                        pixels = inp.read(width * height * 4)
                    assert len(set(pixels)) > 3, 'actual screenshot contains no UI glyphs'
                    # Small dependency-free PNG encoder for captured BGRX pixels.
                    rows = bytearray()
                    for row in range(height):
                        rows.append(0)
                        for col in range(width):
                            offset = (row * width + col) * 4
                            rows.extend(pixels[offset:offset + 3][::-1])
                    def chunk(kind, data):
                        return struct.pack('>I', len(data)) + kind + data + struct.pack('>I', zlib.crc32(kind + data))
                    png = (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0)) +
                           chunk(b'IDAT', zlib.compress(rows)) + chunk(b'IEND', b''))
                    screenshot = 'setup-power-loss.png' if power_loss else ('setup-clock-defaults.png' if invalid_date else 'setup-standard.png')
                    if bad_cmos is True:
                        screenshot = 'setup-invalid-settings.png'
                    elif isinstance(bad_cmos, str):
                        screenshot = 'setup-' + bad_cmos + '.png'
                    (evidence / screenshot).write_bytes(png)
                print('86Box real retained VGA / ' + label + ': PASS', flush=True)
    finally:
        wrapper.write_bytes(production)
    assert wrapper.read_bytes() == production


def run_boot_86box(only=None):
    floppy = importlib.import_module('floppy-matrix')
    build = rtc.BUILD
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    exe = shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA']) /
        'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    roms = build / '86box/roms'
    wrapper = roms / 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    production = (build / 'baios-presario800.bin').read_bytes()
    # order, A type/media/signature, HDD setting/signature, expected endpoint.
    fixtures = [('a-first', 0, 4, True, True, 1, True, 0x66),
                ('hdd-first', 1, 4, True, True, 1, True, 0x67),
                ('hdd-only', 2, 4, True, True, 1, True, 0x67),
                ('hdd-only-no-fallback', 2, 4, True, True, 1, False, 0x64),
                ('hdd-disabled', 0, 4, True, True, 0, True, 0x66),
                ('a-absent', 0, 0, False, False, 1, True, 0x67),
                ('a-read-failure', 0, 4, False, False, 1, True, 0x67),
                ('a-unsigned', 0, 4, True, False, 1, True, 0x67),
                ('hdd-unsigned', 1, 4, True, True, 1, False, 0x66),
                ('no-b-fallback', 0, 4, True, False, 1, False, 0x64),
                ('no-eligible', 0, 0, False, False, 0, True, 0x63),
                ('stale-signature', 0, 4, False, False, 0, True, 0x64),
                ('missing-base', 1, 4, True, True, 1, True, 0x66),
                ('invalid-signature', 1, 4, True, True, 1, True, 0x66),
                ('invalid-schema', 1, 4, True, True, 1, True, 0x66),
                ('invalid-checksum', 1, 4, True, True, 1, True, 0x66),
                ('detection-save', 2, 4, True, True, 1, False, 0x66),
                ('cold-reload', 0, 4, True, True, 1, False, 0x66)]
    saved = None
    try:
        (build / 'tmp').mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='setup-boot-', dir=build / 'tmp') as name:
            work = Path(name)
            for label, boot, a, medium, signed_a, hdd, signed_hdd, expected in fixtures:
                if only is not None and label not in only:
                    continue
                vm = work / label
                vm.mkdir()
                system = vm / 'system.rom'
                defines = ['-DVGA_BIOS_141', '-DEMULATOR_TEST']
                if label == 'detection-save':
                    defines.append('-DEMULATOR_BOOT_POLICY_TEST')
                recovery = label == 'missing-base' or label.startswith('invalid-')
                if recovery:
                    defines.append('-DEMULATOR_BOOT_SETTINGS_RECOVERY')
                if label == 'stale-signature':
                    defines.append('-DEMULATOR_BOOT_STALE')
                source = ROOT / 'src/bios.asm'
                if expected in (0x63, 0x64):
                    # Observe the new real exhaustion terminal; reopening is
                    # separately proved by the stateful native retry fixture.
                    expected = 0x6C
                    observer = '''
    cmp byte [fs:B_CURSOR], 4
    jne .retry_observer_bad
    cmp byte [0x0400+KB_POST_STATE], 2
    jne .retry_observer_bad
    mov ax, [0x041A]
    cmp ax, [0x041C]
    jne .retry_observer_bad
    mov ax, 0xB800
    mov es, ax
    xor di, di
.retry_observer_find:
    xor bx, bx
.retry_observer_text:
    mov al, [cs:msg_boot_retry+bx]
    cmp al, 13
    je .retry_observer_seen
    push di
    add di, bx
    add di, bx
    cmp al, [es:di]
    pop di
    jne .retry_observer_next
    inc bx
    jmp .retry_observer_text
.retry_observer_next:
    add di, 2
    cmp di, 3960
    jb .retry_observer_find
    jmp .retry_observer_bad
.retry_observer_seen:
    mov bx, [0x046C]
    sti
    hlt
    cli
    cmp bx, [0x046C]
    je .retry_observer_bad
    mov al, 0x6C
    call emulator_exit
    jmp hard_halt
.retry_observer_bad:
    mov al, 0x7D
    call emulator_exit
    jmp hard_halt
'''
                    boot_include = vm / 'boot-observer.inc'
                    boot_include.write_text((ROOT / 'src/boot.inc').read_text().replace(
                        '    post_code 0xE4\n', '    post_code 0xE4\n'+observer))
                    source = vm / 'bios-observer.asm'
                    source.write_text((ROOT / 'src/bios.asm').read_text().replace(
                        '%include "boot.inc"', '%include "'+boot_include.as_posix()+'"'))
                floppy.run_hidden([nasm, '-f', 'bin', *defines, '-I', str(ROOT / 'src') + '/',
                                  '-o', str(system), str(source)], check=True)
                data = bytearray(system.read_bytes())
                assert len(data) == 65536
                data[-1] = -sum(data[:-1]) & 255
                wrapper.write_bytes(production[:65536] + data)
                sectors = {}
                for unit in (0, 0x80, 1):
                    sector = vm / f'boot-{unit}.bin'
                    wanted_boot = 1 if recovery or label in ('detection-save', 'cold-reload') else (1, 2, 2)[boot]
                    wanted_seek = 0 if label in ('detection-save', 'cold-reload') else 1
                    floppy.run_hidden([nasm, '-f', 'bin', f'-DEXPECTED_DRIVE={unit}',
                                      f'-DEXPECTED_BOOT={wanted_boot}', f'-DEXPECTED_SEEK={wanted_seek}',
                                      f'-DRESULT={0x67 if unit == 0x80 else 0x66}',
                                      *(['-DEXPECT_NO_INPUT'] if not recovery and label != 'detection-save' else []),
                                      '-o', str(sector), str(ROOT / 'tests/boot-policy-sector.asm')], check=True)
                    sectors[unit] = sector.read_bytes()
                disk, fa, fb = vm / 'hdd.img', vm / 'a.img', vm / 'b.img'
                with disk.open('xb') as out:
                    out.write(sectors[0x80] if signed_hdd else bytes(512))
                    out.truncate(64 * 1024 * 1024)
                if medium:
                    with fa.open('xb') as out:
                        out.write(sectors[0] if signed_a else bytes(512))
                        out.truncate(1440 * 1024)
                with fb.open('xb') as out:
                    out.write(sectors[1])
                    out.truncate(1200 * 1024)
                floppy.config(vm, disk, a, 2, fa, fb, turbo=True, protected=True, boot=boot)
                nvram = vm / 'nvr/d824.nvr'
                cmos = bytearray(nvram.read_bytes()) if saved is None or label != 'cold-reload' else bytearray(saved)
                if label != 'cold-reload':
                    cmos[0x3B] = hdd
                    cmos[0x3D] = -(sum(cmos[0x38:0x3D]) + cmos[0x10]) & 255
                if recovery:
                    # Same valid clock and bootable A/HDD as hdd-first; vary only base validity.
                    if label == 'missing-base':
                        cmos[0x38:0x3E] = bytes(6)
                    elif label == 'invalid-signature':
                        cmos[0x39] ^= 1
                        cmos[0x3D] = -(sum(cmos[0x38:0x3D]) + cmos[0x10]) & 255
                    elif label == 'invalid-schema':
                        cmos[0x3A] = 6
                        cmos[0x3D] = -(sum(cmos[0x38:0x3D]) + cmos[0x10]) & 255
                    else:
                        cmos[0x3D] ^= 1
                nvram.write_bytes(cmos)
                originals = {p: p.read_bytes() for p in (fa, fb) if p.exists()}
                result = floppy.run_hidden([exe, '-P', str(vm), '-R', str(roms), '-L', str(vm / '86box.log'), '-N'], timeout=75)
                assert result.returncode == expected, ('boot policy', label, hex(result.returncode), hex(expected))
                assert all(p.read_bytes() == data for p, data in originals.items()), 'boot check wrote floppy media'
                if recovery:
                    recovered = nvram.read_bytes()
                    assert recovered[0x38:0x3D] == b'B8\x05\x13\x01'
                    assert recovered[0x3E:0x40] == b'\x02\0'
                    assert not (sum(recovered[0x38:0x40])+recovered[0x10]) & 255
                    assert not recovered[0xE] & 0x80
                if label == 'detection-save':
                    saved = nvram.read_bytes()
                    assert saved[0x3A:0x3D] == b'\x05\x11\x01' and saved[0x3E:0x40] == b'\0\0'
                    assert (sum(saved[0x38:0x40]) + saved[0x10]) & 255 == 0
                print('86Box boot policy / ' + label + ': PASS', flush=True)
    finally:
        wrapper.write_bytes(production)
    assert wrapper.read_bytes() == production


def submenu_arrows():
    master = [0x50, 28, 0x50, 0x50, 28]
    for changes, value, enabled in (([], 'Auto', 1), ([0x4D], 'Type 1', 1),
                                   ([0x4D] * 12, 'Type 12', 1),
                                   ([0x4B,0x4B], 'User (48)', 1), ([], 'None', 0)):
        model = Setup()
        settings_fixture(model, hdd=enabled)
        model.call('settings_load')
        seen = []
        def observe(m):
            if m.script or m.pending:
                return
            assert m.cpu.mem_read(m.base + 0x188, 1) == b'\xff'
            for row, text, color in ((8, value, 0x1F), (9, 'Auto', 7)):
                assert m.text(row, 49, len(text)) == text
                assert m.cpu.mem_read(0xB8000 + row * 160 + (50 + len(text)) * 2, 2) == bytes((0x1A, color))
            seen.append(True)
            m.observer = None
            m.script = [1, 1, 28]
        model.observer = observe
        model.open(master + ([0x50] + changes if changes else []) + [1])
        assert seen
    model = Setup()
    seen = []
    def disabled_controller(m):
        if m.script or m.pending:
            return
        for row in (8, 9):
            assert m.cpu.mem_read(0xB8000 + row * 160 + 54 * 2, 2) == b'\x1a\x08'
        seen.append(True)
        m.observer = None
        m.script = [1, 1, 28]
    model.observer = disabled_controller
    model.open([0x50, 28] + [0x50] * 4 + [0x4D])
    assert seen


CASES['submenu-arrows'] = submenu_arrows


def selection_bars():
    master = [0x50, 28, 0x50, 0x50]
    for prefix, row, col, width in (([15], 5, 48, 30),
                                   ([15,0x50,0x50], 7, 48, 30),
                                   (master, 8, 48, 30),
                                   (master + [28], 5, 48, 30),
                                   ([0x50, 0x50, 28], 5, 48, 30),
                                   ([0x50] * 5 + [28], 5, 23, 55),
                                   ([0x50], 6, 1, 18)):
        model = Setup()
        seen = []
        def observe(m):
            if m.script or m.pending:
                return
            for y in range(row - 1, row + 2):
                cells = bytes(m.cpu.mem_read(0xB8000 + y * 160 + col * 2, width * 2))
                if y == row:
                    assert cells[1::2] == b'\x1f' * width, (row, y)
                else:
                    assert b'\x1f' not in cells[1::2], (row, y, 'highlight spills into adjacent row')
                for xcol in (col - 1, col + width):
                    assert m.cpu.mem_read(0xB8000 + y * 160 + xcol * 2 + 1, 1) != b'\x1f'
            seen.append(True)
            m.observer = None
            m.script = [1] * (3 if prefix == master + [28] else (1 if prefix == [0x50] else 2)) + [28]
        model.observer = observe
        model.open(prefix.copy())
        assert seen
    for prefix, row in ((master + [28, 0x50, 28, 0x50], 8),
                        (master + [28, 0x50, 0x50, 0x50, 28], 10)):
        model = Setup()
        seen = []
        def popup(m):
            if m.script or m.pending:
                return
            assert bytes(m.cpu.mem_read(0xB8000 + row * 160 + 25 * 2 + 1, 104))[::2] == b'\x70' * 52
            seen.append(True)
            m.observer = None
            m.script = [1, 1, 1, 1, 28]
        model.observer = popup
        model.open(prefix.copy())
        assert seen


CASES['selection-bars'] = selection_bars


def setup25():
    # Guard actual renderer writes, including repeated redraws, modals and editors.
    def bounded(cpu, access, address, size, value, unused):
        assert address + size <= 0xB8000+4000, (hex(address), size, 'outside 80x25')
    for prefix in ([], [0x50,28], [0x50,0x50,28], [0x50]*3+[28],
                   [0x50]*4+[28,0x50,28,0x51], [0x50]*5+[28]):
        model = Setup()
        model.cpu.hook_add(UC_HOOK_MEM_WRITE, bounded, begin=0xB8000, end=0xB8000+7999)
        observed = []
        def observe(m):
            assert m.cpu.mem_read(0x484,3) == b'\x18\x10\x00'
            footer = m.text(24,2,76)
            assert 'F1 Help' in footer or not footer.strip()
            assert m.cpu.mem_read(0xB8000 + 2*160 + 20*2,2) == b'\xd1\x0b'
            assert m.cpu.mem_read(0xB8000 + 23*160 + 20*2,2) == b'\xcf\x0b'
            assert all(m.cpu.mem_read(0xB8000+y*160+20*2,2)==b'\xb3\x0b' for y in range(3,23))
            assert m.text(3,2,10) == 'SETUP MENU'
            assert m.text(5,2,14) == 'Standard Setup'
            observed.append(True)
            if not m.script and not m.pending:
                m.observer = None
                m.script = [1]*(3 if prefix[:5]==[0x50]*4+[28] else 2 if 28 in prefix else 1)+[28]
        model.observer = observe
        model.open(prefix+[0x3B,1])
        assert observed and model.setup_entries == 1 and not model.warm
    print('80x25 renderer bounds, footer and actual Setup entry/return: PASS',flush=True)


CASES['setup25'] = setup25


def clock_presentation():
    format_field = [15, 0x50, 0x50]
    leave = [1, 1, 28]
    def fixture(m, version, flags):
        record = bytearray((66, 56, version, flags, 1, 0, 2, 0))
        record[5] = -(sum(record)+0x40) & 255
        m.cmos[0x10] = 0x40
        m.cmos[0x38:0x40] = record
        m.call('settings_load')
    # Identical bit7-set policy requires different legacy/new-schema treatment.
    for version, flags, valid, display24 in ((2, 0x13, 1, 0), (2, 0x93, 0, 0),
                                           (3, 0x93, 1, 1), (3, 0x13, 1, 0)):
        m = Setup()
        fixture(m, version, flags)
        before = bytes(m.cmos)
        seen = []
        def observe(n):
            assert n.cpu.mem_read(n.base+0x17C,1) == bytes((valid,))
            assert n.text(7,49,7) == ('24 Hour' if display24 else '12 Hour')
            assert n.text(6,49,11) == ('13:45:59   ' if display24 else '01:45:59 PM')
            seen.append(True)
            n.observer = None
        m.observer = observe
        m.open([1,28])
        assert seen and bytes(m.cmos) == before
    # Both quick arrows and the enum picker use the real Standard field.
    for edit in ([0x4D], [28,0x50,28]):
        m = Setup()
        old = bytes(m.cmos)
        m.open(format_field+edit+leave)
        assert m.cpu.mem_read(m.base+0xFB,1) == b'\1'
        assert m.cpu.mem_read(m.base+0x13D,1) == b'\0' and bytes(m.cmos)==old
    # Confirmed defaults then a custom preference must survive a fresh reload.
    m = Setup()
    clock = bytes(m.cmos[:0x10])
    m.open([0x43,28]+format_field+[0x4D,0x44,28])
    assert m.warm and m.cmos[0x3A] == 5 and m.cmos[0x3B]&0x80
    assert bytes(m.cmos[:0x10]) == clock
    fresh = Setup()
    fresh.cmos[:] = m.cmos
    fresh.call('settings_load')
    assert fresh.cpu.mem_read(fresh.base+0x13D,1) == b'\1'
    fresh.open([0x43,1,0x44,1,1,28])  # Cancel defaults and Save, then discard.
    assert fresh.cpu.mem_read(fresh.base+0xFB,1) == b'\1' and bytes(fresh.cmos)==bytes(m.cmos)
    fresh = Setup()
    fresh.cmos[:] = m.cmos
    fresh.call('settings_load')
    fresh.open([0x43,28,1,28])
    assert fresh.cpu.mem_read(fresh.base+0xFB,1) == b'\0' and bytes(fresh.cmos)==bytes(m.cmos)
    class Mismatch(Setup):
        def port_in(self, cpu, port, size, unused):
            value = super().port_in(cpu,port,size,unused)
            if port==0x71 and self.index==0x3B and (0x38,66) in self.writes:
                return value^0x80
            return value
    n = Mismatch()
    errors = []
    def failed(m):
        if 'CMOS verification failed.' in m.text(19,23,46):
            assert not m.warm and m.cpu.mem_read(m.base+0x13D,1)==b'\0'
            assert m.cpu.mem_read(m.base+0xFB,1)==b'\1'
            errors.append(True)
            m.observer = None
            m.script = leave.copy()
    n.observer = failed
    n.open(format_field+[0x4D,0x44,28])
    assert errors and not n.warm
    # Native format remains opaque across midnight/noon/afternoon conversions.
    for binary in (False, True):
        for native24 in (False, True):
            for text, expected in (('120000a',0x0000),('120000p',0x1200),('014500p',0x1345)):
                n = Setup(binary,native24)
                b = n.cmos[0xB]
                n.open([15,0x50,28]+keys(text+'\r')+leave)
                assert n.invoke(2)[1] == expected and n.cmos[0xB] == b
            n = Setup(binary,native24)
            n.open(format_field+[0x4D,0x48,28]+keys('235958\r')+leave)
            assert n.invoke(2)[1:3] == (0x2359,0x5801)
    for text in ('000000a','130000p','016099p'):
        n = Setup()
        before = bytes(n.cmos)
        seen = []
        def invalid(m):
            if m.text(20,23,7) == 'Invalid':
                seen.append(True)
        n.observer = invalid
        n.open([15,0x50,28]+keys(text+'\r\x1b')+leave)
        assert seen and bytes(n.cmos)==before
    # A mode change between independent repairs retains confirmed absolute time.
    n = Setup()
    n.cmos[0xD] = 0
    n.open([15,0x50,28]+keys('014559p\r')+
           [0x50,0x4D,0x48,0x48,28]+keys('10012026\r')+leave)
    assert n.invoke(2)[1:3] == (0x1345,0x5901)
    assert n.invoke(4)[1:3] == (0x2026,0x1001) and not n.cmos[0xE]&0x80
    # Pending meridiem/cursor survive a natural idle tick and F1 round trip.
    for display24 in (False,True):
        n = Setup()
        phase = [0]
        pending = []
        def idle(m):
            if phase[0] == 0 and not m.script and not m.pending:
                pending.extend((bytes(m.cpu.mem_read(m.base+0x100,12)),
                                m.cpu.mem_read(m.base+0xF9,1),m.text(6,49,11)))
                phase[0] = 1
            elif phase[0] == 1 and m.idles:
                assert m.text(6,49,11) != pending[2]
                m.script = [0x3B,1]
                phase[0] = 2
            elif phase[0] == 2 and not m.script and not m.pending:
                assert bytes(m.cpu.mem_read(m.base+0x100,12)) == pending[0]
                assert m.cpu.mem_read(m.base+0xF9,1) == pending[1]
                assert m.text(19,24,11 if not display24 else 8).encode() == pending[0][:11 if not display24 else 8]
                m.observer = None
                m.script = [28]+leave
                phase[0] = 3
        n.observer = idle
        prefix = format_field+[0x4D,0x48] if display24 else [15,0x50]
        n.open(prefix+[28]+keys('014559'+('' if display24 else 'p')))
        assert phase[0] == 3 and n.invoke(2)[1] == (0x0145 if display24 else 0x1345)
    # Shorter24-hour text erases the AM/PM suffix in both live and body clocks.
    n = Setup()
    seen = []
    def short(m):
        if m.cpu.mem_read(m.base+0xFB,1)==b'\1':
            assert m.text(6,57,3) == '   '
            seen.append(True)
    n.observer = short
    n.open(format_field+[0x4D]+leave)
    assert seen
    # Date cursor skips the two slashes in both directions.
    n = Setup()
    positions = []
    def cursor(m):
        if m.script or m.pending:
            return
        positions.append(m.cpu.mem_read(m.base+0xF9,1)[0])
        if len(positions)==1:
            assert positions[-1]==3
            m.script = keys('31')
        elif len(positions)==2:
            assert positions[-1]==6
            m.script = [0x0E]
        else:
            assert positions[-1]==4
            m.observer=None
            m.script = [1]+leave
    n.observer=cursor
    n.open([15,28]+keys('12'))
    assert positions==[3,6,4]
    print('Clock formats, schema contrasts, F9/save/reload, midnight/noon, repairs and pending editor: PASS',flush=True)


CASES['clock-presentation'] = clock_presentation


def clock_seek_state():
    # The saved format must survive real seek scratch0..3, Setup and F10 POST.
    for display24, seek, failures in ((1,1,0),(1,1,1),(1,1,2),(1,1,3),
                                     (0,1,2),(1,0,0)):
        for cold in (False, True):
            model = production_post_model()
            flags = 9 | seek << 1 | display24 << 7  # No Errors; Num Lock On.
            record = bytearray((66,56,4,flags,2,0,0,0))
            record[5] = -(sum(record)+0x42) & 255
            model.cmos[0x10] = 0x42
            model.cmos[0x38:0x40] = record
            model.track_zero = [True if failures & 1 << unit else None for unit in (0,1)]
            observed, rendered, resets = [], [], []
            def boundary(m, name):
                if name == 'setup_post_gate' and not observed:
                    assert m.cpu.mem_read(m.base+0x176,1) == bytes((failures,))
                    assert m.cpu.mem_read(m.base+0x13D,1) == bytes((display24,))
                    observed.append('seek')
                    m.pending.extend((0xE0,0x53))
                    rtc.Clock.interrupt(m,m.cpu,9,None)
                    rtc.Clock.interrupt(m,m.cpu,9,None)
                elif name == 'setup_main':
                    observed.append('setup')
                    m.script = [0x44,28]
            def visible(m):
                if m.text(0,34,11) != 'bAIos Setup': return
                assert m.cpu.mem_read(m.base+0xFB,1) == bytes((display24,))
                assert m.text(7,49,7) == ('24 Hour' if display24 else '12 Hour')
                rendered.append(True)
            def reset(cpu,address,size,unused):
                resets.append(True)
            model.startup_observer, model.observer = boundary, visible
            model.cpu.hook_add(UC_HOOK_CODE,reset,None,model.warm_entry,model.warm_entry)
            model.startup(reset=cold,production_controls=True,through_boot=True)
            assert observed == ['seek','setup'] and rendered and len(resets) == (2 if not cold else 1)
            assert model.setup_entries == 1 and model.cpu.mem_read(0x7C00,4) == b'BOOT'
            assert bool(model.cmos[0x3B]&0x80) == bool(display24)
            assert not (sum(model.cmos[0x38:0x40])+model.cmos[0x10]) & 255
            fresh = Setup()
            fresh.cmos[:] = model.cmos
            fresh.call('settings_load')
            assert fresh.cpu.mem_read(fresh.base+0x13D,1) == bytes((display24,))
            print(f'Clock preference / seek{seek} failures{failures} cold{cold}: Setup -> F10 warm POST -> BOOT -> reload PASS',flush=True)


CASES['clock-seek-state'] = clock_seek_state


def schema2_fixture(model, types=0x40, flags=0x13, order=(1, 2, 0)):
    model.cmos[0x10] = types
    record = bytearray((66, 56, 2, flags, order[0], 0, order[1], order[2]))
    record[5] = -(sum(record) + types) & 255
    model.cmos[0x38:0x40] = record


def production_post_model(kinds=None, peripherals=False):
    # Opaque external devices only. The changed production POST owners execute.
    chipset = importlib.import_module('test-chipset')
    class ProductionPost(chipset.Chipset, legacy.Disk):
        def __init__(self):
            self.peripheral_device = None
            self.disk_device = None
            super().__init__()
            self.device_present = True
            self.controller_present = True
            self.kbc_write = None
            self.command_byte = 0x5C
            self.led_data = False
            self.led_values = []
            self.tdr = 0
            self.disk_word = 0
            self.boot_reads = []
            self.cmos[0x36:0x38] = b'\0\xA0'  # Normal recovery and detected-strap state.
            self.boot_sector = bytearray(512)
            self.boot_sector[:4] = b'BOOT'
            self.boot_sector[510:] = b'\x55\xaa'
            self.script = []  # Healthy production POST needs no input.
            self.publish_peripherals = peripherals
            self.peripheral_device = None
            self.disk_device = None
            if peripherals:
                ports = importlib.import_module('test-ports')
                self.peripheral_device = ports.Ports(uart=(0x3F8, 0x2F8, 0x3E8, 0x2E8), printer=(0x3BC, 0x378, 0x278))
                self.peripheral_device.cpu = self.cpu
            if kinds is not None:
                self.disk_device = importlib.import_module('test-ide-options').Disk(kinds)
                self.disk_device.cpu = self.cpu
                self.ata = self.disk_device.ata
        def interrupt(self, cpu, vector, unused):
            if getattr(self, 'starting', False) and vector == 0x16 and cpu.reg_read(x.UC_X86_REG_AH) == 1 and self.idles < 2:
                script, self.script = self.script, []
                super().interrupt(cpu, vector, unused)
                self.script = script
                return
            super().interrupt(cpu, vector, unused)
        def port_in(self, cpu, port, size, unused):
            if port == 0x64:
                return 4 | int(bool(self.pending))
            if port == 0x60:
                return self.pending.pop(0) if self.pending else 0xFF
            if port == 0x1F0 and self.ata.get(0x1F7) == 0x20:
                value = int.from_bytes(self.boot_sector[self.disk_word * 2:self.disk_word * 2 + 2], 'little')
                self.disk_word += 1
                return value
            if self.disk_device is not None and (0x1F0 <= port <= 0x1F7 or port == 0x3F6):
                return self.disk_device.port_in(cpu, port, size, unused)
            if self.peripheral_device is not None and (port in (0x3F0, 0x3F1) or any(base <= port < base+8 for base in (0x3F8, 0x2F8, 0x3E8, 0x2E8)) or any(base <= port < base+3 for base in (0x3BC, 0x378, 0x278))):
                return self.peripheral_device.port_in(cpu, port, size, unused)
            return super().port_in(cpu, port, size, unused)
        def port_out(self, cpu, port, size, value, unused):
            if port == 0x3F5 and not self.fdc_command and value == 0x4A:
                if not self.boot_reads or self.boot_reads[-1] != 'Floppy': self.boot_reads.append('Floppy')
            if port == 0x64:
                if value in (0xD1, 0x60): self.kbc_write = value
                elif value == 0xAA and self.controller_present: self.pending.append(0x55)
                elif value == 0x20 and self.controller_present: self.pending.append(self.command_byte)
                else: assert value in (0xAA, 0x20, 0xAD, 0xAE, 0xA7), hex(value)
                return
            if port == 0x60:
                if self.kbc_write is not None:
                    if self.kbc_write == 0x60: self.command_byte = value
                    self.kbc_write = None
                elif value == 0xFF:
                    if self.device_present: self.pending.extend((0xFA, 0xAA))
                elif value == 0xED:
                    self.led_data = True
                    if self.device_present: self.pending.append(0xFA)
                else:
                    assert self.led_data and 0 <= value <= 7
                    self.led_data = False
                    self.led_values.append(value)
                    if self.device_present: self.pending.append(0xFA)
                return
            if port == 0xF0: return  # External numeric-error latch; actual init_fpu executes.
            if port == 0x3F3: self.tdr = value
            if port == 0x1F7 and value == 0xEC:
                self.identify_word = 0  # Each external IDENTIFY command starts a new data phase.
            if port == 0x1F7 and value == 0x20:
                self.disk_word = 0
                self.boot_reads.append('Hard Disk')
            if self.disk_device is not None and (0x1F0 <= port <= 0x1F7 or port == 0x3F6):
                return self.disk_device.port_out(cpu, port, size, value, unused)
            if self.peripheral_device is not None and (port in (0x3F0, 0x3F1) or any(base <= port < base+8 for base in (0x3F8, 0x2F8, 0x3E8, 0x2E8)) or any(base <= port < base+3 for base in (0x3BC, 0x378, 0x278))):
                return self.peripheral_device.port_out(cpu, port, size, value, unused)
            super().port_out(cpu, port, size, value, unused)
        def code(self, cpu, address, size, unused):
            if getattr(self, 'starting', False) and address == self.warm_entry:
                return
            if getattr(self, 'event_observer', None):
                self.event_observer(self, address)
            super().code(cpu, address, size, unused)
    return ProductionPost()


def settle_boot_leds(model):
    """External timer/IRQ1 delivery at boot; no product delay or LED replacement."""
    cpu=model.cpu
    context=cpu.context_save()
    def irq(vector):
        cpu.reg_write(x.UC_X86_REG_CS,0x9000); cpu.reg_write(x.UC_X86_REG_IP,0)
        cpu.reg_write(x.UC_X86_REG_SS,0); cpu.reg_write(x.UC_X86_REG_SP,0x7000)
        cpu.reg_write(x.UC_X86_REG_EFLAGS,0x202)
        cpu.mem_write(0x90000,bytes((0xCD,vector,0x90)))
        cpu.emu_start(0x90000,0x90002,count=100000)
        assert cpu.reg_read(x.UC_X86_REG_CS)==0x9000 and cpu.reg_read(x.UC_X86_REG_IP)==2
    try:
        for _ in range(8):
            while model.pending: irq(9)
            irq(8)
        while model.pending: irq(9)
    finally:
        cpu.context_restore(context)


def boot_numlock():
    # Real early Caps Lock IRQ1 + timer ED handshake must survive saved Num On.
    model = production_post_model()
    schema2_fixture(model, types=0, flags=0x13, order=(2, 0, 0))
    model.script = []
    early, flags = [], []
    begin = 0xF0000+rtc.symbol('post_numlock_apply')
    end = 0xF0000+rtc.symbol('post_keyboard_presence')
    led = 0xF0000+rtc.symbol('keyboard_led_tick')
    led_end = 0xF0000+rtc.symbol('keyboard_enqueue')
    assert model.cpu.mem_read(end-2, 2) == b'\x9d\xc3'
    def early_led(m, name):
        if name == 'settings_load' and not early:
            early.append('caps')
            m.pending.append(0x3A)
            rtc.Clock.interrupt(m, m.cpu, 9, None)
        elif name == 'settings_load' and early == ['caps']:
            early.append('timer')
            rtc.Clock.interrupt(m, m.cpu, 8, None)
    def atomic(cpu, address, size, unused):
        actual = cpu.reg_read(x.UC_X86_REG_EFLAGS)
        if address == begin:
            flags.append(actual)
            assert actual & 0x200 and early == ['caps', 'timer']
            assert cpu.mem_read(0x499, 2) == b'\x02\x04' and model.pending == [0xFA]
        elif address == end-1:
            assert actual == flags[0], 'saved POST flags were not restored'
            assert cpu.mem_read(0x499, 2) == b'\x02\x04', 'in-flight ED transaction replaced'
            assert cpu.mem_read(0x417, 1)[0] & 0x60 == 0x60
            flags.append(actual)
        elif address != begin+1:
            assert not actual & 0x200, 'shared BDA/LED update ran with IRQs enabled'
    model.startup_observer = early_led
    hooks = [model.cpu.hook_add(UC_HOOK_CODE, atomic, None, begin, end-1)]
    def foreground_led(cpu, address, size, unused):
        if len(flags) == 1: atomic(cpu, address, size, unused)
    hooks.append(model.cpu.hook_add(UC_HOOK_CODE, foreground_led, None, led, led_end-1))
    try:
        model.startup(reset=True, production_controls=True, through_boot=True)
        assert len(flags) == 2 and flags[0] == flags[1]
        assert model.cpu.mem_read(0x417, 1)[0] & 0x60 == 0x60
        settle_boot_leds(model)
        assert model.led_values == [4, 6] and model.cpu.mem_read(0x49B, 1) == b'\x06', (model.led_values, bytes(model.cpu.mem_read(0x499, 5)))
        assert model.cpu.mem_read(0x7C00, 4) == b'BOOT'
    finally:
        for hook in hooks: model.cpu.hook_del(hook)
    for on in (False, True):
        for cold in (False, True):
            model = production_post_model()
            schema2_fixture(model, types=0, flags=0x12 | int(on), order=(2, 0, 0))
            model.cpu.mem_write(0x417, bytes((0 if on else 0x20,)))
            model.startup(reset=cold, production_controls=True, through_boot=True)
            assert bool(model.cpu.mem_read(0x417, 1)[0] & 0x20) == on
            settle_boot_leds(model)
            assert model.led_values and bool(model.led_values[-1] & 2) == on
            assert model.cpu.mem_read(0x7C00, 4) == b'BOOT'
            model.scans([0x53])
            head = int.from_bytes(model.cpu.mem_read(0x41A, 2), 'little')
            assert model.cpu.mem_read(0x400 + head, 2) == bytes((ord('.') if on else 0, 0x53))
    # Every action starts from the opposite saved policy and changes the real draft.
    prefix = [0x50, 0x50, 15] + [0x50] * 5 + [0x4D]
    for action, accept in ((a, b) for a in ('save', 'defaults', 'discard') for b in (False, True)):
        model = Setup()
        before = bytes(model.cmos)
        end = ([0x44, 28] if accept else [0x44, 1, 1, 1, 28]) if action == 'save' else (
            [0x43, 28 if accept else 1, 1, 1, 28] if action == 'defaults' else
            [1, 1, 28] if accept else [1, 1, 1, 1, 28])
        model.open(prefix + end)
        if action == 'save' and accept:
            assert model.warm and model.cmos[0x3A] == 5 and not model.cmos[0x3B] & 1
            reboot = production_post_model()
            reboot.cmos[:] = model.cmos
            reboot.startup(reset=True, production_controls=True, through_boot=True)
            assert not reboot.cpu.mem_read(0x417, 1)[0] & 0x20
        else:
            assert bytes(model.cmos) == before and not model.writes
    # The saved policy controls Delete during real detection, then the real gate/UI.
    for cold in (False, True):
        for form, action in (('decimal', None), ('navigation', 'discard'), ('navigation', 'save')):
            model = production_post_model()
            schema2_fixture(model, types=0, flags=0x13, order=(1, 2, 0))
            record = bytes(model.cmos[0x38:0x40])
            model.script = []
            seen = []
            def detection(m, name):
                if name == 'init_floppy' and 'injected' not in seen:
                    assert m.cpu.mem_read(0x417, 1)[0] & 0x20
                    assert m.cpu.mem_read(0x49E, 1) == b'\x01'
                    m.pending.extend([0x53] if form == 'decimal' else [0xE0, 0x53])
                    seen.append('injected')
                if name == 'setup_post_gate' and 'gate' not in seen:
                    assert m.cpu.mem_read(0x49E, 1) == b'\x01'
                    seen.append('gate')
                if name == 'setup_main':
                    assert m.cpu.mem_read(m.base+0xF4, 1) == b'\x01'
                    seen.append('setup')
                    m.script = [0x50, 0x50, 15, 0x4D] + ([0x44, 28] if action == 'save' else [1, 1, 28])
                if name == 'chipset_late_cache':
                    assert m.cpu.mem_read(0x49E, 1) == b'\x02'
                    assert m.cpu.mem_read(0x484, 3) == b'\x18\x10\0'
                    if form == 'decimal':
                        head = int.from_bytes(m.cpu.mem_read(0x41A, 2), 'little')
                        assert m.cpu.mem_read(0x400+head, 2) == b'.\x53'
            model.startup_observer = detection
            model.startup(reset=cold, production_controls=True, through_boot=True)
            assert seen.count('setup') == int(form == 'navigation'), seen
            assert model.startup_hops.count('init_memory') == (2 if action == 'save' else 1)
            if action == 'save':
                assert model.cmos[0x3C] == 2 and model.cmos[0x3E:0x40] == b'\x01\0'
                assert not (sum(model.cmos[0x38:0x40])+model.cmos[0x10]) & 255
            else: assert bytes(model.cmos[0x38:0x40]) == record
            assert model.cpu.mem_read(0x49E, 1) == b'\0'
            assert model.cpu.mem_read(0x484, 3) == b'\x18\x10\0'
            assert model.cpu.mem_read(0x7C00, 4) == b'BOOT'
            settle_boot_leds(model)
            assert model.led_values and model.led_values[-1] & 2


def halt_on():
    saved = Setup()
    saved.open([0x50, 0x50, 15] + [0x50] * 7 + [0x4B, 0x44, 28])
    assert saved.warm and saved.cmos[0x3B] & 0x18 == 8
    reboot = production_post_model()
    reboot.cmos[:] = saved.cmos
    reboot.fdc_timeout = 0
    reboot.startup(reset=True, production_controls=True, through_boot=True)
    assert 'Floppy A seek error.' in reboot.console and 'Press any key to continue' not in reboot.console
    for policy in (0, 1, 2):
        for cold in (False, True):
            model = production_post_model()
            schema2_fixture(model, flags=3 | (policy << 3), order=(2, 1, 0))
            model.fdc_timeout = 0  # Configured logical A has no physical drive.
            model.script = []
            waits = []
            def boundary(m, name):
                if name == 'post_notice_wait' and not waits:
                    waits.append((m.idles, int.from_bytes(m.cpu.mem_read(0x46C, 4), 'little')))
            def timer_gate(m, address):
                if waits and waits[-1] != 'released' and m.cpu.mem_read(address, 1) == b'\xf4':
                    idle, tick = waits[0]
                    assert not m.boot_reads and not m.pending and not m.script
                    assert m.cpu.mem_read(0x41A, 2) == m.cpu.mem_read(0x41C, 2)
                    elapsed = m.idles-idle
                    if elapsed == 5:
                        assert int.from_bytes(m.cpu.mem_read(0x46C, 4), 'little') > tick
                        m.pending.append(0x1E)  # Fresh A scan, consumed by the real notice gate.
                        waits.append('released')
            model.startup_observer = boundary
            model.event_observer = timer_gate
            model.startup(reset=cold, production_controls=True, through_boot=True)
            assert bool(waits) == (policy != 1)
            if policy != 1: assert waits[-1] == 'released', (policy, waits, model.idles, model.startup_hops)
            assert model.cpu.mem_read(0x41A, 2) == model.cpu.mem_read(0x41C, 2), 'notice key leaked past gate'
            assert 'Floppy A seek error.' in model.console
            assert ('Press any key to continue' in model.console) == (policy != 1)
            assert model.fdc_dor == 0x0C and model.cpu.mem_read(model.base + 0x86, 1) == b'\0'
            assert model.cpu.mem_read(0x7C00, 4) == b'BOOT'
            assert model.text(13, 24, 6) == 'Floppy'
            assert model.cpu.mem_read(0x484, 3) == b'\x18\x10\0'
            assert model.startup_hops.index('post_floppy_seek') < model.startup_hops.index('setup_post_gate') < model.startup_hops.index('chipset_late_cache') < model.startup_hops.index('post_debug_summary') < model.startup_hops.index('int19')
    for domain in ('rtc', 'extension', 'base'):
        model = production_post_model()
        schema2_fixture(model, types=0, flags=0x0B, order=(2, 0, 0))
        if domain == 'rtc': model.cmos[8] = 0
        elif domain == 'extension':
            model.call('settings_load')
            model.open([0x44, 28])  # Establish valid extensions, then corrupt just the ports record.
            model.cmos[0x68] ^= 1
        else: model.cmos[0x3D] ^= 1
        before = bytes(model.cmos[0x33:])
        if domain == 'base':
            model.startup(reset=True, production_controls=True, stop_at_notice=True)
            assert model.cpu.mem_read(model.base + 0x17C, 1) == b'\0'
            assert 'Enter/D: Load defaults' in model.console
        else:
            model.warm = False
            model.script = []
            model.startup(reset=True, production_controls=True, through_boot=True)
            assert model.cpu.mem_read(model.base + 0x17C, 1) == b'\x01'
            assert ('CMOS date/time not set' if domain == 'rtc' else 'CMOS settings invalid') in model.console
            assert 'Enter/D: Load defaults' not in model.console
            col, label = (20, 'Clock') if domain == 'rtc' else (44, 'Settings')
            assert model.text(13, {20:18,32:24,44:31}[col], len(label)) == label
            assert model.cpu.mem_read(0x7C00, 4) == b'BOOT'
            assert model.cpu.mem_read(0x484, 3) == b'\x18\x10\0'
            assert model.startup_hops.index('post_clock_alert') < model.startup_hops.index('setup_post_gate') < model.startup_hops.index('chipset_late_cache') < model.startup_hops.index('post_debug_summary') < model.startup_hops.index('int19')
        assert bytes(model.cmos[0x33:]) == before


def keyboard_absence():
    for present in (False, True):
        for policy in (0, 1, 2):
            for cold in (False, True):
                model = production_post_model()
                model.device_present = present
                schema2_fixture(model, types=0, flags=3 | (policy << 3), order=(2, 0, 0))
                pause = not present and policy == 0
                model.startup(reset=cold, production_controls=True, through_boot=not pause, stop_at_notice=pause)
                assert bool(model.cpu.mem_read(0x49F, 1)[0]) == (not present)
                assert ('Keyboard not detected' in model.console) == (not present)
                assert ('Press any key to continue' in model.console) == pause
                if not pause: assert model.cpu.mem_read(0x7C00, 4) == b'BOOT'
    model = production_post_model()
    model.controller_present = False
    schema2_fixture(model, types=0, flags=0x0B, order=(2, 0, 0))
    model.startup(reset=True, production_controls=True, halt=True)
    assert model.posts[-1] == 0xE8 and 'Keyboard not detected' not in model.console


def nondefault_extensions(model):
    # Independent persisted records: no production save creates the input oracle.
    ide = importlib.import_module('test-ide-options')
    ports = importlib.import_module('test-ports')
    policy = bytes.fromhex('5494a700883830000079a85555555555aa04010000030003')
    assert len(policy) == 24
    payload = bytearray(ide.DEFAULT)
    payload[2], payload[3], payload[4] = 1, 2, 1  # Translation, block, EDD disabled.
    ide.saved(model, payload)
    devices = bytes((3, 0, 1, 3, 1, 1, 0, 1))
    ports.record(model, devices)
    model.cmos[0x69:0x80] = bytes((0xC2, -(0xC2+sum(policy)) & 255)) + policy[:21]
    model.cmos[0x33:0x36] = policy[21:]
    model.call('settings_load')
    assert model.cpu.mem_read(model.base+0x174, 1) == b'\x01'
    assert model.cpu.mem_read(model.base+0x190, 25) == bytes(payload)
    assert model.cpu.mem_read(model.base+0x1E6, 8) == devices
    assert model.cpu.mem_read(model.base+0x60, 24) == bytes(policy)
    return bytes(policy)


def boot_priority_save():
    for old in range(3):
        model = Setup()
        settings_fixture(model, hdd=0, boot=old, seek=0xA5)
        model.cmos[0x3F] = 0xA5
        before = bytes(model.cmos)
        model.call('settings_load')
        assert (loaded(model)[2], *model.cpu.mem_read(model.base + 0x189, 2)) == ((1, 2, 0), (2, 1, 0), (2, 0, 0))[old]
        assert loaded(model)[1::2] == b'\0\0' and model.cpu.mem_read(model.base + 0x177, 1) == b'\0'
        assert bytes(model.cmos) == before
        model.open([0x44, 28])
        assert model.cmos[0x3A] == 5 and model.cmos[0x3B] == 0x71
        reboot = Setup()
        reboot.cmos[:] = model.cmos
        reboot.call('settings_load')
        assert loaded(reboot) == loaded(model)
        for enabled in (False, True):
            for cold in (False, True):
                post = production_post_model()
                settings_fixture(post, hdd=int(enabled), boot=old, seek=0xA5)
                post.cmos[0x3F] = 0xA5
                record = bytes(post.cmos[0x38:0x40])
                sought = []
                def before_dispatch(m, name):
                    if name == 'int19': sought.extend(c for c in m.fdc_log if c[0] in (7, 15))
                post.startup_observer = before_dispatch
                post.startup(reset=cold, production_controls=True, through_boot=enabled, boot_failure=not enabled)
                assert bytes(post.cmos[0x38:0x40]) == record, 'POST wrote legacy migration'
                assert post.cpu.mem_read(post.base+0x177, 1) == b'\0'
                assert loaded(post)[3] == 0 and not sought, 'disabled seek tag caused POST mechanics'
                assert (loaded(post)[2], *post.cpu.mem_read(post.base+0x189, 2)) == ((1, 2, 0), (2, 1, 0), (2, 0, 0))[old]
                expected = (['Floppy', 'Hard Disk'] if old == 0 else ['Hard Disk']) if enabled else (['Floppy'] if old != 2 else [])
                assert post.boot_reads == expected, (old, enabled, post.boot_reads)
                assert post.cpu.mem_read(0x475, 1) == bytes((int(enabled),))
                if enabled: assert post.cpu.mem_read(0x7C00, 4) == b'BOOT'
    # Actual Setup changes all three fields and retains unrelated policy.
    model = Setup()
    policy = nondefault_extensions(model)
    model.cmos[0x36:0x38] = b'\xDA\xA0'
    extensions = bytes(model.cmos[0x33:0x38]+model.cmos[0x40:0x80])
    model.open([0x50, 0x50, 15, 0x4B, 0x50, 0x50, 0x4D, 0x4D, 0x44, 28])
    assert (model.cmos[0x3C], model.cmos[0x3E], model.cmos[0x3F]) == (0, 1, 2)
    assert not (sum(model.cmos[0x38:0x40]) + model.cmos[0x10]) & 255
    assert bytes(model.cmos[0x33:0x38]+model.cmos[0x40:0x80]) == extensions
    model.call('settings_load')
    assert model.cpu.mem_read(model.base+0x60, 24) == policy
    assert bytes(model.cmos[0x33:0x38]+model.cmos[0x40:0x80]) == extensions
    for order, marker, attempts in (((0, 1, 2), b'HD3!', ['Floppy', 'Hard Disk']),
                                     ((0, 2, 1), b'HD2!', ['Hard Disk'])):
        saved = model if order == (0, 1, 2) else Setup()
        if order == (0, 2, 1):
            saved.open([0x50, 0x50, 15, 0x4B, 0x50, 0x50, 0x4D, 0x44, 28])
        assert (saved.cmos[0x3C], saved.cmos[0x3E], saved.cmos[0x3F]) == order
        for cold in (False, True):
            reboot = production_post_model()
            reboot.cmos[:] = saved.cmos
            reboot.cmos[0x36] = 0  # Ordinary reset, outside the F10 retention assertion.
            reboot.boot_sector[:4] = marker
            reboot.startup(reset=cold, production_controls=True, through_boot=True)
            assert reboot.boot_reads == attempts, (order, reboot.boot_reads)
            assert reboot.cpu.mem_read(0x7C00, 4) == marker
            assert reboot.cpu.reg_read(x.UC_X86_REG_DL) == 0x80
    for index, value in ((0x3B, 0x80), (0x3B, 0x1B), (0x3C, 3), (0x3E, 3), (0x3F, 3), (0x3E, 1), (0x3F, 2)):
        invalid = production_post_model()
        schema2_fixture(invalid)
        invalid.cmos[index] = value
        invalid.cmos[0x3D] = -(sum(invalid.cmos[0x38:0x3D]) + sum(invalid.cmos[0x3E:0x40]) + invalid.cmos[0x10]) & 255
        snapshot = bytes(invalid.cmos[0x33:])
        for cold in (False, True):
            post = production_post_model()
            post.cmos[:] = invalid.cmos
            post.startup(reset=cold, production_controls=True, stop_at_notice=True)
            assert post.cpu.mem_read(post.base+0x17C, 1) == b'\0', (index, value)
            assert 'CMOS settings invalid' in post.console and 'Enter/D: Load defaults' in post.console
            assert bytes(post.cmos[0x33:]) == snapshot and not post.boot_reads
            assert not any(0x38 <= i <= 0x7F or i == 0x10 for i, _ in post.writes)


def assert_floppy_publication(model, types):
    a, b = types >> 4, types & 15
    assert bytes(model.cpu.mem_read(model.base+0x80, 2)) == bytes((a, b))
    equipment = int.from_bytes(model.cpu.mem_read(0x410, 2), 'little')
    span = 2 if b else int(bool(a))
    assert bool(equipment & 1) == bool(span)
    if span: assert (equipment >> 6 & 3)+1 == span
    model.cpu.mem_write(0x4C, struct.pack('<HH', rtc.symbol('int13'), 0xF000))
    for unit, kind in enumerate((a, b)):
        model.setup(ah=8, cx=0, dx=unit, flags=0x202)
        model.cpu.mem_write(0x90000, b'\xcd\x13\x90')
        model.cpu.emu_start(0x90000, 0x90002, count=100000)
        assert model.cpu.reg_read(x.UC_X86_REG_IP) == 2
        assert bool(model.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1) == (not kind)
        if kind:
            assert model.cpu.reg_read(x.UC_X86_REG_BL) == kind
            assert model.cpu.reg_read(x.UC_X86_REG_DL) == span


def swap_floppy():
    for action in ('save', 'discard', 'cancel-save'):
        model = production_post_model()
        schema2_fixture(model, types=0x42)
        model.call('settings_load')
        model.call('init_floppy')
        assert model.tdr == 0
        active = bytes(model.cpu.mem_read(model.base+0x170, 16))
        before = bytes(model.cmos)
        prefix = [0x50, 15] + [0x50] * 6
        seen = []
        def unsaved(m):
            if m.script or m.pending: return
            assert m.cpu.mem_read(m.base+0x18C, 1) == b'\x01'
            assert m.cpu.mem_read(m.base+0x180, 1) == b'\x42'
            assert m.tdr == 0 and bytes(m.cpu.mem_read(m.base+0x170, 16)) == active
            assert m.cpu.mem_read(m.base+0x80, 2) == b'\x04\x02'
            assert int.from_bytes(m.cpu.mem_read(0x410, 2), 'little') & 0xC1 == 0x41
            seen.append(True)
            m.observer = None
            m.script = {'save': [0x44, 28], 'discard': [1, 1, 28],
                        'cancel-save': [0x44, 1, 1, 1, 28]}[action]
        model.observer = unsaved
        model.open(prefix + [0x4D])
        assert seen
        assert model.cpu.mem_read(model.base + 0x180, 1) == b'\x42'
        assert model.tdr == 0 and bytes(model.cpu.mem_read(model.base+0x170, 16)) == active
        assert_floppy_publication(model, 0x42)
        if action != 'save': assert bytes(model.cmos) == before and not model.warm
        else:
            assert model.cmos[0x10] == 0x24 and model.cmos[0x3B] & 4
            assert model.warm
        for cold in (False, True):
            reboot = production_post_model()
            reboot.cmos[:] = model.cmos
            reboot.startup(reset=cold, production_controls=True, through_boot=True)
            assert reboot.tdr == (0x20 if action == 'save' else 0)
            assert_floppy_publication(reboot, 0x24 if action == 'save' else 0x42)
            assert {c[1] & 3 for c in reboot.fdc_log if c[0] == 7} == {0, 1}
    model = Setup()
    model.open([0x50, 15] + [0x50] * 6 + [0x4D, 0x4D, 0x44, 28])
    assert model.cmos[0x10] == 0x42 and not model.cmos[0x3B] & 4
    for types, enabled in ((4, True), (0x24, False)):
        model = production_post_model()
        schema2_fixture(model, types=types, flags=0x17, order=(2, 0, 0))
        if not enabled:
            model.call('settings_load')
            model.open([0x50, 15] + [0x50] * 5 + [0x4D, 0x44, 28])
        for cold in (False, True):
            reboot = production_post_model()
            reboot.cmos[:] = model.cmos
            reboot.startup(reset=cold, production_controls=True, through_boot=True)
            assert_floppy_publication(reboot, types if enabled else 0)
            assert reboot.tdr == (0x20 if enabled else 0)
            assert {c[1] & 3 for c in reboot.fdc_log if c[0] == 7} == ({1} if enabled else set())


def option_rom_discovery():
    importlib.import_module('test-legacy-boot').discovery()


def boot_retry():
    importlib.import_module('test-legacy-boot').retry()


CASES.update({'boot-numlock': boot_numlock, 'halt-on': halt_on,
              'keyboard-absence': keyboard_absence, 'boot-priority-save': boot_priority_save,
              'swap-floppy': swap_floppy, 'option-rom-discovery': option_rom_discovery,
              'boot-retry': boot_retry, 'processor-summary': processor_summary})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', choices=CASES, action='append')
    parser.add_argument('--86box', action='store_true')
    parser.add_argument('--86box-case', action='append', choices=(
        'hdd', 'clock24', 'no-disk', 'invalid-date', 'power-loss', 'invalid-settings', 'recovery',
        'ide-device', 'ide-types', 'ide-block', 'ide-channel', 'ide-submenu', 'ide-none'))
    parser.add_argument('--boot-86box', action='store_true')
    args = parser.parse_args()
    for name in args.case or CASES:
        CASES[name]()
        print(name + ': production setup/IRQ1 path PASS', flush=True)
    if args.__dict__['86box']:
        run_86box(args.__dict__['86box_case'])
    if args.boot_86box:
        run_boot_86box()


if __name__ == '__main__':
    main()
