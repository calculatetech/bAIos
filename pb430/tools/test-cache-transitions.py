"""Exercise saved cache changes through real Setup, reset and complete POST."""
import importlib
import json
from pathlib import Path
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

timing = importlib.import_module('test-timing-setup')
PORT = Path(__file__).resolve().parents[1]
IMAGE = PORT / 'build/baios-pb430.bin'


def machine(l1=0, cache_kib=512, cls=timing.ACC):
    chip = bytearray(timing.DEFAULT)
    chip[1] = l1
    chip[6] = 1
    m = timing.model(IMAGE, chip, cls)
    sram = bytearray(cache_kib * 1024)
    def read(cpu, access, address, size, value, unused):
        if m.registers[0x1A] & 0x18 == 0x10:
            cpu.mem_write(address, bytes(sram[(address-0x20000+i) % len(sram)]
                                        for i in range(size)) if sram else b'\xff' * size)
    def write(cpu, access, address, size, value, unused):
        if m.registers[0x1A] & 0x18 == 0x10 and sram:
            for i, byte in enumerate(value.to_bytes(size, 'little')):
                sram[(address-0x20000+i) % len(sram)] = byte
    m.cpu.hook_add(UC_HOOK_MEM_READ, read, begin=0x10000, end=0x90003)
    m.cpu.hook_add(UC_HOOK_MEM_WRITE, write, begin=0x10000, end=0x90003)
    m.stop_address = 0xF0000 + m.listing.symbol('.wait', 'boot_retry')
    m.cold_boot()
    return m


def edit(field):
    return [0x50]*4 + [28, 28] + [0x50]*field + [0x4D]


def prepare_ui(m):
    m.stop_address = 0xF0000+m.listing.symbol('setup_post_gate')
    m.irq_scans([0x1D, 0x38, 0xE0, 0x53])
    m.complete_reset(count=300000000)
    m.stop_address = 0xF0000+m.listing.symbol('.wait', 'boot_retry')


def transition(m, script=None, cold=False, l1=1, l2=1, qualified=True):
    if script is not None:
        prepare_ui(m)
    old = bytes(m.cpu.mem_read(m.base+0x60, 24))
    events = []
    cold_registers = []
    names = ('cache_stock_reset', 'cache_initialize', 'cache_initial_policy',
             'cache_stock_cold_resume', 'chipset_late_cache')
    addresses = {0xF0000+m.listing.symbol(n): n for n in names}
    def observe(mm, address):
        if address in addresses:
            name = addresses[address]
            if name == 'cache_stock_reset':
                assert bytes(mm.cpu.mem_read(mm.base+0x60, 24)) == old
            if name == 'cache_stock_cold_resume':
                cold_registers.append(bytes(mm.registers))
            events.append((name, len(mm.acc_writes)))
    m.code_observer = observe
    begin = len(m.posts)
    if script is None:
        m.irq_scans([0x1D, 0x38, 0xE0, 0x53])
        assert m.reset_pending
        m.complete_reset(count=300000000)
    else:
        m.open(script)
    m.code_observer = None
    assert m.stopped and m.posts[-1] == 0xE4, m.posts[begin:]
    assert (0x12 in m.posts[begin:]) == cold, m.posts[begin:]
    assert ('cache_stock_cold_resume' in [n for n, _ in events]) == cold, events
    assert [n for n, _ in events] == (list(names) if cold else
                                     [n for n in names if n != 'cache_stock_cold_resume']), events
    assert bool(m.cpu.reg_read(x.UC_X86_REG_CR0) & 0x40000000) == (not l1)
    assert bool(m.registers[4] & 1) == bool(l1 and l2 and qualified)
    assert bytes(m.cpu.mem_read(m.base+0x61, 2)) == bytes((l1, l2))
    if cold:
        initial = next(i for n, i in events if n == 'cache_initial_policy')
        resume = next(i for n, i in events if n == 'cache_stock_cold_resume')
        writes = m.acc_writes[initial:resume]
        regs = cold_registers[0]
        live = l1 and qualified
        expected = {4: 0x14 if live else 0x54, 6: 0xB7,
                    0x0B: 0x15 if live else 5}
        assert all(regs[i] == value and (i, value) in writes for i, value in expected.items())
        assert regs[7]&0x1F == 0x14 and regs[0x18]&0x73 == 0 and regs[0x1A]&0xBF == 0x24
        assert all((i, regs[i]) in writes for i in (7, 0x18, 0x1A))
        if live:
            assert (0x1D, 0xF0) in writes and (0x1E, 0x7B) in writes, writes
    return {'cold': cold, 'l1': l1, 'l2': l2, 'qualified': qualified,
            'owners': [n for n, _ in events]}


def run():
    rows = []
    # The loader may reject a saved record and clear C_VALID; the helper is read-only.
    for valid in (True, False):
        m = timing.model(IMAGE)
        active = bytes(range(24))
        m.cpu.mem_write(m.base+0x60, active)
        m.cpu.mem_write(m.base+0x174, b'\x5a')
        if not valid:
            m.cmos[0x6A] ^= 1
        entry = 0xF0000+m.listing.symbol('cache_reset_marker')
        def foreign_fs(mm, address):
            if address == entry:
                mm.cpu.reg_write(x.UC_X86_REG_FS, 0x1234)
        m.code_observer = foreign_fs
        m.call('cache_reset_marker')
        assert m.cpu.reg_read(x.UC_X86_REG_AX) == 0
        assert m.cpu.reg_read(x.UC_X86_REG_FS) == 0x1234
        assert m.cpu.reg_read(x.UC_X86_REG_SP) == 0x7000
        assert bytes(m.cpu.mem_read(m.base+0x60, 24)) == active
        assert bytes(m.cpu.mem_read(m.base+0x174, 1)) == b'\x5a'
        rows.append({'snapshot_preserved_with_valid_record': valid})
    print('PASS full active record, validity, caller FS and stack preserved', flush=True)
    m = machine()
    for field, l1, l2 in ((1, 1, 1), (2, 1, 0), (2, 1, 1), (1, 0, 1)):
        rows.append(transition(m, edit(field)+[0x44, 28], True, l1, l2))
        rows.append(transition(m, [0x44, 28], False, l1, l2))
        rows.append(transition(m, None, False, l1, l2))
        print(f'PASS cache change L1={l1} L2={l2}, unchanged Save and CAD', flush=True)
    # Discard a changed draft through the existing confirmation.
    prepare_ui(m)
    m.open(edit(1)+[1, 1, 1, 28])
    rows.append(transition(m, None, False, 0, 1))
    print('PASS discarded cache edit retains warm reset', flush=True)
    # Cancel Save, then discard the draft; neither operation publishes it.
    prepare_ui(m)
    m.open(edit(1)+[0x44, 1, 1, 1, 1, 28])
    rows.append(transition(m, None, False, 0, 1))
    print('PASS canceled Save retains warm reset', flush=True)
    class SaveMismatch(timing.ACC):
        reject = False
        def port_in(self, cpu, port, size, unused):
            value = super().port_in(cpu, port, size, unused)
            if self.reject and port == 0x71 and self.index == 0x3E:
                return value ^ 255
            return value
    m = machine(cls=SaveMismatch)
    prepare_ui(m)
    resets = m.reset_count
    errors = []
    def save_error(mm):
        if 'CMOS verification failed.' in mm.text(19, 23, 46):
            errors.append(True)
            mm.observer = None
            mm.script = [1, 1, 1, 28]
    m.reject = True
    m.observer = save_error
    m.open(edit(1)+[0x44, 28])
    assert errors and m.reset_count == resets
    m.reject = False
    rows.append(transition(m, None, True, 1, 1))
    print('PASS rejected late Save defers reset but later CAD reinitializes cache', flush=True)
    for size in (0, 64):
        m = machine(cache_kib=size)
        rows.append(transition(m, edit(1)+[0x44, 28], True, 1, 1, False))
        assert bytes(m.cpu.mem_read(m.base+0x1003, 4)) == bytes((int(size != 0), 0, 0, 0))
        assert bytes(m.cpu.mem_read(m.base+0x100A, 1)) == bytes((int(size == 64),))
        label = 'Present / unknown' if size else 'Disabled'
        assert m.text(4, 20, len(label)) == label, m.text(4, 20, 24)
        print(f'PASS {size} KiB unqualified SRAM remains disabled', flush=True)
    result = PORT / 'build/tests/results/cache-transitions.json'
    result.parent.mkdir(parents=True, exist_ok=True)
    result.write_text(json.dumps(rows, indent=2)+'\n')


if __name__ == '__main__':
    run()
