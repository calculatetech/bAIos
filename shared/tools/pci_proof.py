"""Independent PCI configuration devices and PCI BIOS caller-state oracles."""
import struct
from unicorn import x86_const as x


class Endpoint:
    def __init__(self,identity=0x56781234,cls=0x020000,header=0,pin=0,bars=None,pi_writable=0,rom_mask=0):
        self.raw=bytearray(256);self.probing=set();self.bars=bars or {};self.pi_writable=pi_writable;self.writes=[];self.rom_mask=rom_mask
        for offset,value in ((0,identity),(4,0xA9000147),(8,cls<<8),(0x0C,header<<16),(0x3C,pin<<8)):
            self.raw[offset:offset+4]=struct.pack('<I',value)
        for offset,mask in self.bars.items():self.raw[offset:offset+4]=struct.pack('<I',mask&15)
    def read(self,offset,size):
        if offset==0x30 and size==4 and offset in self.probing:return self.rom_mask
        result=bytearray(self.raw[offset:offset+size])
        for i in range(size):
            at=offset+i;base=at&~3
            if base in self.probing:result[i]=(self.bars.get(base,0)>>((at&3)*8))&255
        return int.from_bytes(result,'little')
    def write(self,offset,size,value):
        self.writes.append((offset,size,value))
        if offset==0x30 and size==4:
            if value==0xFFFFFFFE:self.probing.add(offset);return
            self.probing.discard(offset)
            value=(value&self.rom_mask)|(value&1) if self.rom_mask else 0
        if offset in range(0x10,0x28,4) and size==4:
            if value==0xFFFFFFFF:self.probing.add(offset);return
            self.probing.discard(offset)
            if offset not in self.bars:return
            mask=self.bars[offset]
            if self.bars.get(offset-4,0)&7!=4:
                flags=mask&3 if mask&1 else mask&15
                value=(value&(~3 if mask&1 else ~15))|flags
        for i in range(size):
            at=offset+i;b=(value>>(i*8))&255
            if at in (6,7):self.raw[at]&=~b
            elif at==9:self.raw[at]=(self.raw[at]&~self.pi_writable)|(b&self.pi_writable)
            elif at<4 or at in (8,10,11,0x0E,0x3D):continue
            else:self.raw[at]=b


class PCI:
    def __init__(self,endpoints=None):
        self.endpoints=endpoints or {};self.accesses=[]
    def read(self,address,port,size):
        bdf=(address>>8)&0xFFFF;offset=(address&0xFC)+port-0xCFC
        self.accesses.append(('read',bdf,offset,size))
        device=self.endpoints.get(bdf)
        return device.read(offset,size) if address&0x80000000 and device else (1<<(size*8))-1
    def write(self,address,port,size,value):
        bdf=(address>>8)&0xFFFF;offset=(address&0xFC)+port-0xCFC
        self.accesses.append(('write',bdf,offset,size,value))
        device=self.endpoints.get(bdf)
        if address&0x80000000 and device:device.write(offset,size,value)


def public_call(fixture,number=0x1A,**inputs):
    u,d,listing,state,cmos,step=fixture
    registers={x.UC_X86_REG_EAX:0xA1B2B101,x.UC_X86_REG_EBX:0xC3D41234,x.UC_X86_REG_ECX:0xE5F68765,
        x.UC_X86_REG_EDX:0x98BA5432,x.UC_X86_REG_ESI:0xFACE1234,x.UC_X86_REG_EDI:0xBEEF4567,
        x.UC_X86_REG_EBP:0x12348765,x.UC_X86_REG_ESP:0xF00D7000,x.UC_X86_REG_DS:0x200,
        x.UC_X86_REG_ES:0x300,x.UC_X86_REG_FS:0x400,x.UC_X86_REG_GS:0x500,
        x.UC_X86_REG_SS:0,x.UC_X86_REG_CS:0,x.UC_X86_REG_EFLAGS:0x240AD7}
    for name,value in inputs.items():registers[getattr(x,'UC_X86_REG_'+name.upper())]=value
    for reg,value in registers.items():u.reg_write(reg,value)
    code=b'\xCD'+bytes((number,))+b'\x90'
    for i,b in enumerate(code):d.write(0x8000+i,1,b)
    u.mem_write(0x8000,code)
    u.emu_start(0x8000,0x8002,count=30000)
    assert (u.reg_read(x.UC_X86_REG_CS),u.reg_read(x.UC_X86_REG_IP))==(0,0x8002),(number,u.reg_read(x.UC_X86_REG_CS),u.reg_read(x.UC_X86_REG_IP))
    return registers,{reg:u.reg_read(reg) for reg in registers}


def api(fixture,pci):
    u,d,listing,state,cmos,step=fixture
    assert d.read(0x1A*4,4)==struct.pack('<HH',listing.symbol('pci_int1a'),0xF000),'Actual installed INT1A'
    rows=[]
    def one(function,expected=None,error=0,**inputs):
        for flags in (0x2408D6,0x240AD7):
            before=len(pci.accesses)
            initial,actual=public_call(fixture,eax=0xA1B2B100|function,eflags=flags,**inputs)
            wanted=dict(initial);wanted[x.UC_X86_REG_EAX]=(initial[x.UC_X86_REG_EAX]&~0xFF00)|(error<<8)
            wanted[x.UC_X86_REG_EFLAGS]=(flags&~1)|bool(error)
            for name,(mask,value) in (expected or {}).items():
                reg=getattr(x,'UC_X86_REG_'+name.upper());wanted[reg]=(wanted[reg]&~mask)|(value&mask)
            assert actual==wanted,(hex(function),inputs,error,{r:(hex(actual[r]),hex(wanted[r])) for r in actual if actual[r]!=wanted[r]})
            if error in (0x81,0x83,0x87):assert len(pci.accesses)==before,('Invalid request performed I/O',function,inputs)
            rows.append({'entry':f'B1{function:02X}','input':inputs,'flags':f'{flags:08X}','status':error,'outputs':expected or {},'state_preserved':True})
    one(1,{'eax':(255,1),'ebx':(65535,0x0210),'ecx':(255,0),'edx':(0xFFFFFFFF,0x20494350)})
    # Two duplicate identities, a later match, distinct class, absent ordinal.
    for ordinal,bdf in enumerate((0x60,0x61,0x72)):
        one(2,{'ebx':(65535,bdf)},edx=0x98BA1234,ecx=0xE5F65678,esi=0xFACE0000|ordinal)
    one(2,error=0x86,edx=0x98BA1234,ecx=0xE5F65678,esi=0xFACE0003)
    one(2,error=0x83,edx=0x98BAFFFF)
    one(3,{'ebx':(65535,0x72)},ecx=0xA0030000,esi=0xFACE0000)
    one(3,error=0x86,ecx=0xA0FFFFFF,esi=0xFACE0000)
    one(3,error=0x86,ecx=0xA0030000,esi=0xFACE0001)
    for function in (0,4,7,14,255):one(function,error=0x81)
    endpoint=pci.endpoints[0x60]
    for function,size in ((8,1),(9,2),(10,4),(11,1),(12,2),(13,4)):
        offset=0xFF if size==1 else 0xFE if size==2 else 0xFC
        value=0x6A5B4C3D&((1<<(size*8))-1)
        if function<=10:
            endpoint.raw[offset:offset+size]=value.to_bytes(size,'little')
            one(function,{'ecx':((1<<(size*8))-1,value)},ebx=0xC3D40060,edi=0xBEEF0000|offset)
        else:
            one(function,ebx=0xC3D40060,edi=0xBEEF0000|offset,ecx=0x6A5B4C3D)
            assert endpoint.read(offset,size)==value
        one(function,error=0x87,ebx=0xC3D40160,edi=0xBEEF0000|offset)
        one(function,error=0x87,ebx=0xC3D40060,edi=0xBEEF0100)
        if size>1:one(function,error=0x87,ebx=0xC3D40060,edi=0xBEEF00FF)
        if size==4:one(function,error=0x87,ebx=0xC3D40060,edi=0xBEEF00FE)
    return rows
