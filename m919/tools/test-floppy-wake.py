"""Check the bounded recovery sequence and its single-code result, no ROM build."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

from unicorn import Uc,UC_ARCH_X86,UC_MODE_16,UC_HOOK_INTR,UC_HOOK_INSN
from unicorn import x86_const as x

PORT=Path(__file__).resolve().parents[1]


def check(raw,success, *, host=0x88811060,bridge=0x888A1060,protected=False):
    u=Uc(UC_ARCH_X86,UC_MODE_16)
    u.mem_map(0,0x200000)
    # Deliberately place the COM across a physical DMA page boundary.
    segment=0x1FA0
    base=segment<<4
    u.mem_write(base+0x100,raw)
    u.mem_write(0xE0014,b'BAISMM1\0')
    for reg in (x.UC_X86_REG_CS,x.UC_X86_REG_DS,x.UC_X86_REG_ES,x.UC_X86_REG_SS):
        u.reg_write(reg,segment)
    u.reg_write(x.UC_X86_REG_SP,0xFFFE)
    u.reg_write(x.UC_X86_REG_EFLAGS,0x202)
    if protected:
        u.reg_write(x.UC_X86_REG_CR0,0x11)
        u.reg_write(x.UC_X86_REG_EFLAGS,0x23202)
    cf8=0x87654320
    initial_cf8=cf8
    writes=[]
    read_stages=[]
    stage=0
    sio=0x60
    output=[]
    def inp(cpu,port,size,_):
        if port==0xCF8:
            return cf8
        if port==0xCFC:
            return host if cf8==0x80008000 else bridge
        assert port==0x109 and size==1
        return sio
    def out(cpu,port,size,value,_):
        nonlocal cf8,stage,sio
        if port==0xCF8:
            cf8=value
            return
        assert not cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200
        writes.append((port,value))
        if port==0x109:
            assert value==0xC1
            sio=value
        elif port==0x108 and value==0x55:
            stage=2
        elif port==0xD4 and value==0:
            stage=3
    def intr(cpu,number,_):
        nonlocal stage
        if number==0x13:
            assert cf8==initial_cf8
            assert cpu.reg_read(x.UC_X86_REG_DX)==0
            ah=cpu.reg_read(x.UC_X86_REG_AH)
            assert ah in (0,2)
            if ah==0:
                stage=max(stage,1)
            else:
                assert cpu.reg_read(x.UC_X86_REG_AX)==0x0201
                assert cpu.reg_read(x.UC_X86_REG_CX)==1
                address=cpu.reg_read(x.UC_X86_REG_ES)*16+cpu.reg_read(x.UC_X86_REG_BX)
                assert address%512==0 and address&65535<=0xFE00
                assert base+0x100<=address and address+512<=base+0x100+len(raw)
                read_stages.append(stage)
            ok=success==stage if ah==2 else True
            flags=cpu.reg_read(x.UC_X86_REG_EFLAGS)
            cpu.reg_write(x.UC_X86_REG_EFLAGS,(flags&~1)|int(not ok))
        else:
            assert number==0x21
            if cpu.reg_read(x.UC_X86_REG_AH)==9:
                address=cpu.reg_read(x.UC_X86_REG_DS)*16+cpu.reg_read(x.UC_X86_REG_DX)
                output.append(bytes(cpu.mem_read(address,8)).split(b'$')[0].decode())
            else:
                assert cpu.reg_read(x.UC_X86_REG_AH)==0x4C
                cpu.emu_stop()
    u.hook_add(UC_HOOK_INSN,inp,None,1,0,x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN,out,None,1,0,x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_INTR,intr)
    u.emu_start(base+0x100,0,count=20000)
    invalid=protected or host!=0x88811060 or bridge not in (0x886A1060,0x888A1060)
    expected='FX' if invalid else f'F{success if success<4 else 4}'
    assert output==[expected+'\r\n'],output
    assert cf8==initial_cf8
    if invalid:
        assert not writes and not read_stages
    else:
        assert read_stages==list(range(min(success,3)+1)),read_stages
        expected_writes=[]
        if success>=2:
            expected_writes += [(0x108,0xAA),(0x108,0xC2),(0x109,0xC1),(0x108,0x55)]
        if success>=3:
            expected_writes += [(0xD4,4),(0xD6,0xC0),(0xD2,0),(0xD4,0)]
        assert writes==expected_writes,writes
    return expected


def main():
    config=json.loads((PORT/'port.json').read_text())['platform']
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    image=PORT/'build/diagnostics/FWAKE.COM'
    subprocess.run([nasm,'-w+error','-f','bin',f'-DSIO_INDEX={config["sio_index"]}',
                    '-o',str(image),str(PORT/'diagnostics/floppy-wake.asm')],check=True)
    raw=image.read_bytes()
    rows=[check(raw,stage) for stage in range(5)]
    rows += [check(raw,0,host=0),check(raw,0,bridge=0),check(raw,0,protected=True),
             check(raw,2,bridge=0x886A1060)]
    result=dict(cases=rows,size=len(raw),SUM32=f'{sum(raw):08X}',sha256=hashlib.sha256(raw).hexdigest(),
                limits='BIOS/media and SIO/DMA effects are seams; physical recovery not yet tested.')
    out=PORT/'build/tests/floppy-wake'
    out.mkdir(parents=True,exist_ok=True)
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))


if __name__=='__main__':
    main()
