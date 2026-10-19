"""Execute cold/warm POST with uncached selected timings before floppy setup."""
import importlib
import json
from pathlib import Path
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

t=importlib.import_module('test-timing-setup')
p=Path(__file__).resolve().parents[1]
chip=bytearray(t.DEFAULT);chip[6]=1;chip[14]=1
m=t.model(p/'build/baios-pb430.bin',chip)
events=[]
testing=[False]
checked=[0]
ram=0xF0000+m.listing.symbol('chipset_visible_ram_test')
finish=0xF0000+m.listing.symbol('post_ram_finish')
floppy=0xF0000+m.listing.symbol('init_floppy')
cache=0xF0000+m.listing.symbol('chipset_late_cache')
def enter(cpu,address,size,unused):
    events.append('ram');testing[0]=True
    assert not m.registers[4]&1
    assert m.cpu.mem_read(0x49E,1)==b'\1'
    assert m.registers[0xB]==0 and m.registers[0x16]&3==3
def done(cpu,address,size,unused):
    testing[0]=False;events.append('ram_done')
def memory(cpu,access,address,size,value,unused):
    if testing[0]:
        assert not m.registers[4]&1 and cpu.reg_read(x.UC_X86_REG_CR0)&0x40000000
        assert m.registers[0xB]==0 and m.registers[0x16]&3==3
        checked[0]+=1
def observe(mm,address):
    if address==floppy:
        assert events==['ram','ram_done'];events.append('floppy')
    if address==cache:
        assert events==['ram','ram_done','floppy']
        assert m.registers[0xB]==0x15 and m.registers[0x16]&0x7F==0
        assert not m.registers[4]&1
        events.append('stock_cache')
m.cpu.hook_add(UC_HOOK_CODE,enter,begin=ram,end=ram)
m.cpu.hook_add(UC_HOOK_CODE,done,begin=finish,end=finish)
m.cpu.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,memory,begin=0x10000,end=0x107FF)
m.code_observer=observe
m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
rows=[]
for mode in ('cold','warm'):
    events.clear();checked[0]=0
    if mode=='cold':
        m.sys_flag=0;m.cpu.mem_write(0x472,b'\0\0')
        m.reset_pending=True;m.continue_reset=True
        m.complete_reset(count=30000000)
    else:
        m.irq_scans([0x1D,0x38,0xE0,0x53]);m.complete_reset(count=30000000)
    assert events==['ram','ram_done','floppy','stock_cache'] and checked[0]
    assert m.registers[4]&1 and m.cpu.mem_read(m.base+0x1006,1)==b'\1'
    assert m.registers[0xB]==0 and m.registers[0x16]&3==3
    rows.append({'mode':mode,'events':list(events),'checked_memory_accesses':checked[0]})
    print(f'PASS {mode}: selected timings, both caches off for RAM, floppy next, stock L2 last',flush=True)
(p/'build/diagnostics/ram-order-checks.json').write_text(json.dumps(rows,indent=2))
