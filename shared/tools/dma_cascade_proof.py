"""Run shared FDC initialization and a guest-programmed ISA DMA1 sink."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.tools.ram_proof import Listing, constants


class Bus:
    def __init__(self, image, enabled, present):
        self.listing = Listing(image.with_suffix('.lst'))
        self.state = constants(ROOT / 'shared/src/pc/state.inc')
        self.base = 0x80000  # Deliberately relocated EBDA selected through BDA.
        self.cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        self.cpu.mem_map(0, 0x200000)
        raw = image.read_bytes()
        self.cpu.mem_write(0x100000 - len(raw), raw)
        self.cpu.mem_write(0x40E, struct.pack('<H', self.base >> 4))
        self.cpu.mem_write(self.base + self.state['C_PORTS'], bytes((1, 2, 1, 2, 0, enabled, 0, 1)))
        self.cpu.mem_write(self.base + self.state['C_TYPES'], b'\x40')
        self.cpu.mem_write(0x0E * 4, struct.pack('<HH', self.listing.symbol('int0e'), 0xF000))
        self.present = present
        self.io, self.fdc, self.dma2 = [], [], []
        self.masks = [15, 15]
        self.modes = [[0] * 4, [0] * 4]
        self.requests = [0, 0]
        self.ports = {0x21: 255, 0xA1: 255}
        self.flip = 0
        self.address, self.count, self.page = 0, 0, 0
        self.fifo, self.command = [], []
        self.pending_irq = False
        self.pit, self.latched, self.high = 0xFFFF, 0xFFFF, False
        self.cpu.hook_add(UC_HOOK_INSN, self.incoming, None, 1, 0, x.UC_X86_INS_IN)
        self.cpu.hook_add(UC_HOOK_INSN, self.outgoing, None, 1, 0, x.UC_X86_INS_OUT)
        self.cpu.hook_add(UC_HOOK_CODE, self.observe)

    def incoming(self, cpu, port, size, unused):
        if port == 0x40:
            value = self.latched >> 8 if self.high else self.latched & 255
            self.high = not self.high
            return value
        if port in (0x3F2, 0x3F4, 0x3F5, 0x3F7):
            self.fdc.append(('in', port))
            if not self.present: return 255
            if port == 0x3F4: return 0xC0 if self.fifo else 0x80
            if port == 0x3F5: return self.fifo.pop(0) if self.fifo else 0
        return self.ports.get(port, 0)

    def outgoing(self, cpu, port, size, value, unused):
        self.io.append((port, value))
        if port in (0x0D, 0xDA):
            controller = int(port == 0xDA)
            self.masks[controller] = 15
            self.modes[controller] = [0] * 4
            self.requests[controller] = 0
        if port in (0x0B, 0xD6): self.modes[int(port == 0xD6)][value & 3] = value
        if port in (0x0A, 0xD4):
            controller = int(port == 0xD4)
            if value & 4: self.masks[controller] |= 1 << (value & 3)
            else: self.masks[controller] &= ~(1 << (value & 3))
        if port in (0x09, 0xD2):
            controller = int(port == 0xD2)
            if value & 4: self.requests[controller] |= 1 << (value & 3)
            else: self.requests[controller] &= ~(1 << (value & 3))
        if port == 0x0C: self.flip = 0
        if port in (2, 3):
            target = 'address' if port == 2 else 'count'
            setattr(self, target, (getattr(self, target) & ~(255 << (8 * self.flip))) | value << (8 * self.flip))
            self.flip ^= 1
        if port == 0x83: self.page = value
        if port in (4, 5, 0x81) or (port in (0x0A, 0x0B) and value & 3 == 2): self.dma2.append((port, value))
        if port == 0x43 and value == 0:
            self.latched = self.pit
            self.pit = (self.pit - 0x1000) & 65535
            self.high = False
        if port in (0x3F2, 0x3F4, 0x3F5, 0x3F7):
            self.fdc.append(('out', port, value))
            if self.present:
                if port == 0x3F2 and value & 4 and not self.ports.get(port, 0) & 4: self.pending_irq = True
                if port == 0x3F5:
                    self.command.append(value)
                    first = self.command[0]
                    length = {3: 3, 8: 1, 0x10: 1, 0x12: 2, 0x13: 4}.get(first)
                    assert length is not None, self.command
                    if len(self.command) == length:
                        self.fifo = [0x20, 0] if first == 8 else [0x80] if first == 0x10 else []
                        self.command = []
        self.ports[port] = value

    def observe(self, cpu, address, size, unused):
        if self.pending_irq and cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200 and not self.ports[0x21] & 0x40:
            self.pending_irq = False
            sp = (cpu.reg_read(x.UC_X86_REG_SP) - 6) & 65535
            cpu.mem_write((cpu.reg_read(x.UC_X86_REG_SS) << 4) + sp,
                          struct.pack('<HHH', cpu.reg_read(x.UC_X86_REG_IP), cpu.reg_read(x.UC_X86_REG_CS), cpu.reg_read(x.UC_X86_REG_EFLAGS) & 65535))
            cpu.reg_write(x.UC_X86_REG_SP, sp)
            cpu.reg_write(x.UC_X86_REG_EFLAGS, cpu.reg_read(x.UC_X86_REG_EFLAGS) & ~0x300)
            cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
            cpu.reg_write(x.UC_X86_REG_IP, self.listing.symbol('int0e'))

    def call(self, owner):
        for reg, value in ((x.UC_X86_REG_CS, 0xF000), (x.UC_X86_REG_DS, 0),
                           (x.UC_X86_REG_SS, 0), (x.UC_X86_REG_SP, 0x7000),
                           (x.UC_X86_REG_FS, self.base >> 4), (x.UC_X86_REG_EFLAGS, 0x202)):
            self.cpu.reg_write(reg, value)
        self.cpu.mem_write(0x7000, b'\x00\x80')
        self.cpu.emu_start(0xF0000 + self.listing.symbol(owner), 0xF8000, timeout=3000000, count=300000)
        assert self.cpu.reg_read(x.UC_X86_REG_IP) == 0x8000, (owner, hex(self.cpu.reg_read(x.UC_X86_REG_IP)))

    def audio(self, guest):
        payload = bytes((n * 37 + 11) & 255 for n in range(64))
        self.cpu.mem_write(0x23400, payload)
        self.cpu.mem_write(0x6000, guest)
        for reg, value in ((x.UC_X86_REG_CS, 0), (x.UC_X86_REG_SS, 0), (x.UC_X86_REG_SP, 0x7000)):
            self.cpu.reg_write(reg, value)
        self.cpu.emu_start(0x6000, 0x6000 + len(guest), timeout=1000000, count=1000)
        # The external byte-wide sink raises DRQ1 after the guest programs it.
        ready = self.modes[1][0] == 0xC0 and not self.masks[1] & 1
        ready = ready and not self.masks[0] & 2 and self.modes[0][1] == 0x49
        transferred = bytes(self.cpu.mem_read((self.page << 16) | self.address, self.count + 1)) if ready else b''
        return transferred, payload


def run(image, guest):
    rows = []
    for enabled, present in ((False, False), (False, True), (True, True), (True, False)):
        bus = Bus(image, enabled, present)
        bus.call('init_floppy')
        assert bus.modes[1][0] == 0xC0 and not bus.masks[1] & 1, 'Shared init left DMA cascade masked'
        assert bus.requests[1] == 0 and bus.masks[0] == 15 and bus.masks[1] == 14
        if not enabled:
            assert not bus.fdc and not bus.dma2 and bus.ports[0x21] == 255
        else:
            assert bus.fdc and not bus.ports[0x21] & 0x40
            assert bus.cpu.mem_read(bus.base + 0x85, 1) == bytes((int(present),))
        transferred, payload = bus.audio(guest)
        assert transferred == payload, 'Guest DMA1 payload never reached external sink'
        rows.append(dict(fdc_enabled=enabled, fdc_present=present, cascade_mode=bus.modes[1][0],
                         mask16=bus.masks[1], dma1_payload=transferred.hex(), disabled_no_FDC_or_DMA2=not enabled))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    folder = args.output.parent
    folder.mkdir(parents=True, exist_ok=True)
    source = folder / 'dma1-guest.asm'
    source.write_text('''bits 16
org 0x6000
cli
mov al,5
out 0x0A,al
xor al,al
out 0x0C,al
mov al,0x49
out 0x0B,al
mov ax,0x3400
out 2,al
mov al,ah
out 2,al
mov al,2
out 0x83,al
mov ax,63
out 3,al
mov al,ah
out 3,al
mov al,1
out 0x0A,al
''')
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    subprocess.run([nasm, '-f', 'bin', '-o', str(folder / 'dma1-guest.bin'), str(source)], check=True)
    guest = (folder / 'dma1-guest.bin').read_bytes()
    result = {'image_sha256': hashlib.sha256(args.image.read_bytes()).hexdigest()}
    if args.baseline:
        bus = Bus(args.baseline, False, False)
        bus.call('init_floppy')
        transfer, expected = bus.audio(guest)
        assert transfer != expected and bus.masks[1] & 1
        result['baseline_disabled_fails'] = True
        bus = Bus(args.baseline, True, True)
        bus.call('init_floppy')
        assert bus.audio(guest)[0] == expected
        result['baseline_enabled_passes'] = True
    result['cases'] = run(args.image, guest)
    result['limits'] = 'Shared entry from master-cleared state; modeled external DMA byte sink, not an ESS DSP or physical ISA/VLB test. PB430 already protects its full POST with a separate cascade recipe.'
    args.output.write_text(json.dumps(result, indent=2) + '\n')
    print('PASS four FDC policy/presence cases plus DMA1 payload' + ('; baseline contrast' if args.baseline else ''), flush=True)


if __name__ == '__main__':
    main()
