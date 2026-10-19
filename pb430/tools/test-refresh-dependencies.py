"""Check real menu commits and retained settings for burst dependencies."""
import importlib
import json
from pathlib import Path
from unicorn import x86_const as x

t=importlib.import_module('test-timing-setup')
p=Path(__file__).resolve().parents[1]
m=t.model(p/'build/baios-pb430.bin')
rows=[]
# group, field, parent byte/mask, child byte/shift.
for group,field,parent,mask,child,shift in ((4,2,19,2,20,6),
        (4,3,19,2,20,4),(4,4,19,2,20,0),
        (3,1,21,8,19,7),(3,3,22,2,22,2)):
    for enabled in (False,True):
        draft=bytearray(t.DEFAULT)
        draft[parent]=(draft[parent]|mask) if enabled else (draft[parent]&~mask)
        if not enabled:draft[child]|=1<<shift
        m.cpu.mem_write(m.base+0x260,bytes(draft))
        m.cpu.mem_write(m.base+0x278,bytes((group,1 if enabled else 0)))
        m.cpu.mem_write(m.base+0xF7,bytes((field,)))
        m.cpu.reg_write(x.UC_X86_REG_CX,field)
        m.call('chipset_ui_editable')
        assert bool(m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1)==(not enabled)
        m.call('chipset_ui_commit')
        assert m.cpu.mem_read(m.base+0x260+child,1)[0]&(1<<shift)
        rows.append([group,field,enabled])
# Disable and re-enable each parent through the real menu, saving/resetting each time.
# A nonzero child must survive both records, even while its editor is locked.
for group,field,parent,mask,child,shift,parent_field,child_mask in (
        (4,2,19,2,20,6,1,3), (4,3,19,2,20,4,1,3),
        (4,4,19,2,20,0,1,7), (3,1,21,8,19,7,0,1),
        (3,3,22,2,22,2,2,1)):
    chip=bytearray(t.DEFAULT)
    chip[6]=1;chip[14]=2;chip[parent]|=mask;chip[child]|=1<<shift
    m=t.model(p/'build/baios-pb430.bin',chip)
    m.continue_reset=True
    m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
    for enabled in (False,True):
        tail=[0x44,28]
        seen=[]
        def draft(mm):
            if mm.script==tail and not mm.pending and not seen:
                data=bytes(mm.cpu.mem_read(mm.base+0x260,24))
                assert bool(data[parent]&mask)==enabled,(group,field,enabled,data.hex())
                assert (data[child]>>shift)&child_mask==1
                seen.append(True)
        m.observer=draft
        # Main -> Chipset -> group -> parent -> toggle -> F10/Enter.
        # The disabled read-burst child is skipped before the write-burst parent.
        steps=1 if group==3 and parent_field==2 else parent_field
        keys=[0x50]*4+[28]+[0x50]*(group-1)+[28]+[0x50]*steps+[0x4D]
        if enabled:
            event=0xF0000+m.listing.symbol('post_ui_begin');injected=[]
            def reopen(mm,address):
                if address==event and not injected:
                    mm.pending.extend((0xE0,0x53));injected.append(True)
            m.code_observer=reopen
            m.after_reset_script=keys+tail
            m.irq_scans([0x1D,0x38,0xE0,0x53]);assert m.reset_pending
            m.complete_reset()
            assert injected
            m.code_observer=None
        else:
            m.open(keys+tail)
        assert seen and m.reset_count==(3 if enabled else 1) and m.posts[-1]==0xE4
        data=bytes(m.cpu.mem_read(m.base+0x60,24))
        assert bool(data[parent]&mask)==enabled
        assert (data[child]>>shift)&child_mask==1
        cmos_index=0x6B+child if child<21 else 0x33+child-21
        assert (m.cmos[cmos_index]>>shift)&child_mask==1
        if group==4:
            assert bool(m.registers[0x18]&2)==enabled
            assert (m.registers[0x19]>>shift)&child_mask==1
        elif field==1:
            assert bool(m.registers[4]&8)==enabled
            assert bool(m.registers[0x18]&0x80)==enabled
        elif enabled:
            assert m.cpu.mem_read(m.base+0x1006,1)==b'\1'
            assert m.registers[0x37]&3==1
        rows.append({'saved_parent': [group,parent_field,enabled], 'retained_child': field})
    m.observer=None
# Valid old Manual records lose only the retired AT-burst field on load.
for parent in (0,8):
    chip=bytearray(t.DEFAULT);chip[19]=0x80;chip[21]|=parent
    m=t.model(p/'build/baios-pb430.bin',chip)
    m.call('chipset_memory_policy')
    assert bool(m.registers[0x18]&0x80)==bool(parent)
    assert m.cpu.mem_read(m.base+0x73,1)==b'\x80'
chip=bytearray(t.DEFAULT);chip[14]=2;chip[18]=0x1B
m=t.model(p/'build/baios-pb430.bin',chip)
assert m.cpu.mem_read(m.base+0x72,1)==b'\x13'
assert bytes(m.cmos)==bytes(t.record(chip)[:128])
m.call('chipset_memory_policy')
assert m.registers[0x16]&0x7F==0x4F
(p/'build/diagnostics/refresh-dependency-checks.json').write_text(json.dumps(rows,indent=2))
print('All five dependencies retain nonzero children across UI save/reset off/on; old AT-burst setting retired')
