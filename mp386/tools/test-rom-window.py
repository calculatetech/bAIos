"""Read-only ROM-window probe through the installed ROM's native AH87."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INTR, UC_HOOK_INSN, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

from fixture import PORT, Listing

FOLDER = PORT/'build/diagnostics/rom-window'


def check(shape,expected,flags=0x246,segment=0x2000,protected=False,failure=0):
    cpu = Uc(UC_ARCH_X86,UC_MODE_16)
    cpu.mem_map(0,0x2000000)
    cpu.mem_write(0xF0000,ROM)
    cpu.mem_write(0x40E,struct.pack('<H',0x9E00))
    for i,(high,low) in enumerate(((0xFF0000,0xF0000),(0xFF8000,0xF8000))):
        data = ROM[low-0xF0000:low-0xF0000+512]
        if shape == 'distinct' or (shape == 'mixed' and i):
            data = bytes(value^0x5A for value in data)
        cpu.mem_write(high,data)
    before = bytes(cpu.mem_read(0xF0000,65536))
    cpu.mem_write(segment*16+0x100,RAW)
    state = dict(calls=[],text='',exit=None,gate=0x21,selector=0xAB)
    for register,value in ((x.UC_X86_REG_CS,segment),(x.UC_X86_REG_DS,segment),
                           (x.UC_X86_REG_ES,0x5678),(x.UC_X86_REG_SS,0x3000),
                           (x.UC_X86_REG_SP,0xFFFE),(x.UC_X86_REG_CR0,0x10|int(protected)),
                           (x.UC_X86_REG_EFLAGS,flags)):
        cpu.reg_write(register,value)
    def inp(cpu,port,size,unused):
        assert port == 0x5B and size == 1 and state['selector'] == 0xE1
        return state['gate']
    def out(cpu,port,size,value,unused):
        assert size == 1
        if port == 0x5A:
            assert value == 0xE1
            state['selector'] = value
        elif port == 0x5B:
            assert state['selector'] == 0xE1 and value&~0x20 == 1
            state['gate'] = value
        else:
            assert port == 0x70 and value in (0,0x80),(port,value)
    def write(cpu,kind,address,size,value,unused):
        own = segment*16 <= address and address+size <= (segment+0x1000)*16
        stack = 0x30000 <= address and address+size <= 0x40000
        assert own or stack,('external write',hex(address),size)
    def interrupt(cpu,vector,unused):
        if vector == 0x21:
            assert state['gate'] == 0x21
            assert cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200 == flags&0x200
            ah = cpu.reg_read(x.UC_X86_REG_AH)
            if ah == 9:
                address = (cpu.reg_read(x.UC_X86_REG_DS)<<4)+cpu.reg_read(x.UC_X86_REG_DX)
                state['text'] += bytes(cpu.mem_read(address,5)).split(b'$')[0].decode()
            else:
                assert ah == 0x4C
                state['exit'] = cpu.reg_read(x.UC_X86_REG_AL)
                cpu.emu_stop()
            return
        assert vector == 0x15 and cpu.reg_read(x.UC_X86_REG_AX) == 0x8700
        assert cpu.reg_read(x.UC_X86_REG_CX) == 256
        address = (cpu.reg_read(x.UC_X86_REG_ES)<<4)+cpu.reg_read(x.UC_X86_REG_SI)
        table = bytes(cpu.mem_read(address,48))
        source = int.from_bytes(table[18:21],'little')|(table[23]<<24)
        dest = int.from_bytes(table[26:29],'little')|(table[31]<<24)
        assert source == (0xFF0000,0xFF8000)[len(state['calls'])]
        assert segment*16+0x100 <= dest < dest+512 <= segment*16+0x100+len(RAW)
        state['calls'].append(source)
        if failure == len(state['calls']):
            cpu.reg_write(x.UC_X86_REG_AX,0x200)
            cpu.reg_write(x.UC_X86_REG_EFLAGS,cpu.reg_read(x.UC_X86_REG_EFLAGS)|1)
            return
        sp = (cpu.reg_read(x.UC_X86_REG_SP)-6)&0xFFFF
        saved = cpu.reg_read(x.UC_X86_REG_EFLAGS)
        cpu.mem_write((cpu.reg_read(x.UC_X86_REG_SS)<<4)+sp,
                      struct.pack('<3H',cpu.reg_read(x.UC_X86_REG_IP),cpu.reg_read(x.UC_X86_REG_CS),saved&0xFFFF))
        cpu.reg_write(x.UC_X86_REG_SP,sp)
        cpu.reg_write(x.UC_X86_REG_EFLAGS,saved&~0x300)
        cpu.reg_write(x.UC_X86_REG_CS,0xF000)
        cpu.reg_write(x.UC_X86_REG_IP,INT15)
    cpu.hook_add(UC_HOOK_INSN,inp,None,1,0,x.UC_X86_INS_IN)
    cpu.hook_add(UC_HOOK_INSN,out,None,1,0,x.UC_X86_INS_OUT)
    cpu.hook_add(UC_HOOK_INTR,interrupt)
    cpu.hook_add(UC_HOOK_MEM_WRITE,write)
    cpu.emu_start(segment*16+0x100,0x2000000,count=100000)
    assert state['text'] == expected+'\r\n' and state['exit'] == int(expected[1]),state
    assert bytes(cpu.mem_read(0xF0000,65536)) == before
    if expected in ('H4','H5'):
        assert not state['calls']
    return dict(code=expected,reads=len(state['calls']),IF=bool(flags&0x200))


def main(image):
    global RAW, ROM, INT15
    FOLDER.mkdir(parents=True,exist_ok=True)
    program=FOLDER/'TGHOLE.COM'
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    subprocess.run([nasm,'-w+error','-f','bin','-o',str(program),str(PORT/'diagnostics/rom-window.asm')],check=True)
    RAW=program.read_bytes()
    ROM=image.read_bytes()
    INT15=Listing(image.with_suffix('.lst')).symbol('int15')
    cases = [check(shape,code,flags) for flags in (0x246,0x46)
             for shape,code in (('mirror','H0'),('distinct','H1'),('mixed','H2'))]
    cases += [check('mirror','H3',failure=i) for i in (1,2)]
    cases += [check('mirror','H4',protected=True),check('mirror','H5',segment=0x7000)]
    result = dict(cases=cases,size=len(RAW),sum32=f'{sum(RAW):08X}',
                  sha256=hashlib.sha256(RAW).hexdigest(),
                  image=str(image),image_sha256=hashlib.sha256(ROM).hexdigest(),
                  scope='Actual current BIOS AH87; synthetic aliases. Physical result is unqualified.')
    (FOLDER/'check.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS',json.dumps(result))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,default=PORT/'build/baios-mp386.bin')
    main(parser.parse_args().image.resolve())
