"""Check required refresh/burst recovery, menu dependency and saved CMOS records."""
import importlib
import json
from pathlib import Path
from unicorn import x86_const as x

t = importlib.import_module('test-timing-setup')
PORT = Path(__file__).resolve().parents[1]
image = PORT / 'build/baios-pb430.bin'
rows = []

# Old valid records can disable DRAM burst; the two removed choices normalize.
chip = bytearray(t.DEFAULT)
chip[6], chip[14], chip[19], chip[21] = 1, 2, 1, 0x80
m = t.model(image, chip)
assert m.cpu.mem_read(m.base+0x73, 1) == b'\0'
assert m.cpu.mem_read(m.base+0x75, 1) == b'\0'
assert m.cpu.mem_read(m.base+0x174, 1) == b'\1'
assert bytes(m.cmos) == bytes(t.record(chip)[:128])
m.call('chipset_memory_policy')
assert m.registers[4] & 0x90 == 0 and not m.registers[0x18] & 1
rows.append({'old_record_loaded_without_writes_and_unsafe_bits_forced': True})

# With no cookie, repair refresh before the first normal-reset BDA access.
m = t.model(image)
m.cmos[0x37] = 0
m.registers[0x18] = 1
m.registers[4] = 5
start = m.listing.symbol('.normal', 'startup')
end = m.listing.symbol('.classified', 'startup')
for reg, value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_DS,0),
                   (x.UC_X86_REG_EFLAGS,2),(x.UC_X86_REG_EDX,0x403),
                   (x.UC_X86_REG_BX,0)):
    m.cpu.reg_write(reg,value)
m.cpu.emu_start(0xF0000+start,0xF0000+end,count=10000)
assert not m.registers[0x18] & 1
t.restore(m)
assert m.registers[4] & 0x10 and not m.registers[0x18] & 1
rows.append({'unmarked_reset_restores_refresh_before_ram_and_required_burst': True})

for burst in (0,2):
    m = t.model(image)
    draft = bytearray(t.DEFAULT)
    draft[14], draft[19] = 2, burst
    m.cpu.mem_write(m.base+0x260, bytes(draft))
    m.cpu.mem_write(m.base+0x278, bytes((4,7)))
    m.cpu.mem_write(m.base+0xF7, b'\4')  # Refresh group, Burst Count.
    m.cpu.reg_write(x.UC_X86_REG_CX,4)
    m.call('chipset_ui_editable')
    assert bool(m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1) == (burst==0)
    m.call('chipset_ui_commit')
    assert m.cpu.mem_read(m.base+0x274,1) == bytes((7 if burst else 0,))
rows.append({'burst_count_locked_until_burst_refresh_enabled': True})

m = t.model(image, chip)
m.continue_reset = True
m.stop_address = 0xF0000 + m.listing.symbol('.wait','boot_retry')
m.open([0x44,28])
assert m.posts[-1] == 0xE4
assert m.cpu.mem_read(m.base+0x174,1) == b'\1'
assert not m.cpu.mem_read(m.base+0x175,1)[0] & 4
assert m.registers[4] & 0x90 == 0 and not m.registers[0x18] & 1
n = m.cmos
assert (n[0x10]+sum(n[0x38:0x40]))&255 == 0
assert sum(n[0x40:0x5D])&255 == 0
assert sum(n[0x5D:0x69])&255 == 0
assert (sum(n[0x69:0x80])+sum(n[0x33:0x36]))&255 == 0
m.irq_scans([0x1D,0x38,0xE0,0x53])
m.complete_reset()
assert m.cpu.mem_read(m.base+0x174,1) == b'\1'
assert not m.cpu.mem_read(m.base+0x175,1)[0] & 4
rows.append({'all_four_cmos_records_valid_after_save_and_two_posts': True})

for enabled in (0,1):
    m = t.model(image)
    m.cpu.mem_write(m.base+0x260,t.DEFAULT)
    m.cpu.mem_write(m.base+0x278,bytes((3,enabled)))
    m.cpu.mem_write(m.base+0xF7,b'\x09')
    m.call('chipset_ui_commit')  # Cache Timing, DRAM Read Burst.
    for profile in (0,1,2):
        t.profile(m,profile)
        assert bool(m.cpu.mem_read(m.base+0x275,1)[0]&0x10)==bool(enabled)
    m.cpu.mem_write(m.base+0x60,bytes(m.cpu.mem_read(m.base+0x260,24)))
    m.call('chipset_memory_policy')
    assert bool(m.registers[4]&0x10)==bool(enabled)
    assert m.registers[4]&7==5
    t.restore(m)
    assert m.registers[4]&0x10
rows.append({'dram_burst_menu_profiles_apply_and_reset_baseline': True})
out = PORT / 'build/diagnostics/required-refresh-checks.json'
out.write_text(json.dumps(rows,indent=2)+'\n')
print(f'{len(rows)} required-refresh and CMOS groups passed',flush=True)
