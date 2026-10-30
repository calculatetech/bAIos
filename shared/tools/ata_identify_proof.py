"""Exercise POST IDENTIFY status transitions without waiting on wall time."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_CODE
from unicorn import x86_const as x

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from shared.tools.ram_proof import Listing,constants


def poll(image,statuses,packet=False,secondary=False):
    listing=Listing(image.with_suffix('.lst'))
    state=constants(ROOT/'shared/src/pc/state.inc')
    for name,offset in re.findall(r'%define\s+(\w+)\s+STATE_BASE\s*\+\s*(\d+)',(ROOT/'shared/src/pc/state.inc').read_text()):
        state[name]=state['STATE_BASE']+int(offset)
    u=Uc(UC_ARCH_X86,UC_MODE_16)
    u.mem_map(0,0x100000)
    raw=image.read_bytes();u.mem_write(0x100000-len(raw),raw)
    base=0x80000
    data,control=(0x170,0x376) if secondary else (0x1F0,0x3F6)
    table=next((int(m[1],0) for line in listing.lines if (m:=re.search(r'%define HW_PORT_TABLE (0x[0-9A-Fa-f]+)',line))),None)
    if secondary and table is None:return None
    if table is not None:u.mem_write(base+table,struct.pack('<9H',*range(data,data+8),control))
    u.mem_write(base+state['S_IDENTIFY_TRACE'],bytes((4 if packet else 3,)))
    for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_FS,base>>4),
                      (x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x7000),(x.UC_X86_REG_EFLAGS,0x202)):
        u.reg_write(reg,value)
    u.mem_write(0x7000,b'\x00\x80')
    delay=0xF0000+listing.symbol('kbc_delay_2ms')
    u.mem_write(delay,b'\xC3') # Count each real wait call; do not emulate PIT time.
    counts={'reads':0,'delays':0}
    expected=control if packet else data+7
    def incoming(cpu,port,size,user):
        assert port==expected and size==1,(hex(port),hex(expected),size)
        value=statuses[min(counts['reads'],len(statuses)-1)]
        counts['reads']+=1
        return value
    def step(cpu,address,size,user):
        if address==delay:counts['delays']+=1
    u.hook_add(UC_HOOK_INSN,incoming,None,1,0,x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_CODE,step,None,delay,delay)
    u.emu_start(0xF0000+listing.symbol('ata_identify_wait_drq'),0xF8000,count=500000)
    assert u.reg_read(x.UC_X86_REG_IP)==0x8000,'IDENTIFY poll did not return'
    return dict(counts,failed=bool(u.reg_read(x.UC_X86_REG_EFLAGS)&1),
                status=u.mem_read(base+state['S_STATUS'],1)[0],packet=packet,secondary=secondary)


def run(image,baseline=False):
    rows=[]
    cases=[('ATA disappears low',[0x40,0],False,True,0,1),
           ('ATA disappears floating',[0x40,0xFF],False,True,0,1),
           ('ATA idle absent',[0],False,True,0,0),
           ('ATA delayed ready',[0x40,0x80,0x80,0x48],False,False,0,3),
           ('ATA busy hides error',[0x81,0x80,0x48],False,False,0,2),
           ('ATA aborted',[0x80,0x41],False,True,0x20,1),
           ('ATA stays busy',[0x80],False,True,0x80,15000),
           ('ATA ready without DRQ',[0x40],False,True,0x80,15000),
           ('Packet cold start',[0,0,0x80,0x48],True,False,0,3),
           ('Packet slow start',[0xFF,0x80,0x48],True,False,0,2),
           ('Packet timeout',[0],True,True,0x80,15000)]
    for secondary in (False,True):
        for name,statuses,packet,failed,status,delays in cases:
            result=poll(image,statuses,packet,secondary)
            if result is None:continue
            if not baseline:
                assert (result['failed'],result['status'],result['delays'])==(failed,status,delays),(name,result)
            rows.append(dict(name=name,**result))
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('--baseline',action='store_true')
    args=parser.parse_args()
    rows=run(args.image,args.baseline)
    build_root=next(p for p in args.image.resolve().parents if p.name=='build')
    output=build_root/'tests/identify-poll'/('baseline.json' if args.baseline else 'candidate.json')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps({'mode':'baseline observation' if args.baseline else 'asserted checks','rows':rows},indent=2)+'\n')
    print(json.dumps({'cases':len(rows),'baseline':args.baseline,'first_cases':rows[:3]},indent=2))
