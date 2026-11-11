"""Execute the production M919 SMM path against independent UMC/CPU seams.

PCI delivery, conditional SMRAM views, CPU save/RSM and cache effects are
models. Passing this proof does not qualify physical chipset or reset timing.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import (Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INTR,
                     UC_HOOK_INSN, UC_HOOK_MEM_WRITE, UC_HOOK_MEM_READ)
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
ROOT = PORT.parent
sys.path.insert(0, str(ROOT))
from shared.tools.ram_proof import Listing, constants
from shared.tools.rom import build
from shared.tools.smm_proof import MAPS, REGS, SEGMENTS, REQUEST, REPLY

OUTPUT = PORT / 'build/tests/smm-activation'
ROM = OUTPUT / 'baios-m919.bin'
CPU_STATE = constants(ROOT / 'shared/src/pc/state.inc')
STATUS = constants(PORT / 'src/hardware/board-definition.inc')['HW_SMM_STATUS']
ERROR = constants(PORT / 'src/hardware/board-definition.inc')['HW_SMM_ERROR']
BOOT_TRACE = constants(PORT / 'src/hardware/board-definition.inc')['HW_SMM_BOOT_TRACE']
FINAL_TRACE = constants(PORT / 'src/hardware/board-definition.inc')['HW_SMM_FINAL_TRACE']
TRACE_VALID = constants(PORT / 'src/hardware/board-definition.inc')['HW_SMM_TRACE_VALID']
HB, SB = 0x80008000, 0x80009000


class Board:
    def __init__(self, *, family='Intel486', bridge=0x886A1060, host=0x88811060,
                 signature=None, vendor=None, warm=False, deliver=True,
                 revision=0x20001, fault=None, decoded=True, id_bit=True, max_leaf=1):
        self.raw = ROM.read_bytes()
        self.listing = Listing(ROM.with_suffix('.lst'))
        self.u = Uc(UC_ARCH_X86, UC_MODE_16)
        self.u.mem_map(0, 0x200000)
        self.u.mem_write(0xE0000, self.raw)
        self.family, self.layout = family, MAPS[family]
        self.vendor = vendor or (b'GenuineIntel' if family == 'Intel486' else b'AuthenticAMD')
        self.signature = signature if signature is not None else (0x480 if family == 'Intel486' else 0x4F0)
        self.id_bit, self.max_leaf, self.flags_after_pop = id_bit, max_leaf, None
        self.deliver, self.revision, self.fault = deliver, revision, fault
        self.sm_base, self.smm = (0xA0000 if warm else 0x30000), False
        self.conf = {HB: bytearray(256), SB: bytearray(256)}
        self.conf[HB][:4] = struct.pack('<I', host)
        self.conf[SB][:4] = struct.pack('<I', bridge)
        self.conf[HB][0x50] = 5
        self.conf[HB][0x55] = 0x40
        self.conf[HB][0x5D] = 0x20
        self.conf[SB][0x46] = 0x10
        self.conf[SB][0x57] = 0x27 if decoded else 7
        self.cf8, self.nmi = 0x81234560, 0x8D
        self.hidden, self.vga = bytes([0xA7]) * 0x20000, bytes([0x39]) * 0x20000
        self.e_shadow = bytearray([0xDE]) * 0x10000
        self.e_decoded = decoded
        self.e_visible, self.e_written, self.e_restore = False, set(), []
        self.visible = False
        self.u.mem_write(0xA0000, self.vga)
        if not decoded:
            self.u.mem_write(0xE0000, bytes([255]) * 0x10000)
        config = constants(OUTPUT / 'configuration.inc')
        self.ebda = config['CFG_PLATFORM_STATE_SEG'] << 4
        self.u.mem_write(0x40E, struct.pack('<H', self.ebda >> 4))
        self.u.mem_write(self.ebda, bytes([config['CFG_PLATFORM_STATE_KIB']]))
        self.u.mem_write(self.ebda + CPU_STATE['S_CPU_SIGNATURE'], struct.pack('<H', self.signature))
        self.visits, self.io, self.events, self.entries, self.replies = [], [], [], [], []
        self.pending, self.action, self.guard = False, None, False
        self.invalidated, self.smi_before, self.dirty = False, None, {}
        self.injected, self.reset, self.stop = False, False, None
        self.dma_during_smm, self.command_cache = False, None
        self.command_controls, self.request_raised = None, False
        self.decoder = Cs(CS_ARCH_X86, CS_MODE_16)
        self.instructions = {}
        self.symbols = {}
        self.owners = {}
        for name in ('board_smm_startup', 'board_smm_initialize', 'board_smm_cpu_query',
                     'm919_smm_qualify', 'm919_smm_initialize', 'm919_smm_prepare',
                     'smm_install', 'board_smm_command', 'm919_smm_command',
                     'm919_smm_command_entry', 'cache_initialize', 'board_cpu_sl_query',
                     'board_smm_quiesce', 'warm_reset', 'controlled_defaults_restart'):
            self.owners[self.address(name)] = name
        self.handler = self.raw[self.listing.symbol('board_smm_image'):
                                self.listing.symbol('board_smm_image_end')]
        self.trace_offset = self.listing.symbol('board_smm_trace') - self.listing.symbol('board_smm_image')
        self.u.hook_add(UC_HOOK_CODE, self.step)
        self.u.hook_add(UC_HOOK_MEM_WRITE, self.write)
        for base in (0x38000, 0xA8000):
            marker = base + self.trace_offset
            self.u.hook_add(UC_HOOK_MEM_READ, self.read, begin=marker, end=marker)
        self.u.hook_add(UC_HOOK_INSN, self.inp, None, 1, 0, x.UC_X86_INS_IN)
        self.u.hook_add(UC_HOOK_INSN, self.out, None, 1, 0, x.UC_X86_INS_OUT)

    def address(self, name):
        if name not in self.symbols:
            extension = name.startswith('m919_') or name in ('smm_install', 'board_smm_image', 'board_smm_image_end')
            self.symbols[name] = (0xE0000 if extension else 0xF0000) + self.listing.symbol(name)
        return self.symbols[name]

    def bank(self):
        visible = self.smm or bool(self.conf[HB][0x60] & 1)
        if visible:
            assert self.conf[HB][0x5C] == 0 and self.conf[HB][0x5D] & 15 == 0, 'wrong SMRAM address'
            assert not self.conf[HB][0x60] & 0x20, 'classic split-data mode'
        if visible != self.visible:
            old = bytes(self.u.mem_read(0xA0000, 0x20000))
            if self.visible:
                self.hidden = old
            else:
                self.vga = old
            self.u.mem_write(0xA0000, self.hidden if visible else self.vga)
            self.u.ctl_remove_cache(0xA0000, 0xC0000)
            self.visible = visible

    def e_bank(self):
        visible = bool(self.conf[HB][0x54] & 1 and self.conf[HB][0x55] & 0x80)
        decoded = bool(self.conf[SB][0x57] & 0x20)
        if visible != self.e_visible or decoded != self.e_decoded:
            self.e_visible = visible
            self.e_decoded = decoded
            self.u.mem_write(0xE0000, bytes(self.e_shadow) if visible else self.raw[:0x10000] if decoded else bytes([255])*0x10000)
            self.u.ctl_remove_cache(0xE0000, 0xF0000)

    def dma_write(self, address, data):
        assert 0xA0000 <= address and address + len(data) <= 0xC0000
        normal = bytearray(self.vga if self.visible else self.u.mem_read(0xA0000, 0x20000))
        normal[address - 0xA0000:address - 0xA0000 + len(data)] = data
        self.vga = bytes(normal)
        if not self.visible:
            self.u.mem_write(address, data)

    def inp(self, u, port, size, user):
        self.io.append(('in', port, size))
        if port == 0xCF8:
            return self.cf8
        if 0xCFC <= port <= 0xCFF:
            device = self.cf8 & ~255
            offset = (self.cf8 & 0xFC) + port - 0xCFC
            if device not in self.conf:
                return (1 << (8 * size)) - 1
            value = int.from_bytes(self.conf[device][offset:offset + size], 'little')
            if self.fault == 'close-readback' and device == HB and offset == 0x60 and not (value & 1):
                return value | 1
            if self.fault == 'base-readback' and device == HB and offset == 0x5C:
                return 1
            return value
        if port == 0x64:
            return 0
        if port in (0x61, 0x92, 0x71, 0x84, 0x3C4, 0x3C5):
            return 0
        raise AssertionError(('unexpected input', hex(port), size))

    def out(self, u, port, size, value, user):
        self.io.append(('out', port, size, value))
        if port == 0xCF8:
            self.cf8 = value
            return
        if 0xCFC <= port <= 0xCFF:
            device = self.cf8 & ~255
            offset = (self.cf8 & 0xFC) + port - 0xCFC
            assert device in self.conf, ('unknown configuration write', hex(self.cf8))
            assert size == 1
            old = self.conf[device][offset]
            if device == HB and offset == 0x50 and self.guard and self.request_raised and not self.smm:
                assert (self.conf[SB][0xA0], self.conf[SB][0xA8]) == self.command_controls, 'PM controls restored after L2'
            if device == HB and offset == 0x60 and value & 1 and self.u.mem_read(self.ebda + ERROR, 1)[0]:
                assert self.conf[SB][0xA0] == 0 and not self.conf[SB][0xA3] & 0xC0, 'trace opened before quiescence'
            # The emulator's A2 W1C interpretation differs from OEM's zero write.
            self.conf[device][offset] = old & ~value if device == SB and offset == 0xA2 else value
            self.events.append(('pci', device, offset, value))
            if device == HB and offset == 0x60:
                self.bank()
            if device == HB and offset in (0x54, 0x55):
                self.e_bank()
            if device == SB and offset == 0x57:
                self.e_bank()
            if device == SB and offset == 0xA3 and value & 0xC0 == 0xC0 and not old & 0x40:
                self.request_raised = True
                assert not self.conf[HB][0x60] & 1, 'enabled before closing SMRAM'
                assert self.conf[SB][0xA0] & 0x34 == 0x34, 'missing reference SMI control'
                assert self.conf[SB][0xA8] & 0x28 == 0x28, 'missing reference SMI control'
                assert self.conf[SB][0x76] & 0x30 == 0, 'wrong CPU interface'
                # Require the reference's enable-before-request order, not just C0.
                if old & 0x80 and not self.conf[SB][0x46] & 0x40 and self.deliver:
                    self.pending = True
            return
        if port == 0x70:
            self.nmi = value
            return
        if port == 0x64 and value == 0xFE:
            assert self.conf[SB][0xA0] == 0 and self.conf[SB][0xA3] & 0xC0 == 0
            self.reset = True
            self.action = 'reset'
            u.emu_stop()
            return
        assert port in (0x41, 0x43, 0x61, 0x71, 0x80, 0x92, 0x64, 0x60, 0x3C4, 0x3C5), ('unexpected output', hex(port), size, value)

    def read(self, u, access, address, size, value, user):
        if self.smm or not self.u.mem_read(self.ebda + ERROR, 1)[0]:
            return
        if address in (0x38000 + self.trace_offset, 0xA8000 + self.trace_offset):
            assert self.conf[SB][0xA0] == 0 and not self.conf[SB][0xA3] & 0xC0, 'trace read before quiescence'
            self.events.append(('trace-read', address))

    def write(self, u, access, address, size, value, user):
        if address == self.ebda + STATUS and value == 1:
            assert len(self.entries) == len(self.replies) == 2
            assert all(reply[1:] == (0, self.revision) for reply in self.replies)
            assert not self.conf[HB][0x60] & 1
            assert self.conf[SB][0xA3] & 0xC0 == 0x80 and self.conf[SB][0xA0] == 0
        if self.smm:
            allowed = [self.sm_base + self.layout[name] for name in ('EAX', 'ECX', 'EBX', 'EFLAGS')]
            allowed.append(self.sm_base + 0xFEF8)
            trace = self.sm_base + 0x8000 + self.trace_offset
            assert (address == trace and size == 1) or any(a <= address and address + size <= a + 4 for a in allowed), ('handler write', hex(address), size)
        elif self.guard:
            raise AssertionError(('ordinary write with cache quiescent', hex(address), size))
        if 0xE0000 <= address and address + size <= 0xF0000:
            offset = address - 0xE0000
            assert not self.conf[HB][0x55] & 0xC0 and not self.e_visible, 'E copy needs writable shadow and external reads'
            assert self.conf[SB][0x57] & 0x20, 'external E ROM not decoded during copy'
            assert value.to_bytes(size, 'little') == self.raw[offset:offset + size]
            if not self.conf[HB][0x55] & 0x40:
                self.e_shadow[offset:offset + size] = value.to_bytes(size, 'little')
                self.e_written.update(range(offset, offset + size))
            # Read and write views differ even when the copied bytes are equal.
            source = self.e_shadow if self.e_visible else self.raw
            self.e_restore.append((address, bytes(source[offset:offset + size])))

    def step(self, u, address, size, user):
        for target, data in self.e_restore:
            if bytes(u.mem_read(target, len(data))) != data:
                u.mem_write(target, data)
        self.e_restore.clear()
        if self.flags_after_pop is not None:
            if not self.id_bit:
                flags = u.reg_read(x.UC_X86_REG_EFLAGS)
                u.reg_write(x.UC_X86_REG_EFLAGS, (flags & ~0x200000) | (self.flags_after_pop & 0x200000))
            self.flags_after_pop = None
        if self.pending and not self.smm:
            self.pending = False
            self.action = 'enter'
            u.emu_stop()
            return
        if address == self.stop:
            self.action = 'stop'
            u.emu_stop()
            return
        if address in self.owners:
            self.visits.append(self.owners[address])
        if address == self.address('m919_smm_command'):
            self.command_cache = self.conf[HB][0x50]
            self.command_controls = (self.conf[SB][0xA0], self.conf[SB][0xA8])
            self.request_raised = False
        assert not (0xE0000 <= address < 0xF0000 and not (self.e_visible or self.conf[SB][0x57] & 0x20)), 'fetch from disabled E ROM'
        opcode = bytes(u.mem_read(address, min(size, 15)))
        if self.smm and opcode[:2] == b'\x0f\xaa':
            self.action = 'resume'
            u.emu_stop()
            return
        if address not in self.instructions:
            self.instructions[address] = next(self.decoder.disasm(opcode, address))
        ins = self.instructions[address]
        if self.address('board_smm_initialize') <= address < self.address('board_smm_command') and ins.mnemonic == 'cmp':
            # Unicorn omits real-mode segment-limit faults: check the actual header operand.
            assert ins.op_str == 'dword ptr es:[0x14], 0x53494142' and u.reg_read(x.UC_X86_REG_ES) == 0xE000
        if ins.mnemonic == 'popfd':
            self.flags_after_pop = u.reg_read(x.UC_X86_REG_EFLAGS)
        if self.smm:
            assert self.sm_base + 0x8000 <= address < self.sm_base + 0x8000 + len(self.handler)
            assert ins.mnemonic not in ('push', 'pushf', 'pushfd', 'pushal', 'pop', 'popfd',
                                        'call', 'lcall', 'ret', 'retf', 'hlt')
            if ins.mnemonic in ('wbinvd', 'invd'):
                assert getattr(self, 'native_idle', False) and self.sm_base == 0xA0000
        if ins.mnemonic == 'cpuid':
            assert self.id_bit
            leaf = u.reg_read(x.UC_X86_REG_EAX)
            if leaf == 0:
                ebx, edx, ecx = struct.unpack('<III', self.vendor)
                values = (self.max_leaf, ebx, ecx, edx)
            else:
                assert leaf == 1 and self.max_leaf >= 1
                values = (self.signature, 0, 0, 0)
            for reg, value in zip(('EAX', 'EBX', 'ECX', 'EDX'), values):
                u.reg_write(REGS[reg], value)
            u.reg_write(x.UC_X86_REG_IP, u.reg_read(x.UC_X86_REG_IP) + size)
        if ins.mnemonic == 'wbinvd':
            for target, data in self.dirty.items():
                u.mem_write(target, data)
            self.dirty.clear()
            self.events.append(('wbinvd', address))
            if self.smm or self.address('m919_smm_command') <= address < self.address('board_smm_image'):
                self.guard, self.invalidated = True, False
        if ins.mnemonic == 'invd':
            assert self.guard and not self.dirty
            assert self.conf[HB][0x50] == self.command_cache, 'L2 restored after tag invalidation'
            self.events.append(('invd', address))
            self.invalidated = True
        if ins.mnemonic == 'mov' and ins.op_str == 'cr0, esi':
            assert self.invalidated, 'CR0 restored before clean-tag invalidation'
            if not self.smm:
                assert (self.conf[SB][0xA0], self.conf[SB][0xA8]) == self.command_controls, 'PM controls restored after CR0'
            self.events.append(('restore-cr0', address))
            self.guard = False
        if self.fault == 'copy' and not self.injected and opcode[:2] == b'\xf3\xa6':
            target = (u.reg_read(x.UC_X86_REG_ES) << 4) + u.reg_read(x.UC_X86_REG_DI)
            u.mem_write(target, bytes([u.mem_read(target, 1)[0] ^ 0x80]))
            self.injected = True

    def enter(self):
        if getattr(self, 'native_idle', False) and self.u.reg_read(x.UC_X86_REG_ECX) & 65535 == 3:
            # Chipset seam: only the final VGA aperture is uncacheable before
            # handler entry. Bootstrap SMRAM still needs the private wrapper.
            assert self.sm_base == 0xA0000
            assert all(not (a < 0xC0000 and a+len(data) > 0xA0000) for a,data in self.dirty.items())
        else:
            assert not self.dirty, 'SMI before dirty ordinary data drained'
            assert self.u.reg_read(x.UC_X86_REG_CR0) & 0x60000000 == 0x60000000
            assert not self.conf[HB][0x50] & 0x80
        assert self.nmi & 0x80 and not self.u.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        self.entries.append(self.sm_base + 0x8000)
        self.events.append(('smi', self.sm_base))
        if self.fault == 'source-cleared-on-entry':
            self.conf[SB][0xA3] &= ~0x40
        self.ack_start, self.ack_a3, self.ack_cf8 = len(self.events), self.conf[SB][0xA3], self.cf8
        self.smm = True
        self.bank()
        if self.dma_during_smm:
            before = bytes(self.u.mem_read(0xA8000, len(self.handler)))
            self.dma_write(0xA8000, b'\xC3\xC3')
            assert bytes(self.u.mem_read(0xA8000, len(self.handler))) == before
        saved = bytearray((i * 73 + 19) & 255 for i in range(0x200))
        for name, offset in self.layout.items():
            struct.pack_into('<H' if name in SEGMENTS else '<I', saved, offset - 0xFE00, self.u.reg_read(REGS[name]))
        struct.pack_into('<IIHH', saved, 0xF8, self.sm_base, self.revision, 0xA501, 0x5A01)
        self.smi_before = bytes(saved)
        self.u.mem_write(self.sm_base + 0xFE00, bytes(saved))
        self.u.reg_write(x.UC_X86_REG_CS, self.sm_base >> 4)
        self.u.reg_write(x.UC_X86_REG_IP, 0x8000)
        self.u.reg_write(x.UC_X86_REG_EFLAGS, 2)

    def resume(self):
        assert self.events[self.ack_start:self.ack_start+3] == [('pci', SB, 0xA2, 0),
            ('pci', SB, 0xA3, self.ack_a3 | 0x20), ('pci', SB, 0xA3, (self.ack_a3 | 0x20) & 0x9F)], 'board acknowledgment order'
        if struct.unpack_from('<H', self.smi_before, self.layout['ECX']-0xFE00)[0] not in (2, 3):
            assert len(self.events) == self.ack_start+3, 'unexpected SMM hardware operation'
        assert self.cf8 == self.ack_cf8, 'acknowledgment CF8 restoration'
        saved = bytes(self.u.mem_read(self.sm_base + 0xFE00, 0x200))
        allowed = set()
        for offset in (0xFEF8, *(self.layout[name] for name in ('EAX', 'ECX', 'EBX', 'EFLAGS'))):
            allowed.update(range(offset - 0xFE00, offset - 0xFE00 + 4))
        assert all(a == b or i in allowed for i, (a, b) in enumerate(zip(saved, self.smi_before))), 'undocumented save-map change'
        restored = {name: struct.unpack_from('<H' if name in SEGMENTS else '<I', saved, offset - 0xFE00)[0]
                    for name, offset in self.layout.items()}
        if restored['EBX'] == REPLY:
            self.replies.append((self.sm_base, restored['EAX'], restored['ECX']))
        for name, value in restored.items():
            self.u.reg_write(REGS[name], value)
        self.sm_base = struct.unpack_from('<I', saved, 0xF8)[0]
        self.smm = False
        self.bank()

    def execute(self, entry, stop=None, count=50000):
        self.stop = stop
        self.action = None
        address = entry
        for _ in range(12):
            self.u.emu_start(address, 0x200000, count=count)
            action, self.action = self.action, None
            if action in ('stop', 'reset'):
                return
            if action == 'enter':
                self.enter()
            elif action == 'resume':
                self.resume()
            else:
                raise AssertionError(('instruction budget exhausted', hex(self.u.reg_read(x.UC_X86_REG_CS)), hex(self.u.reg_read(x.UC_X86_REG_IP))))
            address = (self.u.reg_read(x.UC_X86_REG_CS) << 4) + self.u.reg_read(x.UC_X86_REG_IP)
        raise AssertionError('too many SMI boundaries')

    def context(self, *, cached=False):
        self.u.reg_write(x.UC_X86_REG_CR0, 0x10 if cached else 0x60000010)
        values = dict(EAX=0x12340000, EBX=0x76543210, ECX=0x10203040, EDX=0x99887766,
                      ESI=0x13572468, EDI=0x24681357, EBP=0x31415926, ESP=0xCAFE6FFE,
                      CS=0xF000, DS=0, ES=0, FS=self.ebda >> 4, GS=0x3500, SS=0,
                      EFLAGS=0x646, CR0=0x10 if cached else 0x60000010, CR3=0,
                      DR6=0xFFFF0FF0, DR7=0x400)
        for name, value in values.items():
            self.u.reg_write(REGS[name], value)
        self.u.mem_write(0x6FFE, struct.pack('<H', 0xFFF0))
        return values

    def startup(self):
        original = self.context()
        self.execute(self.address('board_smm_startup'), self.address('cache_initialize'))
        assert self.u.reg_read(x.UC_X86_REG_ES) == original['ES'], 'startup header check changed caller ES'
        assert self.u.reg_read(x.UC_X86_REG_ESP) == original['ESP']-2, 'unbalanced startup stack before cache call'
        return self.u.mem_read(self.ebda + STATUS, 1)[0]

    def early_startup(self):
        self.context()
        self.execute(self.address('chipset_initialize'), self.address('flat_addressing'))
        assert self.conf[SB][0xA0] == 0 and self.conf[SB][0xA3] & 0xC0 == 0
        assert self.conf[SB][0x57] & 0x20
        assert bytes(self.u.mem_read(0xE0014, 8)) == b'BAISMM1\0'
        return self.startup()

    def call(self, name, *, command=0, cached=False):
        original = self.context(cached=cached)
        original['EAX'] |= command
        self.u.reg_write(x.UC_X86_REG_EAX, original['EAX'])
        self.execute(self.address(name), 0xFFFF0)
        return original

    def status_report(self):
        self.u.mem_write(0x10100, (PORT / 'build/diagnostics/SMMSTATE.COM').read_bytes())
        for name in ('CS', 'DS', 'ES', 'SS'):
            self.u.reg_write(REGS[name], 0x1000)
        self.u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
        self.u.reg_write(x.UC_X86_REG_EFLAGS, 0x202)
        output = []
        def interrupt(cpu, number, _):
            assert number == 0x21
            ah = cpu.reg_read(x.UC_X86_REG_AH)
            if ah == 9:
                address = cpu.reg_read(x.UC_X86_REG_DS)*16 + cpu.reg_read(x.UC_X86_REG_DX)
                output.append(bytes(cpu.mem_read(address, 16)).split(b'$')[0].decode())
            else:
                assert ah == 0x4C
                self.action = 'stop'
                cpu.emu_stop()
        hook = self.u.hook_add(UC_HOOK_INTR, interrupt)
        try:
            self.execute(0x10100)
        finally:
            self.u.hook_del(hook)
        return ''.join(output).strip()

    def direct_smi(self, *, software=True, cookie=REQUEST, command=0, target=0xA0000):
        self.context()
        self.u.reg_write(x.UC_X86_REG_IP, 0xFFF0)
        self.u.reg_write(x.UC_X86_REG_EFLAGS, 0x447)
        for name, value in (('EBX', cookie), ('ECX', command), ('EDI', target)):
            self.u.reg_write(REGS[name], value)
        self.conf[SB][0xA3] = 0xC0 if software else 0x80
        self.conf[SB][0xA2] = 0 if software else 4
        cf8 = self.cf8
        self.enter()
        self.execute(self.sm_base + 0x8000, 0xFFFF0)
        assert self.cf8 == cf8
        return bytes(self.u.mem_read(0xA0000, 1)), self.u.reg_read(x.UC_X86_REG_EAX)


def diagnostic():
    folder = PORT / 'build/diagnostics'
    folder.mkdir(parents=True, exist_ok=True)
    image = folder / 'SMMSTATE.COM'
    state_kib = constants(OUTPUT / 'configuration.inc')['CFG_PLATFORM_STATE_KIB']
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    subprocess.run([nasm, '-w+error', '-f', 'bin', '-DSMM_STATUS='+str(STATUS),
                    '-DSMM_ERROR='+str(ERROR),
                    '-DSMM_BOOT_TRACE='+str(BOOT_TRACE), '-DSMM_FINAL_TRACE='+str(FINAL_TRACE),
                    '-DSMM_TRACE_VALID='+str(TRACE_VALID),
                    '-DSTATE_KIB='+str(state_kib), '-o', str(image),
                    str(PORT / 'diagnostics/smm-state.asm')], check=True)
    rows = []
    cases = [(i, True, 0x9E00, 0, None) for i in range(5)] + [(1, False, 0x9E00, 0, None), (1, True, 0xB000, 0, None)]
    cases += [(stage, True, 0x9E00, error, None) for stage in (3, 4) for error in (1, 2, 3, 4, 255)]
    cases += [(3, True, 0x9E00, 4, pair) for pair in ((0, 0), (6, 0), (7, 0), (0, 7), (0, 15))]
    for status, valid_rom, ebda, error, trace in cases:
        u = Uc(UC_ARCH_X86, UC_MODE_16)
        u.mem_map(0, 0x100000)
        u.mem_write(0x10100, image.read_bytes())
        u.mem_write(0xE0014, b'BAISMM1\0' if valid_rom else b'OTHERROM')
        u.mem_write(0x40E, struct.pack('<H', ebda))
        u.mem_write(ebda*16, bytes([state_kib]))
        u.mem_write(ebda*16+STATUS, bytes([status]))
        u.mem_write(ebda*16+ERROR, bytes([error]))
        if trace is not None:
            u.mem_write(ebda*16+BOOT_TRACE, bytes(trace))
            u.mem_write(ebda*16+TRACE_VALID, b'\xA5')
        u.reg_write(x.UC_X86_REG_CS, 0x1000)
        u.reg_write(x.UC_X86_REG_SS, 0x1000)
        u.reg_write(x.UC_X86_REG_SP, 0xFFFE)
        output = []
        def interrupt(uc, number, _):
            assert number == 0x21
            ah = uc.reg_read(x.UC_X86_REG_AH)
            if ah == 9:
                address = uc.reg_read(x.UC_X86_REG_DS)*16+uc.reg_read(x.UC_X86_REG_DX)
                output.append(bytes(uc.mem_read(address, 16)).split(b'$')[0])
            else:
                assert ah == 0x4C
                uc.emu_stop()
        u.hook_add(UC_HOOK_INTR, interrupt)
        def read_only(uc, address, size, _):
            ins = next(Cs(CS_ARCH_X86, CS_MODE_16).disasm(bytes(uc.mem_read(address, size)), address))
            assert ins.mnemonic not in ('in', 'out', 'wbinvd', 'invd', 'wrmsr', 'hlt', 'cli', 'sti', 'lmsw', 'clts')
            assert not (ins.mnemonic == 'mov' and ins.op_str.startswith('cr'))
        def own_write(uc, access, address, size, value, _):
            assert 0x10000 <= address and address+size <= 0x20000, 'diagnostic wrote outside its process'
        u.hook_add(UC_HOOK_CODE, read_only)
        u.hook_add(UC_HOOK_MEM_WRITE, own_write)
        u.emu_start(0x10100, 0x10200, count=200)
        expected = str(status) if valid_rom and ebda == 0x9E00 else 'X'
        if expected in ('3', '4'):
            expected += str(error) if 1 <= error <= 4 else '?'
            if error == 4 and trace is not None:
                expected += ''.join(f'{value:X}' for value in trace)
        assert output == [('S'+expected+'\r\n').encode()], output
        rows.append('diagnostic-S'+expected)
    return rows


def main():
    build(PORT, 'build/tests/smm-activation')
    assert len(ROM.read_bytes()) == 0x20000
    assert all(sum(ROM.read_bytes()[a:a + 0x10000]) & 255 == 0 for a in (0, 0x10000))
    rows = diagnostic()
    for family in MAPS:
        for bridge in (0x886A1060, 0x888A1060):
            for warm in (False, True):
                b = Board(family=family, bridge=bridge, warm=warm, decoded=False)
                b.conf[SB][0xA0], b.conf[SB][0xA3] = 0x34, 0xC0
                b.conf[HB][0x5C], b.conf[HB][0x5D], b.conf[HB][0x60] = 0x12, 0x2F, 0x20
                assert b.early_startup() == 1
                assert b.entries == ([0xA8000, 0xA8000] if warm else [0x38000, 0xA8000]), b.entries
                assert {'m919_smm_qualify', 'm919_smm_prepare', 'smm_install'} <= set(b.visits)
                assert not b.conf[HB][0x60] & 1
                assert b.conf[SB][0xA3] & 0xC0 == 0x80 and b.conf[SB][0xA0] == 0
                observed = bytearray(b.hidden[0x8000:0x8000 + len(b.handler)])
                assert observed[b.trace_offset] == 7
                observed[b.trace_offset] = 0
                assert observed == b.handler
                assert bytes(b.e_shadow) == b.raw[:0x10000] and len(b.e_written) == 0x10000
                rows.append(f'{family}-{bridge:08X}-' + ('warm' if warm else 'cold'))
    for name, options in (
        ('unsupported-cpu', {'signature': 0x400}),
        ('wrong-vendor', {'vendor': b'CyrixInstead'}),
        ('wrong-host', {'host': 0x12341060}),
        ('wrong-bridge', {'bridge': 0x673A1060}),
        ('wrong-host-vendor', {'host': 0x88811234}),
        ('wrong-bridge-vendor', {'bridge': 0x886A1234}),
        ('no-cpuid', {'id_bit': False}),
        ('no-signature-leaf', {'max_leaf': 0}),
        ('classic-amd-save-map', {'family': 'Am5x86', 'signature': 0x480}),
    ):
        b = Board(**options)
        assert b.startup() == 0
        # Ordinary APM uses E even when the CPU cannot enter SMM. Its shadow
        # copy belongs to the identified host, not to SMM qualification.
        host_known=not name.startswith('wrong-host')
        assert b.events == ([('pci',HB,0x55,0),('pci',HB,0x55,0x40)] if host_known else []), (name,b.events)
        assert not b.entries
        if host_known:
            assert bytes(b.e_shadow)==b.raw[:0x10000] and len(b.e_written)==0x10000
        rows.append(name)
    for name, options in (
        ('no-smi', {'deliver': False}),
        ('revision-without-relocation', {'revision': 1}),
        ('copy-verification', {'fault': 'copy'}),
        ('closed-view-readback', {'fault': 'close-readback'}),
        ('base-readback', {'fault': 'base-readback'}),
        ('missing-extension', {'decoded': False}),
    ):
        b = Board(**options)
        assert b.startup() != 1
        if name in ('no-smi', 'revision-without-relocation'):
            assert b.u.mem_read(b.ebda + ERROR, 1)[0] == (4 if name == 'no-smi' else 2)
        assert not b.conf[HB][0x60] & 1
        assert not b.conf[SB][0xA3] & 0xC0
        rows.append(name)
    b = Board()
    assert b.startup() == 1
    b.conf[HB][0x50] = 0xC5
    b.conf[SB][0xA0], b.conf[SB][0xA8] = 0x80, 0x91
    b.cf8 = 0x81234560
    b.nmi = 0x0D
    b.dirty[0x22000] = b'dirty ordinary data'
    original = b.call('board_smm_command', cached=True)
    assert bytes(b.u.mem_read(0x22000, 19)) == b'dirty ordinary data'
    assert not b.dirty and b.conf[HB][0x50] == 0xC5 and b.cf8 == 0x81234560
    assert b.nmi == 0x0D
    assert (b.conf[SB][0xA0], b.conf[SB][0xA8]) == (0x80, 0x91)
    for name, value in original.items():
        wanted = (value & 0xFFFF0000) if name == 'EAX' else value + 2 if name == 'ESP' else value & ~1 if name == 'EFLAGS' else value
        assert b.u.reg_read(REGS[name]) == wanted, ('runtime caller', name, hex(b.u.reg_read(REGS[name])), hex(wanted))
    rows.append('runtime-dirty-cache-context-cf8-nmi')
    b.deliver = False
    b.dirty[0x22000] = b'timeout still drains'
    original = b.call('board_smm_command', cached=True)
    assert b.u.reg_read(x.UC_X86_REG_AX) == 4 and b.u.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert b.cf8 == 0x81234560 and b.conf[HB][0x50] == 0xC5 and b.nmi == 0x0D
    assert b.u.reg_read(x.UC_X86_REG_CR0) == original['CR0'] and not b.guard and not b.dirty
    assert b.conf[SB][0xA3] & 0xC0 == 0x80
    assert (b.conf[SB][0xA0], b.conf[SB][0xA8]) == (0x80, 0x91)
    rows.append('runtime-timeout-restores-cache-cf8-nmi')
    for name, options, expected in (
        ('missing-entry-trace', {'deliver': False}, (0, 0)),
        ('entered-source-declined-trace', {'fault': 'source-cleared-on-entry'}, (6, 0)),
        ('warm-entered-source-declined-trace', {'fault': 'source-cleared-on-entry', 'warm': True}, (0, 6)),
    ):
        b = Board(**options)
        assert b.startup() == 3
        assert b.u.mem_read(b.ebda + ERROR, 1)[0] == 4
        assert bytes(b.u.mem_read(b.ebda + BOOT_TRACE, 2)) == bytes(expected)
        assert b.u.mem_read(b.ebda + TRACE_VALID, 1)[0] == 0xA5
        assert not b.conf[HB][0x60] & 1 and b.conf[SB][0xA0] == 0
        assert not b.conf[SB][0xA3] & 0xC0
        assert [event[1] for event in b.events if event[0] == 'trace-read'] == [0x38000 + b.trace_offset, 0xA8000 + b.trace_offset]
        assert b.status_report() == 'S34' + ''.join(f'{value:X}' for value in expected)
        rows.append(name)
    for shadow_e in (False, True):
        b = Board()
        assert b.startup() == 1
        b.conf[HB][0x54] = int(shadow_e)
        b.e_bank()
        b.u.mem_write(b.ebda + 0x103A, struct.pack('<H', 0xC800))
        b.call('board_vga_shadow')
        assert b.e_visible
        assert bytes(b.u.mem_read(0xE0000, 0x10000)) == b.raw[:0x10000]
        b.call('board_smm_command')
        assert b.u.reg_read(x.UC_X86_REG_AX) == 0
        rows.append('actual-vga-shadow-owner-e-' + ('shadow' if shadow_e else 'rom'))
    # The actual read-only query follows the current BDA, preserving a foreign FS.
    b = Board()
    assert b.startup() == 1
    alternate = 0x9C000
    b.u.mem_write(0x40E, struct.pack('<H', alternate >> 4))
    for ready in (0, 1):
        b.u.mem_write(alternate + STATUS, bytes([ready]))
        original = b.context()
        b.u.reg_write(x.UC_X86_REG_FS, 0x3500)
        before = len(b.io)
        b.execute(b.address('board_cpu_sl_query'), 0xFFFF0)
        assert b.u.reg_read(x.UC_X86_REG_DX) == ready
        assert b.u.reg_read(x.UC_X86_REG_AX) == 1
        assert b.u.reg_read(x.UC_X86_REG_FS) == 0x3500 and len(b.io) == before
    rows.append('query-current-bda-read-only-preserve-fs')
    # Preparation uses live CPU/controller qualification even before readiness.
    b = Board()
    b.context()
    b.conf[HB][0x60] |= 1
    b.bank()
    for name, value in (('DS', 0xE000), ('ES', 0xA000), ('ESI', b.listing.symbol('board_smm_image')),
                        ('EDI', 0x8000), ('ECX', len(b.handler))):
        b.u.reg_write(REGS[name], value)
    b.execute(b.address('board_smm_prepare'), 0xFFFF0)
    assert b.u.reg_read(x.UC_X86_REG_AX) == 0
    assert bytes(b.u.mem_read(0xA8000, len(b.handler))) == b.handler
    assert b.u.mem_read(b.ebda + STATUS, 1)[0] == 0
    rows.append('prepare-live-qualification-with-readiness-zero')
    # Normal CPU and DMA each see VGA while the final handler stays hidden.
    b = Board()
    assert b.startup() == 1
    hidden = b.hidden
    b.u.mem_write(0x12000, bytes.fromhex('b800a08ed8c60600805a'))
    b.context()
    b.u.reg_write(x.UC_X86_REG_CS, 0x1200)
    b.execute(0x12000, 0x1200A)
    assert b.u.mem_read(0xA8000, 1)[0] == 0x5A and b.hidden == hidden
    # An independent bus master accesses normal VGA, never the SMM bank.
    b.dma_write(0xA8000, b'\xC3\xC3')
    assert b.hidden == hidden
    assert b.u.mem_read(b.ebda + STATUS, 1)[0] == 1
    b.dma_during_smm = True
    b.call('board_smm_command')
    assert b.u.reg_read(x.UC_X86_REG_AX) == 0 and b.hidden[:0xFE00] == hidden[:0xFE00]
    rows.append('closed-cpu-and-dma-view-later-real-command')
    b = Board()
    assert b.startup() == 1
    b.context(cached=True)
    b.u.reg_write(x.UC_X86_REG_CR0, 0x11)
    before = len(b.io)
    b.execute(b.address('board_smm_command'), 0xFFFF0)
    assert b.u.reg_read(x.UC_X86_REG_AX) == 1 and b.u.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert len(b.io) == before and not b.guard
    rows.append('protected-mode-command-declines-before-hardware')
    for name, args, expected in (
        ('software-source', {}, 0),
        ('same-cookie-wrong-source', {'software': False}, None),
        ('stale-reply-cookie', {'cookie': REPLY}, None),
        ('unknown-command', {'command': 7}, 1),
        ('wrong-relocation-target', {'command': 1, 'target': 0xB0000}, 3),
    ):
        b = Board()
        assert b.startup() == 1
        b.direct_smi(**args)
        if expected is None:
            assert b.u.reg_read(x.UC_X86_REG_EBX) == args.get('cookie', REQUEST)
            assert b.u.reg_read(x.UC_X86_REG_EAX) == 0x12340000
            assert b.u.reg_read(x.UC_X86_REG_EFLAGS) == 0x447
        else:
            assert b.u.reg_read(x.UC_X86_REG_EBX) == REPLY
            assert b.u.reg_read(x.UC_X86_REG_EAX) == expected
            assert b.u.reg_read(x.UC_X86_REG_ECX) == b.revision
            assert bool(b.u.reg_read(x.UC_X86_REG_EFLAGS) & 1) == bool(expected)
        rows.append(name)
    for name in ('warm_reset', 'controlled_defaults_restart'):
        for decoded in (False, True):
            for protected in (False, True):
                if protected and name == 'controlled_defaults_restart':
                    continue
                b = Board(decoded=decoded)
                b.conf[SB][0xA0], b.conf[SB][0xA3] = 0x34, 0xC0
                b.context()
                if protected:
                    b.u.reg_write(x.UC_X86_REG_CR0, 0x60000011)
                b.execute(b.address(name))
                assert b.reset and 'board_smm_quiesce' in b.visits
                rows.append(name + ('-protected' if protected else '-real') + ('-e-decoded' if decoded else '-e-disabled'))
                b.sm_base = 0x30000 if not decoded else 0xA0000
                assert b.early_startup() == 1
                rows.append(name + ('-protected' if protected else '-real') + ('-cold-reinstall' if not decoded else '-warm-reinstall'))
    result = {'result': 'pass', 'cases': len(rows), 'checks': rows,
              'rom_sha256': hashlib.sha256(b.raw).hexdigest(),
              'source_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (Path(__file__).resolve(), PORT / 'src/hardware/smm.inc',
                                             PORT / 'src/hardware/board-core.inc',
                                             PORT / 'src/hardware/startup-core.inc', PORT / 'src/hardware/pci.inc',
                                             PORT / 'src/hardware/chipset.inc', ROOT / 'shared/src/pc/smm.inc')},
              'limit': 'Independent modeled PCI/SMRAM, save/RSM and cache seams; no physical cache, DMA exclusion or electrical reset qualification.'}
    (OUTPUT / 'proof.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
