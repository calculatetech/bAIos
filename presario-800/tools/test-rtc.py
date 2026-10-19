"""Execute production clock interrupts against a side-effecting RTC/PIC model."""
import datetime
import importlib
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INTR, UC_HOOK_INSN
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / os.environ.get('BAIOS_BUILD_DIRECTORY', 'build')
REGS = ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP',
        'DS', 'ES', 'FS', 'GS', 'SS')


def symbol(name):
    name = 'RTC_INTERRUPT_LABEL' if name == 'int1a' else name
    lines = (BUILD / 'baios-presario800-system.lst').read_text().splitlines()
    start = next(i for i, line in enumerate(lines)
                 if re.search(r'(?<![\w.])' + re.escape(name) + r':\s*$', line))
    for line in lines[start + 1:]:
        match = re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]', line)
        if match:
            return int(match[1], 16)
    raise AssertionError(name)


def bcd(value):
    return (value // 10 << 4) | value % 10


class Clock:
    def __init__(self, binary=False, hour24=True):
        self.cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        self.cpu.mem_map(0, 2 * 1024 * 1024)
        self.cpu.mem_write(0xF0000, (BUILD / 'baios-presario800-system.rom').read_bytes())
        self.cpu.mem_write(0x40E, struct.pack('<H', 0x9FC0))
        self.cpu.mem_write(0x9FCD0, struct.pack('<H', 7168))
        self.cpu.mem_write(0x41A, struct.pack('<HH', 0x1E, 0x1E))
        self.cpu.mem_write(0x90000, b'\xcd\x1a\x90')
        self.cpu.mem_write(0x90100, b'\x2e\x66\xff\x06\x00\x04\xcf')
        self.cpu.mem_write(0x90200, b'\x2e\x66\xff\x06\x04\x04\xcf')
        for vector, offset, segment in ((0x1A, symbol('int1a'), 0xF000),
                                         (0x08, symbol('int08'), 0xF000),
                                         (0x70, symbol('int70'), 0xF000),
                                         (0x4A, 0x100, 0x9000), (0x1C, 0x200, 0x9000)):
            self.cpu.mem_write(vector * 4, struct.pack('<HH', offset, segment))
        self.cmos = bytearray((i * 7 + 3) & 0x7F for i in range(128))
        self.cmos[0xA:0xF] = bytes((0x26, 2 * hour24 + 4 * binary + 1, 0, 0x80, 0x25))
        self.cmos[0x32] = 0x20
        self.seed(13, 45, 59, 2026, 2, 28)
        self.index = 0
        self.delayed = False
        self.writes = []
        self.events = []
        self.masks = {0x21: 0xFB, 0xA1: 0xF7}
        self.eois = []
        self.uip = 0
        self.roll = None
        self.dos_output = ''
        self.dos_exit = None
        self.cpu.hook_add(UC_HOOK_INTR, self.interrupt)
        self.cpu.hook_add(UC_HOOK_INSN, self.port_in, None, 1, 0, x.UC_X86_INS_IN)
        self.cpu.hook_add(UC_HOOK_INSN, self.port_out, None, 1, 0, x.UC_X86_INS_OUT)

    def seed(self, hour, minute, second, year, month, day):
        encode = (lambda n: n) if self.cmos[0xB] & 4 else bcd
        native_hour = encode(hour) if self.cmos[0xB] & 2 else encode(hour % 12 or 12) | (0x80 if hour >= 12 else 0)
        for index, value in ((0, encode(second)), (2, encode(minute)), (4, native_hour),
                             (6, encode((datetime.date(year, month, day).weekday() + 1) % 7 + 1)),
                             (7, encode(day)), (8, encode(month)), (9, encode(year % 100)),
                             (0x32, bcd(year // 100))):
            self.cmos[index] = value

    def interrupt(self, cpu, vector, unused):
        if vector == 0x21:  # External DOS console, for the shipped read-only COM.
            ah = cpu.reg_read(x.UC_X86_REG_AH)
            if ah == 9:
                address = cpu.reg_read(x.UC_X86_REG_DS) * 16 + cpu.reg_read(x.UC_X86_REG_DX)
                self.dos_output += bytes(cpu.mem_read(address, 256)).split(b'$', 1)[0].decode('ascii')
            elif ah == 2:
                value = cpu.reg_read(x.UC_X86_REG_DL)
                self.dos_output += chr(value)
                cpu.reg_write(x.UC_X86_REG_AL, value)
            elif ah == 8:
                self.seed(13, 46, 2, 2026, 2, 28)
                self.cpu.mem_write(0x46C, struct.pack('<I', 50))
                cpu.reg_write(x.UC_X86_REG_AL, 13)
            elif ah == 0x4C:
                self.dos_exit = cpu.reg_read(x.UC_X86_REG_AL)
                cpu.emu_stop()
            else:
                raise AssertionError(('DOS function', ah))
            return
        # A hardware fixture supplies interrupt delivery, not a replacement BIOS.
        flags, cs, ip = (cpu.reg_read(r) for r in (x.UC_X86_REG_EFLAGS, x.UC_X86_REG_CS, x.UC_X86_REG_IP))
        ss, sp = cpu.reg_read(x.UC_X86_REG_SS), cpu.reg_read(x.UC_X86_REG_SP)
        for value in (flags, cs, ip):
            sp = (sp - 2) & 0xFFFF
            cpu.mem_write(ss * 16 + sp, struct.pack('<H', value & 0xFFFF))
        offset, segment = struct.unpack('<HH', cpu.mem_read(vector * 4, 4))
        cpu.reg_write(x.UC_X86_REG_SP, sp)
        cpu.reg_write(x.UC_X86_REG_EFLAGS, flags & ~0x300)
        cpu.reg_write(x.UC_X86_REG_CS, segment)
        cpu.reg_write(x.UC_X86_REG_IP, offset)

    def port_in(self, cpu, port, size, unused):
        assert size == 1
        if port == 0x84:
            self.delayed = True
            return 0
        if port == 0x71:
            assert self.delayed and not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            value = self.cmos[self.index]
            if self.index == 0xD:
                self.cmos[0xD] = 0x80  # Original MC146818A VRT read side effect.
            elif self.index == 0xC:
                self.cmos[0xC] = 0
                self.events.append(('C', value))
            elif self.index == 0xA and self.uip:
                if self.uip > 0:
                    self.uip -= 1
                value |= 0x80
            elif self.index == 0 and self.roll:
                self.seed(*self.roll)
                self.roll = None
            return value
        if port in self.masks:
            return self.masks[port]
        if port == 0x64:  # Actual IRQ0 keyboard/LED owners see an idle controller.
            return 0
        raise AssertionError(('unexpected IN', hex(port)))

    def port_out(self, cpu, port, size, value, unused):
        assert size == 1
        if port == 0x70:
            self.index = value & 0x7F
            self.delayed = False
        elif port == 0x71:
            assert self.delayed and not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            if self.index in (0, 2, 4, 6, 7, 8, 9):
                assert self.cmos[0xB] & 0x80, 'clock write outside SET'
            self.writes.append((self.index, value))
            self.events.append(('W', self.index, value))
            self.cmos[self.index] = value
            if self.index == 0xB and value & 0x80:
                self.cmos[self.index] &= ~0x10  # SET clears UIE in hardware.
        elif port in self.masks:
            self.masks[port] = value
        elif port in (0x20, 0xA0):
            self.eois.append((port, value))
        else:
            raise AssertionError(('unexpected OUT', hex(port), value))

    def state(self):
        return {name: self.cpu.reg_read(getattr(x, 'UC_X86_REG_' + name)) for name in REGS}

    def setup(self, ah=0, cx=0x1357, dx=0x2468, flags=0x602):
        for i, name in enumerate(REGS[:7]):
            self.cpu.reg_write(getattr(x, 'UC_X86_REG_' + name), 0xA0000000 + i * 0x10000 + 0x5A5A)
        for i, name in enumerate(REGS[8:]):
            self.cpu.reg_write(getattr(x, 'UC_X86_REG_' + name), 0x2000 + i * 0x100)
        self.cpu.reg_write(x.UC_X86_REG_ESP, 0x8000)
        self.cpu.reg_write(x.UC_X86_REG_AX, ah * 256 + 0x55)
        self.cpu.reg_write(x.UC_X86_REG_CX, cx)
        self.cpu.reg_write(x.UC_X86_REG_DX, dx)
        self.cpu.reg_write(x.UC_X86_REG_EFLAGS, flags)
        self.cpu.reg_write(x.UC_X86_REG_CS, 0x9000)
        self.cpu.reg_write(x.UC_X86_REG_IP, 0)

    def invoke(self, ah=0, cx=0x1357, dx=0x2468, flags=0x602, vector=0x1A):
        self.setup(ah, cx, dx, flags)
        before = self.state()
        self.cpu.mem_write(0x90000, bytes((0xCD, vector, 0x90)))
        self.cpu.emu_start(0x90000, 0x90002, count=4000000)
        assert self.cpu.reg_read(x.UC_X86_REG_CS) == 0x9000 and self.cpu.reg_read(x.UC_X86_REG_IP) == 2, 'interrupt failed to return'
        after = self.state()
        result_flags = self.cpu.reg_read(x.UC_X86_REG_EFLAGS)
        outputs = {'EAX'} if vector == 0x1A else set()
        if vector == 0x1A and ah in (0, 2, 4) and not result_flags & 1:
            outputs.update(('ECX', 'EDX'))
        for name in REGS:
            if name in outputs:
                assert before[name] >> 16 == after[name] >> 16, name
            else:
                assert before[name] == after[name], (name, hex(before[name]), hex(after[name]))
        assert (flags ^ result_flags) & (0x600 if vector == 0x1A else 0x601) == 0
        return bool(result_flags & 1), after['ECX'] & 0xFFFF, after['EDX'] & 0xFFFF, after['EAX'] & 0xFFFF

    def call(self, name, flags=0x602):
        self.setup(flags=flags)
        before = self.state()
        self.cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
        ss = self.cpu.reg_read(x.UC_X86_REG_SS)
        self.cpu.reg_write(x.UC_X86_REG_SP, 0x7FFE)
        self.cpu.mem_write(ss * 16 + 0x7FFE, b'\xff\xff')
        self.cpu.emu_start(0xF0000 + symbol(name), 0xFFFFF, count=4000000)
        assert self.state() == before, name

    def callbacks(self):
        return struct.unpack('<I', self.cpu.mem_read(0x90400, 4))[0]

    def match(self, cause=0xA0):
        self.cmos[0xC] = cause
        count = self.callbacks()
        self.eois.clear()
        self.invoke(vector=0x70)
        assert self.cmos[0xC] == 0 and self.eois == [(0xA0, 0x60), (0x20, 0x62)]
        return self.callbacks() - count


def check_ticks():
    clock = Clock()
    assert clock.invoke(1, 0x17, 0xFFFF)[0] is False
    assert clock.invoke()[1:3] == (0x17, 0xFFFF)
    clock.invoke(vector=8)
    assert clock.invoke()[1:3] == (0x18, 0)
    assert struct.unpack('<I', clock.cpu.mem_read(0x90404, 4))[0] == 1
    clock.invoke(1, 0x18, 0xAE)
    clock.invoke(vector=8)
    assert clock.invoke()[1:] == (0x18, 0xAF, 0)
    clock.invoke(vector=8)
    assert clock.invoke()[1:] == (0, 0, 1)
    assert clock.invoke()[3] == 0
    clock.cpu.mem_write(0x470, b'\x01')
    clock.invoke(1, 0, 0)
    assert clock.invoke()[3] == 0 and not clock.writes
    print('S1/S4 ticks: set/read, low-word carry, exact midnight, consumed flag, real INT1C: pass')


def check_formats():
    for binary, hour24 in ((False, True), (True, True), (False, False), (True, False)):
        clock = Clock(binary, hour24)
        original = clock.cmos[:]
        for hour in (0, 12, 23):
            clock.cmos[0xB] = 4 * binary + 2 * hour24 + 1
            clock.seed(hour, 59, 58, 2000, 2, 29)
            assert clock.invoke(2)[1:3] == ((bcd(hour) << 8) | 0x59, 0x5801)
            assert clock.invoke(4)[1:3] == (0x2000, 0x0229)
            assert not clock.invoke(3, (bcd(hour) << 8) | 0x17, 0x1900)[0]
            encode = (lambda v: v) if binary else bcd
            expected_hour = encode(hour) if hour24 else encode(hour % 12 or 12) | (0x80 if hour >= 12 else 0)
            assert (clock.cmos[4], clock.cmos[2], clock.cmos[0]) == (expected_hour, encode(17), encode(19))
            assert clock.cmos[0xB] == (4 * binary + 2 * hour24)
            assert clock.invoke(2)[1:3] == ((bcd(hour) << 8) | 0x17, 0x1900)
            assert not clock.invoke(6, (bcd(hour) << 8) | 0x17, 0x1900)[0]
            assert (clock.cmos[5], clock.cmos[3], clock.cmos[1]) == (expected_hour, encode(17), encode(19))
            assert clock.cmos[0xB] == (4 * binary + 2 * hour24 + 0x20)
            assert clock.match() == 1
            assert not clock.invoke(7)[0]
            assert not clock.invoke(5, 0x1999, 0x1231)[0]
            assert clock.cmos[0x32] == 0x19 and clock.cmos[9] == encode(99)
            assert clock.cmos[6] == encode(6)  # Independent calendar: Friday.
            assert clock.invoke(4)[1:3] == (0x1999, 0x1231)
        assert clock.cmos[0x10:0x32] == original[0x10:0x32]
    print('S2/S5 native encoding: binary/BCD, 12/24h midnight/noon/PM, DST, century, weekday: pass')


def check_validation():
    cases = [(3, 0x1A00, 0), (3, 0x2400, 0), (3, 0x0060, 0),
             (3, 0, 0x6000), (3, 0, 2), (5, 0x1900, 0x0229), (5, 0x2001, 0x0229),
             (5, 0x2026, 0x0431), (5, 0x2026, 0x0001), (5, 0x2026, 0x1301),
             (5, 0x2026, 0x0100), (5, 0x2126, 0x0101), (5, 0x202A, 0x0101),
             (6, 0x1A00, 0), (6, 0x2400, 0), (6, 0x0060, 0), (6, 0, 0x6000)]
    for ah, cx, dx in cases:
        clock = Clock()
        before, masks = clock.cmos[:], clock.masks.copy()
        assert clock.invoke(ah, cx, dx)[0], (ah, cx, dx)
        assert clock.cmos == before and clock.masks == masks and not clock.writes
    clock = Clock()
    assert not clock.invoke(5, 0x2000, 0x0229)[0]
    assert clock.cmos[6] == 3  # Tuesday.
    for index, invalid in ((0, 0x6A), (2, 0x60), (4, 0x24), (8, 0x13), (7, 0)):
        clock = Clock()
        clock.cmos[index] = invalid
        assert clock.invoke(2 if index < 6 else 4)[0]
    clock = Clock(True)
    clock.cmos[7] = 161
    assert clock.invoke(4)[0]
    print('S5 validation: malformed BCD/ranges/date/leap-century and alarm rejection before writes: pass')


def check_y2k():
    for binary, hour24 in ((False, True), (True, True), (False, False), (True, False)):
        clock = Clock(binary, hour24)
        clock.invoke(5, 0x1999, 0x1231)
        # Hardware increments YY, not the independent CMOS century byte.
        clock.seed(0, 0, 0, 2000, 1, 1)
        clock.cmos[0x32] = 0x19
        before = clock.cmos[:]
        assert clock.invoke(4)[1:3] == (0x2000, 0x0101)
        assert clock.cmos[0x32] == 0x20
        assert clock.cmos[:0x32] == before[:0x32]
        clock.seed(0, 0, 0, 2000, 2, 29)
        clock.cmos[0x32] = 0x19
        assert clock.invoke(4)[1:3] == (0x2000, 0x0229)
        # A powered-off rollover must also be recovered at POST.
        clock.cmos[0x32] = 0x19
        clock.call('init_rtc')
        assert clock.cmos[0x32] == 0x20
        for year in (1980, 1999, 2000, 2079, 2080, 2099):
            cx = bcd(year // 100) << 8 | bcd(year % 100)
            assert not clock.invoke(5, cx, 0x0101)[0]
            assert clock.invoke(4)[1:3] == (cx, 0x0101)
        before = clock.cmos[:]
        assert clock.invoke(5, 0x1979, 0x1231)[0]
        assert clock.cmos == before
        clock.seed(0, 0, 0, 2000, 4, 30)
        clock.cmos[7] = 31 if binary else 0x31
        clock.cmos[0x32] = 0x19
        clock.writes.clear()
        assert clock.invoke(4)[0] and not clock.writes
    print('Y2K: native YY rollover, persisted century, leap day, POST recovery, DOS date range and invalid-date no-write: pass')


def check_validity():
    for ah in (2, 4, 6):
        clock = Clock()
        clock.cmos[0xB] |= 0x80
        assert clock.invoke(ah, 0x0102, 0x0300)[0]
        assert not clock.writes
        clock = Clock()
        clock.uip = -1
        assert clock.invoke(ah, 0x0102, 0x0300)[0]
        assert not clock.writes
    clock = Clock()
    clock.uip = 3
    assert not clock.invoke(2)[0]
    clock = Clock()
    clock.roll = (0, 0, 0, 2026, 3, 1)
    assert clock.invoke(2)[1:3] == (0, 1)
    clock = Clock()
    clock.roll = (0, 0, 0, 2026, 3, 1)
    assert clock.invoke(4)[1:3] == (0x2026, 0x0301)
    clock = Clock()
    clock.cmos[0xD] = 0
    clock.call('init_rtc')
    assert clock.cmos[0xD] == 0x80 and clock.cmos[0xE] == 0xA5
    for ah in (2, 4, 6):
        assert clock.invoke(ah, 0x0102, 0x0300)[0]
    clock.invoke(3, 0x0102, 0x0300)
    assert clock.invoke(2)[0] and clock.cmos[0xE] == 0xA5
    clock.invoke(5, 0x2026, 0x0301)
    assert clock.invoke(2)[1:3] == (0x0102, 0x0300)
    assert clock.invoke(4)[1:3] == (0x2026, 0x0301) and clock.cmos[0xE] == 0x25
    clock.call('init_rtc')
    assert not clock.invoke(2)[0]
    for first, second in ((3, 5), (5, 3)):
        clock = Clock()
        clock.cmos[0xD] = 0
        clock.call('init_rtc')
        values = {3: (0x0102, 0x0300), 5: (0x2026, 0x0301)}
        assert not clock.invoke(first, *values[first])[0]
        clock.call('init_rtc')  # A partial repair does not survive warm POST.
        assert not clock.invoke(second, *values[second])[0]
        assert clock.cmos[0xE] == 0xA5
        for ah in (2, 4, 6):
            assert clock.invoke(ah, 0x0102, 0x0300)[0]
        assert not clock.invoke(first, *values[first])[0]
        assert clock.cmos[0xE] == 0x25
        assert clock.invoke(2)[1:3] == values[3]
        assert clock.invoke(4)[1:3] == values[5]
    clock = Clock()
    clock.cmos[0xD] = 0
    assert clock.invoke(2)[0]  # Failure first observed outside POST.
    clock.call('init_rtc')
    assert clock.invoke(4)[0] and clock.cmos[0xE] & 0x80
    print('S3 coherence/availability: UIP bounded, SET, second/date rollover, VRT side-effect lifetime and explicit repair: pass')


def check_alarm():
    clock = Clock()
    clock.cmos[0xC] = 0x70  # Old AF plus unrelated PF/UF, AIE clear.
    masks = clock.masks.copy()
    assert not clock.invoke(6, 0x1234, 0x5600)[0]
    assert clock.masks == {0x21: masks[0x21] & ~4, 0xA1: masks[0xA1] & ~1}
    assert clock.cmos[0xC] == 0 and clock.callbacks() == 0
    enable = next(i for i, event in enumerate(clock.events) if event[0] == 'W' and event[1] == 0xB)
    assert ('C', 0x70) in clock.events[:enable]
    before, masks = clock.cmos[:], clock.masks.copy()
    clock.writes.clear()
    assert clock.invoke(6, 0x0102, 0x0300)[0]
    assert clock.cmos == before and clock.masks == masks and not clock.writes
    for cause in (0, 0x10, 0xC0, 0x90):
        assert clock.match(cause) == 0
    assert clock.match() == 1 and clock.match() == 1
    clock.invoke(7)
    assert clock.match() == 0 and clock.callbacks() == 2
    clock.invoke(6, 0x1234, 0x5600)
    clock.cmos[0xC] = 0xA0
    clock.invoke(7)
    assert clock.match() == 0
    for setter, cx, dx in ((3, 0x1210, 0x1100), (5, 0x2026, 0x0301)):
        clock = Clock()
        clock.cmos[0xB] |= 0x50  # Preserve PIE/UIE despite SET clearing UIE.
        clock.invoke(6, 0x1234, 0x5600)
        alarm = bytes(clock.cmos[i] for i in (1, 3, 5))
        controls = clock.cmos[0xB]
        clock.invoke(setter, cx, dx)
        assert bytes(clock.cmos[i] for i in (1, 3, 5)) == alarm
        assert clock.cmos[0xB] & 0x76 == controls & 0x76
        assert clock.match() == 1
    clock = Clock()
    clock.invoke(6, 0x1234, 0x5600)
    # A real guest callback cancels through nested INT1A and clobbers state.
    callback = bytes.fromhex('2e66ff060004 b407 cd1a 66b8efbeadde 66bb78563412 b83333 8ed8 8ec0 8ee0 8ee8 cf')
    clock.cpu.mem_write(0x90100, callback)
    assert clock.match() == 1 and not clock.cmos[0xB] & 0x20
    assert clock.match() == 0
    print('S6/S7 alarms: stale drain, one owner, recurrence, PF/UF gates, pre/callback cancel, armed setters, full callback-state restore: pass')


def check_shared_state():
    for flags in (2, 0x202, 0x602):
        clock = Clock()
        clock.call('publish_memory_cmos', flags=flags)
        assert clock.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x600 == flags & 0x600
        memory = clock.cmos[0x10:0x32]
        # Retain the real EBDA pointer/capacity; poison other non-clock state.
        clock.cpu.mem_write(0x400, bytes((i * 11 + 7) & 255 for i in range(14)))
        clock.cpu.mem_write(0x410, bytes((i * 13 + 3) & 255 for i in range(0xF0)))
        clock.cpu.mem_write(0x9FC00, bytes((i * 17 + 5) & 255 for i in range(1024)))
        clock.cpu.mem_write(0x9FCD0, struct.pack('<H', 7168))
        clock.cpu.mem_write(0x9FCD2, b'\x00')
        retained_bda = bytes(clock.cpu.mem_read(0x400, 256))
        retained_ebda = bytes(clock.cpu.mem_read(0x9FC00, 1024))
        assert int.from_bytes(clock.cmos[0x2E:0x30], 'big') == sum(clock.cmos[0x10:0x2E])
        clock.call('init_rtc')
        expected = (13 * 3600 + 45 * 60 + 59) * 1193182 >> 16
        assert struct.unpack('<I', clock.cpu.mem_read(0x46C, 4))[0] == expected
        assert clock.cmos[0xA] == 0x26 and clock.cmos[0xB] == 3
        for ah, cx, dx in ((0, 0, 0), (1, 2, 3), (2, 0, 0), (3, 0x0304, 0x0501),
                           (4, 0, 0), (5, 0x2026, 0x0930), (6, 0x0305, 0), (7, 0, 0)):
            assert not clock.invoke(ah, cx, dx, flags=flags)[0]
        before, ticks, masks = clock.cmos[:], bytes(clock.cpu.mem_read(0x46C, 5)), clock.masks.copy()
        for ah in (8, 0xFF):
            assert clock.invoke(ah, flags=flags)[0]
            assert clock.cmos == before and bytes(clock.cpu.mem_read(0x46C, 5)) == ticks and clock.masks == masks
        assert clock.cmos[0x10:0x32] == memory
        # Real IRQ8 after the memory publisher, not separate isolated helpers.
        clock.invoke(6, 0x1234, 0x5600, flags=flags)
        assert clock.match() == 1 and clock.cmos[0x10:0x32] == memory
        after_bda = bytes(clock.cpu.mem_read(0x400, 256))
        after_ebda = bytes(clock.cpu.mem_read(0x9FC00, 1024))
        assert after_bda[:0x6C] + after_bda[0x71:] == retained_bda[:0x6C] + retained_bda[0x71:]
        assert after_ebda[:0xD2] + after_ebda[0xD3:] == retained_ebda[:0xD2] + retained_ebda[0xD3:]
    print('S4/S8 POST helper: RTC tick seed; CMOS publication/checksum, unsupported calls, full ABI/IF/DF and actual IRQ8 composition: pass')


def check_dos_probe():
    for valid in (True, False):
        clock = Clock()
        if not valid:
            clock.cmos[0xE] |= 0x80
        clock.cpu.mem_write(0x90100, (BUILD / 'diagnostics/RTCCHECK.COM').read_bytes())
        clock.setup(flags=0x202)
        clock.cpu.emu_start(0x90100, 0, count=1000000)
        assert clock.dos_exit == (0 if valid else 1), clock.dos_output
        if valid:
            assert '2026-02-28 13:45:59' in clock.dos_output
            assert 'RTC and BIOS tick counter both advance.' in clock.dos_output
        else:
            assert 'RTC is invalid or unavailable.' in clock.dos_output
        assert not clock.writes, 'read-only COM must not set the clock'
    print('Read-only RTCCHECK.COM: actual DOS consumer/ROM dispatch, formatted output, advancing clock, unavailable result: pass')


def check_speedsys_probe():
    image = (BUILD / 'diagnostics/SPRTC.COM').read_bytes()
    capsule = image.index(bytes.fromhex('e87d007235a0154a'))
    provider = ROOT.parent / 'reference/software/speedsys/4.78/SPEEDSYS-code.bin'
    if provider.exists():
        code = provider.read_bytes()
        assert image[capsule:capsule + 0x3B] == code[0x9B90:0x9BCB]
        assert image[capsule + 0x80:capsule + 0xF0] == code[0x9C10:0x9C80]
    for binary, hour24 in ((False, True), (True, True), (False, False), (True, False)):
        clock = Clock(binary, hour24)
        clock.seed(13, 45, 58, 2026, 2, 28)
        clock.cpu.mem_write(0x90100, image)
        clock.setup(flags=0x202)

        def rollover(cpu, address, size, unused):
            if address == 0x90100 + capsule + 0x17 and clock.cmos[9] == (99 if binary else 0x99):
                clock.seed(0, 0, 0, 2000, 1, 1)
                clock.cmos[0x32] = 0x19

        clock.cpu.hook_add(UC_HOOK_CODE, rollover)
        clock.cpu.emu_start(0x90100, 0, count=1000000)
        assert clock.dos_exit == 0, clock.dos_output
        assert 'Return CF=00 Y2K mismatch=00' in clock.dos_output, clock.dos_output
        assert '2026-02-28 2000-01-01' in clock.dos_output, clock.dos_output
        assert clock.invoke(4)[1:3] == (0x2026, 0x0228)
        assert clock.invoke(2)[1:3] == (0x1345, 0x5901)
    print('SPRTC.COM: original Speedsys instruction sequence, four formats, year rollover and saved-clock restore: pass')


def check_clean_dos_speedsys():
    # Only a disposable backup copy is writable. No date-seeding driver or TSR.
    Fat16 = importlib.import_module('memory-fixture').Fat16
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    with tempfile.TemporaryDirectory(prefix='rtc-dos-', dir=ROOT / 'build/tmp') as temporary:
        folder = Path(temporary)
        program = folder / 'SPRTC.COM'
        subprocess.run([nasm, '-f', 'bin', '-D', 'RTC_SPEEDSYS_TEST',
                        '-D', 'RTC_SPEEDSYS_EMULATOR', '-o', str(program),
                        str(ROOT / 'tests/rtc-test.asm')], check=True)
        image = folder / 'test.vhd'
        shutil.copyfile(Path(os.environ['BAIOS_DOS_VHD']), image)
        fat = Fat16(image)
        try:
            with image.open('r+b', buffering=0) as disk:
                fat.replace(disk, 'CONFIG.SYS', b'SHELL=C:\\DOS\\COMMAND.COM /P\r\n')
                fat.replace(disk, 'CONFIG.B~K', program.read_bytes(), b'SPRTC   COM')
                fat.replace(disk, 'AUTOEXEC.BAT', b'@ECHO OFF\r\nC:\\SPRTC.COM\r\n')
        finally:
            fat.vhd.close()
        subprocess.run(['pwsh', '-NoProfile', '-File', str(ROOT / 'tools/run-card-vhd.ps1'),
                        '-ImagePath', str(image), '-MemoryKiB', '8192',
                        '-ExpectedExitCode', '103', '-TimeoutSeconds', '45'], check=True)
    print('86Box clean DOS: original Speedsys RTC/Y2K sequence passed without HIMEM, EMM386 or TSRs.')


if __name__ == '__main__':
    check_ticks()
    check_formats()
    check_validation()
    check_y2k()
    check_validity()
    check_alarm()
    check_shared_state()
    check_dos_probe()
    check_speedsys_probe()
    if '--dos-speedsys' in sys.argv:
        check_clean_dos_speedsys()
    print('Production RTC checks passed. Physical clock/battery validation remains required.')
