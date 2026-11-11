"""Run the public ESCD ABI against persistent MX/SST command-state models."""
import importlib.util
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from unicorn import UC_HOOK_MEM_READ
from unicorn import x86_const as x
from shared.tools.isa_pnp_proof import Bus
from shared.tools.stop_grant_proof import descriptor

spec=importlib.util.spec_from_file_location('escd_pnp',Path(__file__).with_name('test-pnp.py'))
pnp=importlib.util.module_from_spec(spec);spec.loader.exec_module(pnp)
pnp.OUTPUT='build'


class Flash(pnp.Caller):
    def __init__(self,kind='mx',mode='real',storage=None,protected=False,cut=None,busy_reads=0):
        self.flash=None
        super().__init__('m919',mode)
        self.cpu.reg_write(x.UC_X86_REG_CR0,self.cpu.reg_read(x.UC_X86_REG_CR0)|0x10)
        self.flash=bytearray(self.image.read_bytes()[:65536] if storage is None else storage)
        self.kind,self.protected,self.cut=kind,protected,cut
        self.command=None;self.unlock=0;self.id=False;self.page=None
        self.mx_id_read = False
        self.programmed=0;self.bus=[]
        self.busy_reads=busy_reads;self.busy=0
        self.pci_address=0x12345678;self.pci={}
        for device in (16,18):
            for reg in (0x47,0x50,0x54,0x55,0x57,0xA0,0xA3):
                self.pci[0x80000000|(device<<11)|reg]=(device*7+reg)&255
        self.nmi=0x0D;self.refresh=0
        self.original=(self.pci_address,self.pci.copy(),self.nmi,self.snapshot())
        self.cpu.hook_add(UC_HOOK_MEM_READ,self.flash_read,None,0xE0000,0xEFFFF)
        if mode=='real':self.nvs=0xE000
        else:
            self.cpu.mem_write(0x6078,descriptor(0xE0000,0x10000,0x92,0))
            self.cpu.reg_write(x.UC_X86_REG_GDTR,(0,0x6000,0x7F,0))
            self.nvs=0x78

    def inp(self,cpu,port,size,unused):
        if hasattr(self,'isa') and (value:=self.isa.input(port,size)) is not None:return value
        if self.flash is not None:
            if port==0xCF8:return self.pci_address
            if 0xCFC<=port<=0xCFF:return self.pci.get((self.pci_address&~3)+(port-0xCFC),0)
            if port==0x70:raise AssertionError('RTC index/NMI latch is not readable')
            if port==0x61:self.refresh^=0x10;return self.refresh
        return super().inp(cpu,port,size,unused)

    def out(self,cpu,port,size,value,unused):
        if hasattr(self,'isa') and self.isa.output(port,size,value):return
        if self.flash is not None:
            if port==0xCF8:self.pci_address=value;return
            if 0xCFC<=port<=0xCFF:
                assert size==1
                self.pci[(self.pci_address&~3)+(port-0xCFC)]=value
                return
            if port==0x70:
                self.nmi=value
                if not hasattr(self,'isa'):return
        return super().out(cpu,port,size,value,unused)

    def flash_read(self,cpu,access,address,size,value,unused):
        if self.public_active:self.mapping()
        off=address-0xE0000
        data=bytearray(self.flash[off:off+size])
        if self.id:
            assert size == 1 and off in (0, 1), ('flash ID requires a byte read at offset 0 or 1', hex(off), size)
            ids = (0xC2, 0x1A) if self.kind == 'mx' else (0xBF, 7)
            data = bytes([ids[off]])
            if self.kind == 'mx':
                # Model the bench chip returning array data after its first ID byte.
                self.id = False
                self.mx_id_read = True
        elif self.busy:
            data[0]^=0x40 if self.busy&1 else 0
            self.busy-=1
        cpu.mem_write(address,bytes(data))

    def rom_guard(self,cpu,access,address,size,value,unused):
        if self.flash is None:return super().rom_guard(cpu,access,address,size,value,unused)
        if not 0xE0000<=address<0xF0000:return super().rom_guard(cpu,access,address,size,value,unused)
        assert size==1 and address>=0xE8000,('unsafe flash write',hex(address),size)
        off=address-0xE0000;self.bus.append((off,value))
        self.mapping()
        assert not cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200
        assert cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
        assert self.pci[0x80008050]==self.original[1][0x80008050]
        assert self.pci[0x800090A3]&0xC0==0
        if self.kind=='unknown':
            # Unprotected EEPROMs may accept command bytes as ordinary writes.
            assert off in (0xBFFE,0xD555,0xAAAA)
            self.flash[off]=value
            return
        if self.kind=='mx':
            if self.command=='program':self.store(off,value);self.command=None
            elif self.command=='erase':
                assert value==0xD0 and off in (0x8000,0xC000)
                if not self.protected:self.flash[off:off+0x4000]=b'\xFF'*0x4000
                self.busy=self.busy_reads
                self.command=None
            elif value==0x90:self.id=not self.mx_id_read
            elif value==0xFF:self.id=self.mx_id_read=False
            elif value==0x40:self.command='program'
            elif value==0x20:self.command='erase'
            else:raise AssertionError(('MX unexpected command',hex(off),hex(value)))
        elif self.page is not None:
            base,count=self.page
            assert off==base+count
            self.store(off,value);count+=1
            self.page=None if count==128 else (base,count)
        elif self.command=='page':self.page=(off,1);self.store(off,value);self.command=None
        elif self.unlock==0 and off==0xD555 and value==0xAA:self.unlock=1
        elif self.unlock==1 and off==0xAAAA and value==0x55:self.unlock=2
        elif self.unlock==2 and off==0xD555:
            self.unlock=0
            if value==0x90:self.id=True
            elif value==0xF0:self.id=False
            elif value==0xA0:self.command='page'
            else:raise AssertionError(('SST unexpected command',hex(value)))
        else:self.unlock=0

    def mapping(self):
        assert self.pci[0x80009047]&0x40==0
        assert self.pci[0x80009057]&0x24==0x24
        assert self.pci[0x80008054]&1==0
        assert self.pci[0x80008055]&0x50==0x40
        assert self.nmi&0x80

    def store(self,off,value):
        self.programmed+=1
        self.busy=self.busy_reads
        if self.cut is not None and self.programmed>=self.cut:return
        if not self.protected:
            if self.kind=='mx':self.flash[off]&=value
            else:self.flash[off]=value

    def request(self,fn,data=None):
        if data is not None:self.cpu.mem_write(0x20200,bytes(data))
        before=bytes(self.cpu.mem_read(0x20200,len(data))) if data is not None else None
        result=self.far(fn,[0x200,self.buffer,self.nvs,self.bios])
        assert (self.pci_address,self.pci,self.nmi,self.snapshot())==self.original,'transaction leaked hardware/settings state'
        assert self.flash[:0x8000]==self.image.read_bytes()[:0x8000],'immutable E code changed'
        if data is not None:assert bytes(self.cpu.mem_read(0x20200,len(data)))==before,'caller input changed'
        return result

    def read(self):
        assert self.request(0x42)==0
        size=struct.unpack('<H',self.cpu.mem_read(0x20200,2))[0]
        return bytes(self.cpu.mem_read(0x20200,size))


def canonical(data):
    data=bytearray(data);data[-2:]=b'\0\0'
    padded=data+b'\0'*(len(data)&1)
    checksum=(-sum(struct.unpack('<'+'H'*(len(padded)//2),padded)))&65535
    if len(data)&1:checksum=((checksum>>8)|(checksum<<8))&65535
    data[-2:]=struct.pack('<H',checksum)
    return bytes(data)


def post_clear(kind,storage,seed):
    c=Flash(kind,storage=storage)
    c.isa=Bus();c.isa.pause=False
    c.call('setup_defaults');c.draft();c.put('U_PNP',bytes(14)+b'\1')
    assert c.call('settings_save')
    c.call('settings_load')
    assert c.get('C_PNP',15)[14]==1
    c.cpu.mem_write(c.base+0x1000,b'\xFF\xFF')
    c.cpu.mem_write(0x413,struct.pack('<H',c.base>>10))
    c.call('pnp_publish')
    assert c.call('pnp_module_install')
    c.call('pnp_post_invoke',BX=c.listing.symbol('pnp_prepare_video'))
    c.call('pnp_configure_isa')
    c.call('pnp_finish_entry')
    assert Flash(kind,storage=c.flash).read()==canonical(seed),'POST clear did not persist'


def main():
    seed=struct.pack('<H4sBB4xH',14,b'ACFG',0,2,0)
    for kind in ('mx','sst'):
        for mode in ('real','ss16','ss32'):
            c=Flash(kind,mode)
            assert c.far(0x41,[0x100,c.buffer,0x102,c.buffer,0x104,c.buffer,c.bios])==0
            assert bytes(c.cpu.mem_read(0x20100,8))==struct.pack('<HHI',8192,8192,0xE0000)
            assert c.far(9)==0x8D and c.far(10)==0x8D
            assert c.read()==canonical(seed)
            data=bytearray(seed+bytes(range(163)));struct.pack_into('<H',data,0,len(data))
            assert len(data)==177
            assert c.request(0x43,data)==0,(kind,mode)
            assert c.read()==canonical(data),(kind,mode,c.read().hex())
            programmed=c.programmed;bus=list(c.bus)
            assert c.request(0x43,data)==0
            assert c.programmed==programmed and c.bus==bus,'identical save programmed flash'
            fresh=Flash(kind,mode,c.flash)
            assert fresh.read()==canonical(data),'database did not survive fresh firmware state'
            broken=Flash(kind,mode,fresh.flash,cut=8)
            assert broken.request(0x43,seed)==0x55
            assert Flash(kind,mode,broken.flash).read()==canonical(data),'torn update lost previous database'
            assert fresh.request(0x43,seed)==0
            assert fresh.read()==canonical(seed)
            print(kind,mode,'persistent read/write, torn update, ABI and cleanup passed')
        c=Flash(kind)
        maximum=bytearray(seed+bytes((n*73)&255 for n in range(8192-14)))
        struct.pack_into('<H',maximum,0,len(maximum))
        assert c.request(0x43,maximum)==0
        assert c.read()==canonical(maximum),'maximum-sized database changed'
        post_clear(kind,c.flash,seed)
        before=c.programmed
        for length,status in ((0,0x56),(13,0x56),(8193,0x5A)):
            invalid=bytearray(seed);struct.pack_into('<H',invalid,0,length)
            assert c.request(0x43,invalid)==status
        assert c.programmed==before
        assert c.far(0x42,[0xFFF3,c.buffer,c.nvs,c.bios])==0x59
        assert c.far(0x43,[0xFFF3,c.buffer,c.nvs,c.bios])==0x59
        print(kind,'maximum-sized database and persistent POST clear passed')
        delayed=Flash(kind,busy_reads=6)
        delayed_data=bytearray(seed);delayed_data[6]=2
        assert delayed.request(0x43,delayed_data)==0
        assert delayed.read()==canonical(delayed_data),'DQ6 busy polling accepted premature data'
    for kind in ('mx','sst'):
        c=Flash(kind)
        changed=bytearray(seed);changed[6]=1
        assert c.request(0x43,changed)==0
        protected=Flash(kind,storage=c.flash,protected=True)
        assert protected.request(0x43,seed)==0x55
        assert protected.flash==c.flash and protected.read()==canonical(changed)
    c=Flash('mx');changed=bytearray(seed);changed[6]=1
    assert c.request(0x43,changed)==0
    saved=c.read();raw=bytes(c.flash)
    unknown=Flash('unknown',storage=raw)
    changed[6]=2
    assert unknown.request(0x43,changed)==0x55 and unknown.read()==saved
    for low,high in ((0x8000,0xA080),(0xC000,0xC080),(0xE000,0x10000)):
        assert unknown.flash[low:high]==raw[low:high],'unknown chip probe overwrote committed data'
    print('ESCD: unknown/protected write failures passed')


if __name__=='__main__':main()
