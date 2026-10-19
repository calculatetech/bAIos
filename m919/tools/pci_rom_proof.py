"""Execute PCI ROM deployment and the late legacy scan with decoded providers."""
import hashlib
import json
from pathlib import Path
from unicorn import UC_HOOK_MEM_WRITE
from pci_proof import Hardware,Endpoint,compose,post_module,invoke

PORT=Path(__file__).resolve().parents[1]


class ROMHardware(Hardware):
    def __init__(self,*,mask=0xFFFF0000,bad=None,blocked=False):
        self.card=Endpoint(identity=0x32491106,cls=0x010185,pin=1,
            bars={0x10:0xFFFFFFF9,0x14:0xFFFFFFFD,0x18:0xFFFFFFF9,
                  0x1C:0xFFFFFFFD,0x20:0xFFFFFFE1,0x24:0xFFFFFF01},rom_mask=mask)
        super().__init__({0x60:Endpoint(cls=0x030000),0x68:self.card})
        self.bad=bad;self.blocked=blocked;self.dshadow=bytearray(65536)
        self.dbase=bytearray(b'\xFF'*65536);self.rom_calls=[]

    def prepare(self,u):
        super().prepare(u)
        if not self.blocked:
            # Retain a legacy provider below the PCI window.
            self.later_segment=0xC800;self.later_return=0xC8007
            self.isa=bytes(u.mem_read(0xD0000,512))
            u.mem_write(0xC8000,self.isa)
            u.mem_write(0xD0000,bytes(self.dbase))
        else:self.dbase[:512]=u.mem_read(0xD0000,512)
        folder=PORT/'build/hardware-tests/pci-rom';folder.mkdir(parents=True,exist_ok=True)
        source=folder/'controller.asm';image=source.with_suffix('.bin')
        source.write_text('''bits 16
org 0
dw 0xAA55
db 64
jmp init
times 0x18-($-$$) db 0
dw pcir
times 0x40-($-$$) db 0
pcir: db 'PCIR'
dw 0x1106,0x3249,0,0x18
db 0,0x85,1,1
dw 64,0
db 0,0x80
dw 0
init:
cmp ax,0x68
jne failed
mov di,4
mov ax,0xB109
int 0x1A
jc failed
test cl,1
jz failed
or cl,4
mov ax,0xB10C
int 0x1A
mov di,0x30
mov ax,0xB10A
int 0x1A
test cl,1
jnz failed
mov di,0x3C
mov ax,0xB108
int 0x1A
cmp cl,12
jne failed
push ds
xor ax,ax
mov ds,ax
mov eax,[0x4C]
mov [cs:saved13],eax
mov word [0x4C],handler
mov [0x4E],cs
inc byte [0x475]
pop ds
mov al,0xDA
out 0x80,al
retf
failed: mov al,0xE9
out 0x80,al
hlt
handler: jmp far [cs:saved13]
saved13: dd 0
times 32768-($-$$) db 0x59
''')
        post_module().assemble(source,image,[folder]);raw=bytearray(image.read_bytes())
        if self.bad=='identity':raw[0x44]=0x07
        if self.bad=='code-type':raw[0x54]=3
        raw[-1]=(-sum(raw[:-1]))&255
        if self.bad=='checksum':raw[-1]^=1
        self.card_rom=bytes(raw);image.write_bytes(raw)
        def write(uc,access,address,size,value,user):
            if 0xD0000<=address<0xE0000 and not self.registers.get(0x55,0)&0x40:
                off=address-0xD0000;self.dshadow[off:off+size]=value.to_bytes(size,'little')
        u.hook_add(UC_HOOK_MEM_WRITE,write)

    def pci_write(self,address,port,size,value):
        super().pci_write(address,port,size,value)
        if hasattr(self,'isa'):self.machine.mem_write(0xC8000,self.isa)
        if not hasattr(self,'card_rom'):return
        effective=bytearray(self.dbase)
        base=self.card.read(0x30,4)
        if base&1 and self.card.read(4,2)&2:
            off=(base&~0x7FF)-0xD0000
            if 0<=off<=65536-len(self.card_rom):effective[off:off+len(self.card_rom)]=self.card_rom
        if self.registers.get(0x55,0)&0x80:
            for i in range(4):
                if self.registers.get(0x54,0)&(0x10<<i):
                    lo=i*16384;effective[lo:lo+16384]=self.dshadow[lo:lo+16384]
        self.machine.mem_write(0xD0000,bytes(effective))


def run():
    rows=[]
    for options in ({},{'mask':0xFFFF8000},{'bad':'checksum'},{'bad':'identity'},
                    {'bad':'code-type'},{'mask':0xFFFE0000},{'mask':0xFFFFA000},{'blocked':True}):
        hardware=ROMHardware(**options);row,fixture=compose(hardware)
        assert hardware.stop=='POST FF'
        entered=not options.get('bad') and not options.get('blocked') and options.get('mask',0xFFFF0000) in (0xFFFF0000,0xFFFF8000)
        assert hardware.provider_events.count(0xDA)==int(entered),(options,hardware.provider_events)
        assert 0xE9 not in hardware.provider_events
        assert hardware.card.read(0x30,4)==0
        assert hardware.card.read(4,2)&7==(5 if entered else 1),hex(hardware.card.read(4,2))
        assert hardware.card.read(6,2)==0xA900
        assert hardware.card.read(0x3C,1)==12
        u,d,listing,state,cmos,step=fixture
        if entered:
            assert hardware.registers[0x54]&0xF0==(0xF0 if not options else 0x30)
            assert hardware.registers[0x55]&0xC0==0xC0
            copied=bytes(u.mem_read(0xD0000,32768))
            # Init modifies only its saved INT13 continuation.
            assert copied[:0x40]==hardware.card_rom[:0x40]
            assert copied[-32:]==hardware.card_rom[-32:]
            assert int.from_bytes(u.mem_read(0x4E,2),'little')==0xD000
            assert u.mem_read(0x475,1)==b'\x01'
        assert 0xD2 in hardware.provider_events,('legacy provider lost',hardware.provider_events,hardware.provider_calls,bytes(u.mem_read(0xC8000,12)).hex(),hex(hardware.registers[0x54]))
        before=hardware.provider_events.count(0xDA)
        invoke(fixture,'option_rom_discovery')
        assert hardware.provider_events.count(0xDA)==before,'provider ran twice'
        boot=hardware.boot(fixture) if entered else None
        rows.append({'options':options,'initialized':entered,'terminal':row['terminal'],
                     'command':hardware.card.read(4,2),'rom_decode_off':True,'irq':12,
                     'legacy_provider_retained':True,'one_time_init':True,'boot':boot})
    rom=PORT/'build/hardware-tests/geometry/baios-m919.bin'
    payload={'cases':rows,'rom_sha256':hashlib.sha256(rom.read_bytes()).hexdigest()}
    path=PORT/'build/hardware-research/pci-rom-proof.json';path.write_text(json.dumps(payload,indent=2)+'\n')
    print(f'PCI ROM deployment: {len(rows)} cases PASS',flush=True)


if __name__=='__main__':run()
