"""Run real OEM-derived L2 initialization with controlled direct SRAM decoding.

86Box does not model VL82C481 L2 data/tags. This check covers presence/failure,
direct-map lifetime, scratch bounds and reset disabling, not electrical timing.
"""
from pathlib import Path
import importlib
import runpy

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

fixture = runpy.run_path(str(Path(__file__).with_name('test-memory-banks.py')))
Banks, symbol, ROOT, MIB, BUILD = (fixture[k] for k in ('Banks', 'symbol', 'ROOT', 'MIB', 'BUILD'))


class Cache(Banks):
    def __init__(self, capacity, broken=False, banks=1):
        super().__init__([4, 0, 0, 0])
        self.reset_entry = True
        self.capacity, self.broken = capacity, broken
        self.banks = banks
        self.sram = bytearray(capacity)
        self.cache_writes = []
        self.direct_reads = 0
        self.regions = {}
        self.fast_commands = 0
        self.ntbref = 0xA1
        self.xctl = 0xD8

    def memory(self, cpu, access, address, size, value, unused):
        if self.external_cache & 7 != 7 or 0xA0000 <= address < MIB:
            return super().memory(cpu, access, address, size, value, unused)
        assert self.ramtmg == 0x96 and not self.xctl & 8
        assert self.miscset & 0xBF == 0x80, 'direct SRAM probe must bypass L1 line fills'
        assert not 0x6000 <= address < 0x7000, 'stack touched in direct SRAM mode'
        assert (0x10000 <= address < 0x10010 or MIB <= address < 2*MIB+4), (hex(address), size, hex(self.external_cache), hex(cpu.reg_read(x.UC_X86_REG_EIP)))
        double=bool(self.external_cache & 0x80)
        missing=double and self.banks==1 and address&4
        # DBLBNK selects alternating dwords. A single card has no bank B.
        physical=(address//8*4+address%4) if double and self.banks==1 else address
        capacity=self.capacity//2 if self.banks==2 and not double else self.capacity
        if access == 16:
            self.direct_reads += 1
            data = bytes(self.sram[(physical + i) % capacity] for i in range(size)) if capacity and not missing else b'\xFF' * size
            if self.broken and address == MIB + 0x200:
                data = bytes([data[0] ^ 1]) + data[1:]
            cpu.mem_write(address, data)
        elif capacity and not missing:
            for i, byte in enumerate(value.to_bytes(size, 'little')):
                self.sram[(physical + i) % capacity] = byte

    def port_in(self, cpu, port, size, unused):
        if port == 0x61:
            return 0
        if port == 0xED and self.index in (1, 0x24):
            assert self.enabled
            return self.ramtmg if self.index == 1 else self.xctl
        if port == 0xED and self.index == 5:
            assert self.enabled
            return self.ntbref
        return super().port_in(cpu, port, size, unused)

    def port_out(self, cpu, port, size, value, unused):
        if port == 0x61:
            return
        if port == 0xED and self.index == 4 and value == self.ramset:
            return  # Warm POST can retain an unchanged map before masking DMA.
        if port == 0xED and self.index == 0x24:
            assert self.enabled
            self.xctl = value
            return
        if port == 0xF5:  # Existing board fast-clock strobe; value is ignored.
            assert self.enabled
            self.fast_commands += 1
            return
        if port == 0xED and self.index == 5:
            assert self.enabled
            self.ntbref = value
            return
        if port == 0xED and self.index == 0x19:
            self.cache_writes.append(value)
        if port == 0xED and 0x13 <= self.index <= 0x18:
            self.regions[self.index] = value
        super().port_out(cpu, port, size, value, unused)


def run(capacity, broken=False, warm=False, caller=False, a20=0, tuned=False, banks=1, requested=True):
    model = Cache(capacity, broken, banks)
    model.a20 = a20
    if tuned:
        model.ramtmg, model.miscset = 0xBF, 0xBF
    saved_timing, saved_xctl, saved_misc = model.ramtmg, model.xctl, model.miscset
    cpu = Uc(UC_ARCH_X86, UC_MODE_16)
    cpu.mem_map(0, 4 * MIB)
    cpu.mem_write(0xF0000, (BUILD / 'baios-presario800-system.rom').read_bytes())
    cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, model.memory)
    cpu.hook_add(UC_HOOK_INSN, model.port_in, None, 1, 0, x.UC_X86_INS_IN)
    cpu.hook_add(UC_HOOK_INSN, model.port_out, None, 1, 0, x.UC_X86_INS_OUT)
    terminal = 0xF0000 + symbol('chipset_memory_prepare') if warm else 0xFEE00
    finished = []
    cpu.hook_add(UC_HOOK_CODE, lambda uc, address, size, _: (
        finished.append(True), uc.emu_stop()) if address == terminal else None)
    registers = {'EAX': 0x12345678, 'EBX': 0x23456789, 'ECX': 0x34567890,
                 'EDX': 0x45678901, 'ESI': 0x56789012, 'EDI': 0x67890123,
                 'EBP': 0x78901234}
    for name, value in {**registers, 'CS': 0xF000, 'SS': 0, 'DS': 0, 'ES': 0,
                        'ESP': 0x6FFE, 'CR0': 0x60000010, 'EFLAGS': 2}.items():
        cpu.reg_write(getattr(x, 'UC_X86_REG_' + name), value)
    gdtr = (0, 0x123450, 0x37, 0)
    cpu.reg_write(x.UC_X86_REG_GDTR, gdtr)
    model.write(0x6FFE, b'\x00\xee')
    model.write(0x500, b'KEEP')
    if warm:
        policy=bytearray.fromhex('bf160000883830000031085555555555aa00000000030001')
        policy[9]=0x31 if requested else 0x30
        model.cmos[0x69],model.cmos[0x6A]=0xC1,-(0xC1+sum(policy))&255
        model.cmos[0x6B:0x80],model.cmos[0x33:0x36]=policy[:21],policy[21:]
        model.external_cache = 0x33
        model.miscset = 0xC8
        model.system_flag = 4
        model.write(0x472, b'\x34\x12')
    entry = '.warm_start' if warm else 'enable_cpu_full_speed' if caller else 'init_external_cache'
    cpu.emu_start(0xF0000 + symbol(entry),
                  0xFFFFFF, count=15000000)
    assert finished, (capacity, broken, warm, 'did not reach terminal')
    if warm:
        assert model.external_cache == 0 and model.cache_writes == [0]
        assert not model.probe_writes and model.miscset == 0xC0
        assert model.cmos[0x69]==0xC1 and model.cmos[0x74]==(0x31 if requested else 0x30)
    else:
        assert model.read(0x500, 4) == b'KEEP'
        success = capacity in (32768,65536,131072,262144,524288,1048576) and not broken
        if not caller:
            flags=cpu.reg_read(x.UC_X86_REG_EFLAGS)
            assert bool(flags & 0x40)==success, 'Probe must preserve its pass result across cleanup'
            assert bool(flags & 1)==(bool(capacity) and not success), 'Distinguish SRAM errors from no response'
        geometry=0xB0 if banks==2 else 0x30
        value=geometry+(capacity.bit_length()-15) if success else 0
        assert model.external_cache == value,(capacity,banks,hex(model.external_cache),hex(value))
        expected=[0xB7]+([0x37] if capacity and banks==1 else [])+[value]
        assert model.cache_writes == expected,(model.cache_writes,expected)
        assert model.posts == ([0x12, 0x13, 0x15] if success else
                               [0x12, 0x16] if not capacity else [0x12, 0x13, 0x14])
        assert model.miscset & 0x88 == (0x88 if caller else 0x80)
        assert model.regions[0x18] == 0xAA
        assert model.fast_commands == int(caller)
        assert model.ntbref == (0x01 if caller else 0xA1)
        assert model.ramtmg == saved_timing and model.xctl == saved_xctl
        assert model.miscset == ((saved_misc | 0x88) if caller else (saved_misc | 0x80) & ~8)
        if caller:
            assert all(model.regions[i] == 0x55 for i in range(0x13, 0x18))
        assert model.a20 == a20 and not model.enabled
        assert cpu.reg_read(x.UC_X86_REG_GDTR) == gdtr
        assert cpu.reg_read(x.UC_X86_REG_CR0) == (0x10 if caller else 0x60000010)
        assert cpu.reg_read(x.UC_X86_REG_ESP) == 0x7000
        assert cpu.reg_read(x.UC_X86_REG_DS) == cpu.reg_read(x.UC_X86_REG_ES) == 0
        for name, value in registers.items():
            assert cpu.reg_read(getattr(x, 'UC_X86_REG_' + name)) == value, name
        assert model.read(0x9FC00, 8) == b'\xFF' * 8
    print(f'L2 {capacity//1024}KiB / {banks}bank / broken={broken} / warm={warm}: PASS',flush=True)


def late_policy(capacity, banks, hole=False):
    model = importlib.import_module('test-chipset').Chipset()
    initial = bytes(model.cpu.mem_read(0, 8*MIB))
    model.cpu = Uc(UC_ARCH_X86, UC_MODE_16)
    model.cpu.mem_map(0, len(initial))
    model.cpu.mem_write(0, initial)
    model.cpu.hook_add(UC_HOOK_INSN, model.port_in, None, 1, 0, x.UC_X86_INS_IN)
    model.cpu.hook_add(UC_HOOK_INSN, model.port_out, None, 1, 0, x.UC_X86_INS_OUT)
    cache = Cache(capacity, banks=banks)
    def direct(cpu, access, address, size, value, unused):
        assert not (model.chipset.get(0x21, 0) & 1 and MIB <= address < MIB+65536), 'POST accessed an ISA window'
        cache.external_cache = model.chipset.get(0x19, 0)
        if cache.external_cache & 7 == 7 and not 0xA0000 <= address < MIB:
            cache.ramtmg, cache.miscset, cache.xctl = (model.chipset[r] for r in (1, 7, 0x24))
            cache.memory(cpu, access, address, size, value, unused)
    model.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, direct)
    model.cpu.mem_write(model.base+0xD0, (3072).to_bytes(2, 'little'))
    model.cpu.mem_write(model.base+0x78, (3072).to_bytes(2, 'little'))
    model.cpu.mem_write(model.base+0x69, b'\x79')  # Both user write-policy bits.
    if hole:
        model.cpu.mem_write(model.base+0x71, b'\x02\x01')
        model.call('chipset_apply', flags=2)
        assert model.cpu.mem_read(model.base+0xD0, 2) == b'\0\0'
    model.call('chipset_late_cache', flags=2, count=15000000)
    geometry = 0xB0 if banks == 2 else 0x30
    assert model.chipset[0x19] == geometry | 0x48 | (capacity.bit_length()-15)
    assert model.cpu.mem_read(model.base+0x7A, 1) == b'\x15'
    assert model.chipset[7] & 8 and model.a20 == 0
    if hole:
        assert model.chipset[0x20] == 2 and model.chipset[0x21] == 1
        assert model.cpu.mem_read(model.base+0xD0, 2) == b'\0\0'
    assert all(model.chipset[r] == (0xAA if r == 0x18 else 0x55) for r in range(0x13, 0x19))
    print(f'Late policy preserves {capacity//1024}KiB / {banks}bank geometry / ISA hole={hole}: PASS', flush=True)


if __name__ == '__main__':
    for capacity, broken in ((0, False), (128 * 1024, False), (128 * 1024, True)):
        for a20 in (0, 2):
            run(capacity, broken, a20=a20)
            run(capacity, broken, caller=True, a20=a20)
    for requested in (False,True):
        run(128 * 1024, warm=True,requested=requested)
    for capacity, broken in ((0, False),(128 * 1024, False),(128 * 1024, True)):
        run(capacity, broken, tuned=True)
    for capacity,banks in ((32768,1),(65536,1),(262144,2),(524288,1),(1048576,2),(98304,1),(2097152,2)):
        run(capacity,banks=banks,tuned=True)
    for capacity, banks in ((131072,1), (262144,2), (1048576,2)):
        late_policy(capacity, banks)
    late_policy(1048576, 2, hole=True)
    print('PASS: OEM bank fallback,32KiB..1MiB sizes, absent/corrupt/invalid SRAM, restored state and warm L2 disable.')
