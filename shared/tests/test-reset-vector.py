"""Execute hardware-reset and legacy software-reset aliases of a built ROM."""
import argparse
import json
import os
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE
from unicorn import x86_const as x

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from shared.tools.ram_proof import Listing


def enter(raw,entry,kind):
    cpu=Uc(UC_ARCH_X86,UC_MODE_16)
    cpu.mem_map(0,0x200000)
    cpu.mem_write(0x100000-len(raw),raw)
    cpu.mem_map(0xFFFF0000,65536)
    cpu.mem_write(0xFFFF0000,raw[-65536:])
    if kind=='hardware':
        # Load reset's hidden CS base, then clear PE without reloading CS.
        # The selector is synthetic; the base, limit, and IP match CPU reset.
        cpu.mem_write(0x1000,bytes(8)+bytes.fromhex('FFFF0000FF9A00FF'))
        cpu.reg_write(x.UC_X86_REG_GDTR,(0,0x1000,15,0))
        cpu.reg_write(x.UC_X86_REG_CR0,0x11)
        cpu.reg_write(x.UC_X86_REG_CS,8)
        cpu.reg_write(x.UC_X86_REG_CR0,0x10)
        begin=0x10070  # Unicorn derives IP from begin minus the visible CS*16.
    elif kind=='software':
        cpu.reg_write(x.UC_X86_REG_CS,0x1000)
        cpu.reg_write(x.UC_X86_REG_SS,0)
        cpu.reg_write(x.UC_X86_REG_SP,0x7000)
        # Standard DOS restart: warm flag, then RETF to FFFF:0000.
        code=bytes.fromhex('31C08ED8C7067204341268FFFF6A00CB')
        cpu.mem_write(0x10000,code)
        begin=0x10000
    else:
        cpu.reg_write(x.UC_X86_REG_CS,0xF000)
        begin=0xFFFF0
    seen=[]
    def observe(u,address,size,unused):
        seen.append(address)
        if address==0xF0000+entry or len(seen)>=16:u.emu_stop()
    cpu.hook_add(UC_HOOK_CODE,observe)
    cpu.emu_start(begin,0xFFFFFFFF,count=20)
    reached=seen[-1]==0xF0000+entry and cpu.reg_read(x.UC_X86_REG_CS)==0xF000
    if kind=='software':assert bytes(cpu.mem_read(0x472,2))==b'\x34\x12'
    return reached,seen


def check(port,output):
    folder=ROOT/port/output
    image=folder/('baios-presario800-system.rom' if port=='presario-800' else f'baios-{port}.bin')
    raw=image.read_bytes();entry=Listing(image.with_suffix('.lst')).symbol('startup')
    assert raw[-16]==0xEA and struct.unpack_from('<HH',raw,len(raw)-15)==(entry,0xF000)
    rows={}
    for kind in ('hardware','canonical','software'):
        reached,trace=enter(raw,entry,kind)
        assert reached,(port,kind,[hex(a) for a in trace])
        rows[kind]={'canonical_startup':True,'trace':[f'{a:08X}' for a in trace]}
    if port=='m919':
        # Contrast the previous near vector with exactly the same DOS caller.
        near=bytearray(raw);struct.pack_into('<Bh',near,len(near)-16,0xE9,(entry+13)&0xFFFF)
        near[-13:-11]=b'\x90\x90'
        reached,trace=enter(bytes(near),entry,'software')
        assert not reached and 0x100000+entry in trace,trace
        rows['previous_near_vector_fails_same_software_entry']=True
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',choices=('m919','pb430','presario-800','mp386'),required=True)
    parser.add_argument('--output',default=os.environ.get('BAIOS_BUILD_DIRECTORY','build'))
    args=parser.parse_args()
    print(json.dumps({args.port:check(args.port,args.output)},indent=2))
