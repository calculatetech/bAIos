"""Execute the production RAM probe with controlled bank decoding and aliases.

86Box D824 does not map RAMCFG nibbles to physical banks. This small fixture
tests the actual ROM instructions, not a second implementation of the probe.
Only the memory decoder and I/O registers are modeled; live slots still need
physical confirmation. Run build.ps1 first.
"""
from pathlib import Path
import re
import os
from itertools import product

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE
from unicorn import UC_HOOK_INSN, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_INTR
from unicorn import x86_const as x


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / os.environ.get('BAIOS_BUILD_DIRECTORY', 'build')
MIB = 1024 * 1024
SIZES = (0, 0, 1, 2, 4, 8, 16, 32)


def interleave_options(config):
    codes = [(config[b // 2] >> (4 * (b % 2))) & 7 for b in range(4)]
    mask = sum(1 << i for i, (a, b) in enumerate(((0, 1), (0, 3), (1, 2), (2, 3)))
               if codes[a] >= 4 and codes[a] == codes[b])
    if mask & 9 == 9:
        mask |= 16
    if mask & 6 == 6:
        mask |= 32
    mask &= ~((1 << 2) | (1 << 5))  # Presario physical failures: modes 3 and 6.
    mode = next((m for m in (5, 6, 1, 2, 3, 4) if mask & (1 << (m - 1))), 0)
    return mode, mask


def symbol(name):
    lines = (BUILD / 'baios-presario800-system.lst').read_text().splitlines()
    start = next(i for i, line in enumerate(lines) if line.rstrip().endswith(name + ':'))
    for line in lines[start + 1:]:
        match = re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]', line)
        if match:
            return int(match[1], 16)
    raise AssertionError(name)


class Banks:
    def __init__(self, sizes, aliases=None, flat=False):
        self.sizes = sizes
        self.aliases = aliases or (0, 1, 2, 3)
        self.flat = flat
        self.config = [0x8C, 0x88]
        self.index = 0
        self.enabled = False
        self.a20 = 0
        self.cells = {}
        self.probe_writes = 0
        self.posts = []
        self.dma_cleared = set()
        self.cmos = bytearray(128)
        self.cmos_index = 0
        self.reset_entry = False
        self.system_flag = 0
        self.shadow = 0
        self.miscset = 0x48
        self.ramset = 0x16
        self.ramtmg = 0x96
        self.ramset_writes = []
        self.external_cache = 0
        self.synthetic_interleave = False
        self.stripe = 16
        self.after_activation = False
        self.stack_rebuilt = False
        self.parity_control = 0
        self.early_registers = {5: 0x10, 6: 4, 0x24: 0}
        self.firmware_ram = (symbol('chipset_ram_test'), symbol('chipset_apply'))

    def physical(self, address):
        if self.flat:
            return (0, address) if address < self.sizes[0] * MIB else None
        # Deliberately synthetic: the datasheet does not specify the full
        # address permutation. This exposes lifetime errors, not timing or
        # electrical behavior. No firmware policy depends on the stripe size.
        mode = self.ramset >> 5 if self.synthetic_interleave else 0
        pairs = {0: (), 1: ((0, 1),), 2: ((0, 3),), 3: ((1, 2),),
                 4: ((2, 3),), 5: ((0, 1), (2, 3)), 6: ((0, 3), (1, 2))}[mode]
        paired = {b: pair for pair in pairs for b in pair}
        base = 0
        for bank in range(4):
            code = (self.config[bank // 2] >> ((bank & 1) * 4)) & 7
            span = SIZES[code] * MIB
            if bank in paired:
                pair = paired[bank]
                if bank != pair[0]:
                    continue
                if base <= address < base + 2 * span:
                    relative = address - base
                    owner = pair[(relative // self.stripe) % 2]
                    offset = (relative // (2 * self.stripe)) * self.stripe + relative % self.stripe
                    return owner, offset
                base += 2 * span
                continue
            if base <= address < base + span:
                alias = self.aliases[bank]
                owner, offset = alias if isinstance(alias, tuple) else (alias, 0)
                offset *= MIB
                actual = self.sizes[owner] * MIB - offset
                return (owner, offset + (address - base) % actual) if actual else None
            base += span
        return None

    def read(self, address, size):
        return bytes(self.cells.get(self.physical(address + i), 0xFF) for i in range(size))

    def write(self, address, data):
        for i, value in enumerate(data):
            key = self.physical(address + i)
            if key is not None:
                self.cells[key] = value

    def memory(self, cpu, access, address, size, value, unused):
        if access == 17 and cpu.reg_read(x.UC_X86_REG_CR0) & 1:
            # The destructive probe has no legitimate stack/workspace writes.
            firmware_test = self.firmware_ram[0] <= cpu.reg_read(x.UC_X86_REG_IP) < self.firmware_ram[1]
            visible_test = (getattr(self, 'visible_progress', (0, 0))[0] <= cpu.reg_read(x.UC_X86_REG_IP) <
                            getattr(self, 'visible_progress', (0, 0))[1])
            assert (0x10000 <= address and address + size <= 0x9FC00 or
                    MIB <= address and address + size <= 32 * MIB or
                    firmware_test and (address + size <= 0x10000 or
                                       0x9FC00 <= address and address + size <= 0xA0000) or
                    visible_test and (0x800 <= address and address+size <= 0xC00 or
                                      0x6000 <= address and address+size <= 0x7000 or
                                      0xB8000 <= address and address+size <= 0xBA000)), (
                        'protected probe wrote reserved memory', hex(address))
        if 0xA0000 <= address < MIB:  # ROM/GDT, not banked RAM.
            return
        if 0x6000 <= address < 0x7000 or 0x9FC00 <= address < 0xA0000:
            assert self.ramset >> 5 or self.physical(address)[0] == 0, 'stack/EBDA accessed with bank 0 remapped'
        if self.after_activation and not self.stack_rebuilt and access == 16 and address < MIB:
            raise AssertionError(('old RAM read after interleave activation', hex(address)))
        if self.after_activation and access == 17 and 0x6000 <= address < 0x7000:
            self.stack_rebuilt = True
        if access == 16:  # UC_MEM_READ
            cpu.mem_write(address, self.read(address, size))
        else:
            self.write(address, value.to_bytes(size, 'little'))
            if address >= 0x10000 and not 0x9FC00 <= address < 0xA0000:
                self.probe_writes += 1

    def port_in(self, cpu, port, size, unused):
        if port == 0x61:
            return self.parity_control
        if self.reset_entry and port in (0x64, 0x3BA, 0x3DA):
            return self.system_flag if port == 0x64 else 0
        if port == 0x71:
            return self.cmos[self.cmos_index]
        if port == 0x84:
            return 0
        if port == 0xED:
            if self.reset_entry and self.index in self.early_registers:
                assert self.enabled
                return self.early_registers[self.index]
            if self.index == 0x19:
                assert self.enabled
                return self.external_cache
            if self.index == 4:
                assert self.enabled
                return self.ramset
            if self.reset_entry and self.index == 7:
                assert self.enabled
                return self.miscset
            assert self.enabled and self.index in (2, 3)
            return self.config[self.index - 2]
        assert port == 0x92, hex(port)
        return self.a20

    def port_out(self, cpu, port, size, value, unused):
        assert size == 1
        if port == 0xFB:
            self.enabled = True
        elif port == 0xF9:
            self.enabled = False
        elif port == 0xEC:
            assert self.enabled
            self.index = value
        elif port == 0xED:
            assert self.enabled
            if self.index == 0x19:
                self.external_cache = value
                return
            if self.index == 4:
                assert not value & 8  # P24T is read-only, not a policy bit.
                assert value >> 5 not in (3, 6, 7), 'unsupported interleave mode written'
                assert self.dma_cleared == {0x0D, 0xDA}, 'interleave write before DMA mask'
                if value >> 5:
                    assert cpu.reg_read(x.UC_X86_REG_SP) == 0x7000, 'outstanding old-map frame'
                    assert self.shadow == 0 and self.dma_cleared == {0x0D, 0xDA}
                    assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
                    assert cpu.reg_read(x.UC_X86_REG_CR0) & 0x60000000 == 0x60000000
                    self.after_activation = True
                self.ramset = value
                self.ramset_writes.append(value)
                return
            if self.reset_entry and self.index not in (2, 3):
                if self.index == 0x12:
                    self.shadow = value
                elif self.index == 7:
                    self.miscset = value
                elif self.index == 1:
                    self.ramtmg = value
                elif self.index in self.early_registers:
                    self.early_registers[self.index] = value
                return
            assert self.index in (2, 3)
            assert self.external_cache == 0, 'bank geometry changed with L2 enabled'
            assert self.ramset == 0x16, 'bank geometry changed with interleave enabled'
            # VL82C481 segment access10 reads DRAM. Remapping with the
            # previous boot's F000 shadow active loses the instruction source.
            assert self.shadow == 0, 'bank remap while executing retained RAM shadow'
            assert self.dma_cleared == {0x0D, 0xDA}, 'bank remap before DMA mask'
            self.config[self.index - 2] = value
        elif port in (0x0D, 0xDA):
            assert value == 0
            self.dma_cleared.add(port)
        elif port == 0x92:
            self.a20 = value
        elif port == 0x61:
            self.parity_control = value
        elif port == 0x80:
            self.posts.append(value)
        elif port == 0x70:
            self.cmos_index = value & 0x7F
        elif port == 0x71:
            self.cmos[self.cmos_index] = value
        elif self.reset_entry and port in (0x20, 0x3B8, 0x3D8, 0x3C0, 0xF5):
            pass
        else:
            raise AssertionError((port, value))


def run(sizes, expected, aliases=None, flat=False, limit_rejections=0):
    model = Banks(sizes, aliases, flat)
    cpu = Uc(UC_ARCH_X86, UC_MODE_16)
    cpu.mem_map(0, 32 * MIB)
    cpu.mem_write(0xF0000, (BUILD / 'baios-presario800-system.rom').read_bytes())
    cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, model.memory)
    cpu.hook_add(UC_HOOK_INSN, model.port_in, None, 1, 0, x.UC_X86_INS_IN)
    cpu.hook_add(UC_HOOK_INSN, model.port_out, None, 1, 0, x.UC_X86_INS_OUT)
    finished = []
    cpu.hook_add(UC_HOOK_CODE, lambda uc, addr, size, _: (
        finished.append(True), uc.emu_stop()) if addr == 0xFEE00 else None)
    text = []

    def interrupt(uc, number, unused):
        assert number == 0x10
        assert uc.reg_read(x.UC_X86_REG_AH) == 0x0E
        text.append(chr(uc.reg_read(x.UC_X86_REG_AL)))

    cpu.hook_add(UC_HOOK_INTR, interrupt)
    gdtr = (0, 0x123450, 0x37, 0)
    preserved = {'EAX': 0x12345678, 'EBX': 0x23456789, 'ECX': 0x34567890,
                 'EDX': 0x45678901, 'EDI': 0x56789012, 'EBP': 0x67890123}
    for warm in (False, True):
        before_writes = model.probe_writes
        before_posts = len(model.posts)
        before_config = model.config[:]
        for name, value in preserved.items():
            cpu.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
        for name, value in {'CS': 0xF000, 'DS': 0, 'ES': 0, 'SS': 0,
                            'ESP': 0x6FFE, 'ESI': int(warm), 'EFLAGS': 2,
                            'CR0': 0x60000010}.items():
            cpu.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
        cpu.reg_write(x.UC_X86_REG_GDTR, gdtr)
        model.write(0x6FFE, b'\x00\xee')
        model.write(0x9FCD0, b'\xCC\xCC')
        finished.clear()
        cpu.emu_start(0xF0000 + symbol('init_memory'), 0xFFFFFF, count=30000)
        assert finished, 'probe did not return'
        assert model.config == list(expected), (sizes, model.config, expected)
        assert model.posts.count(0x2E) == limit_rejections
        total = sum(SIZES[(expected[i // 2] >> (i % 2 * 4)) & 7] for i in range(4))
        assert int.from_bytes(model.read(0x9FCD0, 2), 'little') == total * 1024 - 1024
        assert cpu.reg_read(x.UC_X86_REG_ESP) == 0x7000
        assert cpu.reg_read(x.UC_X86_REG_CR0) == 0x60000010
        assert cpu.reg_read(x.UC_X86_REG_GDTR) == gdtr
        assert cpu.reg_read(x.UC_X86_REG_ESI) == int(warm)
        assert cpu.reg_read(x.UC_X86_REG_DS) == cpu.reg_read(x.UC_X86_REG_ES) == 0
        assert model.a20 == 0 and not model.enabled
        for name, value in preserved.items():
            assert cpu.reg_read(getattr(x, 'UC_X86_REG_' + name)) == value, name
        if warm:
            assert model.probe_writes == before_writes, 'warm reset wrote probe patterns'
            assert model.config == before_config
            wanted_posts = [0x24]
        else:
            wanted_posts = [0x21, 0x23 if expected[0] & 1 else 0x22]
            accepted = SIZES[expected[0] & 7]
            for bank in range(1, 4):
                capacity = SIZES[(expected[bank // 2] >> (bank % 2 * 4)) & 7]
                start = 0x25 + (bank - 1) * 3
                outcome = start + 1 if capacity else start + 2
                if not capacity and accepted + sizes[bank] > 64:
                    outcome = 0x2E
                wanted_posts += [start, outcome]
                accepted += capacity
        assert model.posts[before_posts:] == wanted_posts, (model.posts, wanted_posts)
        # Exercise the actual CMOS publisher at the same total, including
        # exactly 64 MiB / 64512 KiB extended, rather than just its EBDA input.
        model.write(0x6FFE, b'\x00\xee')
        cpu.reg_write(x.UC_X86_REG_ESP, 0x6FFE)
        finished.clear()
        cpu.emu_start(0xF0000 + symbol('publish_memory_cmos'), 0xFFFFFF, count=3000)
        assert finished
        assert int.from_bytes(model.cmos[0x15:0x17], 'little') == 640
        for index in (0x17, 0x30):
            assert int.from_bytes(model.cmos[index:index + 2], 'little') == (total - 1) * 1024
        assert int.from_bytes(model.cmos[0x2E:0x30], 'big') == sum(model.cmos[0x10:0x2E])
        # Carry the detected count into the real interrupt service, not a stub.
        model.write(0x40E, b'\xC0\x9F')
        model.write(0x6FFA, b'\x00\xee\x00\xf0\x03\x00')  # IRET IP, CS, FLAGS
        cpu.reg_write(x.UC_X86_REG_ESP, 0x6FFA)
        cpu.reg_write(x.UC_X86_REG_EAX, 0x12348800)
        cpu.reg_write(x.UC_X86_REG_FS, 0x1234)
        finished.clear()
        cpu.emu_start(0xF0000 + symbol('int15'), 0xFFFFFF, count=100)
        assert finished and cpu.reg_read(x.UC_X86_REG_ESP) == 0x7000
        assert cpu.reg_read(x.UC_X86_REG_EAX) == 0x12340000 + (total - 1) * 1024
        assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
        assert cpu.reg_read(x.UC_X86_REG_FS) == 0x1234
    # Exercise the real report, including decimal totals >= 10 and every bank.
    mode, mask = interleave_options(expected)
    model.write(0x6FFE, b'\x00\xee')
    cpu.reg_write(x.UC_X86_REG_ESP, 0x6FFE)
    finished.clear()
    cpu.emu_start(0xF0000 + symbol('memory_interleave_options'), 0xFFFFFF, count=1000)
    assert finished and cpu.reg_read(x.UC_X86_REG_AX) == mode + (mask << 8)
    model.write(0x40E, b'\xC0\x9F')
    model.write(0x6FFE, b'\x00\xee')
    cpu.reg_write(x.UC_X86_REG_DS, 0xF000)
    cpu.reg_write(x.UC_X86_REG_ESP, 0x6FFE)
    finished.clear()
    cpu.emu_start(0xF0000 + symbol('report_memory'), 0xFFFFFF, count=10000)
    assert finished
    banks = '/'.join(str(SIZES[(expected[i // 2] >> (i % 2 * 4)) & 7]) for i in range(4))
    wanted = (f'RAM CFG={expected[0]:02X}/{expected[1]:02X} banks MiB={banks} total={total} MiB'
              f' INTLV avail={mask:02X} mode=0 RAMSET=16\r\n')
    assert ''.join(text) == wanted, (''.join(text), wanted)


def reset_shadow_checks():
    # Execute reset-vector entry through the complete cold probe. Only port
    # devices are modeled; resume branches must preserve the retained shadow.
    for shadow, system_flag, shutdown in product((0, 0xAA), (0, 4), (0, 5, 10)):
        model = Banks([8, 0, 0, 0])
        model.reset_entry = True
        model.shadow = shadow
        model.system_flag = system_flag
        model.early_registers.update({0x21: 1, 0x23: 2})
        model.cmos[0x0F] = shutdown
        model.config = [0x8D, 0x88]
        model.write(0x472, b'\x34\x12')
        model.write(0x467, b'\x00\x00\x00\x90')
        cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        cpu.mem_map(0, 32 * MIB)
        cpu.mem_write(0xF0000, (BUILD / 'baios-presario800-system.rom').read_bytes())
        cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
        cpu.reg_write(x.UC_X86_REG_CR0, 0x60000010)
        cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, model.memory)
        cpu.hook_add(UC_HOOK_INSN, model.port_in, None, 1, 0, x.UC_X86_INS_IN)
        cpu.hook_add(UC_HOOK_INSN, model.port_out, None, 1, 0, x.UC_X86_INS_OUT)
        resume = bool(system_flag and shutdown in (5, 10))
        terminal = 0x90000 if resume else 0xF0000 + symbol('shadow_system_bios')
        finished = []
        probe_entry = 0xF0000 + symbol('init_memory')
        probe_seen = []

        def observe_reset(uc, addr, size, unused):
            if addr == probe_entry:
                assert not resume and model.miscset == 0x40
                assert model.early_registers[0x21] == model.early_registers[0x23] == 0, 'retained ISA windows intercept RAM probe'
                probe_seen.append(True)
            if addr == terminal:
                finished.append(True)
                uc.emu_stop()

        cpu.hook_add(UC_HOOK_CODE, observe_reset)
        cpu.emu_start(0xFFFF0, 0xFFFFFF, count=1000000)
        assert finished, (shadow, system_flag, shutdown, 'reset did not reach terminal')
        assert len(probe_seen) == (0 if resume else 1)
        assert model.cmos[0x0F] == 0
        assert model.config == [0x8D, 0x88]
        if resume:
            assert model.shadow == shadow and model.probe_writes == 0
            assert (model.early_registers[0x21], model.early_registers[0x23]) == (1, 2)
            assert model.miscset == 0x48
        else:
            assert model.shadow == 0 and model.probe_writes > 0
            assert model.miscset == 0x40
            assert int.from_bytes(model.read(0x9FCD0, 2), 'little') == 7168


def warm_cache_checks():
    # Physical FD/8E population: preserve all 56 MiB and normalize inherited
    # CEN before reaching the actual shadow-copy owner. No cold probe here.
    for miscset in (0x40, 0x48):
        model = Banks([8, 32, 16, 0])
        model.reset_entry = True
        model.config = [0xFD, 0x8E]
        model.miscset = miscset
        model.system_flag = 4
        model.write(0x472, b'\x34\x12')
        model.write(0x40E, b'\xC0\x9F')
        model.write(0x9FCD4, b'\x32\x15')
        model.write(0x20000, b'KEEP')
        cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        cpu.mem_map(0, MIB)
        cpu.mem_write(0xF0000, (BUILD / 'baios-presario800-system.rom').read_bytes())
        cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
        cpu.reg_write(x.UC_X86_REG_CR0, 0x10)
        cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, model.memory)
        cpu.hook_add(UC_HOOK_INSN, model.port_in, None, 1, 0, x.UC_X86_INS_IN)
        cpu.hook_add(UC_HOOK_INSN, model.port_out, None, 1, 0, x.UC_X86_INS_OUT)
        terminal = 0xF0000 + symbol('shadow_system_bios')
        finished = []
        cpu.hook_add(UC_HOOK_CODE, lambda uc, addr, size, _: (
            finished.append(True), uc.emu_stop()) if addr == terminal else None)
        cpu.emu_start(0xF0000 + symbol('.warm_start'), 0xFFFFFF, count=1000000)
        assert finished and model.miscset == 0x40
        assert cpu.reg_read(x.UC_X86_REG_CR0) & 0x60000000 == 0x60000000
        assert model.config == [0xFD, 0x8E] and model.probe_writes == 0
        assert model.read(0x20000, 4) == b'KEEP'
        assert int.from_bytes(model.read(0x9FCD0, 2), 'little') == 55 * 1024
        assert model.read(0x9FCD4, 2) == b'\x32\x15'


def interleave_transition_checks():
    layouts = ([4, 0, 0, 0], [4, 4, 0, 0], [4, 0, 0, 4],
               [4, 8, 8, 0], [4, 0, 8, 8], [4, 4, 8, 8], [4, 8, 8, 4],
               [4, 4, 4, 4])
    checks = 0
    for stripe, enabled in product((8, 16), (False, True)):
        scenarios = [(sizes, 'cold', 0x1234) for sizes in layouts]
        scenarios += [(layouts[1], 'cold', 0)]  # Same retained map, absent marker.
        scenarios += [(sizes, 'warm', 0x1234) for sizes in layouts]
        scenarios += [(layouts[1], shutdown, 0x1234) for shutdown in (5, 10)]
        for sizes, entry, marker in scenarios:
            model = Banks(sizes)
            model.reset_entry = model.synthetic_interleave = True
            model.external_cache = 0x33
            model.stripe = stripe
            word = sum((8 | (SIZES.index(size) if size else 0)) << (b * 4)
                       for b, size in enumerate(sizes))
            expected = [word & 255, word >> 8]
            model.config = expected[:]
            automatic_mode, mask = interleave_options(expected)
            model.ramset = 0x16 | (automatic_mode << 5)
            policy = bytearray.fromhex('96160000883830000031085555555555aa00000000030001')
            policy[1] |= 0x80 if enabled else 0
            model.cmos[0x69] = 0xC1
            model.cmos[0x6A] = -(0xC1 + sum(policy)) & 255
            model.cmos[0x6B:0x80] = policy[:21]
            model.cmos[0x33:0x36] = policy[21:]
            model.shadow = 0xAA if entry != 'warm' else 0
            model.system_flag = 4
            model.write(0x40E, b'\xC0\x9F')
            model.write(0x9FCD4, b'\x32\x15')
            model.write(0x472, marker.to_bytes(2, 'little'))
            model.write(0x467, b'\x00\x00\x00\x90')
            model.write(0x20000, b'KEEP')
            keep_keys = [model.physical(0x20000+i) for i in range(4)]
            if isinstance(entry, int):
                model.cmos[0x0F] = entry
            cpu = Uc(UC_ARCH_X86, UC_MODE_16)
            cpu.mem_map(0, 32 * MIB)
            cpu.mem_write(0xF0000, (BUILD / 'baios-presario800-system.rom').read_bytes())
            cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
            cpu.reg_write(x.UC_X86_REG_CR0, 0x10)
            cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, model.memory)
            cpu.hook_add(UC_HOOK_INSN, model.port_in, None, 1, 0, x.UC_X86_INS_IN)
            cpu.hook_add(UC_HOOK_INSN, model.port_out, None, 1, 0, x.UC_X86_INS_OUT)
            resume = isinstance(entry, int)
            terminal = 0x90000 if resume else 0xF0000 + symbol('shadow_system_bios')
            finished = []
            selector_entry = 0xF0000 + symbol('memory_interleave_options')
            selector_return = [None]
            selector_values = []

            def observe_transition(uc, addr, size, unused):
                if addr == selector_entry:
                    selector_return[0] = 0xF0000 + int.from_bytes(
                        model.read(uc.reg_read(x.UC_X86_REG_SP), 2), 'little')
                elif addr == selector_return[0]:
                    selector_values.append(uc.reg_read(x.UC_X86_REG_AX))
                    selector_return[0] = None
                if addr in (terminal, 0xFEE00):
                    finished.append(True)
                    uc.emu_stop()

            cpu.hook_add(UC_HOOK_CODE, observe_transition)
            start = 0xF0000 + symbol('.warm_start') if entry == 'warm' else 0xFFFF0
            cpu.emu_start(start, 0xFFFFFF, count=1000000)
            assert finished, (sizes, entry, 'transition did not reach owner')
            assert model.config == expected
            mode = automatic_mode if enabled or resume else 0
            assert model.ramset == 0x16 | (mode << 5) and model.ramtmg == 0x96
            assert selector_values == ([] if resume else [automatic_mode | (mask << 8)])
            if resume:
                assert not model.ramset_writes and not model.probe_writes
                assert model.shadow == 0xAA and model.miscset == 0x48
                assert model.external_cache == 0x33
            else:
                assert model.external_cache == 0
                assert model.miscset == 0x40
                assert cpu.reg_read(x.UC_X86_REG_CR0) & 0x60000000 == 0x60000000
                count = (sum(sizes) - 1) * 1024
                assert int.from_bytes(model.read(0x9FCD0, 2), 'little') == count
                assert model.read(0x9FC3A, 1) == bytes([marker == 0x1234])
                assert model.read(0, 0x500) == bytes(0x500)
                assert model.read(0x20, 0x9E0) == bytes(0x9E0)
                ebda = bytearray(1024)
                ebda[0] = 1
                ebda[0x3A] = marker == 0x1234
                ebda[0xD0:0xD2] = count.to_bytes(2, 'little')
                ebda[0xD4:0xD6] = b'\x32\x15' if entry == 'warm' else b'\0\0'
                ebda[0x78:0x7A] = count.to_bytes(2, 'little')
                assert model.read(0x9FC00, 1024) == bytes(ebda)
                if entry == 'warm':
                    assert model.ramset_writes == [0x16 | (mode << 5)] and not model.probe_writes
                    assert bytes(model.cells[k] for k in keep_keys) == b'KEEP'
                    if mode == automatic_mode:
                        assert model.read(0x20000, 4) == b'KEEP'
                else:
                    assert model.ramset_writes == [0x16, 0x16 | (mode << 5)]
                    assert model.probe_writes and 0x18 + mode in model.posts
                # Compose the new map with the actual report and capacity publisher.
                text = []
                cpu.hook_add(UC_HOOK_INTR, lambda uc, number, _: text.append(
                    chr(uc.reg_read(x.UC_X86_REG_AL))) if number == 0x10 else None)
                model.write(0x40E, b'\xC0\x9F')
                for name in ('report_memory', 'publish_memory_cmos'):
                    model.write(0x6FFE, b'\x00\xee')
                    cpu.reg_write(x.UC_X86_REG_SP, 0x6FFE)
                    cpu.reg_write(x.UC_X86_REG_DS, 0xF000)
                    finished.clear()
                    cpu.emu_start(0xF0000 + symbol(name), 0xFFFFFF, count=10000)
                    assert finished
                bank_text = '/'.join(map(str, sizes))
                assert ''.join(text) == (f'RAM CFG={expected[0]:02X}/{expected[1]:02X}'
                    f' banks MiB={bank_text} total={sum(sizes)} MiB INTLV avail={mask:02X}'
                    f' mode={mode} RAMSET={model.ramset:02X}\r\n')
                assert int.from_bytes(model.cmos[0x17:0x19], 'little') == count
                assert int.from_bytes(model.cmos[0x30:0x32], 'little') == count
                # Query the real service against the count produced under the
                # final map, not a replacement EBDA or reconstructed value.
                model.write(0x6FFA, b'\x00\xee\x00\xf0\x03\x00')
                cpu.reg_write(x.UC_X86_REG_SP, 0x6FFA)
                cpu.reg_write(x.UC_X86_REG_EAX, 0x12348800)
                cpu.reg_write(x.UC_X86_REG_FS, 0x1234)
                finished.clear()
                cpu.emu_start(0xF0000 + symbol('int15'), 0xFFFFFF, count=100)
                assert finished and cpu.reg_read(x.UC_X86_REG_SP) == 0x7000
                assert cpu.reg_read(x.UC_X86_REG_EAX) == 0x12340000 + count
                assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
                assert cpu.reg_read(x.UC_X86_REG_FS) == 0x1234
            checks += 1
    return checks


def recovery_transition_checks():
    import importlib
    chipset = importlib.import_module('test-chipset')
    checks = 0
    for stripe, owner in product((8, 16), ('early', 'visible', 'final')):
        m, _ = chipset.recovery_model()
        bank = Banks([4, 4, 0, 0])
        bank.config = [0xCC, 0x88]
        bank.synthetic_interleave = bank.reset_entry = True
        bank.ramset, bank.stripe = 0x36, stripe
        bank.dma_cleared = {0x0D, 0xDA}
        # Full visible passes use native byte buffers; the existing physical
        # decoder and lifetime/bounds checks still own every emulated access.
        storage = [bytearray(b'\xff') * (4*MIB) for _ in range(2)]
        def read(address, size):
            key = bank.physical(address)
            if key is not None and address % stripe + size <= stripe:
                return bytes(storage[key[0]][key[1]:key[1]+size])
            keys = [bank.physical(address+i) for i in range(size)]
            return bytes(storage[k[0]][k[1]] if k is not None else 255 for k in keys)
        def write(address, data):
            key = bank.physical(address)
            if key is not None and address % stripe + len(data) <= stripe:
                storage[key[0]][key[1]:key[1]+len(data)] = data
            else:
                for i, value in enumerate(data):
                    key = bank.physical(address+i)
                    if key is not None: storage[key[0]][key[1]] = value
        bank.read, bank.write = read, write
        bank.write(0, bytes(m.cpu.mem_read(0, 0x10000)))
        bank.write(0x9FC00, bytes(m.cpu.mem_read(0x9FC00, 1024)))
        bank.write(0x472, b'\x34\x12')
        original_out = m.port_out
        boundary, rebuilt, faults, restarts = [False], [False], [], []
        def output(cpu, port, size, value, unused):
            original_out(cpu, port, size, value, unused)
            bank.enabled = port == 0xFB or bank.enabled and port != 0xF9
            bank.index = m.chipset_index
            if port == 0xED:
                index = m.chipset_index
                if index == 4:
                    if bank.ramset >> 5 and not value >> 5:
                        assert faults, 'controlled teardown must follow the injected comparison failure'
                        assert cpu.reg_read(x.UC_X86_REG_CR0) & 0x60000000 == 0x60000000
                        assert m.chipset[0x19] == 0 and not m.chipset[7] & 8
                        assert all(m.chipset.get(r, 0) == 0 for r in range(0xF, 0x13))
                        # Initial map teardown precedes the selected-profile owner.
                        assert m.chipset[0xC] == 0x18 and m.chipset[1] == 0xBF
                        assert m.chipset[5] & ~0x10 == 0 and m.chipset[6] == 0
                        assert m.chipset[0x24] & 0x4C == 8
                        assert m.dma_masks[-2:] == [0x0D, 0xDA]
                        boundary[0] = bank.after_activation = True
                        bank.stack_rebuilt = False
                    bank.ramset = value
                elif index in (2, 3):
                    raise AssertionError('controlled restart changed retained geometry')
                elif index == 1: bank.ramtmg = value
                elif index == 0x12: bank.shadow = value
                elif index == 0x19: bank.external_cache = value
        # Replace the I/O hook with its existing owner plus decoder observations.
        m.port_out = output
        # Existing bound hook calls the original method; remove/reinstall via new CPU.
        initial = bytes(m.cpu.mem_read(0, 8*MIB))
        m.cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        m.cpu.mem_map(0, 8*MIB)
        m.cpu.mem_write(0, initial)
        def interrupt(cpu, vector, unused):
            m.interrupt(cpu, vector, unused)
            bank.write(0x400, bytes(cpu.mem_read(0x400, 0x100)))
        m.cpu.hook_add(UC_HOOK_INTR, interrupt)
        m.cpu.hook_add(UC_HOOK_CODE,
            lambda *args: bank.write(0x42, b'\x00\xc0'), None, 0xC0003, 0xC0003)
        m.cpu.hook_add(UC_HOOK_INSN, m.port_in, None, 1, 0, x.UC_X86_INS_IN)
        m.cpu.hook_add(UC_HOOK_INSN, output, None, 1, 0, x.UC_X86_INS_OUT)
        m.code_hook = m.cpu.hook_add(UC_HOOK_CODE, m.code)
        runtime = symbol('chipset_runtime_ram_check')
        early = symbol('chipset_ram_test')
        visible = symbol('chipset_visible_ram_test')
        bank.visible_progress = (visible, runtime)
        apply, nmi = symbol('chipset_apply'), symbol('chipset_nmi')
        def memory(cpu, access, address, size, value, unused):
            # Model an absent direct SRAM, keeping the actual probe mechanics.
            if m.chipset.get(0x19, 0) & 7 == 7 and not 0xA0000 <= address < MIB:
                if access == 16: cpu.mem_write(address, bytes(size))
                return
            if access == 16 and address == 0x472 and boundary[0] and not rebuilt[0]:
                raise AssertionError('old warm marker read after controlled map change')
            bank.memory(cpu, access, address, size, value, unused)
            if access != 16 or faults:
                return
            point = {'early': 0x9FFFC, 'visible': 0x1FFFFC, 'final': 0x10000}[owner]
            if address != point:
                return
            ip = cpu.reg_read(x.UC_X86_REG_IP)
            opcode = bytes(cpu.mem_read(0xF0000+ip, 4))
            in_owner = (early <= ip < apply if owner == 'early' else
                        visible <= ip < runtime if owner == 'visible' else
                        runtime <= ip < nmi)
            if owner == 'visible':
                compare = opcode[-1:] == b'\xaf' and cpu.reg_read(x.UC_X86_REG_EAX) in (0x55AA55AA, 0xAA55AA55, 0)
            elif owner == 'early':
                compare = opcode[:3] in (b'\x67\x66\x39', b'\x67\x66\x3b')
            else:
                compare = opcode == b'\x67\x66\x8b\x07'
            if address == point and in_owner and compare:
                faults.append(address)
                cpu.mem_write(address, bytes(4))
        m.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, memory)
        for name, callback in (
                ('.controlled_restart', lambda *args: restarts.append(True)),
                ('shadow_system_bios', lambda *args: rebuilt.__setitem__(0, True))):
            address = 0xF0000+symbol(name)
            m.cpu.hook_add(UC_HOOK_CODE, callback, None, address, address)
        m.cpu.reg_write(x.UC_X86_REG_DX, 7168)
        m.startup(entry={'early': 'chipset_ram_test', 'visible': 'chipset_visible_ram_test',
                         'final': 'chipset_late_cache'}[owner], through_visible=True)
        assert len(faults) == len(restarts) == m.restarts == 1
        assert boundary[0] and rebuilt[0] and bank.ramset == 0x16
        assert bank.config == [0xCC, 0x88]
        assert bank.read(0x9FC3A, 1) == b'\0'
        assert bank.read(0x9FCD0, 2) == bank.read(0x9FC78, 2) == (7168).to_bytes(2, 'little')
        assert bytes(m.cmos[0x17:0x19]) == bytes(m.cmos[0x30:0x32]) == (7168).to_bytes(2, 'little')
        assert m.text(5, 3, 8) == 'RAM Test'
        assert m.text(5, 24, 5) == '8192 ' and m.text(5, 34, 6) == 'Passed'
        checks += 1
        print(f'Actual {owner} recovery / {stripe}-byte bank decoder stripe: PASS', flush=True)
    return checks


def main():
    assert interleave_options([0xDC, 0x8D]) == (0, 0)  # Only failed pair 1/2.
    assert interleave_options([0xDC, 0xCD]) == (2, 2)  # Keep proven pair 0/3.
    assert interleave_options([0xCC, 0xCC]) == (5, 0x1B)  # Both good pairs win.
    reset_shadow_checks()
    warm_cache_checks()
    transitions = interleave_transition_checks()
    recovery = recovery_transition_checks()
    cases = 0
    for onboard in (4, 8):
        for optional in product((0, 4, 8, 16, 32), repeat=3):
            sizes = [onboard, *optional]
            word = 0x888C | int(onboard == 8)
            enabled = onboard
            rejected = 0
            for bank in range(1, 4):
                if sizes[bank] and enabled + sizes[bank] <= 64:
                    word |= SIZES.index(sizes[bank]) << (bank * 4)
                    enabled += sizes[bank]
                elif sizes[bank]:
                    rejected += 1
            run(sizes, (word & 255, word >> 8), limit_rejections=rejected)
            cases += 1
    # A candidate mirroring onboard RAM, or a previously accepted SIMM.
    run([4, 0, 0, 0], (0x8C, 0x88), aliases=(0, 0, 0, 0))
    run([4, 4, 0, 0], (0xCC, 0x88), aliases=(0, 1, 1, 1))
    # A 4 MiB window into an earlier 8 MiB bank's upper side must not count
    # as another bank. Lower-side-only cross-checks cannot detect this.
    run([8, 0, 0, 0], (0x8D, 0x88), aliases=(0, (0, 4), 2, 3))
    run([4, 8, 0, 0], (0xDC, 0x88), aliases=(0, 1, (1, 4), 3))
    run([4, 16, 0, 0], (0xEC, 0x88), aliases=(0, 1, (1, 8), 3))
    run([4, 16, 0, 0], (0xEC, 0x88), aliases=(0, 1, (1, 12), 3))
    run([4, 32, 0, 0], (0xFC, 0x88), aliases=(0, 1, (1, 16), 3))
    run([4, 32, 0, 0], (0xFC, 0x88), aliases=(0, 1, (1, 24), 3))
    run([4, 32, 0, 0], (0xFC, 0x88), aliases=(0, 1, (1, 28), 3))
    # Too-small/aliased devices cannot pass as 4 MiB; still find a later bank.
    run([4, 1, 2, 4], (0x8C, 0xC8))
    for size in (4, 8):
        run([size, 0, 0, 0], (0x8D if size == 8 else 0x8C, 0x88), flat=True)
    print(f'PASS: {recovery} actual recovery entries with physical bank decoding; {transitions} synthetic interleave lifetime checks; 12 reset/shadow and 2 retained-56-MiB cache contrasts; {cases + 12} bank layouts, protected writes, cold/warm state, CMOS/AH88 '
          'and exact POST codes/reports; '
          'mixed 4/8/16/32 MiB, 64 MiB limit, sparse banks, undersized devices, '
          'lower/upper-side cross-bank aliases and flat mapping.')


if __name__ == '__main__':
    main()
