"""POST fallback scans must leave runtime scan delivery to the keyboard owner."""
import argparse
import importlib.util
import json
from pathlib import Path
import struct
import sys

from unicorn import x86_const as x

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
spec=importlib.util.spec_from_file_location('ownership_pnp',ROOT/'shared/tests/test-pnp.py')
pnp=importlib.util.module_from_spec(spec);spec.loader.exec_module(pnp)


def check(port,output,masked,runtime):
    class Keyboard(pnp.settings.Settings):
        def __init__(self):
            self.pending=True;self.input_reads=0;self.kbc=[];self.timer_callbacks=0
            super().__init__(port,output)
        def inp(self,cpu,number,size,user):
            if number==0x21:return 2 if masked else 0
            if number==0x20:return 0 # Neither pending nor in-service IRQ1.
            if number==0x64:self.kbc.append(('status',));return int(self.pending)
            if number==0x60:
                assert self.pending
                self.pending=False;self.input_reads+=1;return 0xB8
            return super().inp(cpu,number,size,user)
        def out(self,cpu,number,size,value,user):
            if number in (0x60,0x64):self.kbc.append((number,value))
            return super().out(cpu,number,size,value,user)
        def interrupt(self,cpu,vector,user):
            if vector in (9,0x15,0x1C):
                if vector==0x1C:self.timer_callbacks+=1
                name={9:'int09',0x15:'int15',0x1C:'default_iret'}[vector]
                pnp.Caller.inject(self,name,cpu.reg_read(x.UC_X86_REG_IP))
                return
            return super().interrupt(cpu,vector,user)
    m=Keyboard();u=m.cpu
    u.mem_write(0x417,b'\x28\x02');u.mem_write(0x496,b'\x10')
    u.mem_write(0x49E,bytes((0 if runtime else 1,)))
    u.mem_write(0x41A,struct.pack('<HH',0x1E,0x1E))
    u.mem_write(0x46C,bytes(4))
    u.mem_write(0x7000,struct.pack('<HHH',0xFF00,0xF000,0x202))
    for name,value in dict(CS=0xF000,SS=0,SP=0x7000,DS=0x2345,ES=0x3456,FS=0x4567,GS=0x5678,EFLAGS=0x202).items():
        u.reg_write(getattr(x,'UC_X86_REG_'+name),value)
    u.emu_start(0xF0000+m.listing.symbol('int08'),0xFFF00,count=100000)
    assert u.reg_read(x.UC_X86_REG_IP)==0xFF00
    assert bytes(u.mem_read(0x46C,4))==b'\x01\0\0\0' and m.timer_callbacks==1
    retained=masked or runtime
    assert bytes(u.mem_read(0x417,2))==(b'\x28\x02' if retained else b'\x20\0')
    assert m.input_reads==(0 if retained else 1) and m.pending==retained
    if masked:assert not m.kbc,('Masked keyboard was accessed',m.kbc)
    timer_reads=m.input_reads
    if retained:
        if masked:
            # Explicit BIOS callers can poll; this is not a background scan.
            m.call('keyboard_poll',DS=0x40)
        else:
            # Run the real IRQ1 owner after IRQ0 has left its byte untouched.
            u.mem_write(0x7000,struct.pack('<HHH',0xFF00,0xF000,0x202))
            for name,value in dict(CS=0xF000,SS=0,SP=0x7000,EFLAGS=0x202).items():
                u.reg_write(getattr(x,'UC_X86_REG_'+name),value)
            u.emu_start(0xF0000+m.listing.symbol('int09'),0xFFF00,count=100000)
        assert bytes(u.mem_read(0x417,2))==b'\x20\0' and not m.pending and m.input_reads==1
    return {'IRQ1_masked':masked,'runtime':runtime,'timer_scan_reads':timer_reads,
            'normal_timer_and_INT1C':True,'release_processed_once_by_input_owner':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',choices=('m919','pb430','presario-800','mp386'),required=True)
    parser.add_argument('--output',default='build')
    args=parser.parse_args()
    print(json.dumps({args.port:[check(args.port,args.output,m,r)
                                for r in (False,True) for m in (False,True)]},indent=2))
