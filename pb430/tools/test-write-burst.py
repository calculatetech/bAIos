"""Execute optional write-burst/CBR policy and exact reset restoration."""
import importlib
import json
from pathlib import Path
from unicorn import x86_const as x

t = importlib.import_module('test-timing-setup')
port = Path(__file__).resolve().parents[1]
image = port / 'build/baios-pb430.bin'
rows = []
for original in range(4):
    for refresh in (0x10,0x50):
        for choice in (0,2,4,6,8,10,14):
            chip = bytearray(t.DEFAULT)
            chip[22] = choice
            m = t.model(image,chip)
            m.registers[0x37] = 0xA0 | original
            m.registers[3] = refresh
            m.acc_writes.clear()
            m.call('chipset_memory_policy')
            assert m.registers[2] & 0x20, 'Write choices changed shadow protection'
            assert m.registers[0x37] == (0xA0 | ((choice>>2)&1) if choice&2 else 0xA0|original)
            assert m.registers[3] == (refresh|0x40 if choice&8 else refresh)
            if not choice&0xA:
                assert not any(i in (3,0x37) for i,v in m.acc_writes)
            t.restore(m)
            assert m.registers[0x37] == 0xA0|original
            assert m.registers[3] == refresh
            assert m.cmos[0x37] == 0
            rows.append([original,refresh,choice])

for parent in (0,2):
    m = t.model(image)
    draft = bytearray(t.DEFAULT)
    draft[22] = parent
    m.cpu.mem_write(m.base+0x260,bytes(draft))
    m.cpu.mem_write(m.base+0x278,b'\3\1')
    m.cpu.mem_write(m.base+0xF7,b'\3')  # Cache group, write X222 field 3.
    m.cpu.reg_write(x.UC_X86_REG_CX,3)
    m.call('chipset_ui_editable')
    assert bool(m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1) == (parent==0)
    m.call('chipset_ui_commit')
    assert m.cpu.mem_read(m.base+0x276,1)[0] == (6 if parent else 0)

# Actual Save, POST and Ctrl+Alt+Del preserve both optional settings.
chip = bytearray(t.DEFAULT)
chip[6],chip[22] = 1,14
m = t.model(image,chip)
m.continue_reset = True
m.stop_address = 0xF0000+m.listing.symbol('.wait','boot_retry')
m.open([0x44,28])
assert m.posts[-1] == 0xE4 and m.registers[0x37]&3 == 1 and m.registers[3]&0x40
m.irq_scans([0x1D,0x38,0xE0,0x53])
m.complete_reset()
assert m.posts[-1] == 0xE4 and m.registers[0x37]&3 == 1 and m.registers[3]&0x40
assert m.cpu.mem_read(m.base+0x174,1) == b'\1'
(port/'build/diagnostics/write-burst-checks.json').write_text(json.dumps({'restored_cases':rows,'dependency':True,'save_and_warm_reset':True},indent=2))
print(f'{len(rows)} exact restoration cases, menu dependency and Save/warm reset passed')
