"""Exercise public APM entries, real HLT/wake, and caller-owned protected descriptors."""
import argparse
import hashlib
import importlib
import os
from pathlib import Path
import shutil
import struct
import subprocess

from unicorn import x86_const as x

chip = importlib.import_module('test-chipset')
rtc = chip.setup.rtc
REGS = rtc.REGS
STATE, LENGTH = 0x27A, 0x27D


def descriptor(base, length, access, flags=0):
    limit = length - 1
    return struct.pack('<HHBBBB', limit & 65535, base & 65535,
                       base >> 16 & 255, access, (limit >> 16 & 15) | flags, base >> 24)


class Apm(chip.Chipset):
    def __init__(self):
        self.mode = 0
        self.halts = []
        self.control_writes = []
        self.vga_calls = []
        self.range = (0xF0000 + rtc.symbol('apm_int15'), 0xF0000 + rtc.symbol('apm32_end'))
        super().__init__()
        self.cpu.mem_write(0x15 * 4, struct.pack('<HH', rtc.symbol('int15'), 0xF000))
        self.contract = None

    def code(self, cpu, address, size, unused):
        if 0xC0000 <= address < 0xC8000:
            self.vga_calls.append(address)
        if self.range[0] <= address < self.range[1] and cpu.mem_read(address, 1) == b'\xf4':
            self.halts.append(address)
            return  # Execute HLT itself. The external wake is delivered after Unicorn stops.
        super().code(cpu, address, size, unused)

    def interrupt(self, cpu, vector, unused):
        if vector == 0x10:
            self.vga_calls.append(vector)
        if self.mode and vector < 32:
            raise AssertionError(('Protected OS exception', vector,
                                  cpu.reg_read(x.UC_X86_REG_CS), hex(cpu.reg_read(x.UC_X86_REG_EIP)),
                                  hex(cpu.reg_read(x.UC_X86_REG_CR0)), cpu.reg_read(x.UC_X86_REG_GDTR)))
        super().interrupt(cpu, vector, unused)

    def port_out(self, cpu, port, size, value, unused):
        if port not in (0x20, 0xA0):  # IRQ acknowledgements are permitted.
            self.control_writes.append((port, size, value))
        super().port_out(cpu, port, size, value, unused)

    def controls(self, ebda=False):
        result = (dict(self.chipset), self.fast, self.a20, bytes(self.cmos),
                  self.cpu.reg_read(x.UC_X86_REG_CR0), tuple(self.control_writes),
                  tuple(self.vga_calls), dict(self.masks))
        if ebda:
            base = struct.unpack('<H', self.cpu.mem_read(0x40E, 2))[0] * 16
            data = bytes(self.cpu.mem_read(base, 1024))
            result += (data[:STATE] + data[LENGTH:],)
        return result

    def record_apm(self):
        base = struct.unpack('<H', self.cpu.mem_read(0x40E, 2))[0] * 16
        return bytes(self.cpu.mem_read(base + STATE, 3))

    def run(self, begin, end):
        wakes = 0
        while True:
            before = len(self.halts)
            # Unicorn's MODE16 API subtracts visible CS*16 even in protected mode.
            start = begin + self.cpu.reg_read(x.UC_X86_REG_CS) * 16 if self.mode else begin
            self.cpu.emu_start(start, end, count=4000000)
            if len(self.halts) == before:
                break
            assert len(self.halts) == before + 1, (before, self.halts[before:])
            address = self.halts[-1]
            physical = self.cpu.reg_read(x.UC_X86_REG_IP if self.mode != 3 else x.UC_X86_REG_EIP) + 0xF0000
            assert physical == address + 1, ('HLT did not execute', hex(physical), hex(address))
            assert self.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            if self.mode:
                self.protected_irq()
            else:
                rtc.Clock.interrupt(self, self.cpu, 8, None)
            wakes += 1
            assert wakes == 1, 'One Idle call must not wait across multiple interrupts'
            begin = self.cpu.reg_read(x.UC_X86_REG_EIP) + (0xF0000 if not self.mode else 0)
        return wakes

    def protected_irq(self):
        # External OS IRQ0 frame/handler, using the caller's current stack.
        flags = self.cpu.reg_read(x.UC_X86_REG_EFLAGS)
        cs = self.cpu.reg_read(x.UC_X86_REG_CS)
        ip = self.cpu.reg_read(x.UC_X86_REG_EIP)
        width = 4 if self.mode == 3 else 2
        sp = self.cpu.reg_read(x.UC_X86_REG_ESP if width == 4 else x.UC_X86_REG_SP)
        for value in (flags, cs, ip):
            sp -= width
            self.cpu.mem_write(sp, int(value & ((1 << (8 * width)) - 1)).to_bytes(width, 'little'))
        self.cpu.reg_write(x.UC_X86_REG_ESP if width == 4 else x.UC_X86_REG_SP, sp)
        self.cpu.reg_write(x.UC_X86_REG_EFLAGS, flags & ~0x300)
        self.cpu.reg_write(x.UC_X86_REG_CS, 8)
        self.cpu.reg_write(x.UC_X86_REG_EIP, 0x9100)

    def api(self, function, bx=0, cx=0, flags=0x202, outputs=(), ah=0x53):
        if self.mode == 0:
            self.setup(flags=flags)
            begin, end = 0x90000, 0x90002
            self.cpu.mem_write(begin, b'\xcd\x15\x90')
        else:
            for i, name in enumerate(REGS[:7]):
                self.cpu.reg_write(getattr(x, 'UC_X86_REG_' + name), 0xA0000000 + i * 0x10000 + 0x5A5A)
            self.cpu.reg_write(x.UC_X86_REG_CS, 8)
            self.cpu.reg_write(x.UC_X86_REG_ESP, 0x88000 if self.mode == 3 else 0xA0077FF0)
            self.cpu.reg_write(x.UC_X86_REG_EFLAGS, flags)
            self.cpu.reg_write(x.UC_X86_REG_EIP, 0x9000)
            begin = 0x9000
            width = 4 if self.mode == 3 else 2
            pointer = self.contract['offset'].to_bytes(width, 'little') + struct.pack('<H', self.pm_selector)
            self.cpu.mem_write(0x9200, pointer)
            instruction = b'\xff\x1d\x00\x92\x00\x00' if width == 4 else b'\xff\x1e\x00\x92'
            self.cpu.mem_write(begin, instruction + b'\x90')
            end = begin + len(instruction)
        self.cpu.reg_write(x.UC_X86_REG_AX, ah << 8 | function)
        self.cpu.reg_write(x.UC_X86_REG_BX, bx)
        self.cpu.reg_write(x.UC_X86_REG_CX, cx)
        self.cpu.reg_write(x.UC_X86_REG_DX, 0x2468)
        before = self.state()
        ticks = bytes(self.cpu.mem_read(0x46C, 4)) if not self.mode else bytes(self.cpu.mem_read(0x6500, 4))
        wakes = self.run(begin, end)
        after = self.state()
        returned = self.cpu.reg_read(x.UC_X86_REG_EFLAGS)
        assert self.cpu.reg_read(x.UC_X86_REG_EIP) == (end if self.mode else 2), 'Caller continuation not reached'
        assert (flags ^ returned) & 0x600 == 0, 'IF/DF changed'
        changed = set(outputs) if not returned & 1 else {'EAX'}
        full = {'EBX', 'ESI'} if function == 3 and not returned & 1 else set()
        for name in REGS:
            if name in changed:
                if name not in full:
                    assert before[name] >> 16 == after[name] >> 16, ('Upper half changed', name)
            else:
                assert before[name] == after[name], (function, self.mode, name, hex(before[name]), hex(after[name]))
        if wakes:
            current = bytes(self.cpu.mem_read(0x46C if not self.mode else 0x6500, 4))
            assert struct.unpack('<I', current)[0] == struct.unpack('<I', ticks)[0] + 1
        return {'cf': bool(returned & 1), 'ax': after['EAX'] & 65535,
                'bx': after['EBX'] & 65535, 'cx': after['ECX'] & 65535,
                'dx': after['EDX'] & 65535, 'si': after['ESI'] & 65535,
                'di': after['EDI'] & 65535, 'ebx': after['EBX'], 'esi': after['ESI'], 'wakes': wakes}

    def connect(self, mode):
        result = self.api(mode, outputs=() if mode == 1 else
                          ('EAX', 'EBX', 'ECX', 'ESI', 'EDI') if mode == 2 else
                          ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI'))
        assert not result['cf']
        if mode == 1:
            return
        self.contract = {'offset': result['bx'] if mode == 2 else result['ebx'],
                         'data': result['cx'] if mode == 2 else result['dx'],
                         'code': result['ax'], 'length': result['si'] if mode == 2 else result['esi'] & 65535,
                         'data_length': result['di']}
        assert result['ax'] == 0xF000 and result['di'] == LENGTH
        assert result['si'] == rtc.symbol('apm16_end') if mode == 2 else result['esi'] >> 16 == rtc.symbol('apm16_end')
        if mode == 3:
            assert result['cx'] == 0xF000 and self.contract['length'] == rtc.symbol('apm32_end')
            self.contract.update(code16=result['cx'], length16=result['esi'] >> 16)
        self.enter(mode)

    def enter(self, mode):
        self.mode = mode
        self.pm_selector = 0x30 if mode == 2 else 0x20
        self.data_selector = self.pm_selector + (8 if mode == 2 else 16)
        gdt = bytearray(64)
        gdt[8:16] = descriptor(0, 65536, 0x9A, 0x40 if mode == 3 else 0)
        gdt[16:24] = descriptor(0, 0x100000, 0x92, 0x40 if mode == 3 else 0)
        code = self.contract
        gdt[self.pm_selector:self.pm_selector + 8] = descriptor(code['code'] * 16, code['length'], 0x9A, 0x40 if mode == 3 else 0)
        if mode == 3:
            gdt[0x28:0x30] = descriptor(code['code16'] * 16, code['length16'], 0x9A)
        gdt[self.data_selector:self.data_selector + 8] = descriptor(code['data'] * 16, code['data_length'], 0x92)
        self.cpu.mem_write(0x600, bytes(gdt))
        self.cpu.reg_write(x.UC_X86_REG_GDTR, (0, 0x600, len(gdt) - 1, 0))
        self.cpu.reg_write(x.UC_X86_REG_CR0, self.cpu.reg_read(x.UC_X86_REG_CR0) | 1)
        self.cpu.reg_write(x.UC_X86_REG_CS, 8)
        # UC_MODE16 setters leave data/stack real-mode bases; real OS MOVs load descriptors.
        loader = b'\xfa' + (b'\x66' if mode == 3 else b'') + b'\xb8\x10\x00\x8e\xd8\x8e\xc0\x8e\xe0\x8e\xe8\x8e\xd0'
        self.cpu.mem_write(0x9400, loader)
        self.cpu.emu_start(0x9480, 0x9400 + len(loader), count=100)
        # OS timer handler preserves general registers and acknowledges IRQ0.
        irq = (b'\x50\x1e\xb8\x10\x00\x8e\xd8\x66\xff\x06\x00\x65\xb0\x20\xe6\x20\x1f\x58\xcf' if mode == 2 else
               b'\x50\x1e\x66\xb8\x10\x00\x8e\xd8\xff\x05\x00\x65\x00\x00\xb0\x20\xe6\x20\x1f\x58\xcf')
        self.cpu.mem_write(0x9100, irq)

    def real(self):
        self.cpu.reg_write(x.UC_X86_REG_CR0, self.cpu.reg_read(x.UC_X86_REG_CR0) & ~1)
        self.mode = 0


def ok(m, function, **kwargs):
    result = m.api(function, **kwargs)
    assert not result['cf'], (function, m.mode, result)
    return result


def error(m, function, code, **kwargs):
    before = m.record_apm()
    controls = m.controls(ebda=True)
    result = m.api(function, **kwargs)
    assert result['cf'] and result['ax'] >> 8 == code, (function, m.mode, result, code)
    assert m.record_apm() == before
    assert m.controls(ebda=True) == controls, ('refusal side effect', function, m.mode)
    return result


def interfaces():
    for flags in (0x202, 0x602):
        m = Apm()
        result = ok(m, 0, flags=flags, outputs=('EAX', 'EBX', 'ECX'))
        assert (result['ax'], result['bx'], result['cx']) == (0x0102, 0x504D, 3)
        error(m, 0, 9, bx=0x0100, flags=flags)
        for mode in (1, 2, 3):
            m = Apm()
            m.connect(mode)
            ok(m, 6, flags=flags)
            error(m, 0xFF, 0xFF, flags=flags)
            if mode != 1:
                for function in range(4):
                    error(m, function, 0xFF, flags=flags)
                error(m, 6, 0xFF, ah=0x52, flags=flags)
                m.real()
                ok(m, 4)
                ok(m, 1)  # Supported real connection, while the old far pointer remains.
                m.enter(mode)
                error(m, 6, 3, flags=flags)
                m.real()
                ok(m, 4)
                ok(m, mode, outputs=('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI'))
                m.enter(mode)
            ok(m, 4)
            error(m, 6, 3)
    print('PASS discovery and real/PM16/PM32 public far-call returns, exact descriptors, registers and independent DF success/refusal', flush=True)


def session():
    for mode in (1, 2, 3):
        m = Apm()
        error(m, 5, 3)
        m.connect(mode)
        ok(m, 8, bx=0xFFFF, cx=0)
        if mode != 1:
            m.real()
        for attempted in (1, 2, 3):
            error(m, attempted, {1: 2, 2: 5, 3: 7}[mode])
        for version in (0x0100, 0x0101, 0x0102, 0x0200):
            result = ok(m, 0x0E, cx=version, outputs=('EAX',))
            assert result['ax'] == min(version, 0x0102)
            assert m.record_apm()[1] == (result['ax'] & 255)
        ok(m, 4)
        m.connect(mode)
        assert m.record_apm() == bytes((mode, 0, 1))
        assert ok(m, 5)['wakes'] == 0
        error(m, 0x0C, 0xFF, bx=1)
        result = ok(m, 0x0A, bx=1, cx=0xA55A, outputs=('EBX', 'ECX'))
        assert result['cx'] == 0xA5FF and result['dx'] == 0x2468 and result['si'] == 0x5A5A
        ok(m, 0x0E, cx=0x0101, outputs=('EAX',))
        result = ok(m, 0x0A, bx=1, outputs=('EBX', 'ECX', 'EDX'))
        assert (result['cx'], result['dx'], result['si']) == (0x80FF, 0xFFFF, 0x5A5A)
        ok(m, 0x0E, cx=0x0102, outputs=('EAX',))
        result = ok(m, 0x0A, bx=1, outputs=('EBX', 'ECX', 'EDX', 'ESI'))
        assert (result['bx'], result['cx'], result['dx'], result['si']) == (0x01FF, 0x80FF, 0xFFFF, 0)
    print('PASS exclusive connections, policy retained across disconnect/reconnect, and 1.0/1.1/1.2 negotiated output contracts', flush=True)


def idle():
    for mode in (1, 2, 3):
        for slow in (False, True):
            m = Apm()
            record = bytearray(m.record())
            record[6] = 0x40 if slow else 0
            m.draft(record)
            m.call('chipset_settings_save')
            m.call('chipset_settings_load')
            m.call('chipset_apply')
            m.connect(mode)
            controls = m.controls()
            error(m, 0x0B, 0x80)
            for flags in (2, 0x202, 0x602):
                assert ok(m, 5, flags=flags)['wakes'] == 1
                ok(m, 6, flags=flags)
            ok(m, 6)
            error(m, 0x0B, 0x80)
            assert controls == m.controls()
            ok(m, 8, bx=1, cx=0)
            disabled_controls = m.controls()
            assert ok(m, 5)['wakes'] == 0
            assert m.controls() == disabled_controls
    print('PASS actual HLT -> one IRQ -> caller in all modes, IF/DF preservation, Fast/Slow/cache/CMOS controls unchanged; disabled Idle has no halt', flush=True)


def policy():
    for mode in (1, 2, 3):
        m = Apm()
        m.cmos[0x38] = 0xA6  # Unrelated saved state must survive APM Defaults.
        m.cpu.mem_write(m.base + 0x350, bytes(range(0xB0)))
        m.connect(mode)
        def installation(expected):
            if mode != 1:
                m.real()
            result = ok(m, 0, outputs=('EAX', 'EBX', 'ECX'))
            assert (result['ax'], result['bx'], result['cx']) == (0x0102, 0x504D, expected)
            if mode != 1:
                m.enter(mode)
        installation(3)
        ok(m, 0x0E, cx=0x0102, outputs=('EAX',))
        for function, bx in ((8, 1), (0x0F, 1), (0x0D, 1)):
            error(m, function, 0x0A, bx=bx, cx=2)
            error(m, function, 0x0A, bx=bx, cx=0x0100)
        ok(m, 8, bx=0xFFFF, cx=0)
        installation(11)
        assert ok(m, 5)['wakes'] == 0
        error(m, 0x0F, 1, bx=1, cx=0)
        controls = m.controls(ebda=True)
        ok(m, 9, bx=0xFFFF)
        assert m.controls(ebda=True) == controls
        assert m.record_apm() == bytes((mode, 2, 0))
        installation(3)
        assert ok(m, 5)['wakes'] == 1
        ok(m, 0x0F, bx=1, cx=0)
        installation(19)
        error(m, 8, 0x0B, bx=1, cx=0)
        error(m, 5, 0x0B)
        error(m, 0x0B, 0x0B)
        ok(m, 0x0F, bx=1, cx=1)
        installation(3)
        assert ok(m, 5)['wakes'] == 1
        for function in (8, 9, 0x0F):
            error(m, function, 9, bx=0x0101, cx=1)
        ok(m, 0x0F, bx=1, cx=0)
        if mode != 1:
            m.real()
        ok(m, 4)
        m.connect(mode)
        assert m.record_apm() == bytes((mode, 0, 2))
        error(m, 0x0E, 0x0B, cx=0x0102)
        ok(m, 0x0F, bx=1, cx=1)
        ok(m, 0x0E, cx=0x0102, outputs=('EAX',))
        assert ok(m, 5)['wakes'] == 1
    print('PASS enable/engage/default state transitions, forbidden pair rejection, full-width parameters, and subsequent actual Idle reopening', flush=True)


def status():
    m = Apm()
    result = ok(m, 0x0A, bx=1, outputs=('EBX', 'ECX', 'EDX', 'ESI'))
    assert (result['bx'], result['cx'], result['dx'], result['si']) == (0x01FF, 0x80FF, 0xFFFF, 0)
    result = ok(m, 0x10, outputs=('EBX', 'ECX'))
    assert result['bx'] == result['cx'] == 0
    error(m, 0x0C, 9, bx=1)
    for function in (4, 5, 6, 7, 8, 9, 0x0B, 0x0D, 0x0E, 0x0F, 0x11, 0x12):
        error(m, function, 3, bx=1 if function in (7, 8, 9, 0x0D, 0x0F) else 0, cx=1)
    for function in (1, 2, 3, 0x10):
        error(m, function, 9, bx=0x0100)
    for mode in (1, 2, 3):
        m = Apm()
        m.connect(mode)
        for version in (0x0100, 0x0101, 0x0102):
            ok(m, 0x0E, cx=version, outputs=('EAX',))
            for function, required in ((0x0D, 0x0101), (0x10, 0x0102), (0x11, 0x0102), (0x12, 0x0102)):
                if version < required:
                    error(m, function, 0xFF, bx=1 if function == 0x0D else 0, cx=1)
                elif function == 0x0D:
                    controls = m.controls(ebda=True)
                    ok(m, function, bx=1, cx=1)
                    assert m.controls(ebda=True) == controls
                elif function == 0x10:
                    result = ok(m, function, outputs=('EBX', 'ECX'))
                    assert result['bx'] == result['cx'] == 0
                else:
                    error(m, function, 0x0C)
        ok(m, 0x0E, cx=0x0102, outputs=('EAX',))
        for function in (4, 0x0E, 0x10, 0x11, 0x12):
            error(m, function, 9, bx=0x0100, cx=0x0102)
        ok(m, 8, bx=1, cx=0)
        for function in (7, 0x0C, 0x0D):
            error(m, function, 1, bx=1, cx=1)
        ok(m, 8, bx=1, cx=1)
        for _ in range(2):
            error(m, 0x0B, 0x80)
        assert ok(m, 5)['wakes'] == 1
        error(m, 0x0B, 0x80)
        for state in (1, 2, 3):
            error(m, 7, 0x60, bx=1, cx=state)
            error(m, 0x0B, 0x80)
        error(m, 7, 0x0A, bx=1, cx=6)
        error(m, 7, 9, bx=0x0101, cx=1)
        error(m, 0x0A, 9, bx=0x8001)
        for function in (0x0C, 0x0D):
            error(m, function, 9, bx=0x0100)
        error(m, 0x0C, 9, bx=1)
        before = m.record_apm()
        for value in (0, 1):
            controls = m.controls(ebda=True)
            ok(m, 0x0D, bx=1, cx=value)
            assert m.record_apm() == before
            assert m.controls(ebda=True) == controls
            assert ok(m, 5)['wakes'] == 1
        for function, expected in ((0x11, 0x0C), (0x12, 0x0C), (0x13, 0xFF), (0x20, 0xFF), (0x80, 0xFF)):
            error(m, function, expected)
        result = ok(m, 0x10, outputs=('EBX', 'ECX'))
        assert result['bx'] == result['cx'] == 0
        ok(m, 6)
    print('PASS desktop/no-battery status, empty events/devices, honest global state refusals and complete mandatory/optional dispatch contrasts', flush=True)


def relocation():
    for mode in (1, 2, 3):
        m = Apm()
        m.connect(mode)
        ok(m, 8, bx=1, cx=0)
        original = bytes(m.cpu.mem_read(0x9FC00, 1024))
        m.cpu.mem_write(0x97C00, original)
        m.cpu.mem_write(0x40E, struct.pack('<H', 0x97C0))
        m.cpu.mem_write(0x9FC00 + STATE, b'\0\0\0')
        old = bytes(m.cpu.mem_read(0x9FC00, 1024))
        if mode != 1:
            # The external memory owner keeps its APM data descriptor valid.
            m.cpu.mem_write(0x600 + m.data_selector, descriptor(0x97C00, m.contract['data_length'], 0x92))
        assert ok(m, 5)['wakes'] == 0
        assert m.record_apm() == bytes((mode, 0, 1))
        assert bytes(m.cpu.mem_read(0x9FC00, 1024)) == old
        relocated = bytes(m.cpu.mem_read(0x97C00, 1024))
        assert relocated == original
        m.real()
        error(m, 1, {1: 2, 2: 5, 3: 7}[mode])
        result = ok(m, 0, outputs=('EAX', 'EBX', 'ECX'))
        assert result['cx'] == 11
        ok(m, 4)
        m.connect(2)
        assert m.contract['data'] == 0x97C0
        assert ok(m, 5)['wakes'] == 0
    print('PASS active real/protected sessions after EBDA relocation, valid external descriptor update, stale old state untouched and relocated connect contract', flush=True)


def startup():
    production = type(chip.setup.production_post_model())

    class BootApm(Apm, production):
        def port_out(self, cpu, port, size, value, unused):
            if port in (0x84, 0x40, 0x41):  # External I/O settle and PIT data hardware.
                self.control_writes.append((port, size, value))
                if port in (0x40, 0x41):
                    self.pit_writes.append((port, value))
                return
            super().port_out(cpu, port, size, value, unused)

    for cold in (True, False):
        m = BootApm()
        m.startup_native_owners = ('init_pic_pit', 'init_rtc', 'init_at_prerequisites')
        m.connect(1)
        ok(m, 0x0E, cx=0x0102, outputs=('EAX',))
        ok(m, 8, bx=1, cx=0)
        assert m.record_apm() == b'\x01\x02\x01'
        m.startup(reset=cold, production_controls=True, through_boot=True)
        assert m.startup_hops[-1] == 'boot_sector'
        assert all(owner in m.startup_hops for owner in m.startup_native_owners)
        assert (0x61, 1, 0x0C) in m.control_writes
        assert (0x43, 1, 0x54) in m.control_writes and (0x41, 1, 0x12) in m.control_writes
        assert m.record_apm() == b'\0\0\0'
        result = ok(m, 0, outputs=('EAX', 'EBX', 'ECX'))
        assert result['cx'] == 3
        error(m, 5, 3)
        m.connect(1)
        assert ok(m, 5)['wakes'] == 1
    print('PASS actual cold/warm POST -> boot handoff -> public APM initial state and idle/wake', flush=True)


def dispatch():
    m = Apm()
    m.connect(1)
    assert ok(m, 5)['wakes'] == 1
    result = ok(m, 0x55, ah=0x88, outputs=('EAX',))
    assert result['ax'] == struct.unpack('<H', m.cpu.mem_read(m.base + 0xD0, 2))[0]
    result = ok(m, 0x55, ah=0xC0, outputs=('EAX', 'EBX', 'ES'))
    assert result['bx'] == rtc.symbol('system_configuration')
    m.cpu.mem_write(m.base + 0x1E6 + 6, b'\0')
    error(m, 2, 3, ah=0xC2)
    error(m, 0x55, 2, ah=0x87, cx=0x8001)
    error(m, 0x55, 0x86, ah=0x89)
    assert ok(m, 5)['wakes'] == 1
    print('PASS APM calls preserve existing INT15 memory/configuration/mouse/block-move refusal and unknown-service paths', flush=True)


def native():
    floppy = importlib.import_module('floppy-matrix')
    Fat16 = importlib.import_module('memory-fixture').Fat16
    source = chip.ROOT / 'src'
    backup = Path(os.environ['BAIOS_DOS_VHD'])
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    exe = shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA']) /
        'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    work = rtc.BUILD / 'review/apm'
    work.mkdir(parents=True, exist_ok=True)
    for label, driver, managers in (('probe', False, False), ('driver-dos', True, False), ('driver-emm386', True, True)):
        vm = work / label
        assert vm.resolve().is_relative_to(rtc.BUILD.resolve())
        if vm.exists():
            shutil.rmtree(vm)     # Resolved, task-owned completed/diagnosed VM only.
        vm.mkdir()
        program = vm / 'APMTEST.COM'
        defines = ['-DAPM_DRIVER_ONLY', '-DAPM_REAL_ONLY'] if driver else []
        if managers:
            defines.append('-DAPM_MANAGERS')
        floppy.run_hidden([nasm, *defines, '-f', 'bin', '-o', str(program),
                           str(chip.ROOT / 'tests/apm-test.asm')], check=True)
        disk = vm / 'dos.vhd'
        shutil.copyfile(backup, disk)
        fat = Fat16(disk)
        try:
            provider = fat.read('CPQDOS/POWER.EXE')
            assert hashlib.sha256(provider).hexdigest() == 'a7d9191422e8f3b61c610a0b5f71d2843496ae5b5ecfe7a7ad59a8ed8f5930f8'
            fat.vhd.file.seek(-512, 2)
            footer = fat.vhd.file.read(512)
            geometry = (footer[59], footer[58], struct.unpack_from('>H', footer, 56)[0])
            config = 'SHELL=C:\\DOS\\COMMAND.COM /P /E:1536\r\nFILES=30\r\nBUFFERS=10\r\n'
            if managers:
                config += 'DEVICE=C:\\DOS\\HIMEM.SYS /V\r\nDEVICE=C:\\DOS\\EMM386.EXE NOEMS X=F000-F5FF /V\r\nDOS=HIGH,UMB\r\n'
            if driver:
                config += ('DEVICEHIGH=' if managers else 'DEVICE=') + 'C:\\CPQDOS\\POWER.EXE\r\n'
            batch = '@ECHO OFF\r\n'
            batch += 'C:\\APMTEST.COM >C:\\APM.LOG\r\n'
            with disk.open('r+b', buffering=0) as output:
                fat.replace(output, 'CONFIG.SYS', config.encode())
                fat.replace(output, 'AUTOEXEC.BAT', batch.encode())
                fat.replace(output, 'CONFIG.B~K', program.read_bytes(), b'APMTEST COM')
                fat.replace(output, 'AUTOEXEC.B~K', b'\r\n', b'APM     LOG')
        finally:
            fat.vhd.close()
        roms = floppy.config(vm, disk, 0, 0, vm / 'a.img', vm / 'b.img', geometry)
        private_roms = vm / 'roms'
        shutil.copytree(roms, private_roms)
        wrapper = private_roms / 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
        if driver:
            system = vm / 'observed-system.rom'
            floppy.run_hidden([nasm, '-DVGA_BIOS_141', '-DEMULATOR_APM_TEST', '-f', 'bin', '-I', str(source) + '/',
                               '-o', str(system), str(source / 'bios.asm')], check=True)
            binary = bytearray(system.read_bytes())
            binary[-1] = -sum(binary[:-1]) & 255
            physical = (rtc.BUILD / 'baios-presario800-vga60.bin').read_bytes()
            observed = physical[:65536] + binary
            assert len(observed) == 131072 and sum(binary) & 255 == 0
            wrapper.write_bytes(observed)
        print(f'START native {label}: original CPQ POWER provider, disposable VHD {vm}', flush=True)
        result = floppy.run_hidden([exe, '-P', str(vm), '-R', str(private_roms), '-L', str(vm / '86box.log'), '-N'], timeout=90)
        fat = Fat16(disk)
        try:
            output = fat.read('APM.LOG').decode('cp437')
            print(output, flush=True)
            (work / f'{label}.txt').write_text(output)
            if driver:
                assert 'Compaq POWER installed and APM active' in output
                context = ('HIMEM XMS present; DOS caller is virtual86 (CR0.PE=1)' if managers else
                           'DOS caller is real mode (CR0.PE=0)')
                assert output.count(context) == 2  # Before and after the causal idle/wake.
        finally:
            fat.vhd.close()
        assert result.returncode == (0x6B if driver else 0x6A), (label, result.returncode, vm)
        assert 'PASS' in output and 'FAILED' not in output
        print(f'PASS native {label}: actual calling interfaces/HLT wake or original driver -> BIOS Idle -> interrupt -> DOS keyboard continuation', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    cases = {'interfaces': interfaces, 'session': session, 'idle': idle, 'policy': policy, 'status': status,
             'relocation': relocation, 'startup': startup, 'dispatch': dispatch}
    parser.add_argument('--case', choices=cases, action='append')
    parser.add_argument('--86box', action='store_true', dest='native')
    args = parser.parse_args()
    for case in args.case or ([] if args.native else cases):
        cases[case]()
    if args.native:
        native()
