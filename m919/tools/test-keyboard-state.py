"""Build and check the read-only keyboard snapshot used around Windows exit."""
import os
from pathlib import Path
import shutil
import struct
import subprocess

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INTR, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT=Path(__file__).resolve().parents[1]


def main():
    folder=PORT/'build/diagnostics';folder.mkdir(parents=True,exist_ok=True)
    image=folder/'KBSTATE.COM'
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    subprocess.run([nasm,'-w+error','-f','bin','-o',str(image),str(PORT/'diagnostics/keyboard-state.asm')],check=True)
    batch=(PORT/'diagnostics/KBWIN.BAT').read_bytes().replace(b'\r\n',b'\n')
    (folder/'KBWIN.BAT').write_bytes(batch.replace(b'\n',b'\r\n'))
    cases=[('normal',0,0,0x10,0x1E,0x1E,0,0,'K0000'),
           ('alt held',8,2,0x10,0x1E,0x1E,0,0,'K8200'),
           ('right Ctrl',4,0,0x14,0x1E,0x1E,0,0,'K4040'),
           ('invalid head',0,0,0x10,0x40,0x1E,0,0,'K0001'),
           ('full ring',0,0,0x10,0x1E,0x3C,0,0,'K0002'),
           ('pause owners',0,0,0x10,0x1E,0x1E,1,1,'K000C')]
    for name,f1,f2,ext,head,tail,paused,owner,expected in cases:
        cpu=Uc(UC_ARCH_X86,UC_MODE_16);cpu.mem_map(0,0x100000)
        cpu.mem_write(0x10100,image.read_bytes())
        for at,value in ((0x417,f1),(0x418,f2),(0x496,ext),(0x4A7,paused),(0x4A6,owner)):
            cpu.mem_write(at,bytes((value,)))
        for at,value in ((0x41A,head),(0x41C,tail),(0x480,0x1E),(0x482,0x3E)):
            cpu.mem_write(at,struct.pack('<H',value))
        bda=bytes(cpu.mem_read(0x400,256));output=[];exit_status=[]
        def irq(u,number,unused):
            assert number==0x21
            ax=u.reg_read(x.UC_X86_REG_AX)
            if ax>>8==9:
                at=(u.reg_read(x.UC_X86_REG_DS)<<4)+u.reg_read(x.UC_X86_REG_DX)
                output.append(bytes(u.mem_read(at,256)).split(b'$',1)[0].decode('ascii'))
            else:
                assert ax>>8==0x4C
                exit_status.append(ax&255);u.emu_stop()
        def write(u,access,address,size,value,unused):
            assert address+size<=0x400 or address>=0x500,('BDA write',hex(address))
        cpu.hook_add(UC_HOOK_INTR,irq);cpu.hook_add(UC_HOOK_MEM_WRITE,write)
        for register,value in (('CS',0x1000),('IP',0x100),('DS',0x1000),('ES',0x1000),('SS',0x1000),('SP',0xFFFE),('EFLAGS',0x202)):
            cpu.reg_write(getattr(x,'UC_X86_REG_'+register),value)
        cpu.emu_start(0x10100,0x20000,count=10000)
        assert exit_status==[0] and len(output)==1 and output[0].startswith(expected+' '),(name,output)
        assert bytes(cpu.mem_read(0x400,256))==bda
    print(f'PASS {len(cases)} keyboard snapshots, code meanings and no BDA writes; {image}')


if __name__=='__main__':main()
