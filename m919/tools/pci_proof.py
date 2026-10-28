"""M919 PCI composition, independent AMI wiring and external ROM/IDE providers."""
import hashlib
import json
import struct
from collections import Counter
from pathlib import Path
from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn import x86_const as x
from cache_proof import SRAM,POSTHardware,composed,post_module
from geometry_proof import invoke
from shared.tools.pci_proof import PCI,Endpoint,api,public_call
from shared.tools.ram_proof import Listing
PORT=Path(__file__).resolve().parents[1]
REPOSITORY=PORT.parent


class Hardware(POSTHardware):
    def __init__(self,endpoints=None,vga_kib=32,**options):
        options.setdefault('kib',64)
        options.setdefault('kind','absent')
        super().__init__(**options)
        self.pci=PCI(endpoints or {0x60:Endpoint(cls=0x030000)})
        self.south=bytearray(256);self.south[0x46:0x48]=b'\xA0\x50'
        self.ports.update({0x4D0:0x21,0x4D1:0x80})
        self.atomic=[];self.taskfiles=[];self.af=[];self.vga_kib=vga_kib
        self.shadow=bytearray(65536);self.rom_enabled=True;self.provider_calls=[]
        self.terminal_boot=False;self.phase='post';self.router_events=[]
        self.provider_events=[]
        self.irq_endpoint=None;self.irq_active=False;self.irq_serviced=False;self.irq_events=[]
        self.ata_visits=[]
    def pci_read(self,address,port,size):
        device=(address>>11)&31;offset=(address&0xFC)+port-0xCFC
        if device==16:return sum(self.registers.get(offset+i,0)<<(8*i) for i in range(size))
        if device==18:return int.from_bytes(self.south[offset:offset+size],'little')
        return self.pci.read(address,port,size)
    def pci_write(self,address,port,size,value):
        device=(address>>11)&31;offset=(address&0xFC)+port-0xCFC
        if device==16:
            for i in range(size):self.registers[offset+i]=(value>>(8*i))&255
            self.writes.append((offset,size,value))
        elif device==18:self.south[offset:offset+size]=value.to_bytes(size,'little')
        else:
            self.pci.write(address,port,size,value)
            if (address>>8)&255==self.vga_bdf and offset==0x30:
                self.rom_enabled=bool(value&1)
                # Physical reads switch to the shadow only in selected regions.
                effective=bytearray(b'\xFF'*65536)
                if self.rom_enabled:effective[:len(self.provider)]=self.provider
                if self.registers.get(0x55,0)&0x80:
                    if self.registers.get(0x54,0)&2:effective[:32768]=self.shadow[:32768]
                    if self.registers.get(0x54,0)&4:effective[32768:49152]=self.shadow[32768:49152]
                    if self.registers.get(0x54,0)&8:effective[49152:]=self.shadow[49152:]
                self.machine.mem_write(0xC0000,bytes(effective))
    def incoming(self,u,port,size):
        if port in (*range(0x1F0,0x1F8),*range(0x170,0x178),0x3F6,0x376):self.taskfiles.append(('in',port,size));return 0xFF
        return super().incoming(u,port,size)
    def outgoing(self,u,port,size,value):
        if port==0x80:self.provider_events.append(value)
        if port==0x80 and value==0xE4 and self.phase=='boot':
            self.stop='boot retry E4';u.emu_stop()
        if port==0x300 and self.irq_endpoint is not None:
            self.irq_active=bool(value);self.irq_events.append(('assert' if value else 'deassert',self.irq_endpoint))
        if port in (0x20,0xA0) and value==0x20 and self.irq_endpoint is not None:
            self.irq_events.append(('EOI',port))
            if port==0x20:self.irq_serviced=False
        if port==0xCF8 or 0xCFC<=port<=0xCFF:
            self.atomic.append((port,bool(u.reg_read(x.UC_X86_REG_EFLAGS)&0x200)))
            assert not u.reg_read(x.UC_X86_REG_EFLAGS)&0x200,('non-atomic PCI access',port,hex(u.reg_read(x.UC_X86_REG_CS)),hex(u.reg_read(x.UC_X86_REG_IP)))
        if port in (*range(0x1F0,0x1F8),*range(0x170,0x178),0x3F6,0x376):self.taskfiles.append(('out',port,size,value))
        if port==0x108 and value in (0x4A,0x6C):self.af.append(value)
        super().outgoing(u,port,size,value)
        if port in (0x4D0,0x4D1):self.router_events.append((port,value))
    def prepare(self,u):
        super().prepare(u)
        self.machine=u
        listing=Listing(PORT/'build/hardware-tests/geometry/baios-m919.lst')
        self.cache_entry=0xF0000+listing.symbol('cache_initialize')
        self.ata_entry=0xF0000+listing.symbol('ata_detect_primary')
        self.ide_entry=0xF0000+listing.symbol('ide_apply_controller')
        self.vga_bdf=next(bdf for bdf,device in self.pci.endpoints.items() if device.read(8,4)>>16==0x0300)
        folder=PORT/'build/hardware-tests/pci-providers';folder.mkdir(parents=True,exist_ok=True)
        source=folder/f'vga{self.vga_kib}.asm';image=source.with_suffix('.bin')
        end=self.vga_kib*1024;self.near_end=end-32
        source.write_text(f'''bits 16
org 0
dw 0xAA55
db {self.vga_kib*2}
mov bx,{self.vga_bdf}
mov di,0x30
xor cl,cl
mov ax,0xB10B
int 0x1A
cmp byte [cs:{end-32}],0xA7
jne failed
push ax
push es
xor ax,ax
mov es,ax
mov word [es:0x40],handler
mov word [es:0x42],0xC000
inc byte [es:0xB90]
pop es
pop ax
jmp returning
failed: mov al,0xE9
out 0x80,al
hlt
handler: iret
returning: retf
times {end-32}-($-$$) db 0x59
db 0xA7
times {end}-($-$$) db 0
''')
        post_module().assemble(source,image,[folder]);raw=bytearray(image.read_bytes())
        # Valid internal suffix ROM must be excluded from the later generic scan.
        suffix=bytearray(b'\x55\xAA\x01\xB0\xD1\xE6\x80\xCB'+bytes(504));suffix[-1]=(-sum(suffix))&255
        if end>32768:raw[32768:33280]=suffix
        raw[-1]=(-sum(raw))&255;image.write_bytes(raw);self.provider=bytes(raw)
        self.returning=0xC0000+raw.index(b'\xCB',40,120)
        u.mem_write(0xC0000,self.provider)
        self.later_segment=0xD000
        later=bytearray(b'\x55\xAA\x01\xB0\xD2\xE6\x80\xCB'+bytes(504));later[-1]=(-sum(later))&255
        u.mem_write(self.later_segment<<4,bytes(later));self.later_return=(self.later_segment<<4)+7
        def write(uc,access,address,size,value,user):
            if 0xC0000<=address<0xD0000 and not self.registers.get(0x55,0)&0x40:
                off=address-0xC0000;self.shadow[off:off+size]=value.to_bytes(size,'little')
        u.hook_add(UC_HOOK_MEM_WRITE,write)
    def observe(self,u,address,size):
        if address in (self.ata_entry,self.ide_entry):self.ata_visits.append('ata_detect_primary' if address==self.ata_entry else 'ide_apply_controller')
        if self.irq_active and not self.irq_serviced and u.reg_read(x.UC_X86_REG_EFLAGS)&0x200:
            # Independent native AMI board wires, not the firmware link table.
            slot,pin=self.irq_endpoint;wire={12:(0,1,2,3),13:(3,0,1,2),14:(2,0,1,3)}[slot][pin-1]
            router=self.south[0x43+wire//2];irq=(router>>(4 if wire%2==0 else 0))&15
            if not self.ports.get(0xA1,255)&(1<<(irq-8)) and not self.ports.get(0x21,255)&4:
                assert self.ports.get(0x4D1,0)&(1<<(irq-8)),('not level triggered',irq)
                self.irq_serviced=True;self.irq_events.append(('deliver',irq))
                self.cpu_interrupt(u,0x70+irq-8,resume=address&0xFFFF)
                return
        if address in (self.returning,self.later_return):
            self.provider_calls.append(address)
            sp=u.reg_read(x.UC_X86_REG_SP);frame=self.read((u.reg_read(x.UC_X86_REG_SS)<<4)+sp,4)
            u.reg_write(x.UC_X86_REG_SP,sp+4);u.reg_write(x.UC_X86_REG_CS,int.from_bytes(frame[2:],'little'))
            u.reg_write(x.UC_X86_REG_IP,int.from_bytes(frame[:2],'little'));return
        if address==0xC0019:
            SRAM.observe(self,u,address,size)
            return
        # Keep the existing real POST/cache/keyboard observation; the fixture's
        # provider return replaces only the opaque external ROM CPU instruction.
        super().observe(u,address,size)
    def finish(self,fixture):
        u,d,listing,state,cmos,step=fixture
        assert self.stop=='POST FF'
        self.stop=None;self.continuing=False
        invoke(fixture,'option_rom_discovery',count=100000)
        assert 0xD2 in self.provider_events and 0xD1 not in self.provider_events and self.provider_calls==[self.returning,self.later_return],(self.provider_calls,self.provider_events)
        assert bytes(self.shadow[:len(self.provider)])==self.provider
        assert bytes(u.mem_read(0xC0000,len(self.provider)))==self.provider
        assert not self.rom_enabled
        # Same real late boot owner for accepted and rejected IDE hardware.
        self.terminal_boot=True
        return {'size':len(self.provider),'sha256':hashlib.sha256(self.provider).hexdigest(),
                'shadow':self.registers[0x54],'end_segment':0xC000+len(self.provider)//16,'provider_calls':self.provider_calls,
                'whole_copy':True,'decode_disabled_end_witness':True,'later_boot_consumer':'option_rom_discovery'}
    def boot(self,fixture):
        u,d,listing,state,cmos,step=fixture
        self.phase='boot';self.stop=None;self.continuing=False
        u.reg_write(x.UC_X86_REG_CS,0);u.reg_write(x.UC_X86_REG_SS,0);u.reg_write(x.UC_X86_REG_SP,0x7000)
        u.reg_write(x.UC_X86_REG_EFLAGS,0x202)
        self.write(0x8000,2,0x19CD);u.mem_write(0x8000,b'\xCD\x19')
        u.emu_start(0x8000,0xFFFFF,count=300000)
        assert self.stop=='boot retry E4',(self.stop,u.reg_read(x.UC_X86_REG_IP))
        self.phase='post'
        return {'installed_int19':True,'terminal':self.stop,'published_disks':self.read(0x475,1).hex()}


def compose(hardware,keys=(),saved=None):
    cmos=bytearray(post_module().nvram(types=0x40)[:128]) if saved is None else bytearray(saved)
    if saved is None:
        cmos[0x5D:0x68]=b'P1\x01'+bytes((3,4,1,3,0,1,0,1));cmos[0x68]=(-sum(cmos[0x5D:0x68]))&255
        cmos[0x69]=0x55;cmos[0x6B]=0x40;cmos[0x6D]=1;cmos[0x6A]=(-0x55-0x41)&255
    hardware.saved_cmos=bytes(cmos)
    return composed(memory=hardware,keys=keys)


def resources():
    bars={0x10:0xFFFFF000,0x14:0xFFFFE004,0x18:0xFFFFFFFF,0x1C:0xFFFFFF01,0x20:0x0000FFE1}
    good=Endpoint(cls=0x020000,bars=bars);hardware=Hardware({0x60:Endpoint(cls=0x030000),0x68:good})
    row,fixture=compose(hardware);hardware.finish(fixture)
    assert good.read(0x10,4)==0xD0000000
    assert good.read(0x14,4)==0xD0002004 and good.read(0x18,4)==0
    assert good.read(0x1C,4)==0xC001 and good.read(0x20,4)==0xC101
    assert good.read(4,4)==0xA9000143,hex(good.read(4,4))
    rows=[{'bars':{f'{k:02X}':f'{good.read(k,4):08X}' for k in bars},'command_status':f'{good.read(4,4):08X}'}]
    vga=Endpoint(cls=0x030000,bars={0x10:0xFFFFF000,0x14:0xFFFFA000})
    hardware.pci.endpoints[0x60]=vga
    u,d,listing,state,cmos,step=fixture
    d.write(0x9E000+0x1000,2,0xFFFF)
    u.reg_write(x.UC_X86_REG_FS,0x9E00)
    invoke(fixture,'pci_initialize')
    assert not vga.read(4,2)&6 and vga.read(0x10,4)&~15 and not vga.read(0x14,4)&~15
    rows.append({'case':'VGA-valid-then-invalid-MMIO','command_status':f'{vga.read(4,4):08X}','special_enable_respects_rejection':True})
    bads=[('noncontiguous-mmio',{0x10:0xFFFFA000},2),('below1MiB',{0x10:0xFFFFF002},2),
          ('reserved-type',{0x10:0xFFFFF006},2),('wide-upper',{0x10:0xFFFFF004,0x14:0},2),
          ('wide-missing-partner',{0x24:0xFFFFF004},2),('mmio-pool',{0x10:0x80000000},2),
          ('noncontiguous-io',{0x10:0xFFFFFFA1},1),('io-width',{0x10:0xFFFE0001},1),
          ('io-reserved',{0x10:0xFFFFFF03},1),('io-pool',{0x10:0xFFFF8001},1),
          ('mmio-valid-then-invalid',{0x10:0xFFFFF000,0x14:0xFFFFA000},2),
          ('io-valid-then-invalid',{0x10:0xFFFFFFF9,0x14:0xFFFFFFA1},1)]
    for name,bar_masks,decode in bads:
        endpoint=Endpoint(bars=bar_masks);hardware=Hardware({0x60:Endpoint(cls=0x030000),0x68:endpoint})
        row,fixture=compose(hardware);hardware.finish(fixture)
        assert not endpoint.read(4,2)&(decode|4),(name,endpoint.read(4,2))
        assert endpoint.read(6,2)==0xA900,(name,'W1C status changed')
        rejected=list(bar_masks)[1:] if 'valid-then-invalid' in name else bar_masks
        assert all(not endpoint.read(offset,4)&~15 for offset in rejected),(name,bar_masks)
        if 'valid-then-invalid' in name:assert endpoint.read(0x10,4)&~15
        rows.append({'case':name,'decode_disabled':True,'status_preserved':True})
    return rows


def bf_modes():
    rows=[]
    for name,pi,writable,usable in (('switchable',0x8F,5,True),('fixed-compat',0x80,0,True),
        ('fixed-native',0x85,0,False),('mixed-fixed',0x81,0,False),('ignored-write',0x8F,0,False),
        ('unsupported-later-io-bar',0x8F,5,False)):
        bars={0x10:0xFFFFFFF9,0x14:0xFFFFFFA1} if name=='unsupported-later-io-bar' else None
        bf=Endpoint(identity=0x673A1060,cls=0x010100|pi,pi_writable=writable,bars=bars)
        hardware=Hardware({0x60:Endpoint(cls=0x030000),0x58:bf})
        row,fixture=compose(hardware);terminal=hardware.finish(fixture)
        u,d,listing,state,cmos,step=fixture;base=0x9E000
        assert d.read(base+0x1039,1)==bytes((usable,))
        assert bool(bf.read(4,2)&1)==usable,(name,bf.read(4,2))
        assert not hardware.af,(name,hardware.af)
        if not usable:assert not hardware.taskfiles,(name,hardware.taskfiles)
        for slot in (base,base+0x200):assert d.read(slot+0x20,1)!=b'\x01' and d.read(slot+state['S_ATAPI'],1)!=b'\x01'
        assert d.read(base+state['C_IDE'],1)==b'\x01','Saved Enabled must remain policy'
        boot=hardware.boot(fixture)
        if not usable:assert not hardware.taskfiles,(name,hardware.taskfiles)
        assert hardware.ata_visits==['ata_detect_primary','ide_apply_controller'],hardware.ata_visits
        accesses=[{'access':access,'count':count} for access,count in Counter(hardware.taskfiles).items()]
        rows.append({'mode':name,'pi_before':pi,'pi_after':bf.read(9,1),'usable':usable,'taskfile_count':len(hardware.taskfiles),'taskfiles':accesses,
                     'af_writes':hardware.af,'saved_ide':1,'terminal':row['terminal'],'consumer':terminal})
        rows[-1]['boot']=boot
        rows[-1]['actual_ata_visits']=hardware.ata_visits
    return rows


def interrupts():
    endpoints={}
    for slot in (12,13,14):
        for pin in (1,2,3,4):
            endpoints[slot*8+pin-1]=Endpoint(cls=0x030000 if (slot,pin)==(12,1) else 0x020000,header=0x80 if pin==1 else 0,pin=pin)
    hardware=Hardware(endpoints);row,fixture=compose(hardware);hardware.finish(fixture)
    u,d,listing,state,cmos,step=fixture
    assert hardware.south[0x43:0x45]==b'\x9A\xBC'
    assert hardware.south[0x46:0x48]==b'\x1F\x4F'
    hardware.south[0x46:0x48]=b'\xA0\x50'
    hardware.ports.update({0x4D0:0x21,0x4D1:0x80})
    invoke(fixture,'board_pci_router')
    assert hardware.south[0x46:0x48]==b'\xAF\x5F'
    assert hardware.ports[0x4D0]==0x21 and hardware.ports[0x4D1]==0x9E
    rows=[]
    for slot,wires in ((12,(9,10,11,12)),(13,(12,9,10,11)),(14,(11,9,10,12))):
        for pin,irq in enumerate(wires,1):
            assert endpoints[slot*8+pin-1].read(0x3C,1)==irq,(slot,pin)
            folder=PORT/'build/hardware-tests/pci-irq';folder.mkdir(parents=True,exist_ok=True)
            source=folder/'guest.asm';image=folder/'guest.bin'
            source.write_text(f'%define IRQ_NUMBER {irq}\n%define IRQ_VECTOR {0x70+irq-8}\n%include "pci-irq.asm"\n')
            post_module().assemble(source,image,[REPOSITORY/'shared/tests/dos',folder]);guest=image.read_bytes()
            for i,b in enumerate(guest):d.write(0x9000+i,1,b)
            u.mem_write(0x9000,guest)
            u.ctl_remove_cache(0x9000,0xA000)
            hardware.irq_endpoint=(slot,pin);hardware.irq_events=[];hardware.irq_active=False;hardware.irq_serviced=False
            u.reg_write(x.UC_X86_REG_CS,0);u.reg_write(x.UC_X86_REG_SS,0);u.reg_write(x.UC_X86_REG_SP,0x7000)
            u.emu_start(0x9000,0x9000+guest.index(b'\xF4'),count=80000)
            assert hardware.read(0xB91,1)==b'\x02',(slot,pin,hardware.irq_events)
            expected=[('assert',(slot,pin)),('deliver',irq),('deassert',(slot,pin)),('EOI',0xA0),('EOI',0x20)]*2
            assert hardware.irq_events==expected,(slot,pin,hardware.irq_events)
            rows.append({'slot':slot,'pin':pin,'irq':irq,'events':hardware.irq_events,'line':endpoints[slot*8+pin-1].read(0x3C,1)})
    hardware.irq_endpoint=None
    return rows


def run():
    hardware=Hardware({0x60:Endpoint(header=0x80),0x61:Endpoint(),0x70:Endpoint(identity=0xBEEFCAFE,header=0x80),
                       0x72:Endpoint(cls=0x030000),0x79:Endpoint(cls=0x030000)})
    row,fixture=compose(hardware);hardware.finish(fixture)
    public=api(fixture,hardware.pci)
    vga=[]
    for size in (32,48,64):
        hardware=Hardware(vga_kib=size);row,fixture=compose(hardware);vga.append(hardware.finish(fixture))
    payload={'api':public,'bars':resources(),'bf':bf_modes(),'vga':vga,'irq':interrupts()}
    image=PORT/'build/hardware-tests/geometry/baios-m919.bin';payload['rom_sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
    path=PORT/'build/research/hardware/pci-proof.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(payload,indent=2)+'\n')
    print(f'PCI installed API {len(public)}, BAR {len(payload["bars"])}, BF {len(payload["bf"])}, VGA {len(vga)}: PASS',flush=True)
    return path
