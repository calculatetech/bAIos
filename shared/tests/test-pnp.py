"""Independent scanner and far callers for the shared PnP BIOS interface."""
import argparse
import hashlib
import importlib.util
import json
import os
import re
from pathlib import Path
import struct
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from shared.tools.rom import build,verify
from shared.tools.stop_grant_proof import descriptor
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

spec=importlib.util.spec_from_file_location('pnp_settings',Path(__file__).with_name('test-pnp-settings.py'))
settings=importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)
PORTS=('m919','mp386','pb430','presario-800')
OUTPUT='build/tests/pnp-interface'
M919_MASKS=[0xF0,1,1,0x70,0x90,3,1,0xFF,0xFF,7,0x0F,0x7F,1,0x0F,1,0xFC,0xFF,0xFF,0x0F,1,0xFF,1,3,0x1F]


def prepare(port):
    if port=='presario-800':
        subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/port/'tools/build.ps1'),
                        '-OutputDirectory',OUTPUT+'/production'],check=True,stdout=sys.stderr)
        subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/port/'tools/build.ps1'),
                        '-OutputDirectory',OUTPUT,'-PnpInterfaceTest'],check=True,stdout=sys.stderr)
    elif port=='pb430':
        spec=importlib.util.spec_from_file_location('pnp_pb430_build',ROOT/port/'tools/build.py')
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
        owner.run(OUTPUT+'/production')
        owner.run(OUTPUT,defines=('EMULATOR_PNP_TEST',))
    else:
        build(port,OUTPUT+'/production')
        build(port,OUTPUT,('EMULATOR_PNP_TEST',))


def scan(raw):
    """No listing/symbol input: installation checks follow the public ROM contract."""
    return [raw[at:at+33] for at in range(0,len(raw)-32,16)
            if raw[at:at+4]==b'$PnP' and raw[at+4:at+6]==b'\x10\x21'
            and sum(raw[at:at+33])&255==0]


class Caller(settings.Settings):
    def __init__(self,port,mode='real',persistent=None,active=None,switches=0):
        self.switches=switches
        super().__init__(port,OUTPUT)
        fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
        self.cmos[:]=bytes.fromhex(fixture['cmos'])
        self.nvram[0x200:0x240]=bytes.fromhex(fixture['nvram_0200_023f'])
        if persistent is not None:self.cmos[:],self.nvram[:]=persistent
        self.call('settings_load')
        self.put('S_EXTENDED_KIB',struct.pack('<H',7168))
        if port=='m919':
            self.cpu.mem_write(self.base+0xDC,struct.pack('<I',7168))
        if active:active(self)
        # Dynamic EBDA relocation and a poisoned former allocation are intentional.
        live=bytes(self.cpu.mem_read(self.base,self.allocated))
        self.cpu.mem_write(self.base,b'\xD6'*self.allocated)
        self.base=0x90000
        self.cpu.mem_write(self.base,live)
        self.cpu.mem_write(0x40E,struct.pack('<H',self.base>>4))
        before=self.snapshot()
        live_state=bytes(self.cpu.mem_read(self.base,self.allocated))
        self.call('pnp_publish')
        assert self.snapshot()==before
        assert bytes(self.cpu.mem_read(self.base,self.allocated))==live_state,'Publication changed live/draft state'
        headers=scan(self.image.read_bytes())
        assert len(headers)==1,(port,len(headers))
        self.header=headers[0]
        assert self.header[6:9]==b'\x00\x00'+self.header[8:9]
        assert struct.unpack_from('<I',self.header,9)[0]==0
        assert struct.unpack_from('<H',self.header,15)[0]==0xF000
        assert struct.unpack_from('<I',self.header,19)[0]==0xF0000
        assert struct.unpack_from('<I',self.header,23)[0]==0
        assert struct.unpack_from('<HI',self.header,27)==(0x40,0x400)
        self.mode=mode
        self.buffer=0x2000 if mode=='real' else 0x58
        self.bios=0x40 if mode=='real' else 0x48
        self.stack=0x3000 if mode=='real' else 0x68
        self.code=0xF000 if mode=='real' else 0x28
        self.return_code=0x1000 if mode=='real' else 0x38
        self.stack_offset=0xABCD7080 if mode!='ss32' else 0x100D0
        if mode!='real':
            gdt=bytearray(0x78)
            for selector,base,length,access,flags in [
                (0x28,0xF0000,0x10000,0x9A,0),(0x38,0x10000,0x10000,0x9A,0),
                (0x48,0x400,0x10000,0x92,0),(0x58,0x20000,0x10000,0x92,0),
                (0x68,0x30000,0x30000 if mode=='ss32' else 0x10000,0x92,0x40 if mode=='ss32' else 0)]:
                gdt[selector:selector+8]=descriptor(base,length,access,flags)
            self.cpu.mem_write(0x6000,bytes(gdt))
            self.cpu.reg_write(x.UC_X86_REG_GDTR,(0,0x6000,len(gdt)-1,0))
            self.cpu.reg_write(x.UC_X86_REG_CR0,self.cpu.reg_read(x.UC_X86_REG_CR0)|1)
            # UC_MODE16 data-register setters retain real-mode bases. Use the
            # caller's real MOV instructions to load its nonidentity descriptors.
            self.cpu.reg_write(x.UC_X86_REG_CS,self.return_code)
            loader=b'\xFA\xB8\x58\x00\x8E\xD8\x8E\xC0\x8E\xE0\x8E\xE8\xB8\x68\x00\x8E\xD0'
            self.cpu.mem_write(0x10300,loader)
            self.cpu.emu_start(0x300+(self.return_code<<4),0x10300+len(loader),count=100)
        self.io=[]
        self.old_out=self.out
        self.cpu.mem_write(0x30000,b'\xB7'*0x1000)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE,self.rom_guard)
        self.public_active=False
        self.rom_low=0xC0000 if port in ('pb430','presario-800') else 0x100000-self.image.stat().st_size
        # Bound forbidden reads instead of hooking RETF's internal stack reads;
        # Unicorn's global read callback can overwrite its partially loaded IP.
        self.public_read_hook=self.cpu.hook_add(UC_HOOK_MEM_READ,self.public_memory,None,0x80000,0x91FFF)
        if mode=='ss32':
            self.cpu.hook_add(UC_HOOK_MEM_READ,self.public_memory,None,0x30000,0x30FFF)

    def rom_guard(self,cpu,access,address,size,value,_):
        assert address+size<=self.rom_low or address>=0x100000,('ROM write',hex(address))
        if self.public_active:self.public_memory(cpu,access,address,size,value,_)

    def public_memory(self,cpu,access,address,size,value,_):
        if not self.public_active:return
        for lo,hi in [(0x80000,0x82000),(self.base,self.base+self.allocated)]+([(0x30000,0x31000)] if self.mode=='ss32' else []):
            assert address+size<=lo or address>=hi,('public memory alias',self.mode,hex(address),size)

    def inp(self,cpu,port,size,unused):
        if hasattr(self,'io'):self.io.append(('in',port,size))
        if port==0x60 and getattr(self,'keybytes',None):return self.keybytes.pop(0)
        if port==0x5F:return self.switches
        if port==0x64:return 1 if getattr(self,'keybytes',None) else 0
        return super().inp(cpu,port,size,unused)

    def out(self,cpu,port,size,value,unused):
        if hasattr(self,'io'):self.io.append(('out',port,size,value))
        return super().out(cpu,port,size,value,unused)

    def interrupt(self,cpu,vector,unused):
        if vector==0x15:
            self.inject('int15',cpu.reg_read(x.UC_X86_REG_IP))
            return
        return super().interrupt(cpu,vector,unused)

    def inject(self,name,ip):
        cpu=self.cpu
        sp=(cpu.reg_read(x.UC_X86_REG_SP)-6)&65535
        cpu.mem_write((cpu.reg_read(x.UC_X86_REG_SS)<<4)+sp,
                      struct.pack('<HHH',ip,cpu.reg_read(x.UC_X86_REG_CS),cpu.reg_read(x.UC_X86_REG_EFLAGS)&65535))
        cpu.reg_write(x.UC_X86_REG_SP,sp)
        cpu.reg_write(x.UC_X86_REG_EFLAGS,cpu.reg_read(x.UC_X86_REG_EFLAGS)&~0x300)
        cpu.reg_write(x.UC_X86_REG_CS,0xF000)
        cpu.reg_write(x.UC_X86_REG_IP,self.listing.symbol(name))

    def far(self,function,args=()):
        cpu=self.cpu
        registers=dict(EAX=0x1234A55A,EBX=0x87654321,ECX=0xABCD1234,EDX=0x76543210,
                       ESI=0x24681357,EDI=0x13572468,EBP=0x19283746,
                       DS=self.buffer,ES=self.buffer,FS=self.buffer,GS=self.buffer,
                       SS=self.stack,CS=self.code,ESP=self.stack_offset,EFLAGS=0xED7)
        for name,value in registers.items():
            if self.mode!='real' and name in ('DS','ES','FS','GS','SS'):continue
            cpu.reg_write(getattr(x,'UC_X86_REG_'+name),value)
        offset=self.stack_offset if self.mode=='ss32' else self.stack_offset&65535
        frame=struct.pack('<'+'H'*(3+len(args)),0x200,self.return_code,function,*args)
        lower=0x30000+offset-1041
        upper=0x30000+offset+len(frame)
        cpu.mem_write(lower,b'BEFORE-PNP-STACK!')
        cpu.mem_write(upper,b'AFTER-PNP-STACK!!')
        cpu.mem_write(0x30000+offset,frame)
        cpu.mem_write(0x10200,b'\xF4')
        before={name:cpu.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in registers}
        descriptor_state=tuple(cpu.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in ('CR0','GDTR','IDTR'))
        stopped=[]
        def stop(u,address,size,_):stopped.append(address);u.emu_stop()
        hook=cpu.hook_add(UC_HOOK_CODE,stop,None,0x10200,0x10200)
        self.public_active=True
        try:
            entry=struct.unpack_from('<H',self.header,13 if self.mode=='real' else 17)[0]
            cpu.emu_start((self.code<<4)+entry,0x100000,count=1000000)
        finally:
            self.public_active=False
            cpu.hook_del(hook)
        assert stopped,('far return missing',hex(cpu.reg_read(x.UC_X86_REG_IP)))
        result=cpu.reg_read(x.UC_X86_REG_AX)
        for name,value in before.items():
            actual=cpu.reg_read(getattr(x,'UC_X86_REG_'+name))
            expected=(value&0xFFFF0000|result) if name=='EAX' else value+4 if name=='ESP' else self.return_code if name=='CS' else value
            assert actual==expected,(self.port,self.mode,name,hex(actual),hex(expected))
        assert descriptor_state==tuple(cpu.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in ('CR0','GDTR','IDTR'))
        assert bytes(cpu.mem_read(lower,17))==b'BEFORE-PNP-STACK!'
        assert bytes(cpu.mem_read(upper,17))==b'AFTER-PNP-STACK!!'
        assert bytes(cpu.mem_read(0x30000+offset,len(frame)))==frame,'Caller argument/return frame changed'
        return result


def abi(port):
    for mode in ('real','ss16','ss32'):
        c=Caller(port,mode)
        c.cpu.mem_write(0x20100,b'\xCC'*16)
        assert c.far(0,[0x100,c.buffer,0x108,c.buffer,c.bios])==0
        raw=bytes(c.cpu.mem_read(0x20100,16))
        assert raw[1:8]==b'\xCC'*7 and raw[10:]==b'\xCC'*6
        assert 10<=raw[0]<=20 and struct.unpack_from('<H',raw,8)[0]>=40
        assert c.far(0x1234)==0x81
    return {'caller_modes':['real','ss16','ss32'],'full_state_preserved':True}


def get_node(c,handle,control=1):
    c.cpu.mem_write(0x20100,bytes([handle])+b'\xCC'*7)
    c.cpu.mem_write(0x20200,b'\xCC'*256)
    status=c.far(1,[0x100,c.buffer,0x200,c.buffer,control,c.bios])
    if status:return status,None,None
    length=struct.unpack('<H',c.cpu.mem_read(0x20200,2))[0]
    assert 18<=length<=128,length
    assert bytes(c.cpu.mem_read(0x20200+length,256-length))==b'\xCC'*(256-length)
    assert bytes(c.cpu.mem_read(0x20101,7))==b'\xCC'*7
    return 0,bytes(c.cpu.mem_read(0x20200,length)),c.cpu.mem_read(0x20100,1)[0]


def decode(node):
    assert struct.unpack_from('<H',node)[0]==len(node)
    vendor=int.from_bytes(node[3:5],'big')
    identity=''.join(chr(64+((vendor>>shift)&31)) for shift in (10,5,0))+node[5:7].hex().upper()
    blocks=[]
    at=12
    while at<len(node):
        block=[]
        while True:
            tag=node[at]
            if tag&128:
                length=int.from_bytes(node[at+1:at+3],'little');head=3
            else:length=tag&7;head=1
            end=at+head+length
            assert end<=len(node),(identity,at,tag,length,len(node))
            block.append((tag,node[at+head:end]))
            data=node[at+head:end]
            if tag==0x4B:assert int.from_bytes(data[:2],'little')<0x400,'FixedLocationIO reserved address bits'
            if tag==0x47:
                assert len(data)==7 and data[0] in (0,1)
                minimum=int.from_bytes(data[1:3],'little');maximum=int.from_bytes(data[3:5],'little')
                assert minimum==maximum and data[5]==0
                if minimum or data[6]:assert data[0]==1,'16-bit IO decode capability'
            at=end
            if tag==0x79:break
        blocks.append(block)
    assert len(blocks)==3,(identity,blocks)
    return identity,int.from_bytes(node[10:12],'little'),blocks


def keyboard(c):
    """The real IRQ1 E1 owner must coexist with the adjacent public snapshot."""
    assert c.mode=='real'
    cpu=c.cpu
    before=bytes(cpu.mem_read(0x4AD,83))
    cpu.mem_write(0x41A,struct.pack('<HH',0x1E,0x1E))
    cpu.mem_write(0x480,struct.pack('<HH',0x1E,0x3E))
    for name in ('KB_PAUSED','KB_PAUSE_OWNER','KB_POST_STATE','KB_E1_REMAIN','KB_EXT_FLAGS','KB_FLAGS'):
        cpu.mem_write(0x400+c.state[name],b'\0')
    c.keybytes=[0xE1,0x1D,0x45,0xE1,0x9D,0xC5,0x1E]
    e1=[]
    def memory(u,a,p,z,v,_):
        assert p+z<=0x4AD or p>=0x500,('IRQ1 overwrote PnP snapshot',hex(p))
        if p==0x4AC:e1.append(v)
    def nested(u,address,size,_):
        assert c.keybytes,'Pause did not consume the supplied scan sequence'
        c.inject('int09',(cpu.reg_read(x.UC_X86_REG_IP)+1)&65535)
    hlt=0xF0000+c.listing.symbol('.pause','int09')+1
    assert bytes(cpu.mem_read(hlt,1))==b'\xF4'
    hooks=[cpu.hook_add(UC_HOOK_MEM_WRITE,memory),cpu.hook_add(UC_HOOK_CODE,nested,None,hlt,hlt)]
    def run():
        for name,value in dict(CS=0x1000,IP=0x200,SS=0,ESP=0x7000,EFLAGS=0x202).items():
            cpu.reg_write(getattr(x,'UC_X86_REG_'+name),value)
        c.inject('int09',0x200)
        cpu.emu_start(0xF0000+c.listing.symbol('int09'),0x10200,count=1000000)
        assert cpu.reg_read(x.UC_X86_REG_CS)==0x1000 and cpu.reg_read(x.UC_X86_REG_IP)==0x200
    try:
        run()
        assert not c.keybytes and e1==[5,4,3,2,1,0],e1
        c.keybytes=[0x1E]
        run()
        assert bytes(cpu.mem_read(0x41E,2))==b'\x61\x1E','normal key decode after Pause'
    finally:
        for hook in hooks:cpu.hook_del(hook)
    assert bytes(cpu.mem_read(0x4AD,83))==before
    return {'actual_irq1_e1_and_normal_key':True,'AC_owner_preserved':True}


def decode_saved(c):
    """Independent bit-cursor decoder of the published physical NV6 record."""
    payload=bytes(c.logical(i) for i in settings.PAYLOAD_INDICES)
    assert c.logical(0x33)==ord('N') and c.logical(0x34)==6
    assert (ord('N')+6+sum(payload)+c.logical(0x35))&255==0
    count=4 if c.port=='m919' else 2
    ide=[1]+([63,3,15,1]+[255]*8)*count+([1,1] if count==4 else [])
    chip=M919_MASKS if count==4 else [255]*24
    result={};at=0
    for name,masks in [('C_IDE',ide),('C_PORTS',[7,7,1,3,3,1,1,1]),('C_CHIP',chip),('C_PNP',[255]*12+[15,1,1])]:
        bits=sum(mask.bit_count() for mask in masks)
        length=(bits+7)//8
        value=int.from_bytes(payload[at:at+length],'little')
        logical=[]
        for mask in masks:
            byte=0
            for bit in range(8):
                if mask&(1<<bit):byte|=(value&1)<<bit;value>>=1
            logical.append(byte)
        assert value==0,(name,'unused bits')
        result[name]=bytes(logical)
        at+=length
    assert not any(payload[at:])
    base=bytes(c.logical(i) for i in [0x10,*range(0x39,0x40)])
    assert c.logical(0x38)==ord('B') and base[1:3]==b'8\x05'
    assert (sum(base)+ord('B'))&255==0
    settings.at_checksum(c.cmos)
    return result,base,payload


def restarted(c):
    argv=[sys.executable,'-B',str(Path(__file__).resolve()),'--port',c.port,
          '--startup-cmos',bytes(c.cmos).hex(),'--startup-nv',bytes(c.nvram[0x200:0x240]).hex()]
    result=json.loads(subprocess.check_output(argv,cwd=ROOT,text=True).splitlines()[-1])
    for snapshot in result['snapshots']:
        cpu=Caller(c.port,'ss32',c.snapshot())
        cpu.cpu.mem_write(0x4AD,bytes.fromhex(snapshot))
        node=get_node(cpu,8,1)[1]
        expected=get_node(c,8,2)[1]
        assert node[12:19]==expected[12:19],(c.port,node.hex(),expected.hex())
        # Repeat IRQ1/Get on the actual POST-published snapshot.
        real=Caller(c.port,'real',c.snapshot())
        real.cpu.mem_write(0x4AD,bytes.fromhex(snapshot))
        before=get_node(real,8,1)[1]
        keyboard(real)
        assert get_node(real,8,1)[1]==before
    return result


def legacy_recovery(port):
    fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
    cmos=bytearray.fromhex(fixture['cmos']);nv=bytearray(0x10000)
    nv[0x200:0x240]=bytes.fromhex(fixture['nvram_0200_023f'])
    expected={key:bytearray.fromhex(value) for key,value in fixture['expected'].items()}
    if port=='m919':
        # Independent legacy P2/57 format, including saved DMA1 versus safe DMA3.
        expected['C_PORTS'][4]=2
        expected['C_CHIP'][22]|=2
        def pack(values,masks,length):
            bits=[(value>>bit)&1 for value,mask in zip(values,masks) for bit in range(8) if mask&(1<<bit)]
            return sum(value<<at for at,value in enumerate(bits)).to_bytes(length,'little')
        cmos[0x6F:0x71]=pack(expected['C_PORTS'],[7,7,1,3,3,1,1,1],2)
        cmos[0x6E]=(-sum(cmos[0x6C:0x6E])-sum(cmos[0x6F:0x71]))&255
        cmos[0x73:0x80]=pack(expected['C_CHIP'],M919_MASKS,13)
        cmos[0x72]=(-0x57-sum(cmos[0x73:0x80]))&255
        cmos[0x71]=0xD2
    elif port=='mp386':nv[0x229]=0xD2
    else:cmos[0x69]=0xD2
    initial=Caller(port,'real',(bytes(cmos),bytes(nv)))
    state=startup_result(initial)
    cmos=bytes.fromhex(state['cmos']);nv[0x200:0x240]=bytes.fromhex(state['nvram_0200_023f'])
    caller=Caller(port,'ss32',(cmos,bytes(nv)))
    caller.cpu.mem_write(0x4AD,bytes.fromhex(state['snapshots'][-1]))
    safe=caller.get('C_CHIP',24)
    assert safe!=bytes(expected['C_CHIP']),'Recovery contrast did not select different effective timings'
    caller.put('U_CHIP',b'\xCA'*24)
    caller.put('U_PNP',b'\xDB'*15)
    draft=bytes(caller.cpu.mem_read(caller.base,caller.allocated))
    caller.cmos[0x36]=0xAB
    prior=caller.snapshot()
    original=get_node(caller,8,1)[1]
    request=bytearray(get_node(caller,8,2)[1])
    if port!='mp386':request[13:16]=b'\xF8\x03\x08';request[17:19]=b'\x10\0';expected['C_PORTS'][0]=1
    caller.cpu.mem_write(0x20200,bytes(request))
    assert caller.far(2,[0xCD08,0x200,caller.buffer,2,caller.bios])==0
    decoded,base,payload=decode_saved(caller)
    assert all(decoded[key]==bytes(value) for key,value in expected.items()),(port,decoded,expected)
    assert caller.logical(0x69)==0xD2 and caller.cmos[0x36]==0xAB
    assert bytes(caller.cpu.mem_read(caller.base,caller.allocated))==draft
    assert get_node(caller,8,1)[1]==original
    settings.check_mutation(port,prior,caller.snapshot(),caller.writes,'settings_save')
    if port=='m919':
        current=decode(get_node(caller,10,1)[1])[2][0]
        saved=decode(get_node(caller,10,2)[1])[2][0]
        assert [d[0] for t,d in current if t==0x2A]==[8]
        assert [d[0] for t,d in saved if t==0x2A]==[2]
    reset=restarted(caller)
    return {'raw_saved_timings_preserved':True,'safe_live_state_and_drafts_preserved':True,
            'prior_D2_and_36_preserved':True,'post_publication':state['publication_boundaries'],
            'reset':reset}


def startup_result(c):
    argv=[sys.executable,'-B',str(Path(__file__).resolve()),'--port',c.port,
          '--startup-cmos',bytes(c.cmos).hex(),'--startup-nv',bytes(c.nvram[0x200:0x240]).hex()]
    return json.loads(subprocess.check_output(argv,cwd=ROOT,text=True).splitlines()[-1])


def invalid_next(port):
    """A failed NV6 read must restore all74 frozen bytes, never its dirty scratch."""
    fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
    producer=settings.Settings(port,OUTPUT)
    producer.cmos[:]=bytes.fromhex(fixture['cmos'])
    producer.nvram[0x200:0x240]=bytes.fromhex(fixture['nvram_0200_023f'])
    producer.call('settings_load');producer.call('setup_defaults');producer.draft()
    producer.put('U_PNP',bytes.fromhex('0884A20003200010031000050A0101'))
    assert producer.call('settings_save')
    for failure in ('checksum','padding'):
        c=Caller(port,'ss32',producer.snapshot())
        good,base,payload=decode_saved(c)
        expected=get_node(c,8,2)[1]
        current=get_node(c,8,1)[1]
        frozen=bytes(c.cpu.mem_read(0x4AD,83))
        for index in settings.PAYLOAD_INDICES:
            if port=='mp386' and index>=0x40:c.nvram[0x200+index-0x40]=255
            else:c.cmos[index]=255
        c.cmos[0x35]=(-ord('N')-6-66*255+(failure=='checksum'))&255
        for index in (0x10,*range(0x39,0x40)):c.cmos[index]=255
        c.put('U_PORTS',b'\xCE'*8);c.put('U_PNP',bytes(15))
        before=c.snapshot();c.writes.clear()
        assert get_node(c,8,2)[1]==expected and get_node(c,8,1)[1]==current
        assert c.snapshot()==before and not c.writes
        c.cpu.mem_write(0x20200,expected)
        assert c.far(2,[8,0x200,c.buffer,2,c.bios])==0
        actual,actual_base,actual_payload=decode_saved(c)
        assert actual==good and actual_base==base and actual_payload==payload
        assert bytes(c.cpu.mem_read(0x4AD,83))==frozen
        settings.check_mutation(port,before,c.snapshot(),c.writes,'settings_save')
    return {'checksum_and_padding_CF_fallback':True,'full74B_preserved_on_Get_and_Set':True,
            'no_load_writes_and_current_unchanged':True,'complete_republication_verified':True}


def information_services_mode(port,mode):
    c=Caller(port,mode)
    before=c.snapshot()
    for fn in (*range(3,11),0x41,0x42,0x43):assert c.far(fn)==0x82,fn
    for fn in (0x0C,0x3F,0x44,0xFFFF):assert c.far(fn)==0x81,fn
    for capacity in (0,1,0xFFFF):
        c.cpu.mem_write(0x20100,struct.pack('<H',capacity)+b'\xCC'*6)
        c.cpu.mem_write(0x20200,b'\xA6'*16)
        assert c.far(0x0B,[0x100,c.buffer,0x200,c.buffer,c.bios])==0
        assert bytes(c.cpu.mem_read(0x20100,8))==b'\0\0'+b'\xCC'*6
        assert bytes(c.cpu.mem_read(0x20200,16))==b'\xA6'*16
    c.cpu.mem_write(0x20100,b'\xCC'*12)
    assert c.far(0x40,[0x100,c.buffer,c.bios])==0
    assert bytes(c.cpu.mem_read(0x20100,12))==b'\x01'+bytes(5)+b'\xCC'*6
    for control in (0,3,4,0xFFFF):assert get_node(c,0,control)[0]==0x84,control
    for handle in (0xFE,0xFF):assert get_node(c,handle)[0]==0x83,handle
    assert c.snapshot()==before and not c.writes
    assert not c.io,'Information services performed hardware I/O'
    return {'exact_statuses':True,'empty_apm':True,'zero_isa':True,'no_persistent_writes':True}


def information_services(port):
    return {mode:information_services_mode(port,mode) for mode in ('real','ss16','ss32')}


def m919_resources(c):
    sys.path.insert(0,str(ROOT/'m919/tools'))
    import sio_proof
    from geometry_proof import invoke
    hardware,fixture=sio_proof.peripheral_fixture(c.image)
    u,d,listing,state,cmos,step=fixture
    base=0x9E000
    tested=[]
    for address,selector,irq,c1,c3 in [(0x378,2,7,8,0),(0x278,3,5,0,0x20)]:
        for mode in range(3):
            for dma in (0,2):
                for incoming in (0,255):
                    ports=bytes((1,2,1,selector,mode,1,0,1))
                    for at,value in enumerate(ports):d.write(base+state['C_PORTS']+at,1,value)
                    d.write(base+state['C_CHIP']+22,1,dma)
                    hardware.sio[0xC0]=incoming;hardware.sio[0xC1]=incoming;hardware.sio[0xC3]=incoming
                    invoke(fixture,'ports_apply')
                    assert hardware.sio[0xC0]&0xD0==incoming&0xD0
                    assert hardware.sio[0xC1]&0x30==incoming&0x30
                    assert hardware.sio[0xC1]&8==c1 and hardware.sio[0xC3]&0x30==c3
                    expected=(incoming&0xCF)|c3
                    if mode==2:expected=(expected&0xBF)|((dma&2)<<5)
                    assert hardware.sio[0xC3]==expected
                    invoke(fixture,'pnp_publish')
                    c.cpu.mem_write(0x4AD,d.read(0x4AD,83))
                    node=get_node(c,10,1)[1]
                    identity,attributes,blocks=decode(node)
                    assert identity==('PNP0401' if mode==2 else 'PNP0400')
                    io=[(int.from_bytes(data[:2],'little'),data[2]) if tag==0x4B else
                        (int.from_bytes(data[1:3],'little'),data[6]) for tag,data in blocks[0] if tag in (0x4B,0x47)]
                    assert io==[(address,8 if mode==1 else 3),(address+0x400,3) if mode==2 else (0,0)],io
                    assert [int.from_bytes(data,'little') for tag,data in blocks[0] if tag==0x22]==[1<<irq]
                    assert [data[0] for tag,data in blocks[0] if tag==0x2A]==[(2 if dma else 8) if mode==2 else 0]
                    assert [data[1] for tag,data in blocks[0] if tag==0x2A]==[8]
                    high=next(data for tag,data in blocks[0] if tag==0x47)
                    assert high[0]==1 and high[1:3]==high[3:5] and high[5]==0
                    tested.append((selector,mode,dma,incoming))
    invalid=settings.Settings('m919',OUTPUT)
    invalid.call('settings_load')
    ports=bytearray(invalid.get('C_PORTS',8));ports[3]=1
    invalid.put('U_PORTS',ports)
    assert not invalid.call('ports_valid',SI=invalid.state['U_PORTS'])
    return {'actual_full_tuples_and_resource_nodes':len(tested),'hidden_3bc_rejected':True}


def inventory(port):
    common=['PNP0000','PNP0100','PNP0200','PNP0303' if port in ('pb430','presario-800') else 'PNP0301',
            'PNP0B00','PNP0800','PNP0C01','PNP0A00','PNP0500']
    if port!='presario-800':common+=['PNP0500']
    return common+['PNP0400','PNP0700','PNP0600']+(['PNP0A03'] if port=='m919' else
           ['PNP0900','PNP0F13'] if port in ('pb430','presario-800') else [])


def resource_oracle(port,ports,ide_enabled,secondary=True,ram_end=0x800000,dma1=False):
    """Independent AT/controller resource tuples, without ROM templates or C-byte decoding."""
    def io(base,length,wide=False):
        return (0x47,bytes((1,))+struct.pack('<HHBB',base,base,0,length)) if wide else (0x4B,struct.pack('<HB',base,length))
    def irq(mask):return (0x22,struct.pack('<H',mask))
    def mem(base,length):return (0x86,b'\x01'+struct.pack('<II',base,length))
    def zero(items):return [(tag,bytes(len(data))) for tag,data in items]
    def uart(value):
        pair=((0x338,0x238),(0x3E8,0x2E8))[ports[2]]
        base=(0,0x3F8,0x2F8,*pair)[value]
        return [io(base,8),irq(16 if value&1 else 8)] if value else [io(0,0),irq(0)]
    resources=[[io(0x20,2),io(0xA0,2),irq(4)],[io(0x40,4),irq(1)],
               [io(0,16),io(0x80,16),io(0xC0,32),(0x2A,b'\x10\x02')],
               [io(0x60,1),io(0x64,1),irq(2)],[io(0x70,2),irq(0x100)],
               [io(0x61,1)],[mem(0,0xA0000),mem(0x100000,ram_end-0x100000)],[],uart(ports[0])]
    if port!='presario-800':resources+=[uart(ports[1])]
    base=(0,0x3BC,0x378,0x278)[ports[3]]
    lpt=[io(base,(8 if ports[4]==1 else 3) if port=='m919' else 3),
         irq(0x20 if port=='pb430' or (port=='m919' and ports[3]==3) else 0x80)]
    if port=='m919':lpt += [(0x2A,bytes(((2 if dma1 else 8) if ports[4]==2 else 0,8))),
                           io(base+0x400 if ports[4]==2 else 0,3 if ports[4]==2 else 0,True)]
    if not base:lpt=zero(lpt)
    fdc=[io(0x3F0,6),io(0x3F7,1),irq(0x40),(0x2A,b'\x04\x08')]
    if not ports[5]:fdc=zero(fdc)
    primary=[io(0x1F0,8),io(0x3F6,1),irq(0x4000)]
    if not ide_enabled:primary=zero(primary)
    if port=='m919':
        second=[io(0x170,8),io(0x376,1),irq(0x8000)]
        primary+=second if ide_enabled and secondary else zero(second)
    resources += [lpt,fdc,primary]
    if port=='m919':resources += [[io(0xCF8,8,True)]]
    elif port in ('pb430','presario-800'):
        resources += [[io(0x3B0,12),io(0x3C0,32),mem(0xA0000,0x20000)], [irq(0x1000 if ports[6] else 0)]]
    return resources


def complete_nodes(port):
    fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
    ports=bytes.fromhex(fixture['expected']['C_PORTS'])
    def verify(c,view,expected_ports,ide,secondary=True,dma1=False):
        resources=resource_oracle(port,expected_ports,ide,secondary,dma1=dma1)
        identities=inventory(port)
        if port=='m919' and expected_ports[4]==2:identities[10]='PNP0401'
        c.cpu.mem_write(0x20100,b'\xCC'*12)
        assert c.far(0,[0x100,c.buffer,0x108,c.buffer,c.bios])==0
        assert c.cpu.mem_read(0x20100,1)[0]==len(identities)
        assert bytes(c.cpu.mem_read(0x20101,7))==b'\xCC'*7
        assert int.from_bytes(c.cpu.mem_read(0x20108,2),'little')=={'m919':76,'mp386':42,'pb430':61,'presario-800':61}[port]
        handle=0
        for at,(identity,expected) in enumerate(zip(identities,resources)):
            status,node,handle=get_node(c,at,view)
            actual,attrs,blocks=decode(node)
            assert status==0 and actual==identity,(port,at,actual,identity)
            assert blocks[0]==expected+[(0x79,b'\0')],(port,view,at,blocks[0],expected)
            assert blocks[2]==[(0x79,b'\0')]
        assert handle==255
    c=Caller(port,'ss32')
    current=list(ports)
    if port=='mp386':current=[1,2,ports[2],1,ports[4],1,ports[6],ports[7]]
    verify(c,1,current,bool(c.cpu.mem_read(0x4FE,1)[0]&1),bool(c.cpu.mem_read(0x4FE,1)[0]&2))
    tested=['full_legacy_collection']
    # Fixed-switch resource branches use actual input reads at POST publication.
    if port=='mp386':
        for switch in (0,1,2,3,0x4C,0x10,0x5F):
            c=Caller(port,'ss32',switches=switch)
            values=[0 if switch&4 else 1,0 if switch&8 else 2,ports[2],(1,2,3,0)[switch&3],ports[4],0 if switch&64 else 1,ports[6],ports[7]]
            for view in (1,2):verify(c,view,values,not switch&16)
            tested.append(switch)
    else:
        # Verified saved policy differs from the explicit effective hardware state.
        producer=settings.Settings(port,OUTPUT)
        producer.cmos[:]=bytes.fromhex(fixture['cmos']);producer.nvram[0x200:0x240]=bytes.fromhex(fixture['nvram_0200_023f'])
        producer.call('settings_load');producer.draft()
        saved=bytearray(ports);saved[0]=0;saved[5]=0
        producer.put('U_PORTS',saved)
        ide=bytearray(producer.get('U_IDE',51 if port=='m919' else 25));ide[0]=0;producer.put('U_IDE',ide)
        assert producer.call('settings_save')
        def live(model):
            model.put('C_PORTS',ports)
            active=bytearray(model.get('C_IDE',len(ide)));active[0]=1;model.put('C_IDE',active)
            if port=='m919':model.cpu.mem_write(model.base+0x1039,b'\1')
        c=Caller(port,'ss32',producer.snapshot(),active=live)
        verify(c,1,ports,True,not bool(c.get('C_CHIP',24)[23]&16))
        verify(c,2,saved,False)
        tested.append('effective_enabled_vs_saved_disabled_UART_FDC_IDE')
        if port=='m919':
            for capable in (0,1):
                for enabled in (0,1):
                    for secondary in (0,1):
                        def active(model):
                            model.cpu.mem_write(model.base+0x1039,bytes((capable,)))
                            value=bytearray(model.get('C_IDE',51));value[0]=enabled;model.put('C_IDE',value)
                            value=bytearray(model.get('C_CHIP',24));value[23]=(value[23]&~16)|(0 if secondary else 16);model.put('C_CHIP',value)
                        c=Caller(port,'ss32',active=active)
                        verify(c,1,ports,bool(capable and enabled),bool(secondary))
                        verify(c,2,ports,bool(capable and enabled),
                               not bool(bytes.fromhex(fixture['expected']['C_CHIP'])[23]&16))
                        tested.append((capable,enabled,secondary))
    return {'exact_inventory_count_ids_all_allocated_resources':tested,'RAM_extent_source':7168}


def nodes(port):
    c=Caller(port,'ss32')
    c.cpu.mem_write(0x20100,b'\xCC'*12)
    assert c.far(0,[0x100,c.buffer,0x108,c.buffer,c.bios])==0
    count=c.cpu.mem_read(0x20100,1)[0]
    maximum=int.from_bytes(c.cpu.mem_read(0x20108,2),'little')
    handle=0
    result=[]
    for _ in range(count):
        status,node,next_handle=get_node(c,handle)
        assert status==0
        assert node[2]==handle
        identity,attributes,blocks=decode(node)
        result.append((identity,len(node),node,blocks))
        handle=next_handle
    assert handle==255 and maximum==max(r[1] for r in result),(maximum,[(r[0],r[1]) for r in result])
    assert not c.io,'Current-node query performed hardware I/O'
    ids=[r[0] for r in result]
    assert ids.count('PNP0500')==(1 if port=='presario-800' else 2),ids
    assert 'PNP0700' in ids and 'PNP0600' in ids and 'PNP0A00' in ids
    assert ('PNP0900' in ids)==(port in ('presario-800','pb430'))
    for identity,_,node,blocks in result:
        routing=3 if port=='mp386' else 0
        expected_attributes={'PNP0301':0x0B,'PNP0303':0x0B,'PNP0900':7,'PNP0600':0x13,
                             'PNP0700':routing|0x10,'PNP0500':routing,'PNP0400':routing,
                             'PNP0401':routing,'PNP0F13':0}
        assert int.from_bytes(node[10:12],'little')==expected_attributes.get(identity,3),(identity,node[10:12].hex())
        for tag,data in blocks[0]:
            if tag==0x4B:
                base=int.from_bytes(data[:2],'little');length=data[2]
                if identity=='PNP0700':assert not base<=0x3F6<base+length
                if identity=='PNP0900':assert not base<=0x3BC<base+length
            if tag==0x2A and identity in ('PNP0700','PNP0401'):
                assert not data[1]&4
                if data[0]:assert data[1]==8,'Byte-count slave DMA capability'
    real=Caller(port)
    before=[get_node(real,h)[1] for h in range(count)]
    irq=keyboard(real)
    assert [get_node(real,h)[1] for h in range(count)]==before
    routing=m919_resources(c) if port=='m919' else {}
    return {'count':count,'maximum':maximum,'identities':ids,'three_descriptor_blocks':True,'complete_independent_nodes':complete_nodes(port),**irq,**routing}


def public_commit_contracts(port):
    """Real and both PM stack forms use the complete public publication owner."""
    result={}
    for mode in ('real','ss16','ss32'):
        c=Caller(port,mode)
        c.put('U_CHIP',b'\xCB'*24);c.put('U_PNP',b'\xD7'*15)
        draft=bytes(c.cpu.mem_read(c.base,c.allocated))
        node=get_node(c,8,1)[1]
        saved=c.snapshot();frozen=bytes(c.cpu.mem_read(0x4AD,83))
        c.cpu.mem_write(0x20200,node);c.io.clear();c.writes.clear()
        assert c.far(2,[8,0x200,c.buffer,0,c.bios])==0x84
        assert c.far(2,[0xABFF,0x200,c.buffer,2,c.bios])==0x83
        assert c.far(2,[0xEF08,0x200,c.buffer,1,c.bios])==0
        assert not c.io and not c.writes and c.snapshot()==saved
        # A changed Current must reject before even reading a controller.
        changed=bytearray(node);changed[13:16]=b'\xE8\x03\x08';changed[17:19]=b'\x10\0'
        if changed[12:19]==node[12:19]:changed[13:16]=b'\xF8\x03\x08'
        c.cpu.mem_write(0x20200,bytes(changed));c.io.clear()
        assert c.far(2,[8,0x200,c.buffer,1,c.bios])==0x85
        assert not c.io and not c.writes and c.snapshot()==saved
        assert bytes(c.cpu.mem_read(0x4AD,83))==frozen
        # First legacy Both (also fixed MP) really commits the full record.
        assert c.logical(0x33)!=ord('N')
        c.cpu.mem_write(0x20200,node)
        assert c.far(2,[8,0x200,c.buffer,3,c.bios])==0
        decoded,base,payload=decode_saved(c)
        fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
        assert all(decoded[key]==bytes.fromhex(value) for key,value in fixture['expected'].items())
        assert base==bytes(saved[0][i] for i in [0x10,*range(0x39,0x40)])
        assert bytes(c.cpu.mem_read(c.base,c.allocated))==draft
        settings.check_mutation(port,saved,c.snapshot(),c.writes,'settings_save')
        assert get_node(c,8,1)[1]==node and get_node(c,8,2)[1]==node
        result[mode]={'unchanged_current_no_io':True,'changed_current_85_no_io':True,
                      'first_legacy_Both_complete_commit':True}
    failures=[]
    for control in (2,3):
        for recovery in (0,0xD2):
            c=Caller(port,'ss32')
            if port=='mp386':c.nvram[0x229]=recovery
            else:c.cmos[0x69]=recovery
            c.cmos[0x36]=0xAB
            c.put('U_CHIP',b'\xCA'*24);c.put('U_PNP',b'\xDE'*15)
            draft=bytes(c.cpu.mem_read(c.base,c.allocated));frozen=bytes(c.cpu.mem_read(0x4AD,83))
            node=get_node(c,8,1)[1];c.cpu.mem_write(0x20200,node)
            before=c.snapshot();c.writes.clear();c.fail=('cmos',0x33)
            assert c.far(2,[8,0x200,c.buffer,control,c.bios])==0x85
            assert c.writes,'Public failure never entered complete commit'
            assert c.logical(0x33)!=ord('N'),'Failed transaction was published'
            assert c.logical(0x69)==0xD2 and c.cmos[0x36]==0xAB
            assert bytes(c.cpu.mem_read(0x4AD,83))==frozen
            assert bytes(c.cpu.mem_read(c.base,c.allocated))==draft
            assert get_node(c,8,1)[1]==node and get_node(c,8,2)[1]==node
            settings.check_mutation(port,before,c.snapshot(),c.writes,'settings_save')
            failures.append((control,recovery))
    return {'caller_modes':result,'public_static_Both_verification_failures':failures}


def set_node(port):
    c=Caller(port,'ss32')
    status,node,_=get_node(c,8,2)
    assert status==0
    original=node
    fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
    expected={key:bytes.fromhex(value) for key,value in fixture['expected'].items()}
    c.put('U_PNP',bytes.fromhex('0080A20003200010031000050A0101'))
    c.put('U_PORTS',b'\x04\x03\x02\x03\x01\x00\x00\x01')
    c.put('U_IDE',b'\xC6'*(51 if port=='m919' else 25))
    draft=bytes(c.cpu.mem_read(c.base,c.allocated))
    before=c.snapshot()
    c.cpu.mem_write(0x20200,node)
    assert c.far(2,[0xAB08,0x200,c.buffer,0,c.bios])==0x84
    assert c.far(2,[0xABFF,0x200,c.buffer,2,c.bios])==0x83
    assert c.snapshot()==before
    if port=='mp386':
        changed=bytearray(node);changed[13:16]=b'\xE8\x03\x08'
        c.cpu.mem_write(0x20200,bytes(changed))
        assert c.far(2,[8,0x200,c.buffer,2,c.bios])==0x85
        assert c.snapshot()==before
        c.cpu.mem_write(0x20200,node)
        assert c.far(2,[0xAB08,0x200,c.buffer,2,c.bios])==0
    else:
        # First publication is a genuinely changed legacy resource request.
        request=bytearray(node)
        request[13:16]=b'\xF8\x03\x08'
        request[17:19]=b'\x10\x00'
        request[3:12]=b'\xD9'*9 # Extraneous identity/type/attribute metadata.
        c.cpu.mem_write(0x20200,bytes(request))
        assert c.far(2,[0xAB08,0x200,c.buffer,1,c.bios])==0x85
        assert c.snapshot()==before
        assert c.far(2,[0xAB08,0x200,c.buffer,2,c.bios])==0
        assert c.logical(0x33)==ord('N') and c.logical(0x34)==6
        status,next_node,_=get_node(c,8,2)
        assert status==0 and next_node[13:16]==b'\xF8\x03\x08' and next_node[17:19]==b'\x10\x00'
        status,current,_=get_node(c,8,1)
        assert status==0 and current==original
    decoded,base,payload=decode_saved(c)
    for key,value in expected.items():
        assert decoded[key]==(b'\x01'+value[1:] if key=='C_PORTS' and port!='mp386' else value),(port,key)
    assert decoded['C_PNP']==bytes(15)
    assert base==bytes(before[0][i] for i in [0x10,*range(0x39,0x40)])
    assert bytes(c.cpu.mem_read(c.base,c.allocated))==draft
    settings.check_mutation(port,before,c.snapshot(),c.writes,'settings_save')
    reset=restarted(c)
    if port!='mp386':
        c.cpu.mem_write(0x20200,original)
        assert c.far(2,[8,0x200,c.buffer,3,c.bios])==0
        assert get_node(c,8,2)[1]==original
    # Real Setup Save/Discard changes the same record owner and pending policy.
    ui=settings.Settings(port,OUTPUT)
    ui.cmos[:],ui.nvram[:]=c.snapshot()
    ui.call('settings_load')
    policy=settings.ui_checks(ui)
    for recovery in (0,0xD2):
        keep=Caller(port,'ss32',ui.snapshot())
        keep.cmos[0x36]=0xAB
        if port=='mp386':keep.nvram[0x229]=recovery
        else:keep.cmos[0x69]=recovery
        old,old_base,old_payload=decode_saved(keep)
        keep.put('U_PNP',bytes(15))
        keep.put('U_CHIP',b'\xCE'*24)
        request=get_node(keep,8,2)[1]
        keep.cpu.mem_write(0x20200,request)
        prior=keep.snapshot()
        assert keep.far(2,[8,0x200,keep.buffer,2,keep.bios])==0
        new,new_base,new_payload=decode_saved(keep)
        assert old==new and new_base==old_base and old_payload==new_payload
        assert new['C_PNP']==policy and keep.logical(0x69)==recovery and keep.cmos[0x36]==0xAB
        settings.check_mutation(port,prior,keep.snapshot(),keep.writes,'settings_save')
    # A later, differently shaped controller uses its own field and accepts the
    # complete zero-resource form with don't-care tag/attribute bytes.
    if port!='mp386':
        keep=Caller(port,'ss32',ui.snapshot())
        handle=10 if port=='presario-800' else 11
        original=get_node(keep,handle,2)[1]
        request=bytearray(original)
        for offset in (1,2,3,5,6,7,9,10,12):request[12+offset]=0
        for offset in (0,4,8,11,13):request[12+offset]=0xFF
        keep.cpu.mem_write(0x20200,bytes(request))
        before=keep.snapshot()
        assert keep.far(2,[handle,0x200,keep.buffer,1,keep.bios])==0x85
        assert keep.snapshot()==before
        broken=bytearray(request);broken[26]=0
        keep.cpu.mem_write(0x20200,bytes(broken))
        assert keep.far(2,[handle,0x200,keep.buffer,2,keep.bios])==0x84
        assert keep.snapshot()==before
        keep.cpu.mem_write(0x20200,bytes(request))
        assert keep.far(2,[handle,0x200,keep.buffer,2,keep.bios])==0
        disabled=decode(get_node(keep,handle,2)[1])[2][0]
        assert all(not any(data) for tag,data in disabled if tag!=0x79)
        keep.cpu.mem_write(0x20200,original)
        assert keep.far(2,[handle,0x200,keep.buffer,3,keep.bios])==0
        assert get_node(keep,handle,2)[1]==original
        assert decode_saved(keep)[0]['C_PNP']==policy
    recovery_proof=legacy_recovery(port)
    return {'first_legacy_publication':True,'by_value_byte_handle':True,
            'static_changed':port!='mp386','control3':port!='mp386','complete_checksum':True,
            'unrelated_saved_and_distinct_draft_preserved':True,'actual_setup_save_discard':True,
            'manual_clear_recovery_preserved':True,'reset':reset,'first_legacy_D2':recovery_proof,
            'invalid_nv6_next_fallback':invalid_next(port),'public_commit_contracts':public_commit_contracts(port),'causal_routing':causal_routing(port)}


def startup(port,cmos,nv,causal=False):
    """Real reset/application/publication, using the existing board hardware seams."""
    import importlib
    sys.path.insert(0,str(ROOT/port/'tools'))
    image=ROOT/port/OUTPUT/('baios-presario800-system.rom' if port=='presario-800' else f'baios-{port}.bin')
    saved=bytearray.fromhex(cmos)
    # The legacy fixture captures settings, not a live century clock provider.
    saved[0x32]=0x20
    saved=bytes(saved)
    publication_listing=settings.Listing(image.with_suffix('.lst'))
    publication_begin=0xF0000+publication_listing.symbol('pnp_publish')
    publication_end=0xF0000+publication_listing.symbol('post_debug_summary')
    startup_end=(publication_end if port in ('presario-800','m919') else
                 0xF0000+publication_listing.symbol('int19'))
    progress={0xF0000+publication_listing.symbol(name):name for name in
              ('settings_load','chipset_apply','chipset_visible_ram_test','init_peripherals',
               'chipset_late_cache','pnp_publish','post_debug_summary')}
    snapshots=[]
    boundaries=[]
    hardware=[]
    transition=[]
    def hardware_state():
        if port=='mp386':
            return {'switches':m.disk_switches,'EC':m.controls.get(0xEC,0),'E2':m.controls.get(0xE2,0)}
        if port=='pb430':
            return {'registers':{str(i):m.registers[i] for i in (0xDB,0xDC,0xDD,0xDE,0xBE,0xBF)},
                    'uarts':sorted(m.uart_mapping())}
        if port=='presario-800':
            device=m.peripheral_device
            return {'CR':list(device.cr),'onboard_uart_keys':sorted(device.onboard_uart),
                    'uarts':sorted(device.devices()[0])}
        return {'SIO':dict(m.routing.sio),'uarts':[a for a in (0x3F8,0x2F8,0x3E8,0x2E8) if m.routing.uart(a)]}
    def between():
        if not causal or port=='mp386':return
        persistent=(bytes(nv_cmos) if port=='m919' else bytes(m.cmos),bytes(0x10000))
        c=Caller(port,'ss32',persistent)
        c.cpu.mem_write(0x4AD,bytes.fromhex(snapshots[0]))
        old=get_node(c,8,1)[1]
        assert old[13:16]==bytes(3),'Cold input must really have UART A disabled'
        request=bytearray(get_node(c,8,2)[1]);request[13:16]=b'\xF8\x03\x08';request[17:19]=b'\x10\0'
        c.cpu.mem_write(0x20200,bytes(request));c.io.clear()
        actual=hardware_state()
        assert c.far(2,[8,0x200,c.buffer,1,c.bios])==0x85
        assert not c.io and hardware_state()==actual
        assert c.far(2,[8,0x200,c.buffer,2,c.bios])==0
        assert get_node(c,8,1)[1]==old
        assert get_node(c,8,2)[1][13:16]==b'\xF8\x03\x08'
        assert hardware_state()==actual
        assert all(event[1] in (0x70,0x71,0x84) for event in c.io),'Static Set accessed a controller'
        decode_saved(c)
        if port=='m919':m.initial_cmos=bytes(c.cmos)
        else:m.cmos[:]=c.cmos
        transition.append({'old_hardware':actual,'current_unchanged':True,'verified_static_record':True})
    escape=[False]
    ram_entry=0xF0000+publication_listing.symbol('chipset_visible_ram_test')
    keyboard_boundary=0xF0000+publication_listing.symbol('post_keyboard_wait')
    active=[False]
    writes=[]
    def memory(cpu,access,address,size,value,unused):
        if active[0] and 0x400<=address<0x510:
            writes.extend(range(address,address+size))
    def observe(cpu,address,listing):
        if address==ram_entry:escape[0]=False
        if port!='m919' and address==keyboard_boundary and not escape[0]:
            base=cpu.reg_read(x.UC_X86_REG_FS)<<4
            if bytes(cpu.mem_read(base+0x50,1))==b'\x01':
                m.pending.append(1) # Real external Escape, consumed by IRQ1.
                escape[0]=True
        if address in progress:print(port,progress[address],file=sys.stderr,flush=True)
        if address==publication_begin:
            active[0]=True;writes.clear()
        if address==publication_end:
            active[0]=False
            assert set(writes)==set(range(0x4AD,0x500)),('snapshot bounds',writes)
            boundaries.append([min(writes),max(writes)])
            snapshots.append(bytes(cpu.mem_read(0x4AD,83)).hex())
            if causal:hardware.append(hardware_state())
        if address==startup_end and port!='presario-800':
            cpu.emu_stop()
    if port=='mp386':
        fixture=importlib.import_module('fixture')
        m=fixture.Tiger(image,cache=False)
        m.cmos[:]=saved
        if causal:m.disk_switches=0x42
        m.nvram[0x200:0x240]=bytes.fromhex(nv)
        listing=m.listing
        m.cpu.hook_add(UC_HOOK_MEM_WRITE,memory)
        m.code_observer=lambda mm,address:observe(mm.cpu,address,listing)
        for warm in (False,True):
            if warm:
                m.sys_flag=4
                m.seed_physical(0,0x472,b'\x34\x12')
            try:m.boot(warm=warm,count=50000000)
            except AssertionError as error:
                assert error.args[0][0]=='no signed boot' and len(snapshots)==1+warm,str(error)
    elif port=='pb430':
        timing=importlib.import_module('test-timing-setup')
        m=timing.model(image)
        m.cmos[:]=saved
        m.stop_address=startup_end
        m.cpu.hook_add(UC_HOOK_MEM_WRITE,memory)
        m.code_observer=lambda mm,address:observe(mm.cpu,address,m.listing)
        m.cpu.hook_add(UC_HOOK_CODE,lambda u,a,z,v:observe(u,a,m.listing),None,ram_entry,ram_entry)
        m.cold_boot()
        between()
        m.sys_flag=4
        m.cpu.mem_write(0x472,b'\x34\x12')
        m.reset_pending=True
        m.complete_reset(count=300000000)
    elif port=='presario-800':
        os.environ['BAIOS_BUILD_DIRECTORY']=OUTPUT
        chipset=importlib.import_module('test-chipset')
        m=chipset.setup.production_post_model(peripherals=True)
        m.cmos[:]=saved
        m.publish_peripherals=True
        m.startup_observer=lambda mm,name:escape.__setitem__(0,False) if name=='chipset_visible_ram_test' else None
        listing=settings.Listing(image.with_suffix('.lst'))
        m.cpu.hook_add(UC_HOOK_MEM_WRITE,memory)
        begin=0xF0000+listing.symbol('pnp_publish')
        end=0xF0000+listing.symbol('post_debug_summary')
        for address in {begin,end,startup_end,keyboard_boundary}:
            m.cpu.hook_add(UC_HOOK_CODE,lambda u,a,z,v:observe(u,a,listing),None,address,address)
        m.startup(reset=True,production_controls=True,through_publication=True)
        between()
        m.warm=True
        m.startup(production_controls=True,through_publication=True)
    else:
        cache=importlib.import_module('cache_proof')
        geometry=importlib.import_module('geometry_proof')
        if causal:
            sio=importlib.import_module('sio_proof')
        class Hardware(cache.POSTHardware):
            def __init__(self,**kwargs):
                super().__init__(**kwargs)
                if causal:self.routing=sio.SIO(kib=64,ram=4,kind='real')
            def incoming(self,cpu,port,size):
                if causal and (port in (0x108,0x109) or self.routing.uart(port) or self.routing.parallel(port)):
                    return self.routing.incoming(cpu,port,size)
                return super().incoming(cpu,port,size)
            def outgoing(self,cpu,port,size,value):
                if causal and (port in (0x108,0x109) or self.routing.uart(port) or self.routing.parallel(port)):
                    return self.routing.outgoing(cpu,port,size,value)
                return super().outgoing(cpu,port,size,value)
            def observe(self,cpu,address,size):
                observe(cpu,address,self.pnp_listing)
                if address!=startup_end:
                    super().observe(cpu,address,size)
        m=Hardware(kib=64,ram=4)
        m.rom_image=image;m.initial_cmos=saved;m.keys=[];m.ui_returns=[]
        m.pnp_listing=settings.Listing(image.with_suffix('.lst'))
        m.points={0xF0000+m.pnp_listing.symbol(name):name for name in ('post_keyboard_wait','post_notice_wait')}
        for warm in (False,True):
            m.continuing=False
            m.escaped=False
            m.defaults_requested=False
            if warm:m.write(0x472,2,0x1234)
            _,fixture=geometry.mapped(m.modules,expected=4,memory=m,rom_image=image)
            cpu,m,listing,state,nv_cmos,step=fixture
            m.state=state
            cpu.hook_add(UC_HOOK_MEM_WRITE,memory)
            m.continuing=True
            step.execute(0xF0000+cpu.reg_read(x.UC_X86_REG_IP),0xFFFFF,50000000)
            m.initial_cmos=bytes(nv_cmos)
            if not warm:between()
    assert len(snapshots)==2,(port,len(snapshots))
    final_cmos=bytes(nv_cmos) if port=='m919' else bytes(m.cmos)
    final_nv=bytes(m.nvram) if port=='mp386' else bytes(0x10000)
    return {'snapshots':snapshots,'publication_boundaries':boundaries,'cold_warm_actual_startup':True,
            'cmos':final_cmos.hex(),'nvram_0200_023f':final_nv[0x200:0x240].hex(),
            'hardware':hardware,'static_transition':transition}


def causal_routing(port):
    c=Caller(port)
    argv=[sys.executable,'-B',str(Path(__file__).resolve()),'--port',port,'--startup-causal',
          '--startup-cmos',bytes(c.cmos).hex(),'--startup-nv',bytes(c.nvram[0x200:0x240]).hex()]
    result=json.loads(subprocess.check_output(argv,cwd=ROOT,text=True).splitlines()[-1])
    (ROOT/port/OUTPUT/'trace-causal-raw.json').write_text(json.dumps(result,indent=2))
    return check_causal_routing(port,result)


def check_causal_routing(port,result):
    for phase,(snapshot,hardware) in enumerate(zip(result['snapshots'],result['hardware'])):
        caller=Caller(port,'ss32')
        caller.cpu.mem_write(0x4AD,bytes.fromhex(snapshot))
        uart=decode(get_node(caller,8,1)[1])[2][0]
        if port=='mp386':
            assert hardware['switches']==0x42
            assert hardware['EC']&12==4,hardware
            assert hardware['E2']&12==4,hardware
            assert uart[:2]==[(0x4B,b'\xF8\x03\x08'),(0x22,b'\x10\0')]
            lpt=decode(get_node(caller,10,1)[1])[2][0]
            assert lpt[0]==(0x4B,b'\x78\x02\x03')
            fdc=decode(get_node(caller,11,1)[1])[2][0]
            assert all(not any(data) for tag,data in fdc if tag!=0x79)
        else:
            expected=0x3F8 if phase else 0
            assert uart[0]==(0x4B,struct.pack('<HB',expected,8 if phase else 0))
            if port=='m919':
                regs=hardware['SIO'];regs={int(k):v for k,v in regs.items()}
                assert bool(regs[0xC0]&2)==bool(phase)
                if phase:assert regs[0xC1]&2 and 0x3F8 in hardware['uarts']
            elif port=='pb430':
                regs={int(k):v for k,v in hardware['registers'].items()}
                assert bool(regs[0xDB]&0x18)==(not phase)
                if phase:assert (regs[0xDC]&0xFE)<<2==0x3F8 and 0x3F8 in hardware['uarts']
            else:
                regs=hardware['CR']
                assert (regs[2]&12)==(12 if phase else 0)
        real=Caller(port)
        real.cpu.mem_write(0x4AD,bytes.fromhex(snapshot))
        before=get_node(real,8,1)[1];keyboard(real);assert get_node(real,8,1)[1]==before
    return result


def image_contract(port):
    c=Caller(port)
    image=c.image.parent/'production'/c.image.name
    assert not scan(image.read_bytes())
    raw=image.read_bytes();rom=raw[-65536:]
    listing=settings.Listing(image.with_suffix('.lst'))
    if port!='presario-800':verify(port,image)
    else:
        assert len(raw)==65536 and sum(raw)&255==0
        assert rom[0xFFF0]==0xEA and struct.unpack_from('<HH',rom,0xFFF1)==(listing.symbol('startup'),0xF000)
    if port in ('presario-800','pb430'):
        assert rom[0xF065:0xF070]==bytes.fromhex('80fc1d7305ea972800c0cf')
    physical=image.with_name('baios-presario800-vga60.bin') if port=='presario-800' else image
    full=physical.read_bytes()
    if port=='pb430':
        spec=importlib.util.spec_from_file_location('pnp_pb430_build',ROOT/port/'tools/build.py')
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
        owner.validate(image)
    if port=='presario-800':
        frozen=json.loads((ROOT/'shared/tests/fixtures/ui-text-p0.json').read_text())['ports'][port]['physical']
        assert len(full)==frozen['size'] and full[-65536:]==rom
        assert hashlib.sha256(full[:-65536]).hexdigest()==frozen['retained_sha256']
        assert sum(full)&255==int(frozen['sum32'],16)&255
    if port=='m919':
        # E0 is generated APM/SMM code, not a retained vendor input. Test-only
        # discovery cannot alter it; its independent region checksum also holds.
        assert sum(raw[:65536])&255==0
        assert raw[:65536]==c.image.read_bytes()[:65536]
    regions=[]
    for line in listing.lines:
        if re.search(r'\btimes\s+(?:0xF065|0xFFF0|CFG_ROM_CHECKSUM_OFFSET)',line) and 'db 0xFF' in line:
            match=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+FF<rep ([0-9A-F]+)h>',line)
            if match:regions.append((int(match[1],16),int(match[2],16)))
    return {'normal_installation_absent':True,'sha256':hashlib.sha256(full).hexdigest(),
            'size':len(full),'sum32':f'{sum(full):08X}',
            'system_sha256':hashlib.sha256(rom).hexdigest(),
            'free_system_bytes':sum(n for at,n in regions if at<0xFFF0),'padding_regions':regions}


def settings_regressions(port):
    """Compare affected load/fallback/recovery against retained P0S firmware."""
    fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
    seed=(bytes.fromhex(fixture['cmos']),bytes(0x200)+bytes.fromhex(fixture['nvram_0200_023f'])+bytes(0xFDC0))
    producer=settings.Settings(port,OUTPUT)
    producer.cmos[:],producer.nvram[:]=seed
    producer.call('settings_load');producer.call('setup_defaults');producer.draft()
    producer.put('U_PNP',bytes.fromhex('0884A20003200010031000050A0101'))
    assert producer.call('settings_save')
    nv6=producer.snapshot()
    tested=[]
    formats=[('legacy',seed),('nv6',nv6)]
    if port in ('m919','presario-800'):
        legacy=bytearray(seed[0])
        indices=list(range(0x6B,0x80))+[0x33,0x34,0x35]
        if port=='presario-800':
            legacy[0x69]=0xC1
            legacy[indices[10]]&=15;legacy[indices[23]]&=1
        else:
            legacy[0x69]=0x56
            logical=bytes.fromhex(fixture['expected']['C_CHIP'])[:10]+b'\xA5'*14
            for at,value in zip(indices,logical):legacy[at]=value
        legacy[0x6A]=(-legacy[0x69]-sum(legacy[at] for at in indices))&255
        formats.append(('legacy-prior', (bytes(legacy),seed[1])))
    for fmt,persistent in formats:
        for bad in (False,True):
            for recovery in (False,True):
                old=settings.Settings(port,'build/tests/ui-text')
                new=settings.Settings(port,OUTPUT)
                for model in (old,new):
                    model.cmos[:],model.nvram[:]=persistent
                    if bad:
                        at=0x35 if fmt=='nv6' else 0x72 if port=='m919' else 0x6A
                        if port=='mp386' and at>=0x40:model.nvram[0x200+at-0x40]^=1
                        else:model.cmos[at]^=1
                    if recovery:
                        at=0x71 if port=='m919' and fmt=='legacy' else 0x69
                        if port=='mp386':model.nvram[0x200+at-0x40]=0xD2
                        else:model.cmos[at]=0xD2
                    model.call('settings_load')
                    assert not model.writes
                assert new.get('C_CHIP',24)==old.get('C_CHIP',24),(port,fmt,bad,recovery,'chip')
                assert new.get('C_VALID')==old.get('C_VALID'),(port,fmt,bad,recovery,'valid')
                state=bytes(new.cpu.mem_read(new.base,new.allocated));saved=new.snapshot()
                new.call('pnp_publish')
                assert bytes(new.cpu.mem_read(new.base,new.allocated))==state and new.snapshot()==saved
                tested.append((fmt,bad,recovery))
    s=producer
    policy=s.get('U_PNP',15)
    s.cmos[0x37]=0xB5
    if port=='mp386':s.nvram[0x229]=0xD2
    else:s.cmos[0x69]=0xD2
    for owner in ('ide_settings_save','ports_settings_save','chipset_settings_save'):
        before=s.snapshot();start=len(s.writes)
        assert s.call(owner)
        settings.check_mutation(port,before,s.snapshot(),s.writes[start:],owner)
        assert s.logical(0x69)==0xD2 and s.cmos[0x37]==0xB5
        assert decode_saved(s)[0]['C_PNP']==policy
    s.fail=('cmos',0x3B);s.put('U_CLOCK24',b'\x01')
    assert not s.call('settings_save') and s.logical(0x69)==0xD2
    assert s.cmos[0x36] not in (0x5A,0x1A),'Failed Save fabricated a RAM failure'
    s.fail=None;selected=s.get('U_CHIP',24)
    assert s.call('settings_save') and s.logical(0x69)==0
    s.call('settings_load')
    assert s.get('C_CHIP',24)==selected and s.get('C_VALID')==b'\x01'
    return {'P0S_load_contrasts':len(tested),'component_preservation':True,'failed_and_successful_D2_save':True}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port',choices=('all',)+PORTS,default='all')
    parser.add_argument('--case',choices=('all','abi','information-services','nodes','set-node','image-contract'))
    parser.add_argument('--startup-causal',action='store_true')
    parser.add_argument('--startup-cmos')
    parser.add_argument('--startup-nv',default='')
    args=parser.parse_args()
    if args.startup_cmos:
        assert args.port!='all'
        print(json.dumps(startup(args.port,args.startup_cmos,args.startup_nv,args.startup_causal)))
        raise SystemExit
    assert args.case,'--case is required'
    ports=PORTS if args.port=='all' else (args.port,)
    results={}
    for port in ports:
        prepare(port)
        cases=('abi','information-services','nodes','set-node','image-contract') if args.case=='all' else (args.case,)
        results[port]={case:globals()[case.replace('-','_')](port) for case in cases}
        if args.case in ('all','set-node'):results[port]['affected_settings']=settings_regressions(port)
    print(json.dumps(results,indent=2))
