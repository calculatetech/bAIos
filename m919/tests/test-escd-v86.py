"""Execute real V86 paging; model only architectural SMI/save/RSM and flash."""
import importlib.util
from pathlib import Path
import struct
import sys

ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn import x86_const as x
from capstone import Cs,CS_ARCH_X86,CS_MODE_16
from shared.tools.smm_proof import MAPS,SEGMENTS,REGS

spec=importlib.util.spec_from_file_location('escd_flash',ROOT/'shared/tests/test-escd.py')
flash=importlib.util.module_from_spec(spec);spec.loader.exec_module(flash)


class Virtual(flash.Flash):
    def public_memory(self,cpu,access,address,size,value,unused):
        if address==self.base+0x1040 and size==1:return
        return super().public_memory(cpu,access,address,size,value,unused)

    def __init__(self,kind='mx'):
        self.smm=False
        super().__init__(kind)
        self.pci[0x800090A8]=0;self.pci[0x800090A2]=0
        self.original=(self.pci_address,self.pci.copy(),self.nmi,self.snapshot())
        self.smm=False;self.pending=False;self.action=None;self.smi_count=0
        self.decoder=Cs(CS_ARCH_X86,CS_MODE_16)
        self.pages={page:page for page in range(512)}
        self.pages.update({0x20:0x140,0x21:0x170,0x22:0x150})
        self.cpu.mem_write(0x180000,struct.pack('<I',0x181007)+bytes(4092))
        self.cpu.mem_write(0x181000,b''.join(struct.pack('<I',(self.pages[p]<<12)|(5 if 0xE0<=p<0x100 else 7)) for p in range(512))+bytes(2048))
        self.cpu.mem_write(self.base+0x1040,b'\1')
        self.smr=bytearray(65536)
        begin=self.listing.symbol('board_smm_image');end=self.listing.symbol('board_smm_image_end')
        self.smr[0x8000:0x8000+end-begin]=self.image.read_bytes()[begin:end]
        self.cpu.hook_add(UC_HOOK_CODE,self.step)
        self.cpu.hook_add(UC_HOOK_MEM_READ,self.upper_smram,None,0xA0000,0xA7FFF)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE,self.upper_smram,None,0xA0000,0xA7FFF)
        self.cpu.reg_write(x.UC_X86_REG_CR3,0x180000)
        self.cpu.reg_write(x.UC_X86_REG_CR0,0x80000011)
        self.caller_flags=0x23202
        self.cpu.reg_write(x.UC_X86_REG_EFLAGS,self.caller_flags)

    def upper_smram(self,cpu,access,address,size,value,unused):
        assert not self.smm,("ESCD uses unqualified lower SMRAM",hex(address),size)

    def out(self,cpu,port,size,value,unused):
        super().out(cpu,port,size,value,unused)
        if not self.smm and port==0xCFF and self.pci_address==0x800090A0 and value&0xC0==0xC0:
            self.pending=True

    def step(self,cpu,address,size,unused):
        if self.pending:
            self.pending=False;self.action='enter';cpu.emu_stop();return
        raw=bytes(cpu.mem_read(address,min(size,15)))
        if self.smm and raw[:2]==b'\x0F\xAA':self.action='resume';cpu.emu_stop();return
        if not self.smm:
            assert cpu.reg_read(x.UC_X86_REG_CR0)&0x80000001==0x80000001
            assert cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x20000
            instruction=next(self.decoder.disasm(raw,address))
            assert instruction.mnemonic not in ('wbinvd','invd','rsm') and 'cr0' not in instruction.op_str,('V86 privileged instruction',instruction.mnemonic,instruction.op_str)

    def enter(self):
        u=self.cpu;layout=MAPS['Am5x86']
        self.context=u.context_save()
        saved=bytearray(512)
        for name,offset in layout.items():
            struct.pack_into('<H' if name in SEGMENTS else '<I',saved,offset-0xFE00,u.reg_read(REGS[name]))
        struct.pack_into('<II',saved,0xF8,0xA0000,0x20001)
        self.smr[0xFE00:]=saved
        self.vga=bytes(u.mem_read(0xA0000,65536))
        u.mem_write(0xA0000,bytes(self.smr))
        # Intel Table8-3: visible CS remains3000h even after SMBASE relocation.
        gdt=bytearray(0x3008)
        gdt[8:16]=flash.descriptor(0,0x100000,0x92,0x80)
        gdt[0x3000:]=flash.descriptor(0xA0000,0x100000,0x9A,0x80)
        u.mem_write(0x190000,bytes(gdt))
        u.reg_write(x.UC_X86_REG_CR0,0x11)
        u.reg_write(x.UC_X86_REG_EFLAGS,2)
        u.reg_write(x.UC_X86_REG_GDTR,(0,0x190000,len(gdt)-1,0))
        u.reg_write(REGS['CS'],0x3000)
        for name in ('DS','ES','FS','GS','SS'):u.reg_write(REGS[name],8)
        u.reg_write(x.UC_X86_REG_CR0,0x10)
        for name in ('DS','ES','FS','GS','SS'):u.reg_write(REGS[name],0)
        u.reg_write(REGS['EIP'],0x8000)
        self.smm=True;self.smi_count+=1

    def resume(self):
        u=self.cpu;layout=MAPS['Am5x86']
        self.smr[:]=u.mem_read(0xA0000,65536)
        reply={name:struct.unpack_from('<I',self.smr,layout[name])[0] for name in ('EAX','EBX','ECX','EFLAGS')}
        u.mem_write(0xA0000,self.vga)
        u.context_restore(self.context)
        for name,value in reply.items():u.reg_write(REGS[name],value)
        self.smm=False

    def execute(self,entry,end,count):
        for _ in range(8):
            self.action=None
            self.cpu.emu_start(entry,end,count=2000000)
            if self.action=='enter':self.enter()
            elif self.action=='resume':self.resume()
            else:return
            entry=(self.cpu.reg_read(REGS['CS'])<<4)+self.cpu.reg_read(x.UC_X86_REG_IP)
        raise AssertionError('SMM event loop did not return')

    def put_virtual(self,address,data):
        for offset,value in enumerate(data):
            at=address+offset;self.cpu.mem_write((self.pages[at>>12]<<12)+(at&4095),bytes((value,)))

    def get_virtual(self,address,length):
        return bytes(self.cpu.mem_read((self.pages[at>>12]<<12)+(at&4095),1)[0] for at in range(address,address+length))

    def request_virtual(self,fn,data=None):
        address=0x20FFF
        if data is not None:self.put_virtual(address,data)
        status=self.far(fn,[0xFFF,self.buffer,self.nvs,self.bios])
        assert (self.pci_address,self.pci,self.nmi,self.snapshot())==self.original
        return status


def main():
    seed=struct.pack('<H4sBB4xH',14,b'ACFG',0,2,0)
    data=bytearray(seed+bytes(range(163)));struct.pack_into('<H',data,0,len(data))
    for kind in ('mx','sst'):
        c=Virtual(kind)
        assert c.request_virtual(0x43,data)==0,kind
        assert c.get_virtual(0x20FFF,len(data))==data,'write modified virtual caller input'
        c.put_virtual(0x20FFF,b'\xCC'*len(data))
        assert c.request_virtual(0x42)==0,kind
        assert c.get_virtual(0x20FFF,len(data))==flash.canonical(data)
        assert c.smi_count==2
        assert flash.Flash(kind,storage=c.flash).read()==flash.canonical(data),'V86 write did not persist'
        if kind=='mx':
            maximum=bytearray(seed+bytes((n*73)&255 for n in range(8192-14)))
            struct.pack_into('<H',maximum,0,len(maximum))
            assert c.request_virtual(0x43,maximum)==0
            c.put_virtual(0x20FFF,b'\xCC'*8192)
            assert c.request_virtual(0x42)==0
            assert c.get_virtual(0x20FFF,8192)==flash.canonical(maximum),'three-page transfer changed data'
        else:
            original=c.get_virtual(0x20FFF,len(data))
            for at,value in ((0x180000,0x181005),(0x181000+0x21*4,0xA0007),(0x181000+0x21*4,0)):
                prior=bytes(c.cpu.mem_read(at,4));c.cpu.mem_write(at,struct.pack('<I',value))
                assert c.request_virtual(0x42)==0x55
                assert c.get_virtual(0x20FFF,len(data))==original,'rejected output partially changed data'
                c.cpu.mem_write(at,prior)
        print(kind,'true V86/PG cross-page nonidentity read/write via SMM passed')
    former=Virtual()
    entry=0xF0000+former.listing.symbol('board_escd')
    def bypass(cpu,address,size,unused):
        if not former.smm:cpu.reg_write(x.UC_X86_REG_IP,former.listing.symbol('board_escd_native'))
    former.cpu.hook_add(UC_HOOK_CODE,bypass,None,entry,entry)
    try:former.request_virtual(0x43,data)
    except AssertionError as error:
        assert 'V86 privileged instruction' in str(error),error
    else:raise AssertionError('Former direct V86 path did not expose its privilege fault')
    assert former.smi_count==0 and former.programmed==0
    print('Former direct path contrast rejected its privileged V86 instruction')


if __name__=='__main__':main()
