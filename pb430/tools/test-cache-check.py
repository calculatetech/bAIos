"""Execute the short SRAM check and actual cold/warm POST with an external SRAM."""
import importlib
import json
import sys
from pathlib import Path

from unicorn import UC_HOOK_INSN, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

timing = importlib.import_module('test-timing-setup')
PORT = Path(__file__).resolve().parents[1]


class ACCReadback(timing.ACC):
    def port_in(self, cpu, port, size, unused):
        value = super().port_in(cpu, port, size, unused)
        return value | 0x2C if port == 0xF3 and self.acc_index == 1 else value

    def port_out(self, cpu, port, size, value, unused):
        if port == 0xF3 and self.acc_index == 1:
            # The new wrapper calls acc_write; inspect that call's return site.
            stack = cpu.reg_read(x.UC_X86_REG_SS)*16+cpu.reg_read(x.UC_X86_REG_SP)
            caller = int.from_bytes(cpu.mem_read(stack+2,2),'little')
            if self.listing.symbol('cache_test') <= caller < self.listing.symbol('cache_test_end'):
                assert not value & 0x2C, ('Register01 readback bits written', hex(value))
        return super().port_out(cpu, port, size, value, unused)


class SRAM:
    def __init__(self, machine, kib, fault=None):
        self.m = machine
        self.capacity = kib * 1024
        self.data = bytearray(self.capacity)
        self.fault = fault
        self.reads = self.writes = 0
        self.active = False
        self.dram = b''
        self.first = 0xF0000 + machine.listing.symbol('cache_test')
        self.last = 0xF0000 + machine.listing.symbol('cache_test_end')
        machine.cpu.hook_add(UC_HOOK_MEM_READ, self.read, begin=0, end=0x9FFFF)
        machine.cpu.hook_add(UC_HOOK_MEM_WRITE, self.write, begin=0, end=0x9FFFF)
        machine.cpu.hook_add(UC_HOOK_INSN, self.out, None, 1, 0, x.UC_X86_INS_OUT)

    def checking(self, cpu):
        return self.first <= cpu.reg_read(x.UC_X86_REG_CS)*16 + cpu.reg_read(x.UC_X86_REG_IP) < self.last

    def direct(self, cpu, address, size):
        if self.m.registers[0x1A] & 0x18 != 0x10:
            return False
        assert 0x10000 <= address and address+size <= 0x90004, ('Live RAM/stack accessed in SRAM mode', hex(address))
        assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        return True

    def offset(self, address):
        # Inject the check fault after reference discovery has established size.
        mask = self.capacity//2-1 if self.fault == 'alias' and self.checking(self.m.cpu) else self.capacity-1
        if self.fault == 'low_alias':
            mask &= ~0x100
        return address & mask

    def selected_word(self, address):
        # Four data SRAMs supply one DWORD; the probe's wider line has a hole.
        geometry = (self.m.registers[4] >> 1) & 3
        line_bytes = (4, 8, 4, 16)[geometry]
        return address % line_bytes < 4

    def read(self, cpu, access, address, size, value, unused):
        if not self.direct(cpu, address, size):
            return
        if self.checking(cpu):
            self.reads += 1
        if not self.selected_word(address):
            # Bench capture: an undriven read returned the loop's bus bytes.
            cpu.mem_write(address, bytes.fromhex('83c70475')[:size])
            return
        # Capacity does not imply that the next address mirrors valid SRAM.
        if self.checking(cpu) and address >= 0x10000+self.capacity:
            cpu.mem_write(address, b'\xff'*size)
            return
        payload = bytearray(self.data[self.offset(address+i)] for i in range(size)) if self.capacity else bytearray(b'\xff'*size)
        corrupt = self.fault in ('data', 'boundary') or (self.fault == 'complement' and self.reads > self.capacity//2)
        last = 0x1FFFE if self.fault == 'boundary' else 0x10000+self.capacity-2
        if corrupt and address == last and self.checking(cpu):
            payload[0] ^= 1
        cpu.mem_write(address, bytes(payload))

    def write(self, cpu, access, address, size, value, unused):
        if not self.direct(cpu, address, size):
            return
        if self.checking(cpu):
            self.writes += 1
        if not self.selected_word(address):
            return
        if self.checking(cpu) and address >= 0x10000+self.capacity:
            return
        if self.capacity:
            for i, byte in enumerate(value.to_bytes(size, 'little')):
                self.data[self.offset(address+i)] = byte

    def out(self, cpu, port, size, value, unused):
        active = self.m.registers[0x1A] & 0x18 == 0x10
        if active and not self.active:
            self.dram = bytes(cpu.mem_read(0x10000, 0x80004))
            if self.checking(cpu):
                assert self.m.registers[2] & 0x50 == 0, 'SRAM test instruction fetches must stay in ROM'
                if self.m.starting:
                    assert self.m.registers[0x1A] & 0x80, 'Cold SRAM test must precede policy ADS-delay changes'
                    assert self.m.registers[0x1D] == 0 and self.m.registers[0x1E] == 0, 'Cold SRAM test must precede size/range policy'
        if self.active and not active:
            cpu.mem_write(0x10000, self.dram)
        if active:
            assert port != 0x80, 'POST I/O inserted in SRAM mode'
        self.active = active


def component(image, kib, fault=None):
    m = timing.model(image, cls=ACCReadback)
    m.registers[1] &= 0xD3
    code = {128: 1, 256: 3, 512: 2}[kib]
    m.cpu.mem_write(m.base+0x1003, bytes((1, code, 1)))
    m.cpu.mem_write(m.base+0x100B, b'\x00')
    m.registers[4] = 0x94
    m.registers[0x1A] = 0xA4
    m.registers[2] = 0x80
    saved = bytes(m.registers)
    m.cpu.reg_write(x.UC_X86_REG_CR0, 0x60000010)
    registers = {reg: 0x12345678+i for i, reg in enumerate((x.UC_X86_REG_EAX, x.UC_X86_REG_EBX, x.UC_X86_REG_ECX, x.UC_X86_REG_EDX, x.UC_X86_REG_ESI, x.UC_X86_REG_EDI, x.UC_X86_REG_EBP))}
    for reg, value in registers.items():
        m.cpu.reg_write(reg, value)
    sram = SRAM(m, kib, fault)
    m.call('cache_test', flags=0x602, count=10000000)
    passed = fault is None
    assert m.cpu.mem_read(m.base+0x1005, 1) == bytes((int(passed),))
    assert m.cpu.mem_read(m.base+0x100D, 1) == bytes((1 if passed else 2,))
    assert m.cpu.mem_read(m.base+0x100B, 1) == b'\x00'
    assert bytes(m.registers) == saved, 'Controller state not restored'
    assert m.cpu.reg_read(x.UC_X86_REG_CR0) == 0x60000010
    assert m.cpu.reg_read(x.UC_X86_REG_SP) == 0x7000
    assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x602 == 0x602
    assert m.cpu.reg_read(x.UC_X86_REG_DS) == 0
    assert all(m.cpu.reg_read(reg) == value for reg, value in registers.items())
    if passed:
        assert sram.writes == sram.capacity+16*(sram.capacity//65536)
        assert sram.reads == sram.writes
    assert not sram.active
    if fault:
        if fault in ('alias', 'low_alias'):
            address, expected = 0x10000, 0x1357
            observed = expected+(sram.capacity//2//65536)*16 if fault == 'alias' else expected+8
        else:
            address = 0x1FFFE if fault == 'boundary' else 0x10000+sram.capacity-2
            expected = 0xAA55 if fault == 'complement' else 0x55AA
            observed = expected^1
        values = (address, expected, observed)
        assert bytes(m.cpu.mem_read(m.base+0x101C,12)) == b''.join(value.to_bytes(4,'little') for value in values), values
    print(f'PASS SRAM {kib} KiB, fault={fault}', flush=True)
    return {'kib': kib, 'fault': fault, 'passed': passed, 'reads': sram.reads, 'writes': sram.writes, 'controller_and_context_restored': True}


def post(image, fault=None, kib=512):
    chip = bytearray(timing.DEFAULT)
    chip[6] = 1
    m = timing.model(image, chip, ACCReadback)
    m.cache_kib = kib
    m.registers[1] &= 0xD3
    sram = SRAM(m, kib, fault)
    m.stop_address = 0xF0000+m.listing.symbol('.wait', 'boot_retry')
    m.cold_boot()
    assert m.stopped and m.posts[-1] == 0xE4
    assert m.cpu.mem_read(m.base+0x1004,1) == bytes(({128:1,256:3,512:2}[kib],))
    assert m.cpu.mem_read(m.base+0x100D, 1) == bytes((1 if fault is None else 2,))
    assert bool(m.registers[4] & 1) == (fault is None)
    assert m.cpu.mem_read(m.base+0x174,1) == b'\x01', 'Settings must remain valid'
    assert not m.cpu.mem_read(m.base+0x175,1)[0] & 4
    if fault:
        assert m.text(4, 20, 17) == 'Cache test failed'
        values = ((0x10000, 0x1357, 0x1357+(kib//128)*16) if fault == 'alias'
                  else (0x10000+kib*1024-2, 0x55AA, 0x55AB))
        assert bytes(m.cpu.mem_read(m.base+0x101C,12)) == b''.join(value.to_bytes(4,'little') for value in values)
    else:
        assert m.text(4,20,20).strip() == f'{kib} KB'
        saved = bytes(m.cmos[0x33:0x36]+m.cmos[0x38:0x40]+m.cmos[0x69:0x80])
        count = sram.reads, sram.writes
        m.irq_scans([0x1D, 0x38, 0xE0, 0x53])
        assert m.reset_pending
        m.complete_reset(count=300000000)
        assert m.stopped and m.posts[-1] == 0xE4
        assert (sram.reads, sram.writes) == count, 'Unchanged warm reset must retain the reference cache path'
        assert m.cpu.mem_read(m.base+0x100D, 1) == b'\x00' and m.registers[4] & 1
        assert m.cpu.mem_read(m.base+0x174,1) == b'\x01'
        assert not m.cpu.mem_read(m.base+0x175,1)[0] & 4
        assert bytes(m.cmos[0x33:0x36]+m.cmos[0x38:0x40]+m.cmos[0x69:0x80]) == saved
        transitions = importlib.import_module('test-cache-transitions')
        transitions.prepare_ui(m)
        m.open([0x44,28])
        assert m.stopped and m.posts[-1] == 0xE4
        assert m.cpu.mem_read(m.base+0x174,1) == b'\x01'
        assert not m.cpu.mem_read(m.base+0x175,1)[0] & 4
        assert (sram.reads,sram.writes) == count, 'Unchanged Save/Exit must retain the reference warm path'
        assert bytes(m.cmos[0x33:0x36]+m.cmos[0x38:0x40]+m.cmos[0x69:0x80]) == saved
        # Change L1 through the real Setup page, Save/Exit and reset.
        transitions.prepare_ui(m)
        m.open(transitions.edit(1)+[0x44,28])
        assert m.stopped and m.posts[-1] == 0xE4
        assert m.cpu.mem_read(m.base+0x174,1) == b'\x01'
        assert not m.cpu.mem_read(m.base+0x175,1)[0] & 4
        assert m.cpu.mem_read(m.base+0x61,1) == b'\x00'
        assert not m.registers[4] & 1
        assert m.cpu.mem_read(m.base+0x100D,1) == b'\x01'
        assert (sram.reads,sram.writes) == tuple(n*2 for n in count), 'Changed cache choice must run a fresh cold check'
    print(f'PASS actual POST {kib} KiB, fault={fault}, warm={fault is None}', flush=True)
    return {'kib': kib, 'cold_post': True, 'warm_post': fault is None, 'unchanged_save_exit': fault is None, 'save_exit_changed_cache_choice': fault is None, 'settings_valid': True, 'register01_readback_mask': True, 'pre_policy_rom_check': True, 'fault': fault, 'failure_details': values if fault else None, 'effective_l2_after_save': bool(m.registers[4] & 1), 'terminal': 'boot_retry after E4'}


if __name__ == '__main__':
    image = Path(sys.argv[1]) if len(sys.argv) > 1 else PORT/'build/cache-check/baios-pb430.bin'
    rows = [component(image, kib) for kib in (128, 256, 512)]
    rows += [component(image, 512, fault) for fault in ('data', 'alias')]
    rows += [component(image, 128, fault) for fault in ('complement', 'low_alias', 'boundary')]
    rows += [post(image, kib=kib) for kib in (128, 256, 512)]
    rows += [post(image, fault) for fault in ('data', 'alias')]
    target = image.parent/'cache-check-results.json'
    target.write_text(json.dumps(rows, indent=2)+'\n')
    print(f'PASS: {len(rows)} SRAM/POST cases; {target}')
