"""Run the assembled ATA transfer owners against delayed device transitions."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_CODE, UC_HOOK_INTR
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.tools.ram_proof import Listing, constants


class Device:
    """A PIO device whose old status persists for four I/O reads."""
    def __init__(self, command, count, multiple, fault=None, stale_command=False):
        self.command, self.count, self.multiple = command, count, multiple
        self.fault, self.stale_command = fault, stale_command
        self.phase, self.remaining, self.words = 'idle', 0, 0
        self.events, self.written = [], []
        self.command_count = 0
        self.widths = set()
        self.ecc, self.ecc_written, self.ecc_widths = 0, [], set()
        self.sectors, self.end = 1, count * 256

    def status(self):
        if self.remaining:
            self.remaining -= 1
            return 0x48 if self.phase != 'command' or self.stale_command else 0x40
        if self.phase == 'command':
            self.phase = 'data'
            return 0x80
        if self.phase == 'transition':
            self.phase = 'data' if self.words < self.end else 'done'
            return 0x80
        if self.phase == 'data':
            return 0x48
        if self.phase == 'done':
            return {'error': 0x41, 'drq': 0x48}.get(self.fault, 0x40) if self.words == self.count * 256 else 0x40
        return 0x40

    def data(self, cpu, size, value=None):
        assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        assert self.phase == 'data', ('premature data transfer', self.phase, self.remaining)
        if self.command in (0x22, 0x32) and self.words == self.end:
            assert size == 1 and self.ecc < 4
            self.ecc_widths.add(size)
            result = 0xD0 + self.ecc
            if value is not None:
                self.ecc_written.append(value)
            self.ecc += 1
            if self.ecc == 4:
                self.phase, self.remaining = 'transition', 4
            return result
        assert size in (2, 4)
        self.widths.add(size)
        result = 0
        for i in range(size // 2):
            result |= ((self.words * 37 + 0x1357) & 65535) << (16 * i)
            if value is not None:
                self.written.append(value >> (16 * i) & 65535)
            self.words += 1
        if self.words % (self.multiple * 256) == 0 or self.words == self.count * 256:
            if self.command not in (0x22, 0x32):
                self.phase, self.remaining = 'transition', 4
            self.events.append(self.words)
        return result

    def incoming(self, cpu, port, size, _):
        if port in (0x1F7, 0x3F6):
            return self.status()
        if port == 0x1F0:
            return self.data(cpu, size)
        return 0

    def outgoing(self, cpu, port, size, value, _):
        if port == 0x1F2:
            self.sectors = value or 256
        if port == 0x1F0:
            self.data(cpu, size, value)
        if port == 0x1F7 and value in (0x20, 0x22, 0x30, 0x32, 0xC4, 0xC5, 0x40, 0x70):
            assert self.phase in ('idle', 'done'), ('overlapping command', self.phase)
            self.command_count += 1
            self.end = self.words + self.sectors * 256
            self.phase, self.remaining = 'command', 4
            # Non-data commands still have a delayed final status.
            if value in (0x40, 0x70):
                self.phase = 'transition'
                self.words = self.count * 256


def transfer(image, command, count=1, multiple=1, fault=None, stale_command=False, public=False, pio32=False):
    listing = Listing(image.with_suffix('.lst'))
    state = constants(ROOT / 'shared/src/pc/state.inc')
    for name, offset in re.findall(r'%define\s+(\w+)\s+STATE_BASE\s*\+\s*(\d+)',
                                  (ROOT / 'shared/src/pc/state.inc').read_text()):
        state[name] = state['STATE_BASE'] + int(offset)
    cpu = Uc(UC_ARCH_X86, UC_MODE_16)
    cpu.mem_map(0, 0x100000)
    raw = image.read_bytes()
    cpu.mem_write(0x100000 - len(raw), raw)
    base = 0x80000
    # Dynamic port adapters expose this table in the assembled board definition.
    table = next((int(m[1], 0) for line in listing.lines
                  if (m := re.search(r'%define HW_PORT_TABLE (0x[0-9A-Fa-f]+)', line))), None)
    if table is not None:
        cpu.mem_write(base + table, struct.pack('<9H', *range(0x1F0, 0x1F8), 0x3F6))
    for name, value, size in (
        ('S_PRESENT', 1, 1), ('S_COMMAND', command, 1), ('S_COUNT', count, 1),
        ('S_BLOCK_SIZE', 516 if command in (0x22, 0x32) else 512, 2), ('S_BUFFER_SEG', 0x2000, 2),
        ('S_BUFFER_OFF', 0x1000, 2), ('S_LBA', 8, 4),
        ('S_MULTIPLE', multiple, 1), ('S_PIO32', int(pio32), 1)):
        cpu.mem_write(base + state[name], value.to_bytes(size, 'little'))
    payload = b''.join(struct.pack('<H', (i * 37 + 0x1357) & 65535) for i in range(count * 256))
    if command in (0x22, 0x32):
        assert count == 1 and multiple == 1
        payload += bytes(range(0xD0, 0xD4))
    cpu.mem_write(0x21000, payload if command in (0x30, 0x32) else bytes(len(payload)))
    device = Device(command, count, multiple, fault, stale_command)
    cpu.hook_add(UC_HOOK_INSN, device.incoming, None, 1, 0, x.UC_X86_INS_IN)
    cpu.hook_add(UC_HOOK_INSN, device.outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
    cpu.reg_write(x.UC_X86_REG_FS, base >> 4)
    cpu.reg_write(x.UC_X86_REG_SS, 0)
    cpu.reg_write(x.UC_X86_REG_SP, 0x7000)
    cpu.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
    cpu.mem_write(0x7000, b'\x00\x80')
    delivered, eois = [], []
    if public:
        assert multiple == 1 and not fault
        cpu.mem_write(0x40E, struct.pack('<H', base >> 4))
        cpu.mem_write(base + state['S_CAPACITY'], struct.pack('<I', 65536))
        cpu.mem_write(base + state['S_GEOMETRY'], struct.pack('<H', 0x3F10))
        cpu.reg_write(x.UC_X86_REG_AX, {0x20: 0x0200, 0x30: 0x0300, 0x22: 0x0A00, 0x32: 0x0B00}[command] | count)
        cpu.reg_write(x.UC_X86_REG_ES, 0x2000)
        cpu.reg_write(x.UC_X86_REG_BX, 0x1000)
        cpu.reg_write(x.UC_X86_REG_CX, 9)
        cpu.reg_write(x.UC_X86_REG_DX, 0x80)
        cpu.mem_write(0x7000, struct.pack('<HHH', 0x8000, 0xF000, 0x202))
        cpu.reg_write(x.UC_X86_REG_EFLAGS, 2)  # Architectural INT entry clears IF.
        for vector, name in ((0x76, 'int76'), (0x15, 'int15')):
            cpu.mem_write(vector * 4, struct.pack('<HH', listing.symbol(name), 0xF000))
        def enter_interrupt(uc, vector, _=None):
            sp = uc.reg_read(x.UC_X86_REG_SP) - 6
            flags = uc.reg_read(x.UC_X86_REG_EFLAGS)
            uc.mem_write((uc.reg_read(x.UC_X86_REG_SS) << 4) + sp,
                         struct.pack('<HHH', uc.reg_read(x.UC_X86_REG_IP),
                                     uc.reg_read(x.UC_X86_REG_CS), flags & 65535))
            uc.reg_write(x.UC_X86_REG_SP, sp)
            uc.reg_write(x.UC_X86_REG_EFLAGS, flags & ~0x300)
            ip, cs = struct.unpack('<HH', bytes(uc.mem_read(vector * 4, 4)))
            uc.reg_write(x.UC_X86_REG_CS, cs)
            uc.reg_write(x.UC_X86_REG_IP, ip)
        def pending_irq(uc, address, size, _):
            if not delivered and uc.reg_read(x.UC_X86_REG_EFLAGS) & 0x200:
                delivered.append(address)
                enter_interrupt(uc, 0x76)
        def pic(uc, port, size, value, _):
            if port in (0x20, 0xA0):
                eois.append((port, value))
        cpu.hook_add(UC_HOOK_INTR, enter_interrupt)
        cpu.hook_add(UC_HOOK_CODE, pending_irq, None,
                     0xF0000 + listing.symbol('.loop', 'ata_wait_drq'),
                     0xF0000 + listing.symbol('.loop', 'ata_wait_drq'))
        cpu.hook_add(UC_HOOK_INSN, pic, None, 1, 0, x.UC_X86_INS_OUT)
    owner = 'ide_multiple_transfer' if multiple > 1 else 'ata_transfer'
    if public:
        owner = 'int13'
    cpu.emu_start(0xF0000 + listing.symbol(owner), 0xF8000,
                  count=32000000 if fault == 'drq' else 200000)
    assert cpu.reg_read(x.UC_X86_REG_IP) == 0x8000, 'transfer did not return'
    failed = bool(cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1)
    status = cpu.mem_read(base + state['S_STATUS'], 1)[0]
    assert failed == bool(fault), (failed, status, device.phase)
    if fault:
        assert status == (0x20 if fault == 'error' else 0x80), status
    else:
        assert device.phase == 'done' and device.remaining == 0, 'premature completion'
        assert cpu.mem_read(base + state['S_DONE'], 1)[0] == count
        if command in (0x20, 0x22):
            assert bytes(cpu.mem_read(0x21000, len(payload))) == payload
        elif command in (0x30, 0x32):
            assert struct.pack('<' + 'H' * len(device.written), *device.written) + bytes(device.ecc_written) == payload
    if public:
        assert delivered and eois == [(0xA0, 0x66), (0x20, 0x62)], (delivered, eois)
        assert cpu.mem_read(0x48E, 1) == b'\xff'
        assert cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
    if command in (0x20, 0x30):
        assert device.widths == {4 if pio32 else 2}, device.widths
    if command in (0x22, 0x32):
        assert device.widths == {2} and device.ecc_widths == {1} and device.ecc == 4
    return dict(command=hex(command), sectors=count, block=multiple, fault=fault,
                stale_command=stale_command, status=status, words=device.words,
                public_int13=public, irq14_serviced=bool(delivered), pic_eois=eois,
                io_width_bytes=sorted(device.widths), ecc_width_bytes=sorted(device.ecc_widths), ecc_bytes=device.ecc)


def run(image, faults=(None, 'error', 'drq'), pio32=False):
    cases = []
    for command in (0x20, 0x30):
        for count, block in ((1, 1), (3, 1), (8, 4), (7, 4)):
            for stale in (False, True):
                for fault in faults:
                    cases.append(transfer(image, command, count, block, fault, stale, pio32=pio32))
    for command in (0x40, 0x70):
        for fault in faults:
            cases.append(transfer(image, command, fault=fault, pio32=pio32))
    if None in faults:
        for command in (0x22, 0x32):
            cases.append(transfer(image, command, pio32=pio32))
        for command in (0x20, 0x30, 0x22, 0x32):
            cases.append(transfer(image, command, public=True, pio32=pio32))
    return cases


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--fault', choices=('error', 'drq'))
    args = parser.parse_args()
    result = run(args.image.resolve(), (args.fault,) if args.fault else (None, 'error', 'drq'))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2) + '\n')
    print(f'ATA delayed completion: {len(result)} cases PASS')
