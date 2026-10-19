"""Execute device setup, POST and installed INT14/17 against external devices."""
import argparse
import importlib
import struct
import os
import shutil
import tempfile
import zlib
from pathlib import Path
from unicorn import x86_const as x
from unicorn import UC_HOOK_CODE

setup = importlib.import_module('test-setup')
ide = importlib.import_module('test-ide-options')
rtc = setup.rtc
DEFAULT = bytes((1, 0, 1, 2, 0, 1, 1, 1))
PAIRS = ((0x338, 0x238), (0x3E8, 0x2E8), (0x2E8, 0x2E0), (0x220, 0x228))
PARALLEL = (0, 0x3BC, 0x378, 0x278)
DIVISORS = (1047, 768, 384, 192, 96, 48, 24, 12, 6, 3, 2)
ENTER_DEVICES = [0x50] * 3 + [28]


def board_policy(payload):
    data = bytearray(payload)
    data[1] = 0
    data[2] = 1
    data[7] = 1
    return bytes(data)


def record(model, payload=DEFAULT):
    data = b'P1\x01' + payload
    model.cmos[0x5D:0x69] = data + bytes((-sum(data) & 255,))


class Ports(setup.Setup):
    def __init__(self, segment=0x9FC0, uart=(), printer=()):
        self.cr = [0x3F, 0x9F, 0xDC, 0x6C]
        self.config = False
        self.unlock = 0
        self.cr_index = 0
        self.io = []
        self.uarts = {base: [0, 0xA0, 0, 0x83, 0x12, 0x60, 0xB0, 0x39] for base in uart}
        self.divisors = {}
        self.tx = []
        self.rx = {}
        self.delayed_uart = None
        self.lpts = {base: [0x37, 0xD8, 0x2C] for base in printer}
        self.lpt_pins = 0xE7   # External input differs from every saved latch.
        self.printed = []
        self.onboard_uart = {}
        self.onboard_lpt = {}
        self.kbc_cb = 0x4D
        self.kbc_next = None
        self.aux_reply = []
        self.mouse_commands = []
        self.mouse_packets = 0
        self.stop_post = False
        self.post_done = False
        self.post_terminal = 0xF0000+rtc.symbol('init_fpu')
        self.ata_device = None
        self.rtc_fault = None
        self.continue_warm = False
        self.starting = False
        self.controlled_entry = 0xF0000+rtc.symbol('controlled_defaults_restart')
        self.probe_snapshot = None
        self.probe_entry = 0xF0000+rtc.symbol('ports_uart_probe')
        self.initialize_entry = 0xF0000+rtc.symbol('ports_uart_initialize')
        self.pit0_writes = []
        self.wait_irqs = []
        self.delivered_irqs = []
        self.wait_start = 0xF0000+rtc.symbol('ports_wait')
        self.wait_end = 0xF0000+rtc.symbol('int14')
        self.vga_input = (rtc.ROOT/'build/baios-presario800.bin').read_bytes()[:32768]
        super().__init__(segment=segment)
        self.cpu.mem_map(0x200000, 6*1024*1024)  # Match retained 8 MiB bank/count.
        # The device observer has no events inside the interrupt-masked RAM
        # pass. Execute every RAM instruction without per-instruction Python.
        self.cpu.hook_del(self.code_hook)
        self.cpu.hook_add(UC_HOOK_CODE, self.code, begin=1,
                         end=0xF0000+rtc.symbol('chipset_visible_ram_test')-1)
        self.cpu.hook_add(UC_HOOK_CODE, self.code,
                         begin=0xF0000+rtc.symbol('chipset_runtime_ram_check'),
                         end=0xFFFFFFFF)
        self.cmos[0x3E] = 0xA5  # Fixed unrelated mechanical seek policy.
        self.ata_device = ide.Disk(('ata', 'absent'))
        self.ata_device.cpu = self.cpu
        for vector, name in ((0x13, 'int13'), (0x11, 'int11'), (0x74, 'int74')):
            self.cpu.mem_write(vector*4, struct.pack('<HH', rtc.symbol(name), 0xF000))
        self.cpu.mem_write(0x410, struct.pack('<H', 0x31FE))
        self.cpu.mem_write(self.base+0x174, b'\x01')
        self.cpu.mem_write(0x49E, b'\x01')

    def warm_continuation(self, initial=(0x3F, 0x9F, 0xDC, 0x6C)):
        self.cr[:] = initial
        self.onboard_uart = {0: [0, 0, 0, 3, 0, 0x60, 0xB0, 0], 4: [0, 0, 0, 3, 0, 0x60, 0xB0, 0]}
        self.continue_warm = True
        self.post_done = False

    def devices(self):
        uarts = dict(self.uarts)
        for shift, regs in self.onboard_uart.items():
            if self.cr[2] & (0xC << shift) == (0xC << shift):
                selector = (self.cr[2] >> shift & 3) + 1
                base = (0, 0x3F8, 0x2F8, *PAIRS[self.cr[1] >> 5 & 3])[selector]
                uarts[base] = regs
        lpts = dict(self.lpts)
        if self.cr[1] & 4 and self.cr[1] & 3:
            lpts[PARALLEL[self.cr[1] & 3]] = self.onboard_lpt.setdefault('regs', [0x33, 0xD8, 0x2C])
        return uarts, lpts

    def port_in(self, cpu, port, size, unused):
        if self.starting and port == 0x71 and not self.delayed:
            assert cpu.reg_read(x.UC_X86_REG_CX) == 0, 'stackless CMOS settle loop did not finish'
            self.delayed = True
        if self.starting and port == 0x60 and not self.pending and not self.aux_reply:
            return 0xFF
        if port == 0x92:
            return 2
        if port in (0x3BA, 0x3DA, 0x3C0, 0x3CC):
            return 1 if port == 0x3CC else 0
        if port == 0x71 and self.rtc_fault == self.index and self.writes:
            return super().port_in(cpu, port, size, unused) ^ 1
        if port in (0xE1, 0x23):
            return 0
        if port == 0x3F1 and self.config:
            self.io.append(('in', port, self.cr[self.cr_index]))
            return self.cr[self.cr_index]
        uarts, lpts = self.devices()
        for base, regs in uarts.items():
            if base <= port < base+8:
                offset = port-base
                if self.delayed_uart and (base, offset) == tuple(self.delayed_uart[:2]):
                    self.delayed_uart[2] -= 1
                    if self.delayed_uart[2] == 0:
                        regs[offset] |= self.delayed_uart[3]
                        if offset == 5 and self.delayed_uart[3] == 1:
                            self.rx[base] = [0xD7]
                        self.delayed_uart = None
                value = regs[offset]
                if offset < 2 and regs[3] & 0x80:
                    value = self.divisors.get(base, [0xAA, 0xBB])[offset]
                elif offset == 0 and self.rx.get(base):
                    value = self.rx[base].pop(0)
                    if not self.rx[base]:
                        regs[5] &= ~1
                self.io.append(('in', port, value))
                return value
        for base, regs in lpts.items():
            if base <= port < base+3:
                value = regs[port-base]
                if port == base and self.printer_input(base, regs[2]):
                    value = self.lpt_pins
                self.io.append(('in', port, value))
                return value
        if any(base <= port < base+8 for base in (0x3F8, 0x2F8, 0x338, 0x238, 0x3E8, 0x2E8, 0x2E0, 0x220, 0x228)) or any(base <= port < base+3 for base in PARALLEL[1:]):
            self.io.append(('in', port, 255))
            return 255
        if port == 0x64:
            return 0x21 if self.aux_reply else int(bool(self.pending))
        if port == 0x60 and self.aux_reply:
            return self.aux_reply.pop(0)
        if port in (0x1F0, 0x1F1, 0x1F2, 0x1F3, 0x1F4, 0x1F5, 0x1F6, 0x1F7, 0x3F6):
            return self.ata_device.port_in(cpu, port, size, unused)
        return super().port_in(cpu, port, size, unused)

    def printer_input(self, base, control):
        onboard = bool(self.cr[1] & 4) and base == PARALLEL[self.cr[1] & 3]
        return bool(control & 0x20 and (not onboard or not self.cr[1] & 8))

    def port_out(self, cpu, port, size, value, unused):
        if self.starting and port == 0x71 and not self.delayed:
            assert cpu.reg_read(x.UC_X86_REG_CX) == 0, 'stackless CMOS settle loop did not finish'
            self.delayed = True
        if port in (0x92, 0x3B8, 0x3D8, 0x3C0, 0x3C2, 0x0D, 0xDA, 0x41, 0x84):
            return
        if port == 0x40:
            self.pit0_writes.append(value)
            self.pit_counter = 0xFFFF
            return
        if port == 0xED:
            self.chipset[self.chipset_index] = value
            if self.chipset_index == 0xF and value == 5:
                self.cpu.mem_write(0xC0000, self.vga_input)
            return
        if port in (0xF0, 0xF1, 0xF4, 0xF5, 0xE1, 0x23):
            return
        if port == 0x3F0:
            assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            self.io.append(('out', port, value))
            if self.config:
                if value == 0xAA:
                    self.config = False
                else:
                    self.cr_index = value
                    assert value <= 3
            elif value == 0x55:
                self.unlock += 1
                if self.unlock == 2:
                    self.config, self.unlock = True, 0
            return
        if port == 0x3F1:
            assert self.config
            self.io.append(('out', port, value))
            self.cr[self.cr_index] = value
            return
        uarts, lpts = self.devices()
        for base, regs in uarts.items():
            if base <= port < base+8:
                offset = port-base
                self.io.append(('out', port, value))
                if offset < 2 and regs[3] & 0x80:
                    self.divisors.setdefault(base, [0xAA, 0xBB])[offset] = value
                elif offset == 0:
                    self.tx.append((base, value))
                else:
                    regs[offset] = value
                return
        for base, regs in lpts.items():
            if base <= port < base+3:
                self.io.append(('out', port, value))
                if (port == base+2 and value & 1 and not regs[2] & 1
                        and value & 8 and not self.printer_input(base, value)):
                    self.printed.append((base, regs[0]))
                regs[port-base] = value
                return
        if any(base <= port < base+8 for base in (0x3F8, 0x2F8, 0x338, 0x238, 0x3E8, 0x2E8, 0x2E0, 0x220, 0x228)) or any(base <= port < base+3 for base in PARALLEL[1:]):
            self.io.append(('out', port, value))
            return
        if port == 0x64:
            if value in (0xA7, 0xA8):
                self.kbc_cb = (self.kbc_cb | 0x20) if value == 0xA7 else (self.kbc_cb & ~0x20)
            elif value in (0x60, 0xD4, 0xD1):
                self.kbc_next = value
            elif value == 0x20:
                self.pending.insert(0, self.kbc_cb)
            elif value == 0xAA:
                self.pending.insert(0, 0x55)
            elif value == 0xAD:
                self.kbc_cb |= 0x10
            elif value == 0xAE:
                self.kbc_cb &= ~0x10
            else:
                return super().port_out(cpu, port, size, value, unused)
            return
        if port == 0x60 and value == 0xFF and self.starting and self.kbc_next is None:
            self.pending.extend((0xFA, 0xAA))
            return
        if port == 0x60 and self.kbc_next:
            mode, self.kbc_next = self.kbc_next, None
            if mode == 0x60:
                self.kbc_cb = value
            elif mode == 0xD4:
                self.mouse_commands.append(value)
                self.aux_reply.append(0xFA)
                if value == 0xFF:
                    self.aux_reply.extend((0xAA, 0))
            return
        if 0x1F0 <= port <= 0x1F7 or port == 0x3F6:
            self.ata_device.port_out(cpu, port, size, value, unused)
            return
        return super().port_out(cpu, port, size, value, unused)

    def code(self, cpu, address, size, unused):
        if address == self.controlled_entry:
            self.starting = self.stop_post = True
            return                 # Execute the actual controlled startup entry.
        if (self.wait_irqs and self.wait_start <= address < self.wait_end
                and bytes(cpu.mem_read(address, 1)) == b'\xec'
                and cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200):
            vector = self.wait_irqs.pop(0)
            assert not self.masks[0x21] & (1 << (vector-8))
            if vector == 9:
                self.pending.append(0x1E)
            self.delivered_irqs.append(vector)
            rtc.Clock.interrupt(self, cpu, vector, None)
            return
        if address in (self.probe_entry, self.initialize_entry):
            base = cpu.reg_read(x.UC_X86_REG_DX)
            regs = self.devices()[0].get(base)
            if address == self.probe_entry:
                self.probe_snapshot = (base, tuple(regs[i] for i in (1, 3, 7))) if regs else None
            elif self.probe_snapshot:
                assert self.probe_snapshot == (base, tuple(regs[i] for i in (1, 3, 7))), 'probe must restore IER/LCR/SCR before initialization'
        if address == self.warm_entry and self.continue_warm:
            self.warm = self.starting = self.stop_post = True
            return                 # Execute the real startup instruction.
        if self.starting and address == 0xC0003:
            # Opaque retained VGA firmware far-entry response. Firmware's
            # header/checksum/shadow validation above this entry ran unchanged.
            self.cpu.mem_write(0x40, struct.pack('<HH', 0x100, 0xC000))
            ss, sp = cpu.reg_read(x.UC_X86_REG_SS), cpu.reg_read(x.UC_X86_REG_SP)
            ip, cs = struct.unpack('<HH', cpu.mem_read(ss*16+sp, 4))
            cpu.reg_write(x.UC_X86_REG_SP, sp+4)
            cpu.reg_write(x.UC_X86_REG_CS, cs)
            cpu.reg_write(x.UC_X86_REG_IP, ip)
            return
        if self.stop_post and address == self.post_terminal:
            self.post_done = True
            if self.starting:
                self.segment = struct.unpack('<H', cpu.mem_read(0x40E, 2))[0]
                self.base = self.segment*16
            self.starting = self.continue_warm = False
            cpu.emu_stop()
            return
        super().code(cpu, address, size, unused)

    def post(self, payload=DEFAULT, initial=(0x3F, 0x9F, 0xDC, 0x6C)):
        if payload is not None:
            record(self, payload)
        self.cr[:] = initial
        # Opaque physical onboard devices, fixed identities independent of mapping.
        self.onboard_uart = {0: [0, 0, 0, 3, 0, 0x60, 0xB0, 0], 4: [0, 0, 0, 3, 0, 0x60, 0xB0, 0]}
        self.stop_post = True
        cpu = self.cpu
        for reg, val in ((x.UC_X86_REG_CS, 0xF000), (x.UC_X86_REG_IP, rtc.symbol('.post_settings')),
                         (x.UC_X86_REG_DS, 0), (x.UC_X86_REG_ES, 0), (x.UC_X86_REG_SS, 0),
                         (x.UC_X86_REG_SP, 0x7000), (x.UC_X86_REG_EFLAGS, 0x202)):
            cpu.reg_write(reg, val)
        # Invalid settings can run two full RAM passes across controlled restart.
        cpu.emu_start(0xF0000+rtc.symbol('.post_settings'), 0xFFFFF, count=100000000)
        assert self.post_done, ('POST did not reach final gate', hex(cpu.reg_read(x.UC_X86_REG_IP)))
        self.stop_post = False
        assert not self.config

    def api(self, vector, ax, dx=0, bx=0x1234, cx=0x5678, flags=0x602):
        self.setup(ax >> 8, cx, dx, flags)
        self.cpu.reg_write(x.UC_X86_REG_AX, ax)
        self.cpu.reg_write(x.UC_X86_REG_BX, bx)
        old = self.state()
        self.cpu.mem_write(0x90000, bytes((0xCD, vector, 0x90)))
        self.cpu.emu_start(0x90000, 0x90002, count=12000000)
        assert self.cpu.reg_read(x.UC_X86_REG_CS) == 0x9000 and self.cpu.reg_read(x.UC_X86_REG_IP) == 2
        new = self.state()
        outputs = {'EAX'}
        if vector == 0x14 and ax == 0x0500 and dx <= 3:
            outputs.add('EBX')
        if vector == 0x15:
            outputs.update(('EBX', 'ECX', 'EDX'))
        if vector == 0x13:
            outputs.update(('EBX', 'ECX', 'EDX', 'EDI', 'ES'))
        for name in rtc.REGS:
            if name in outputs:
                if name.startswith('E'):
                    assert old[name] >> 16 == new[name] >> 16, (name, old[name], new[name])
            else:
                assert old[name] == new[name], (name, old[name], new[name])
        if vector in (0x14, 0x17):
            assert self.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x601 == flags & 0x601
        return new['EAX'] & 65535, new['EBX'] & 65535, self.cpu.reg_read(x.UC_X86_REG_EFLAGS)

    def table(self, start, count):
        return struct.unpack('<'+'H'*count, self.cpu.mem_read(start, count*2))


def publication():
    for expansion, onboard in (((), False), ((0x3E8,), False), ((0x3F8, 0x2F8, 0x3E8, 0x2E8), True)):
        m = Ports(uart=expansion, printer=PARALLEL[1:])
        payload = bytearray(DEFAULT)
        payload[:3] = (3, 4, 0) if onboard else (0, 0, 1)
        m.post(bytes(payload))
        assert not any(kind == 'out' and port == base+4 and value
                       for kind, port, value in m.io for base in m.devices()[0]), 'POST must never assert modem lines'
        assert not any(0x220 <= port < 0x230 for _, port, _ in m.io), 'unselected sound-card addresses must not be probed'
        expected = [0x3E8] if onboard else []
        expected += [b for b in (0x3F8, 0x2F8, 0x3E8, 0x2E8) if b in expansion and b not in expected]
        assert m.table(0x400, 4) == tuple(expected[:4]+[0]*(4-min(4, len(expected))))
        assert m.table(0x408, 3) == (0x378, 0x3BC, 0x278)
        assert m.table(0x40E, 1) == (m.segment,)
        assert m.table(0x410, 1)[0] & 0xCE00 == min(4, len(expected))*512+3*16384
        assert m.table(0x410, 1)[0] & 0x3100 == 0x3100
        for base, regs in m.devices()[0].items():
            assert regs[1] == regs[4] == 0 and regs[3] == 3
            assert m.divisors[base] == [12, 0], (base, m.divisors)
        assert not m.tx, 'POST must not transmit'
        assert m.cpu.mem_read(0x47C, 4) == b'\x01'*4
        assert m.cpu.mem_read(0x478, 3) == b'\x14'*3
        for base, regs in m.lpts.items():
            assert regs[0] == 0x37 and regs[2] == 0x2C
        for regs in m.uarts.values():
            assert regs[7] == 0x39
    for expansion in ((), (0x278,), (0x3BC, 0x278)):
        m = Ports(printer=expansion)
        m.post(bytes((0, 0, 1, 0, 0, 1, 1, 0)))
        expected = [base for base in PARALLEL[1:] if base in expansion]
        assert m.table(0x408, 3) == tuple(expected+[0]*(3-len(expected)))
        assert m.table(0x400, 4) == (0, 0, 0, 0)
        assert m.table(0x410, 1)[0] & 0xCE00 == len(expected)*16384
        assert m.table(0x40E, 1) == (m.segment,)
        for regs in m.lpts.values():
            assert regs[0] == 0x37 and regs[2] == 0x2C


def discovery():
    m = Ports(uart=(0x3F8, 0x2F8, 0x3E8, 0x2E8))
    m.post()
    assert not m.tx and not any(kind == 'out' and port in (0x3FC, 0x2FC, 0x3EC, 0x2EC) and value for kind, port, value in m.io)
    assert m.table(0x400, 4) == (0x3F8, 0x2F8, 0x3E8, 0x2E8)
    assert m.api(0x14, 0x014D, 3)[0] == 0x604D
    assert m.tx == [(0x2E8, 0x4D)]
    selected = Ports()
    selected.post(bytes((3, 4, 3, 0, 0, 1, 1, 0)))
    assert selected.table(0x400, 4) == (0x3E8, 0, 0, 0)
    assert any(port == 0x3EF for _, port, _ in selected.io)
    assert not any(0x220 <= port < 0x230 for _, port, _ in selected.io)
    assert not any(port == 0x22F for _, port, _ in selected.io)
    m = Ports(uart=(0x2E8,))
    m.post(bytes((0, 0, 1, 0, 0, 1, 1, 1)))
    assert m.table(0x400, 4) == (0x2E8, 0, 0, 0)
    assert m.api(0x14, 0x014D)[0] == 0x604D
    assert m.tx == [(0x2E8, 0x4D)]


def serial_api():
    m = Ports(uart=(0x2F8, 0x3E8))
    m.post()
    for selector, base in enumerate((0x3F8, 0x2F8, 0x3E8)):
        for rate in range(8):
            for fmt in range(32):
                assert m.api(0x14, rate*32+fmt, selector)[0] == 0x60B0
                assert m.divisors[base] == [DIVISORS[rate]&255, DIVISORS[rate]>>8]
                assert m.devices()[0][base][3] == fmt
        for rate in range(11):
            for parity in range(6):
                result = m.api(0x14, 0x0401, selector, bx=parity*256+1, cx=0x300+rate)[0]
                assert result == 0x60B0
                assert m.devices()[0][base][3] == 0x47 | (0, 8, 0x18, 0x28, 0x38, 0x3C)[parity]
                assert m.divisors[base] == [DIVISORS[rate]&255, DIVISORS[rate]>>8]
        assert m.api(0x14, 0x0501, selector, bx=0x12F5)[0] == 0x60B0
        assert m.devices()[0][base][4] == 0x15
        assert m.api(0x14, 0x0500, selector)[1] == 0x1215
        assert m.api(0x14, 0x035A, selector)[0] == 0x60B0
        for brk, stop, data in ((0, 0, 0), (1, 0, 0), (0, 1, 0), (0, 0, 1), (0, 0, 2), (0, 0, 3)):
            assert m.api(0x14, 0x0400+brk, selector, bx=stop, cx=data*256+7)[0] == 0x60B0
            assert m.devices()[0][base][3] == brk*64+stop*4+data
            assert m.divisors[base] == [12, 0]
        for lsr, msr in ((0, 0), (0x1F, 0xA5), (0xE1, 0x5A)):
            m.devices()[0][base][5:7] = [lsr, msr]
            assert m.api(0x14, 0x035A, selector)[0] == lsr*256+msr
        m.devices()[0][base][5:7] = [0x60, 0xB0]
    for vector, absent_status, max_selector in ((0x14, 0x80, 3), (0x17, 1, 2)):
        for selector in (max_selector+1, 0x100, 0xFFFF):
            for function in range(6 if vector == 0x14 else 3):
                n = len(m.io)
                assert m.api(vector, function*256+0x5A, selector)[0] == absent_status*256+0x5A
                assert len(m.io) == n
        n = len(m.io)
        assert m.api(vector, 0xFF5A, 0xFFFF)[0] == 0xFF5A and len(m.io) == n
    for selector in (3,):
        n = len(m.io)
        assert m.api(0x14, 0x015A, selector)[0] == 0x805A and len(m.io) == n
    for flags in (2, 3, 0x202, 0x203, 0x402, 0x403, 0x602, 0x603):
        assert m.api(0x14, 0x035A, flags=flags)[0] == 0x60B0
        assert m.api(0x17, 0x025A, flags=flags)[0] == 0x905A
        assert m.api(0x14, 0xFF5A, flags=flags)[0] == 0xFF5A
        assert m.api(0x17, 0xFF5A, flags=flags)[0] == 0xFF5A


def serial_waits():
    for function, bits, register in ((1, (0x20, 0x10), 6), (1, (0x20,), 5), (2, (0x20,), 6), (2, (1,), 5)):
        for bit in bits:
            m = Ports()
            m.post()
            m.devices()[0][0x3F8][register] &= ~bit
            m.cpu.mem_write(0x47C, b'\x01')
            n = len(m.pit_writes)
            pit0 = len(m.pit0_writes)
            result = m.api(0x14, function*256+0xD7)[0]
            assert result == 0x80D7 and not m.tx and not m.rx
            assert 500 <= len(m.pit_writes)-n <= 2500
            assert all(port == 0x43 and value == 0 for port, value in m.pit_writes[n:])
            assert len(m.pit0_writes) == pit0
            m.devices()[0][0x3F8][register] |= bit
            if function == 2:
                m.rx[0x3F8] = [0xD7]
                m.devices()[0][0x3F8][5] = 0x7F
            result = m.api(0x14, function*256+0xD7)[0]
            assert result == (0x1ED7 if function == 2 else 0x60D7)
            assert m.tx == ([] if function == 2 else [(0x3F8, 0xD7)])
    for timeout in (0, 132, 255):
        m = Ports()
        m.post()
        m.devices()[0][0x3F8][6] = 0
        m.cpu.mem_write(0x47C, bytes((timeout,)))
        n = len(m.pit_writes)
        assert m.api(0x14, 0x01D7)[0] == 0x80D7
        assert len(m.pit_writes)-n == timeout*500*4, (timeout, len(m.pit_writes)-n)
    m = Ports()
    m.post()
    m.devices()[0][0x3F8][5] &= ~1
    m.delayed_uart = [0x3F8, 5, 7, 1]
    received = m.api(0x14, 0x02D7)[0]
    assert received == 0x00D7, hex(received)
    assert not m.rx[0x3F8] and m.delayed_uart is None
    wait_interrupts(0x14)


def wait_interrupts(vector):
    m = Ports()
    m.post()
    m.devices()[0][0x3F8][6] = 0
    m.devices()[1][0x378][1] = 0x58
    m.cpu.mem_write(0x47C, b'\x01')
    m.cpu.mem_write(0x478, b'\x01')
    m.masks[0x21] &= ~3
    for flags in (3, 0x603):
        ticks = struct.unpack('<I', m.cpu.mem_read(0x46C, 4))[0]
        m.wait_irqs = [8, 9]
        m.delivered_irqs = []
        assert m.api(vector, 0x01D7 if vector == 0x14 else 0x00D7, flags=flags)[0] == (0x80D7 if vector == 0x14 else 0x11D7)
        assert m.delivered_irqs == [8, 9] and not m.wait_irqs
        assert struct.unpack('<I', m.cpu.mem_read(0x46C, 4))[0] == ticks+1
        assert m.api(0x16, 0)[0] == 0x1E61


def printer_api():
    for mode in (0, 1):
        m = Ports(printer=PARALLEL[1:])
        data = bytearray(DEFAULT)
        data[4] = mode
        m.post(bytes(data))
        assert m.cr[1] & 8 == (0 if mode else 8)
        for selector, base in enumerate((0x378, 0x3BC, 0x278)):
            regs = m.devices()[1][base]
            control = regs[2]
            n = len(m.io)
            assert m.api(0x17, 0x00D7, selector)[0] == 0x90D7
            assert regs[0] == 0xD7 and regs[2] == control & ~1
            assert m.printed[-1] == (base, 0xD7)
            assert [('out', base+2, control&0xDE), ('out', base, 0xD7), ('out', base+2, (control&~0x20)|1), ('out', base+2, control&~1)] == [event for event in m.io[n:] if event[0] == 'out']
            init_control = regs[2]
            n = len(m.io)
            assert m.api(0x17, 0x015A, selector)[0] == 0x905A
            assert regs[2] == control|0x0C
            assert [event for event in m.io[n:] if event[0] == 'out'] == [('out', base+2, (init_control|8) & ~4), ('out', base+2, init_control | 0x0C)]
            for cold_control in (0, 0x20):
                regs[2] = cold_control
                n = len(m.io)
                assert m.api(0x17, 0x015A, selector)[0] == 0x905A
                assert [event for event in m.io[n:] if event[0] == 'out'] == [('out', base+2, cold_control|8), ('out', base+2, cold_control|0x0C)]
                assert m.api(0x17, 0x005A, selector)[0] == 0x905A
                assert m.printed[-1] == (base, 0x5A)
                assert regs[2] == cold_control|0x0C
            regs[1] = 0xDF
            assert m.api(0x17, 0x025A, selector)[0] == 0x905A
            regs[1] = 0x58
            m.cpu.mem_write(0x478+selector, b'\x00')
            n = len(m.io)
            assert m.api(0x17, 0x00D7, selector)[0] == 0x11D7
            assert not any(event[0] == 'out' for event in m.io[n:])
            if mode == 0 and selector == 0:
                m.cpu.mem_write(0x478, b'\x01')
                ticks = len(m.pit_writes)
                n = len(m.io)
                assert m.api(0x17, 0x00D7)[0] == 0x11D7
                assert len(m.pit_writes)-ticks == 2000
                assert not any(event[0] == 'out' for event in m.io[n:])
                m.cpu.mem_write(0x478, b'\x14')
            regs[1] = 0xD8
        for selector in (3, 0xFFFF):
            n = len(m.io)
            assert m.api(0x17, 0x005A, selector)[0] == 0x015A
            assert len(m.io) == n and m.table(0x40E, 1) == (m.segment,)
        m.cpu.mem_write(0x40C, b'\x00\x00')
        n = len(m.io)
        assert m.api(0x17, 0x025A, 2)[0] == 0x015A and len(m.io) == n
        assert m.api(0x17, 0x035A)[0] == 0x035A and len(m.io) == n
    wait_interrupts(0x17)


def edit_script(payload, current=DEFAULT):
    current = list(board_policy(current))
    script = list(ENTER_DEVICES)
    field = 0
    def choose(target, value):
        nonlocal field
        available = [i for i in (0, 3, 4, 6) if i != 4 or current[3]]
        distance = available.index(target)-available.index(field)
        script.extend([0x50 if distance > 0 else 0x48]*abs(distance))
        field = target
        script.append(28)
        option = current[target]
        limits = (4, 4, 3, 3, 1, 1, 1, 1)
        while option != value:
            option = (option+1) % (limits[target]+1)
            if target <= 1 and option and option == current[target^1]:
                continue
            script.append(0x50)
        script.append(28)
        current[target] = value
    choose(0, payload[0])
    choose(3, payload[3] or 2)
    choose(4, payload[4])
    if payload[3] == 0:
        choose(3, 0)
    choose(6, payload[6])
    # Move from Devices to Drives; the FDC edits the same persisted draft byte.
    script += [15, 0x48, 0x48, 28]+[0x50]*5+[28]
    if current[5] != payload[5]:
        script.append(0x50)
    script += [28, 15, 0x50, 0x50, 28]
    return script


def expected_cr(payload, initial):
    a, b, pair, printer, mode, fdc, mouse, isa = board_policy(payload)
    uart = ((a-1)|12) if a else 0
    uart |= (((b-1)|12)<<4) if b else 0
    return ((initial[0] & 0xE7)|(24 if fdc else 0),
            (initial[1] & 0x90)|(pair<<5)|printer|(4 if printer else 0)|(8 if mode == 0 else 0),
            uart, 0x6C)


def ports_options():
    payloads = []
    for field, values in ((0, range(5)), (3, range(4)), (4, range(2)), (5, range(2)), (6, range(2))):
        for value in values:
            data = bytearray(DEFAULT)
            data[field] = value
            if field == 0 and value == data[1]:
                data[1] = 0
            if field == 1 and value == data[0]:
                data[0] = 0
            if field == 2:
                data[0] = 3
            payloads.append(bytes(data))
    for payload in payloads:
        m = Ports()
        initial = (0x3F, 0x90, 0, 0x6C)
        m.warm_continuation(initial)
        m.open(edit_script(payload)+[0x44, 28])
        assert m.warm and bytes(m.cmos[0x60:0x68]) == payload
        assert sum(m.cmos[0x5D:0x69]) & 255 == 0
        assert m.post_done
        assert tuple(m.cr) == expected_cr(payload, initial), (payload, m.cr)
        assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == payload
        bases = []
        for select in payload[:2]:
            if select:
                base = (0, 0x3F8, 0x2F8, *PAIRS[payload[2]])[select]
                bases.append(base)
        assert list(m.table(0x400, 4))[:len(bases)] == bases
        assert m.table(0x408, 3)[0] == PARALLEL[payload[3]]


def ports_conflicts():
    for sibling in range(1, 5):
        data = bytearray(DEFAULT)
        data[:2] = (0, sibling)
        m = Ports()
        m.post(bytes(data))
        seen = []
        def observe(model):
            draft = bytes(model.cpu.mem_read(model.base+0x1EE, 8))
            assert not draft[0] or draft[0] != draft[1]
            seen.append(draft[0])
        m.observer = observe
        m.warm_continuation()
        m.open(ENTER_DEVICES+[0x4D]*5+[28]+[0x50]*5+[28, 0x44, 28])
        assert sibling in seen and m.warm  # Hidden onboard B no longer reserves a choice.
        assert m.post_done
        assert len([base for base in m.table(0x400, 4) if base]) == len(set(base for base in m.table(0x400, 4) if base))
        data[:2] = (sibling, sibling)
        record(m, bytes(data))
        m.script = [28]
        m.post(None)
        assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == DEFAULT
        assert 'CMOS settings invalid.' in m.console


def ports_record():
    for defect in ('absent', 'signature', 'schema', 'checksum', *range(8), 'duplicate'):
        m = Ports()
        setup.settings_fixture(m, hdd=0, seek=0xA5)
        m.cmos[0x3F] = 0xA5
        record(m)
        if defect == 'absent':
            m.cmos[0x5D] = 0
        elif defect == 'signature':
            m.cmos[0x5E] = 0
        elif defect == 'schema':
            m.cmos[0x5F] = 2
        elif defect == 'checksum':
            m.cmos[0x68] ^= 1
        elif defect == 'duplicate':
            m.cmos[0x61] = 1
        else:
            m.cmos[0x60+defect] = (4, 4, 3, 3, 1, 1, 1, 1)[defect]+1
        if defect not in ('absent', 'checksum'):
            m.cmos[0x68] = -sum(m.cmos[0x5D:0x68]) & 255
        before = bytes(m.cmos)
        m.script = [] if defect == 'absent' else [28]
        m.post(None)
        assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == DEFAULT
        if defect == 'absent':
            assert not any(0x5D <= index <= 0x68 for index, value in m.writes)
            assert bytes(m.cmos[0x38:0x69]) == before[0x38:0x69]
            assert m.cpu.mem_read(m.base+0x171, 1) == b'\x00'
            assert m.cpu.mem_read(m.base+0x177, 1) == b'\x00'
        else:
            assert 'CMOS settings invalid.' in m.console
            assert m.cmos[0x5D:0x68] == b'P1\x01'+DEFAULT
            assert sum(m.cmos[0x5D:0x69]) & 255 == 0


def post_composition():
    payload = bytes((3, 4, 3, 1, 1, 0, 0, 1))
    snapshots = []
    for initial in ((0x3F, 0x9F, 0xDC, 0x6C), (0x3F, 0xF0, 0, 0x6C)):
        m = Ports(uart=(0x3E8,), printer=(0x278,))
        m.post(payload, initial)
        snapshots.append((tuple(m.cr), m.table(0x400, 4), m.table(0x408, 3)))
        assert tuple(m.cr) == expected_cr(payload, initial)
        assert not m.fdc_log and not m.mouse_commands
        assert m.ata_device.selected_commands
        assert m.cpu.mem_read(0x475, 1) == b'\x01'
        assert m.masks[0xA1] & 0x10 and m.kbc_cb & 0x20
        assert not m.kbc_cb & 0x10
        writes = [(p, v) for kind, p, v in m.io if kind == 'out' and p in (0x3F0, 0x3F1)]
        assert writes[:2] == [(0x3F0, 0x55)]*2 and writes[-1] == (0x3F0, 0xAA)
    assert snapshots[0] == snapshots[1]
    m = Ports()
    m.ata_device = ide.Disk(('ata', 'ata'))
    m.ata_device.cpu = m.cpu
    struct.pack_into('<H', m.ata_device.payloads[1], 2, 733)
    struct.pack_into('<H', m.ata_device.payloads[1], 6, 7)
    struct.pack_into('<H', m.ata_device.payloads[1], 12, 17)
    m.cmos[0x3F] = 0x5A
    ide.saved(m, ide.DEFAULT[:13]+ide.record(48, 1, 0, 0, 733, 7, 17, 128, 733))
    m.post()
    assert m.cpu.mem_read(0x475, 1) == b'\x02'
    m.script = []
    m.call('post_debug_summary')
    offset, segment = struct.unpack('<HH', m.cpu.mem_read(0x118, 4))
    fdpt = bytes(m.cpu.mem_read(segment*16+offset, 16))
    assert (struct.unpack_from('<H', fdpt)[0], fdpt[2], fdpt[14]) == (733, 7, 17)
    assert m.text(6, 58, 20) == '03F8'+' '*16
    assert m.text(7, 58, 20) == '0378'+' '*16
    for flags in (2, 0x202):
        for owner in ('ports_apply', 'init_floppy', 'ide_apply_controller'):
            m.call(owner, flags=flags)
            assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200 == flags & 0x200, owner


def ports_draft():
    edited = bytes((3, 0, 1, 1, 1, 0, 0, 1))
    for segment in (0x9FC0, 0x9800):
        for action in ('cancel-save', 'cancel-defaults', 'defaults', 'discard', 'save', 'failed-save'):
            m = Ports(segment=segment)
            initial = bytes((4, 0, 1, 1, 1, 0, 0, 1)) if action == 'defaults' else DEFAULT
            m.post(initial)
            old = bytes(m.cmos)
            hardware = tuple(m.cr)
            script = edit_script(edited, current=initial)
            if action in ('save', 'defaults'):
                m.warm_continuation(hardware)
            defaults_seen = []
            canceled_seen = []
            if action == 'cancel-save':
                script += [0x44, 1]
            elif action == 'cancel-defaults':
                script += [0x43, 1]
            elif action == 'defaults':
                script += [0x43, 28, 0x44, 28]
                def observe_defaults(model):
                    if model.script != [0x44, 28] or model.pending:
                        return
                    assert bytes(model.cpu.mem_read(model.base+0x1EE, 8)) == DEFAULT
                    assert bytes(model.cpu.mem_read(model.base+0x1E6, 8)) == initial
                    assert tuple(model.cr) == hardware and bytes(model.cmos) == old
                    defaults_seen.append(True)
                    model.observer = None
                m.observer = observe_defaults
            elif action == 'discard':
                script += [1, 1, 28]
            elif action == 'save':
                script += [0x44, 28]
            else:
                m.writes.clear()
                m.rtc_fault = 0x62
                script += [0x44, 28, 1, 1, 28]
            if action in ('cancel-save', 'cancel-defaults'):
                def observe_cancel(model):
                    if model.script or model.pending:
                        return
                    assert bytes(model.cpu.mem_read(model.base+0x1EE, 8)) == edited
                    assert bytes(model.cpu.mem_read(model.base+0x1E6, 8)) == DEFAULT
                    assert tuple(model.cr) == hardware and bytes(model.cmos) == old
                    assert model.cpu.mem_read(model.base+0xF5, 2) == b'\x03\x01'
                    canceled_seen.append(True)
                    model.observer = None
                    model.script = [1, 1, 28]
                m.observer = observe_cancel
            m.open(script)
            if action in ('save', 'defaults'):
                wanted = edited if action == 'save' else DEFAULT
                assert m.warm and m.cmos[0x60:0x68] == wanted
                assert m.post_done
                assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == wanted
                if action == 'defaults':
                    assert defaults_seen == [True]
            elif action == 'failed-save':
                assert not m.warm and tuple(m.cr) == hardware
            else:
                if action.startswith('cancel-'):
                    assert canceled_seen == [True]
                assert tuple(m.cr) == hardware and bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == DEFAULT
                assert not m.warm and bytes(m.cmos) == old
                # Discard/reopen starts a fresh draft from the active saved owner.
                m.cpu.mem_write(0x49E, b'\x01')
                m.open([1, 28])
                assert bytes(m.cpu.mem_read(m.base+0x1EE, 8)) == DEFAULT
    for fault in (None, *range(0x5D, 0x69)):
        m = Ports()
        m.post()
        hardware = tuple(m.cr)
        m.writes.clear()
        m.rtc_fault = fault
        if fault is None:
            m.warm_continuation(hardware)
        seen = []
        def observe_failure(model):
            if 'CMOS verification failed.' not in model.text(19, 23, 46):
                return
            assert not model.warm and tuple(model.cr) == hardware
            assert bytes(model.cpu.mem_read(model.base+0x1EE, 8)) == edited
            assert bytes(model.cpu.mem_read(model.base+0x1E6, 8)) == DEFAULT
            assert model.cpu.mem_read(model.base+0x185, 1)[0] == fault
            seen.append(True)
            model.observer = None
            model.script = [1, 1, 28]
        if fault is not None:
            m.observer = observe_failure
        m.open(edit_script(edited)+[0x44, 28])
        device_writes = [(index, value) for index, value in m.writes if 0x5D <= index <= 0x68]
        encoded = b'P1\x01'+edited
        expected = [(0x5D, 0)]+list(enumerate(edited, 0x60))+[(0x68, -sum(encoded)&255), (0x5F, 1), (0x5E, ord('1')), (0x5D, ord('P'))]
        assert device_writes == expected
        assert m.warm if fault is None else seen == [True] and not m.warm


def ports_ui():
    for pair_enabled, parallel_enabled in ((False, False), (True, False), (False, True), (True, True)):
        m = Ports()
        payload = bytes((*((3, 0, 1) if pair_enabled else (1, 0, 1)),
                         3 if parallel_enabled else 0, int(parallel_enabled), 1, 1, 1))
        m.post(payload)
        observed = []
        rows = (5, 0, 0, 6, 7, 0, 8, 0)
        available = [i for i in (0, 3, 4, 6) if i != 4 or parallel_enabled]
        labels = ('Serial Port', 'Serial Port B', 'COM3 / COM4 Addresses', 'Parallel Port',
                  'Parallel Port Mode', 'Floppy Controller', 'PS/2 Mouse', 'ISA Serial Discovery')
        details = ('Select the onboard serial I/O address and IRQ.', 'Select the onboard serial I/O address and IRQ.',
                   'COM3 and COM4 share this address pair.', 'Select the onboard parallel address or Disabled.',
                   'Printer output or PS/2 bidirectional data.', 'Disabled hides both drives and disables the FDC.',
                   'Disabled inhibits AUX and mouse BIOS services.', 'Discover decoded UARTs at standard ISA addresses.')
        values = (('Disabled', '3F8h / IRQ4', '2F8h / IRQ3', '3E8h / IRQ4', '2E8h / IRQ3'),)*2 + (
            ('338h / 238h', '3E8h / 2E8h', '2E8h / 2E0h', '220h / 228h'),
            ('Disabled', '3BCh', '378h', '278h'), ('Printer', 'PS/2 Bidirectional'),
            ('Disabled', 'Enabled'), ('Disabled', 'Enabled'), ('Disabled', 'Enabled'))
        step = [0, -2]
        popup_seen = []
        def observe(model):
            if model.script or model.pending:
                return
            field = model.cpu.mem_read(model.base+0xF7, 1)[0]
            position, phase = step
            if phase == -2:
                assert model.cpu.mem_read(model.base+0xF5, 2) == b'\x03\x00'
                assert model.text(18, 25, 7) == 'Devices'
                assert model.text(19, 25, len('Configure onboard ports and devices.')) == 'Configure onboard ports and devices.'
                model.script = [1]
                step[1] = -1
                return
            if phase == -1:
                assert model.cpu.mem_read(model.base+0xF5, 2) == b'\x03\x00'
                assert bytes(model.cpu.mem_read(model.base+0x1EE, 8)) == payload
                model.script = [28, 0x48]  # First-field Up must stay at the first field.
                step[1] = 0
                return
            expected_field = available[position]
            assert field == expected_field, (pair_enabled, parallel_enabled, position, phase, field)
            assert bytes(model.cpu.mem_read(model.base+0x1EE, 8)) == payload
            if phase == 0:
                for i, row in enumerate(rows):
                    if i in (1, 2, 5, 7):
                        assert labels[i].encode('ascii') not in bytes(model.cpu.mem_read(0xB8000, 80*25*2))[::2]
                        continue
                    assert model.text(row, 24, len(labels[i])) == labels[i]
                    if i not in available:
                        assert model.cpu.mem_read(0xB8000+row*160+49*2+1, 1) == b'\x08'
                for row in (rows[field],):
                    assert bytes(model.cpu.mem_read(0xB8000+row*160+48*2+1, 60))[::2] == b'\x1f'*30
                assert model.text(rows[field], 49, 28).strip() == values[field][payload[field]]
                model.script = [0x3B]
            elif phase == 1:
                assert model.text(18, 25, len(labels[field])) == labels[field]
                assert model.text(19, 25, len(details[field])) == details[field]
                model.script = [1]
            elif phase == 2:
                assert model.text(3, 23, 21) == 'bAIos Setup > Devices'
                popup_seen.clear()
                model.script = [28]
            elif phase == 3:
                legal = [i for i in range(len(values[field])) if field > 1 or not i or i != payload[field^1]]
                selected = legal[(legal.index(payload[field])+len(popup_seen)) % len(legal)]
                for i, text in enumerate(values[field]):
                    assert model.text(10+i, 26, len(text)) == text
                assert model.cpu.reg_read(x.UC_X86_REG_BP) == selected
                assert model.cpu.mem_read(0xB8000+(10+selected)*160+26*2+1, 1) == b'\x70'
                popup_seen.append(selected)
                if len(popup_seen) <= len(legal):
                    model.script = [0x50]
                    return
                assert set(popup_seen) == set(legal)
                model.script = [0x48] * (payload[field]+1)  # Previous wraps through zero.
                step[1] = 8
                return
            elif phase == 8:
                selected = len(values[field])-1
                assert model.cpu.reg_read(x.UC_X86_REG_BP) == selected
                assert model.cpu.mem_read(0xB8000+(10+selected)*160+26*2+1, 1) == b'\x70'
                model.script = [0x3B]
                step[1] = 9
                return
            elif phase == 9:
                assert model.text(18, 25, len(labels[field])) == labels[field]
                assert model.text(19, 25, len(details[field])) == details[field]
                model.script = [1]
                step[1] = 10
                return
            elif phase == 10:
                selected = len(values[field])-1
                assert model.cpu.reg_read(x.UC_X86_REG_BP) == selected
                assert model.text(10+selected, 26, len(values[field][selected])) == values[field][selected]
                assert model.cpu.mem_read(0xB8000+(10+selected)*160+26*2+1, 1) == b'\x70'
                model.script = [1]
                step[1] = 4
                return
            elif phase == 4:
                observed.append(field)
                if position+1 == len(available):
                    model.script = [0x50]  # Last-field Down cannot wrap.
                    step[1] = 5
                    return
                step[0] += 1
                model.script = [0x50]
                step[1] = 0
                return
            elif phase in (5, 6):
                if position:
                    step[0] -= 1
                    step[1] = 6
                    model.script = [0x48]
                else:
                    step[1] = 7
                    model.script = [0x48]
                return
            else:
                assert field == 0
                model.observer = None
                model.script = [1, 1, 28]
                return
            step[1] = phase+1
        m.observer = observe
        before = bytes(m.cmos)
        m.open([0x50]*3+[0x3B])
        assert observed == available
        assert bytes(m.cmos) == before
        assert bytes(m.cpu.mem_read(m.base+0x1EE, 8)) == payload


def board_layout():
    # Independent old schema input: formerly visible UART B and discovery off.
    old = bytes((1, 2, 1, 2, 0, 1, 1, 0))
    for modem in (False, True):
        m = Ports(uart=(0x2F8,) if modem else ())
        record(m, old)
        before = bytes(m.cmos[0x5D:0x69])
        m.post(None)
        assert bytes(m.cmos[0x5D:0x69]) == before
        assert 'CMOS settings invalid.' not in m.console
        assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == DEFAULT
        assert m.cr[2] == 0x0C
        assert m.table(0x400, 4) == ((0x3F8, 0x2F8, 0, 0) if modem else (0x3F8, 0, 0, 0))
        if modem:
            assert m.api(0x14, 0x014D, 1)[0] == 0x604D
            assert m.tx == [(0x2F8, 0x4D)]
        m.warm_continuation()
        m.open(ENTER_DEVICES+[0x44, 28])
        assert m.warm and m.post_done and m.cmos[0x60:0x68] == DEFAULT
        assert sum(m.cmos[0x5D:0x69]) & 255 == 0
        assert m.cr[2] == 0x0C
        assert m.table(0x400, 4) == ((0x3F8, 0x2F8, 0, 0) if modem else (0x3F8, 0, 0, 0))

    # F9 must produce the canonical draft before Save can normalize it.
    for modem in (False, True):
        m = Ports(uart=(0x2F8,) if modem else ())
        initial = bytes((4, 0, 1, 1, 1, 0, 0, 1))
        m.post(initial)
        before = bytes(m.cmos)
        hardware = tuple(m.cr)
        seen_defaults = []
        def observe_defaults(model):
            if model.script != [0x44, 28] or model.pending:
                return
            assert bytes(model.cpu.mem_read(model.base+0x1EE, 8)) == DEFAULT
            assert model.text(5, 49, 28).strip() == '3F8h / IRQ4'
            assert bytes(model.cpu.mem_read(model.base+0x1E6, 8)) == initial
            assert bytes(model.cmos) == before and tuple(model.cr) == hardware
            seen_defaults.append(True)
            model.observer = None
        m.observer = observe_defaults
        m.warm_continuation(hardware)
        m.open(ENTER_DEVICES+[0x43, 28, 0x44, 28])
        assert seen_defaults == [True] and m.warm and m.post_done
        assert m.cmos[0x60:0x68] == DEFAULT and sum(m.cmos[0x5D:0x69]) & 255 == 0
        assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == DEFAULT
        assert m.cr[1] >> 5 & 3 == 1 and m.cr[2] == 0x0C
        assert m.table(0x400, 4) == ((0x3F8, 0x2F8, 0, 0) if modem else (0x3F8, 0, 0, 0))
        assert m.api(0x14, 0x014D)[0] == 0x604D
        assert m.tx == [(0x3F8, 0x4D)]

    m = Ports()
    m.post()
    before = bytes(m.cmos)
    hardware = tuple(m.cr)
    seen = []
    def observe(model):
        if model.script or model.pending:
            return
        phase = len(seen)
        assert model.cpu.mem_read(model.base+0xF5, 3) == bytes((1, 1, 5))
        if phase != 2:  # The enum popup temporarily covers this row.
            assert model.text(12, 24, 17) == 'Floppy Controller'
        if phase == 0:
            assert model.text(12, 49, 7) == 'Enabled'
            for row in (12,):
                assert bytes(model.cpu.mem_read(0xB8000+row*160+48*2+1, 60))[::2] == b'\x1f'*30
            model.script = [0x3B]
        elif phase == 1:
            assert model.text(18, 25, 17) == 'Floppy Controller'
            assert model.text(19, 25, 48).strip() == 'Disabled hides both drives and disables the FDC.'
            model.script = [1, 28]
        elif phase == 2:
            assert model.text(10, 26, 8) == 'Disabled'
            assert model.text(11, 26, 7) == 'Enabled'
            model.script = [0x50, 28]
        elif phase == 3:
            assert model.text(12, 49, 8) == 'Disabled'
            assert model.cpu.mem_read(model.base+0x1EE+5, 1) == b'\x00'
            model.script = [0x4B]
        elif phase == 4:
            assert model.text(12, 49, 7) == 'Enabled'
            assert model.cpu.mem_read(model.base+0x1EE+5, 1) == b'\x01'
            model.script = [0x4D]
        else:
            assert model.text(12, 49, 8) == 'Disabled'
            assert model.cpu.mem_read(model.base+0x1EE+5, 1) == b'\x00'
            assert model.cpu.mem_read(model.base+0x1E6+5, 1) == b'\x01'
            assert bytes(model.cmos) == before and tuple(model.cr) == hardware
            model.observer = None
            model.script = [1, 1, 28]
        seen.append(phase)
    m.observer = observe
    m.open([0x50, 28]+[0x50]*5)  # Select the FDC field.
    assert seen == [0, 1, 2, 3, 4, 5] and not m.warm
    assert bytes(m.cmos) == before and tuple(m.cr) == hardware


def serial_addresses():
    # Retained records are independent old-schema inputs, not UI-generated data.
    addresses = (0, 0x3F8, 0x2F8, 0x3E8, 0x2E8)
    for retained_pair in (0, 1, 2, 3):
        m = Ports()
        raw = bytes((3, 0, retained_pair, 2, 0, 1, 1, 1))
        record(m, raw)
        before = bytes(m.cmos[0x5D:0x69])
        m.post(None)
        assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == bytes((3, 0, 1, 2, 0, 1, 1, 1))
        assert bytes(m.cmos[0x5D:0x69]) == before
        assert 'CMOS settings invalid.' not in m.console
        assert m.cr[1] >> 5 & 3 == 1 and m.cr[2] == 0x0E
        assert m.table(0x400, 4) == (0x3E8, 0, 0, 0)
    for choice, old_pair in enumerate((0, 2, 3, 0, 2)):
        m = Ports()
        raw = bytearray(DEFAULT)
        raw[0] = 4 if choice == 3 else 3
        raw[2] = old_pair
        record(m, raw)
        before = bytes(m.cmos)
        m.post(None)
        active = bytes(board_policy(raw))
        assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == active
        assert bytes(m.cmos[0x5D:0x69]) == before[0x5D:0x69]
        before = bytes(m.cmos)  # POST legitimately updates equipment/memory fields.
        assert 'CMOS settings invalid.' not in m.console
        assert m.cr[1] >> 5 & 3 == 1
        assert m.table(0x400, 4) == (addresses[raw[0]], 0, 0, 0)
        hardware = tuple(m.cr)
        wanted = bytearray(DEFAULT)
        wanted[0] = choice
        seen = []
        def observe(model):
            if model.script != [0x44, 28] or model.pending:
                return
            assert bytes(model.cpu.mem_read(model.base+0x1EE, 8)) == wanted
            label = ('Disabled', '3F8h / IRQ4', '2F8h / IRQ3', '3E8h / IRQ4', '2E8h / IRQ3')[choice]
            assert model.text(5, 49, 28).strip() == label
            assert bytes(model.cpu.mem_read(model.base+0x1E6, 8)) == active
            assert bytes(model.cmos) == before and tuple(model.cr) == hardware
            seen.append(True)
            model.observer = None
        m.observer = observe
        m.warm_continuation(hardware)
        m.open(edit_script(wanted, active)+[0x44, 28])
        assert seen == [True] and m.warm and m.post_done
        assert m.cmos[0x60:0x68] == wanted and sum(m.cmos[0x5D:0x69]) & 255 == 0
        assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == wanted
        assert m.cr[1] >> 5 & 3 == 1
        assert m.cr[2] == (choice-1 | 12 if choice else 0)
        assert m.table(0x400, 4) == (addresses[choice], 0, 0, 0)
        result = m.api(0x14, 0x014D)[0]
        assert result == (0x604D if choice else 0x804D)
        assert m.tx == ([(addresses[choice], 0x4D)] if choice else [])
    for terminal in (0, 4):
        m = Ports()
        m.post()
        before, hardware = bytes(m.cmos), tuple(m.cr)
        sequence = (0, 4, 0, 1, 2, 3, 4) + ((0,) if not terminal else ())
        seen = []
        def observe_arrows(model):
            if model.script or model.pending:
                return
            choice = sequence[len(seen)]
            wanted = bytearray(DEFAULT)
            wanted[0] = choice
            assert model.cpu.mem_read(model.base+0xF5, 3) == b'\x03\x01\x00'
            assert bytes(model.cpu.mem_read(model.base+0x1EE, 8)) == wanted
            assert bytes(model.cpu.mem_read(model.base+0x1E6, 8)) == DEFAULT
            assert bytes(model.cmos) == before and tuple(model.cr) == hardware
            label = ('Disabled', '3F8h / IRQ4', '2F8h / IRQ3', '3E8h / IRQ4', '2E8h / IRQ3')[choice]
            assert model.text(5, 49, 28).strip() == label
            seen.append(choice)
            if len(seen) < len(sequence):
                model.script = [0x4B if len(seen) == 1 else 0x4D]
            else:
                model.observer = None
                model.script = [0x44, 28]
        m.observer = observe_arrows
        m.warm_continuation(hardware)
        m.open(ENTER_DEVICES+[0x4B])
        wanted = bytearray(DEFAULT)
        wanted[0] = terminal
        assert tuple(seen) == sequence and m.warm and m.post_done
        assert m.cmos[0x60:0x68] == wanted and sum(m.cmos[0x5D:0x69]) & 255 == 0
        assert bytes(m.cpu.mem_read(m.base+0x1E6, 8)) == wanted
        assert m.cr[1] >> 5 & 3 == 1 and m.cr[2] == (15 if terminal else 0)
        assert m.table(0x400, 4) == (addresses[terminal], 0, 0, 0)
        assert m.api(0x14, 0x014D)[0] == (0x604D if terminal else 0x804D)
        assert m.tx == ([(addresses[terminal], 0x4D)] if terminal else [])
    # Includes the real F9 draft-before-Save path and its warm terminal oracle.
    board_layout()


def floppy_policy():
    for enabled in (0, 1):
        m = Ports()
        payload = bytearray(DEFAULT)
        payload[5] = enabled
        m.warm_continuation()
        m.open(edit_script(bytes(payload))+[0x44, 28])
        assert m.warm and m.cmos[0x10] == 0x42
        assert m.cmos[0x3A] == 5 and m.cmos[0x3B] & 2 and m.post_done
        assert m.cmos[0x3E:0x40] == b'\x02\0'
        assert bytes(m.cpu.mem_read(m.base+0x80, 2)) == (b'\x04\x02' if enabled else b'\x00\x00')
        assert m.api(0x11, 0)[0] & 0xC1 == (0x41 if enabled else 0)
        assert m.cpu.mem_read(0x475, 1) == b'\x01'
        if enabled:
            assert m.fdc_log
            assert m.api(0x13, 0, dx=0)[0] >> 8 == 0
            assert m.api(0x13, 0x0800, dx=0)[0] >> 8 == 0
            assert m.api(0x13, 0x1500, dx=0)[0] >> 8 == 2  # 1.44M has a disk-change line.
        else:
            assert not m.fdc_log
            for function in (0, 1, 2, 8, 0x15, 0x16, 0x17, 0x18):
                n = len(m.fdc_log)
                ax, _, flags = m.api(0x13, function*256+1, dx=0, cx=1)
                assert (ax >> 8 == 0 and not flags & 1) if function == 0x15 else (ax >> 8 == 1 and flags & 1)
                assert len(m.fdc_log) == n and m.cr[0] & 0x18 == 0
        from unicorn import UC_HOOK_CODE
        attempts = []
        retry_entry = 0xF0000+rtc.symbol('boot_retry')
        terminal = []
        disk_entry = 0xF0000+rtc.symbol('int13')
        def boot(cpu, address, size, unused):
            if address == disk_entry:
                attempts.append((cpu.reg_read(x.UC_X86_REG_AH), cpu.reg_read(x.UC_X86_REG_DL)))
            if address >= retry_entry and bytes(cpu.mem_read(address, 1)) == b'\xF4':
                assert m.console.endswith('Press any key to retry\r\n')
                assert cpu.mem_read(0x49E, 1) == b'\x02'
                terminal.append(address)
                cpu.emu_stop()
        m.cpu.hook_add(UC_HOOK_CODE, boot)
        # External A drive does not complete recalibration; actual boot must
        # reset installed services, try A when enabled, then the HDD and retry.
        m.fdc_timeout = 0
        m.cpu.mem_write(0x43E, b'\x00')
        m.cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
        m.cpu.reg_write(x.UC_X86_REG_IP, rtc.symbol('int19'))
        m.cpu.reg_write(x.UC_X86_REG_SS, 0)
        m.cpu.reg_write(x.UC_X86_REG_SP, 0x7000)
        m.cpu.emu_start(0xF0000+rtc.symbol('int19'), 0xFFFFF, count=4000000)
        assert attempts == [(0, 0), (0, 0x80)] + ([(2, 0)] if enabled else []) + [(2, 0x80)], attempts
        assert len(terminal) == 1
        assert bool(m.fdc_log) == bool(enabled)


def mouse_policy():
    for enabled in (0, 1):
        m = Ports()
        payload = bytearray(DEFAULT)
        payload[6] = enabled
        m.warm_continuation()
        m.open(edit_script(bytes(payload))+[0x44, 28])
        assert m.warm
        assert m.post_done
        if not enabled:
            m.cpu.mem_write(m.base+0xB0, bytes((0, 0, 0, 0x21, 1, 2, 8, 7, 9)))
            m.masks[0xA1] &= ~0x10
            m.kbc_cb &= ~0x20
            m.call('init_mouse')
            assert bytes(m.cpu.mem_read(m.base+0xB0, 9)) == bytes(9)
            assert m.masks[0xA1] & 0x10 and m.kbc_cb & 0x20
        # Real callback body counts delivery, external AUX supplies three bytes.
        m.cpu.mem_write(0x80000, b'\x2e\xff\x06\x00\x01\xcb')
        for function in (5, 7, 0):
            m.cpu.reg_write(x.UC_X86_REG_ES, 0x8000)
            if function == 7:
                # api() sets ES to its ABI sentinel; use that segment's callback.
                m.cpu.mem_write(0x21000, b'\x2e\xff\x06\x00\x01\xcb')
            ax, _, flags = m.api(0x15, 0xC200+function, bx=0 if function == 7 else 0x0300 if function == 5 else 0x0100)
            assert ax >> 8 == (0 if enabled else 3)
            assert bool(flags & 1) == (not enabled)
        commands = list(m.mouse_commands)
        for byte in (8, 7, 9):
            m.aux_reply.append(byte)
            m.api(0x74, 0)
        assert m.cpu.mem_read(0x21100, 2) == (b'\x01\x00' if enabled else b'\x00\x00')
        assert m.masks[0xA1] & 0x10 == (0 if enabled else 0x10)
        if not enabled:
            assert not commands and not m.mouse_commands
            assert bytes(m.cpu.mem_read(m.base+0xB0, 9)) == bytes(9)
            # Retained runtime state must not bypass the independent policy
            # gate in IRQ12, even when ordinary enabled/callback gates pass.
            m.cpu.mem_write(m.base+0xB0, bytes((0, 0, 0, 0x21, 1, 0, 0, 0, 0)))
            for byte in (8, 7, 9):
                m.aux_reply.append(byte)
                m.api(0x74, 0)
            assert m.cpu.mem_read(0x21100, 2) == bytes(2)
            m.cpu.mem_write(m.base+0xB9, b'\x4F')
            m.masks[0xA1] &= ~0x10
            m.call('mouse_end')
            assert m.cpu.mem_read(m.base+0xB4, 2) == bytes(2)
            assert m.masks[0xA1] & 0x10 and m.kbc_cb & 0x20
            assert m.kbc_cb & 0x12 == 0 and not m.mouse_commands
            for byte in (8, 7, 9):
                m.aux_reply.append(byte)
                m.api(0x74, 0)
            assert m.cpu.mem_read(0x21100, 2) == bytes(2)
        m.scans([0x1E])
        ax, _, _ = m.api(0x16, 0)
        assert ax == 0x1E61, 'persistent mouse policy must preserve real keyboard IRQ/INT16'


def relocation():
    payload = bytes((3, 4, 3, 1, 1, 0, 0, 1))
    results = []
    for segment in (0x9FC0, 0x9800):
        m = Ports(segment=segment, uart=(0x3E8,), printer=(0x278,))
        if segment != 0x9FC0:
            m.cpu.mem_write(0x9FC00, b'\xA6'*1024)
        m.cpu.mem_write(m.base+0x1F8, b'\xC7'*8)
        m.cpu.mem_write(m.base+0x3F6, b'\xD8'*10)
        m.post(payload)
        m.open(ENTER_DEVICES+[1, 1, 28])
        assert not m.warm
        ax, _, _ = m.api(0x14, 0x015A)
        assert ax == 0x605A
        assert m.api(0x17, 0x025A)[0] == 0x905A
        assert m.api(0x15, 0xC205, bx=0x0300)[0] >> 8 == 3
        assert m.api(0x13, 1)[0] >> 8 == 1
        assert m.cpu.mem_read(m.base+0x1F8, 8) == b'\xC7'*8
        assert m.cpu.mem_read(m.base+0x1F6,2) == bytes(2)  # Loaded/draft fourth stay Disabled.
        assert m.cpu.mem_read(m.base+0x3F6, 10) == b'\xD8'*10
        if segment != 0x9FC0:
            assert m.cpu.mem_read(0x9FC00, 1024) == b'\xA6'*1024
        results.append((m.table(0x400, 4), m.table(0x408, 3), bytes(m.cpu.mem_read(m.base+0x1E6, 16)), tuple(m.cr)))
    assert results[0] == results[1]


CASES = {'serial-addresses': serial_addresses,
         'discovery': discovery, 'publication': publication, 'serial-api': serial_api,
         'serial-waits': serial_waits, 'printer-api': printer_api,
         'ports-options': ports_options, 'ports-conflicts': ports_conflicts,
         'ports-record': ports_record, 'post-composition': post_composition,
         'board-layout': board_layout,
         'ports-draft': ports_draft, 'ports-ui': ports_ui, 'floppy-policy': floppy_policy,
         'mouse-policy': mouse_policy, 'relocation': relocation}


def run_86box():
    floppy = importlib.import_module('floppy-matrix')
    build = rtc.ROOT/'build'
    evidence = build/'chipset-review/serial-addresses'
    evidence.mkdir(parents=True, exist_ok=True)
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    exe = shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA'])/'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    roms = build/'86box/roms'
    wrapper = roms/'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    production = (build/'baios-presario800.bin').read_bytes()
    saved = None
    try:
        with tempfile.TemporaryDirectory(prefix='ports-', dir=build/'tmp') as name:
            work = Path(name)
            for label in ('screen', 'save-warm', 'cold-reload'):
                vm = work/label
                vm.mkdir()
                system = vm/'test.rom'
                defines = ['-DVGA_BIOS_141', '-DEMULATOR_TEST', '-DEMULATOR_PORTS_TEST']
                if label == 'screen':
                    defines.append('-DEMULATOR_PORTS_SCREEN')
                if saved is not None:
                    defines.append('-DEMULATOR_PORTS_COLD')
                floppy.run_hidden([nasm, '-f', 'bin', *defines, '-I', str(rtc.ROOT/'src')+'/', '-o', str(system), str(rtc.ROOT/'src/bios.asm')], check=True)
                data = bytearray(system.read_bytes())
                assert len(data) == 65536
                data[-1] = -sum(data[:-1]) & 255
                wrapper.write_bytes(production[:65536]+data)
                disk = vm/'scratch.img'
                with disk.open('xb') as out:
                    out.truncate(64*1024*1024)
                floppy.config(vm, disk, 4, 2, vm/'a.img', vm/'b.img', seek=True, turbo=True)
                nvram = vm/'nvr/d824.nvr'
                if saved is not None:
                    nvram.write_bytes(saved)
                result = floppy.run_hidden([exe, '-P', str(vm), '-R', str(roms), '-L', str(vm/'86box.log'), '-N'], timeout=90, capture_output=True, text=True)
                print(label+': native exit '+hex(result.returncode), flush=True)
                if (vm/'86box.log').exists():
                    shutil.copyfile(vm/'86box.log', evidence/(label+'.log'))
                if result.returncode != 0x67:
                    shutil.copyfile(disk, evidence/(label+'-failed.img'))
                    shutil.copyfile(nvram, evidence/(label+'-failed.nvr'))
                assert result.returncode == 0x67, (label, hex(result.returncode), result.stdout, result.stderr)
                nvdata = nvram.read_bytes()
                (evidence/(label+'.nvr')).write_bytes(nvdata)
                if label == 'screen':
                    with disk.open('rb') as inp:
                        inp.seek(63*512)
                        width, height = struct.unpack('<HH', inp.read(4))
                        assert width in (640, 720) and height == 400
                        inp.seek(64*512)
                        pixels = inp.read(width*height*4)
                    assert len(set(pixels)) > 3
                    rows = bytearray()
                    for row in range(height):
                        rows.append(0)
                        for col in range(width):
                            offset = (row*width+col)*4
                            rows.extend(pixels[offset:offset+3][::-1])
                    def chunk(kind, data):
                        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
                    png = b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))+chunk(b'IDAT', zlib.compress(rows))+chunk(b'IEND', b'')
                    (evidence/'devices.png').write_bytes(png)
                    print('86Box real retained VGA / screen: PASS', flush=True)
                    continue
                saved = nvdata
                assert result.returncode == 0x67, (label, hex(result.returncode), result.stdout, result.stderr)
                assert saved[0x60:0x68] == bytes((3, 0, 1, 3, 1, 0, 0, 1))
                assert sum(saved[0x5D:0x69]) & 255 == 0
                print('86Box real retained VGA / '+label+': PASS', flush=True)
    finally:
        wrapper.write_bytes(production)
    assert wrapper.read_bytes() == production


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', action='append', choices=CASES)
    parser.add_argument('--86box', action='store_true')
    args = parser.parse_args()
    for name in args.case or CASES:
        CASES[name]()
        print(name+': actual ROM device path PASS', flush=True)
    if args.__dict__['86box']:
        run_86box()


if __name__ == '__main__':
    main()
