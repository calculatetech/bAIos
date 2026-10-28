"""Build ACCORDER and check actual COM control flow with synthetic devices.

Synthetic PIT values verify arithmetic, not physical throughput or stability.
"""
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
BASELINE = {0:0xA9, 1:0xBF, 4:0x15, 5:0x9F, 6:0xB7, 0x0B:4,
            0x12:9, 0x18:0, 0x1A:0x24, 0x1D:0xF0, 0x1E:0x7B}


def symbols(listing):
    """Read NASM listing offsets; listed offsets exclude COM origin."""
    lines = listing.splitlines()
    result = {}
    names = ['operation', 'order_phase', 'order_column', 'order_measure', 'order_pointer',
             'ticks', 'protected_chunk', '.order_read', '.order_load', '.order_pointer_bad',
             'order_main', 'phase', 'real_chunk', 'order_l2']
    for name in names:
        pattern = re.compile(r'(?<![\w.])' + re.escape(name) + r'(?:[: ]+)(?:db|dd|dw|$)')
        for index, line in enumerate(lines):
            if pattern.search(line.strip()):
                for following in lines[index:]:
                    match = re.match(r'\s*\d+ ([0-9A-F]{8}) ', following)
                    if match:
                        result[name] = 0x100 + int(match.group(1), 16)
                        break
                break
        assert name in result, name
    return result


def run_case(raw, sym, case):
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x1000000)
    u.mem_write(0x20100, raw)
    argument = b' H' if case == 'argument' else b''
    u.mem_write(0x20080, bytes([len(argument)]) + argument)
    for reg in (x.UC_X86_REG_CS,x.UC_X86_REG_DS,x.UC_X86_REG_ES,x.UC_X86_REG_SS):
        u.reg_write(reg,0x2000)
    u.reg_write(x.UC_X86_REG_SP,0xFFFE)
    u.reg_write(x.UC_X86_REG_EFLAGS,0x23202 if case=='protected-mode' else 0x202)
    u.reg_write(x.UC_X86_REG_CR0,0x11 if case=='protected-mode' else 0x10)
    gdtr = (0,0x900,0x47,0)
    u.reg_write(x.UC_X86_REG_GDTR,gdtr)
    for address, data in ((0xFFFFC,b'LOW!'),(0x500000,b'HIGH'),(0x500,b'GATE')):
        u.mem_write(address,data)
    registers = dict(BASELINE)
    if case in ('off-128','off-512-admission'):
        registers.update({4:0x14,0x1A:0x2C,0x1E:0x5B,0x0B:0x15})
    if case in ('off-128','on-128-admission'):
        registers.update({0x1D:0xFC,0x1E:0x59 if case=='off-128' else 0x79})
    if case=='wrong-pair': registers[0x1A]=0x2C
    if case=='wrong-cache': registers[4]=0x1D
    if case=='wrong-write': registers[0x0B]=5
    if case=='wrong-refresh': registers[5]=0x9D
    selector,a20,parity=0xA7,0xFC,0x22
    pit_bytes=[]
    output=bytearray()
    exits=[]
    samples=0
    walks={}
    verified=[]
    injected=False
    kernel_entries=0
    decoder=Cs(CS_ARCH_X86,CS_MODE_16)
    decoder.detail=True
    expected_next=None

    def byte(name): return u.mem_read(0x20000+sym[name],1)[0]
    def dword(name): return struct.unpack('<I',u.mem_read(0x20000+sym[name],4))[0]

    def validate_chain(column):
        scratch = bytes(u.mem_read(0x100000,0x400000))
        pointer=0x100000
        seen=bytearray(0x40000)
        for n in range(0x40000):
            expected = 0x100000 + ((n%1024)*4096 + (n//1024)*16 if column else n*16)
            assert pointer==expected,(case,n,hex(pointer),hex(expected))
            i=(pointer-0x100000)//16
            assert not seen[i]
            seen[i]=1
            pointer=struct.unpack_from('<I',scratch,pointer-0x100000)[0]
        assert pointer==0x100000 and all(seen)
        verified.append(column)

    def enter_kernel(machine,address,size,_):
        nonlocal injected,kernel_entries
        kernel_entries+=1
        if case=='memory-error' and byte('operation')==1 and not injected:
            machine.mem_write(0x100000,struct.pack('<I',0x100020));injected=True

    def enter_read(machine,address,size,_):
        nonlocal injected
        phase=byte('order_phase')
        if phase not in walks:
            validate_chain(byte('order_column'))
            walks[phase]=0
            if (case.startswith('pointer-') and case!='pointer-endpoint') or case in ('cycle','cycle-self'):
                bad={'pointer-low':0xFFFF0,'pointer-high':0x500000,'pointer-alignment':0x100001,'cycle':0x100010,'cycle-self':0x100000}[case]
                machine.mem_write(0x100000,struct.pack('<I',bad))
                if case=='cycle':machine.mem_write(0x100010,struct.pack('<I',bad))
                injected=True
        walks[phase]+=1
        if case=='pointer-endpoint' and walks[phase]==256:
            machine.mem_write(0x4FFFF0,struct.pack('<I',0x500000));injected=True

    def memory_read(machine,access,address,size,value,_):
        nonlocal injected
        if case=='bad-a20':
            if not injected and machine.mem_read(0x100500,4)==bytes([255])*4:
                machine.mem_write(0x500,bytes([255])*4);injected=True
            return
        if case.startswith('pointer-'):
            bad={'pointer-low':0xFFFF0,'pointer-high':0x500000,'pointer-alignment':0x100001,'pointer-endpoint':0x500000}[case]
            ip=machine.reg_read(x.UC_X86_REG_IP)
            insn=next(decoder.disasm(bytes(machine.mem_read(0x20000+ip,15)),ip,count=1))
            # The intentional A20 witness at 100500 and untimed verification
            # are separate. No pointer-load may touch the rejected pointer.
            if insn.mnemonic=='mov' and insn.op_str=='esi, dword ptr es:[esi]':
                assert address!=bad,('Dereferenced rejected pointer',hex(address))

    def local_write(machine,access,address,size,value,_):
        if not machine.reg_read(x.UC_X86_REG_CR0)&1 or machine.reg_read(x.UC_X86_REG_EFLAGS)&0x20000:return
        ip=machine.reg_read(x.UC_X86_REG_IP)
        insn=next(decoder.disasm(bytes(machine.mem_read(0x20000+ip,15)),ip,count=1))
        if insn.mnemonic=='mov' and insn.op_str in ('es, ax','ds, ax'):
            # CPU sets descriptor accessed bits while loading segment caches.
            assert machine.reg_read(x.UC_X86_REG_GDTR)[1]<=address<machine.reg_read(x.UC_X86_REG_GDTR)[1]+32
            return
        assert insn.mnemonic not in ('push','call'),'Stack write in protected chunk'
        assert 0x2E not in insn.prefix,'#GP: write through CS'
        selector=machine.reg_read(x.UC_X86_REG_DS)
        descriptor=bytes(machine.mem_read(machine.reg_read(x.UC_X86_REG_GDTR)[1]+selector,8))
        assert descriptor[5]&0x9A==0x92,('Local state needs writable DS',hex(ip),insn.mnemonic,insn.op_str,hex(selector),hex(address))

    def input_port(machine,port,size,_):
        assert size==1
        if port==0xF2:return selector
        if port==0xF3:return registers.get(selector,0)
        if port==0x78:return 0x1D
        if port==0x92:return a20
        if port==0x61:return parity
        if port==0x40:
            assert pit_bytes
            return pit_bytes.pop(0)
        raise AssertionError(('unexpected IN',hex(port)))

    def output_port(machine,port,size,value,_):
        nonlocal selector,a20,parity,samples,expected_next
        assert size==1
        assert port!=0xF3,'Chipset configuration write in ACCORDER'
        if port==0xF2:selector=value
        elif port==0xED:pass
        elif port==0x92:
            assert value in (0xFC,0xFE)
            a20=value
        elif port==0x61:
            assert value in (0x22,0x2E)
            parity=value
        elif port==0x43:
            assert not pit_bytes
            if value==0xE2:pit_bytes.append(0x34 if case=='wrong-pit' else 0x36)
            else:
                assert value==0
                assert machine.reg_read(x.UC_X86_REG_CR0)&1
                assert not machine.reg_read(x.UC_X86_REG_EFLAGS)&0x200
                samples+=1
                if samples%2:
                    start=machine.reg_read(x.UC_X86_REG_ESI)
                    column=byte('order_column')
                    expected_next=(0x100000+((start-0x100000+16)&0xFFF)) if column else (0x100000+((start-0x100000+0x4000)&0x3FFFFF))
                elif not injected:
                    assert machine.reg_read(x.UC_X86_REG_ECX)==0
                    assert machine.reg_read(x.UC_X86_REG_ESI)==expected_next
                count=0xF000 if samples%2 or case=='stopped-timer' else 0xE830
                pit_bytes.extend((count&255,count>>8))
        else:raise AssertionError(('unexpected OUT',hex(port),value))

    def interrupt(machine,number,_):
        ax=machine.reg_read(x.UC_X86_REG_AX)
        flags=machine.reg_read(x.UC_X86_REG_EFLAGS)&~1
        if number==0x2F:machine.reg_write(x.UC_X86_REG_AX,0x4380 if case=='xms' else 0x4300)
        elif number==0x15:machine.reg_write(x.UC_X86_REG_AX,3072 if case=='little-memory' else 15360)
        elif number==0x21 and ax>>8==0x40:
            assert selector==0xA7 and a20==0xFC and parity==0x22
            assert machine.reg_read(x.UC_X86_REG_GDTR)==gdtr
            assert machine.reg_read(x.UC_X86_REG_CR0)==(0x11 if case=='protected-mode' else 0x10)
            assert machine.reg_read(x.UC_X86_REG_EFLAGS)&0x200
            count=machine.reg_read(x.UC_X86_REG_CX)
            data=bytes(machine.mem_read(machine.reg_read(x.UC_X86_REG_DS)*16+machine.reg_read(x.UC_X86_REG_DX),count))
            if case=='short-output':count-=1
            if case=='output-error':flags|=1
            if case.endswith('-admission') and b'PB430 address-order' in data:flags|=1
            if case=='result-output-error' and b'useful MiB/s;' in data:flags|=1
            output.extend(data[:count]);machine.reg_write(x.UC_X86_REG_AX,count)
        elif number==0x21 and ax>>8==0x4C:
            exits.append(ax&255);machine.emu_stop()
        else:raise AssertionError(('unexpected interrupt',number,hex(ax)))
        machine.reg_write(x.UC_X86_REG_EFLAGS,flags)

    u.hook_add(UC_HOOK_CODE,enter_kernel,begin=0x20000+sym['protected_chunk'],end=0x20000+sym['protected_chunk'])
    u.hook_add(UC_HOOK_CODE,enter_read,begin=0x20000+sym['.order_read'],end=0x20000+sym['.order_read'])
    u.hook_add(UC_HOOK_INSN,input_port,None,1,0,x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN,output_port,None,1,0,x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_INTR,interrupt)
    u.hook_add(UC_HOOK_MEM_WRITE,local_write,begin=0x20100,end=0x20100+len(raw)-1)
    u.hook_add(UC_HOOK_MEM_WRITE,local_write,begin=0x2F000,end=0x2FFFF)
    if case=='bad-a20':u.hook_add(UC_HOOK_MEM_READ,memory_read,begin=0x500,end=0x503)
    elif case.startswith('pointer-'):
        bad={'pointer-low':0xFFFF0,'pointer-high':0x500000,'pointer-alignment':0x100001,'pointer-endpoint':0x500000}[case]
        u.hook_add(UC_HOOK_MEM_READ,memory_read,begin=bad,end=bad+3)
    u.emu_start(0x20100,0,count=130000000)
    expected=0 if case in ('on-512','off-128') else 3 if case in ('short-output','output-error','result-output-error') or case.endswith('-admission') else 1 if case.startswith('pointer-') or case in ('memory-error','bad-a20','cycle','cycle-self','stopped-timer') else 2
    assert exits==[expected],(case,exits,output.decode(errors='replace'),hex(u.reg_read(x.UC_X86_REG_IP)))
    assert selector==0xA7 and a20==0xFC and parity==0x22
    assert u.reg_read(x.UC_X86_REG_GDTR)==gdtr
    assert u.reg_read(x.UC_X86_REG_CR0)==(0x11 if case=='protected-mode' else 0x10)
    assert u.reg_read(x.UC_X86_REG_EFLAGS)&0x200
    for address,data in ((0xFFFFC,b'LOW!'),(0x500000,b'HIGH'),(0x500,b'GATE')):
        assert bytes(u.mem_read(address,len(data)))==data
    text=output.decode('ascii')
    if expected==0:
        assert verified==[0,1,0] and walks=={0:1280,1:1280,2:1280}
        assert samples==7680 and text.count('4.6 useful MiB/s; pointer check OK.')==3
        assert ('L2: Off' if case=='off-128' else 'L2: On ') in text
        assert f'0B={registers[0x0B]:02X} 05={registers[5]:02X}' in text
    if case.startswith('pointer-') or case=='cycle':assert 'invalid pointer or chain endpoint' in text
    if case in ('memory-error','cycle-self'):assert 'RAM mismatch at 00100000' in text
    if case=='bad-a20':assert 'A20 address check' in text and samples==0
    if case=='stopped-timer':assert 'timer did not advance' in text
    if expected==1:assert 'Machine state restored' in text
    print(case+': PASS',flush=True)
    return {'case':case,'exit':expected,'pit_samples':samples,'verified_orders':verified,'kernel_entries':kernel_entries,'output':text}


def main():
    out=PORT/'build/diagnostics';out.mkdir(parents=True,exist_ok=True)
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    image=out/'ACCORDER.COM';listing=out/'ACCORDER.lst'
    subprocess.run([nasm,'-w+error','-f','bin','-DACC_ORDER','-I'+str(PORT/'diagnostics')+'/', '-l',str(listing),'-o',str(image),str(PORT/'diagnostics/acc-timing.asm')],check=True)
    raw=image.read_bytes();sym=symbols(listing.read_text())
    decoder=Cs(CS_ARCH_X86,CS_MODE_16)
    kernel=list(decoder.disasm(raw[sym['protected_chunk']-0x100:sym['order_main']-0x100],sym['protected_chunk']))
    all_code=list(decoder.disasm(raw[:sym['order_l2']-0x100],0x100))
    assert not any(i.mnemonic=='out' and '0xf3' in i.op_str for i in all_code)
    loop=list(decoder.disasm(raw[sym['.order_load']-0x100:sym['.order_pointer_bad']-0x100],sym['.order_load']))[:9]
    assert [i.mnemonic for i in loop]==['cmp','jb','cmp','jae','test','jne','mov','mov','loop']
    assert loop[-1].op_str==hex(sym['.order_load']) and loop[-1].bytes[0]==0x67
    assert any(i.mnemonic=='mov' and i.op_str=='ecx, 0x400' for i in kernel)

    load=[i for i in kernel if i.mnemonic=='mov' and i.op_str=='esi, dword ptr es:[esi]']
    assert len(load)==1,'Both orders must share one dependent-load instruction'
    normal=out/'ACCPROBE-normal-check.COM'
    subprocess.run([nasm,'-w+error','-f','bin','-o',str(normal),str(PORT/'diagnostics/acc-timing.asm')],check=True)
    baseline=normal.read_bytes()
    assert len(baseline)==3002 and sum(baseline)==0x4525E
    retained=out/'ACCPROBE.COM'
    if retained.exists():assert baseline==retained.read_bytes()
    normal.unlink()
    cases=['on-512','off-128','on-128-admission','off-512-admission','argument','protected-mode','xms','little-memory','wrong-pair','wrong-cache','wrong-write','wrong-refresh','wrong-pit','short-output','output-error','result-output-error','bad-a20','memory-error','pointer-low','pointer-high','pointer-alignment','pointer-endpoint','cycle','cycle-self','stopped-timer']
    rows=[run_case(raw,sym,case) for case in cases]
    result={'path':str(image),'size':len(raw),'sum32':f'{sum(raw):08X}','normal_accprobe_byte_identical':retained.exists(),'normal_size':len(baseline),'normal_sum32':f'{sum(baseline):08X}','checks':rows,'scope':'Synthetic assembled-code checks. No physical timing, refresh, cache or hardware stability proof.'}
    (out/'acc-order-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'{image}: {len(raw)} bytes, SUM32 {sum(raw):08X}')

if __name__=='__main__':main()
