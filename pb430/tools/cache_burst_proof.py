"""Execute burst-policy code; synthetic devices do not model electrical cache bursts."""
import json
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x
from shared.tools.ram_proof import Listing


def check(image, case='success'):
    image=Path(image);raw=image.read_bytes();listing=Listing(image.with_suffix('.lst'))
    u=Uc(UC_ARCH_X86,UC_MODE_16);u.mem_map(0,0x1000000);u.mem_write(0xE0000,raw)
    u.mem_write(0x40E,(0x9E00).to_bytes(2,'little'))
    u.mem_write(0x9E060,bytes([0,1,1,1,1,0,0,0]))
    u.mem_write(0x9E0D0,(15360).to_bytes(2,'little'))
    u.mem_write(0x9F005,b'\x01\x01')
    if case=='l1-off':u.mem_write(0x9E061,b'\0')
    if case=='l2-off':u.mem_write(0x9E062,b'\0')
    if case=='unqualified':u.mem_write(0x9F005,b'\0')
    if case=='small':u.mem_write(0x9E0D0,(3072).to_bytes(2,'little'))
    original_cr0=0x60000010 if case in ('l1-off','disable-off') else 0x10
    regs={4:0x35 if case=='guard' else 0x1D if case in ('disable','disable-off','early') else 0x15,5:0x9C}
    index=0xA7;a20=0xFC;parity=0x22;posts=[];writes=[];injected=[];samples=[]
    initial={x.UC_X86_REG_EAX:0x12345678,x.UC_X86_REG_EBX:0x56781234,
             x.UC_X86_REG_ECX:0x13572468,x.UC_X86_REG_EDX:0x24681357,
             x.UC_X86_REG_ESI:0x11223344,x.UC_X86_REG_EDI:0x55667788,
             x.UC_X86_REG_EBP:0x12345678,x.UC_X86_REG_DS:0x1234,
             x.UC_X86_REG_ES:0x2345,x.UC_X86_REG_FS:0x9E00,x.UC_X86_REG_GS:0x3456}
    for reg,value in initial.items():u.reg_write(reg,value)
    u.reg_write(x.UC_X86_REG_CS,0xF000);u.reg_write(x.UC_X86_REG_SS,0x9000)
    u.reg_write(x.UC_X86_REG_ESP,0x5FFE);u.mem_write(0x95FFE,(0xFFF0).to_bytes(2,'little'))
    u.reg_write(x.UC_X86_REG_CR0,original_cr0);u.reg_write(x.UC_X86_REG_EFLAGS,0x202)
    original_gdtr=(0,0x900,0x47,0);u.reg_write(x.UC_X86_REG_GDTR,original_gdtr)
    low=bytes(u.mem_read(0,0x90000));firmware=bytes(u.mem_read(0x97000,0x69000))
    def inp(cpu,port,size,unused):
        assert size==1
        return {0xF2:index,0xF3:regs.get(index,0),0x92:a20,0x61:parity}[port]
    def out(cpu,port,size,value,unused):
        nonlocal index,a20,parity
        assert size==1
        assert not cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200 or case=='early'
        if port==0xF2:index=value
        elif port==0xF3:
            assert index in (4,5)
            if index==4:
                assert cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
                assert value in (0x15,0x1D)
                if case=='readback' and value==0x1D:value=0x15
                if case=='clear' and value==0x15 and regs[4]==0x1D:value=0x1D
            regs[index]=value;writes.append((index,value))
        elif port==0x92:a20=value
        elif port==0x61:parity=value
        elif port==0x80:
            posts.append(value)
            if value==0x7C:
                assert cpu.reg_read(x.UC_X86_REG_CR0)==original_cr0|1
                assert regs[4]==0x1D and a20&2
            if value>=0xE0:u.emu_stop()
        else:assert port==0xED,hex(port)
    def read(cpu,access,address,size,value,unused):
        assert not cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000
        samples.append(address)
        if case=='memory' and not injected:
            cpu.mem_write(address,bytes([cpu.mem_read(address,1)[0]^1]));injected.append(address)
    def write(cpu,access,address,size,value,unused):
        assert cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
        assert regs[4]==0x15,'Pattern must be written with stock cache control'
    u.hook_add(UC_HOOK_INSN,inp,None,1,0,x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN,out,None,1,0,x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_MEM_READ,read,begin=0x100000,end=0x100003)
    u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0x100000,end=0x100003)
    start=listing.symbol('chipset_burst_disable' if case.startswith('disable') else 'chipset_burst_policy')
    end=0xFFF0
    if case=='early':
        start=listing.symbol('.refresh_dma_ready','startup');end=listing.symbol('.burst_reset_ready','startup')
        u.reg_write(x.UC_X86_REG_CR0,0x60000010)
        decoded=Cs(CS_ARCH_X86,CS_MODE_16).disasm(raw[65536+start:65536+end],start)
        assert not any(i.mnemonic.startswith(('push','pop','call','ret')) for i in decoded)
    u.emu_start(0xF0000+start,0xF0000+end,count=100000000)
    assert bytes(u.mem_read(0,0x90000))==low
    assert bytes(u.mem_read(0x97000,0x69000))==firmware
    if case in ('readback','memory','clear','guard'):
        assert posts[-1]=={'readback':0xEC,'memory':0xED,'clear':0xE9,'guard':0xEF}[case],posts
        if case!='guard':assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
        assert regs[4]==(0x1D if case=='clear' else 0x35 if case=='guard' else 0x15)
    elif case=='early':
        assert regs[4]==0x15 and writes==[(4,0x15)]
        for reg in (x.UC_X86_REG_EDX,x.UC_X86_REG_EBP):assert u.reg_read(reg)==initial[reg]
        assert u.reg_read(x.UC_X86_REG_ESP)==0x5FFE
    else:
        assert u.reg_read(x.UC_X86_REG_IP)==end
        assert u.reg_read(x.UC_X86_REG_ESP)==0x6000
        assert u.reg_read(x.UC_X86_REG_CR0)==original_cr0
        assert u.reg_read(x.UC_X86_REG_EFLAGS)==0x202
        assert u.reg_read(x.UC_X86_REG_GDTR)==original_gdtr
        assert a20==0xFC and parity==0x22
        for reg,value in initial.items():assert u.reg_read(reg)==value,(case,reg)
        if case=='success':
            assert posts==[0x7A,0x7B,0x7C]*2+[0x7D] and samples==[0x100000]*2
            assert writes==[(5,0x9C),(4,0x1D),(4,0x15),(4,0x1D)]
            assert index==5 and regs[4]==0x1D
            for at in (0x100000,0x100004,0x10000C,0x2FFFFC,0x4FFFFC):
                assert int.from_bytes(u.mem_read(at,4),'little')==at^0x5AA55AA5
        elif case.startswith('disable'):assert writes==[(4,0x15)] and not posts
        else:assert posts==[0x7E] and writes==[(5,0x9C)]
    return {'case':case,'posts':posts,'writes':writes,'scope':'synthetic CPU and register checks; electrical bursts unmodelled'}


def verify(image):
    image=Path(image);raw=image.read_bytes()[65536:];listing=Listing(image.with_suffix('.lst'))
    def calls(start,end):
        return [int(i.op_str,16)&0xFFFF for i in Cs(CS_ARCH_X86,CS_MODE_16).disasm(raw[start:end],start) if i.mnemonic=='call']
    late=calls(listing.symbol('.clock_checked'),listing.symbol('.clock_checked')+90)
    assert late[late.index(listing.symbol('chipset_late_cache'))+1]==listing.symbol('chipset_burst_policy')
    reset=calls(listing.symbol('warm_reset'),listing.symbol('.reset_pulse_prepare','warm_reset'))
    assert reset[0]==listing.symbol('chipset_burst_disable')
    assert reset.index(listing.symbol('chipset_burst_disable'))<reset.index(listing.symbol('cache_stock_controller_high'))<reset.index(listing.symbol('cache_stock_reset'))
    apply=calls(listing.symbol('chipset_apply'),listing.symbol('chipset_apply')+50)
    assert apply[0]==listing.symbol('chipset_burst_disable')
    return [check(image,case) for case in ('success','readback','memory','clear','guard','l1-off','l2-off','unqualified','small','disable','disable-off','early')]
