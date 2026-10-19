"""Execute cache firmware against independently addressed SRAM, tags and DRAM."""
import hashlib
import json
import random
import struct
import sys
import importlib.util
from collections import OrderedDict
from pathlib import Path
from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn import x86_const as x

PORT=Path(__file__).resolve().parents[1]
REPOSITORY=PORT.parent
sys.path.insert(0,str(REPOSITORY))
from geometry_proof import DRAM, mapped


class Registers(dict):
    def get(self,key,default=None):
        value=super().get(key,default)
        return (value&0xF8)|3 if key==0x50 else value


class SRAM(DRAM):
    """Independent SRAM/tag capacity, dirty L2 and separate CPU cache policy."""
    def __init__(self,kib=512,banks=1,kind='real',fault=None,alias=None,tag_alias=False,ordinary_fault=None,ram=16,cpu_policy='wt',snoop=True,lost_writeback=False):
        super().__init__([(ram,False,False),None,None,None])
        self.registers=Registers(self.registers)
        self.capacity=kib*1024
        self.banks=banks
        self.kind=kind
        self.sram=bytearray(random.Random(0x8881).randbytes(self.capacity))
        self.sram_fault=fault
        self.sram_alias=alias
        self.tag_alias=tag_alias
        self.ordinary_fault=ordinary_fault
        self.lines={}
        self.l2_dirty=set()
        self.l2_copybacks=0
        self.lost_writeback=lost_writeback
        self.hits=0
        self.evictions=0
        self.hit_indices=set()
        self.coverage={name:set() for name in ('55','AA','address','inverse')}
        self.qualification_policies=set()
        self.machine=None
        self.cache_interval_instructions=0
        self.decoder=Cs(CS_ARCH_X86,CS_MODE_16)
        self.decoded={}
        self.opcodes={}
        self.qualifying=True
        self.queue=[]
        self.ports={}
        self.keys=[]
        self.key_points=set()
        self.keys_sent=[]
        self.key_log=[]
        self.speaker=[]
        self.l1=OrderedDict()
        self.l1_evictions=0
        self.l1_dirty=set()
        self.cpu_policy=cpu_policy
        self.snoop=snoop
        self.copybacks=0
        self.flushes=0
        self.flush_states=[]
        self.prime_reads={'before':0,'after':0}
        self.pit=0xFFFF
        self.pit_high=False
        self.fifo=[]
        self.command=[]
        self.fdc_irq=False
        self.pcn=0
        self.dma_bytes={4:[],5:[]}
        self.dma_mask=True
        self.dma_mode=0
        self.dma_page=0
        self.dma_pending=None
        self.dma_events=[]
        self.disc=bytearray((i*31+0x27)&255 for i in range(18*512))
        self.partial=False
        self.prefetch_ip=None
        self.prefetch_sent=False
        self.prefetch_done=False
        self.guest_exit=None

    def incoming(self,uc,port,size):
        if port==0x64:return int(bool(self.queue))
        if port==0x60:return self.queue.pop(0) if self.queue else 0
        if port==0x20:return 0
        if port==0x3F4:return 0xC0 if self.fifo else 0x80
        if port==0x3F5:return self.fifo.pop(0) if self.fifo else 0
        if port==0x3F7:return 0
        if port==0x40:
            result=(self.pit>>8)&255 if self.pit_high else self.pit&255
            self.pit_high=not self.pit_high
            return result
        return self.ports.get(port,0)

    def outgoing(self,uc,port,size,value):
        self.ports[port]=value
        if port==0x60:self.queue.append(0xFA)
        if port==0x61:self.speaker.append(value&3)
        if port==0x43 and value==0:self.pit=(self.pit-3000)&0xFFFF;self.pit_high=False
        if port==0x80 and value==0xE7:uc.emu_stop()
        if port==0x80 and value in (0xF9,0xFA):self.guest_exit=value;uc.emu_stop()
        if port==0x0C:self.dma_bytes={4:[],5:[]}
        if port in (4,5):self.dma_bytes[port].append(value)
        if port==0x81:self.dma_page=value
        if port==0x0B:self.dma_mode=value
        if port==0x0A:self.dma_mask=bool(value&4)
        if port==0x3F2 and value&4 and not self.ports.get('dor',0)&4:self.fdc_irq=True
        if port==0x3F2:self.ports['dor']=value
        if port==0x3F5:self.fdc_command(value)

    def fdc_command(self,value):
        self.command.append(value)
        command=self.command[0]
        length={3:3,4:2,7:2,8:1,0x0F:3,0x10:1,0x12:2,0x13:4,0x4A:2,0x45:9,0x46:9,0x56:9,0x4D:6}[command]
        if len(self.command)<length:return
        args=self.command;self.command=[]
        if command==8:self.fifo=[0x20,self.pcn]
        elif command==4:self.fifo=[0x28|(0x10 if self.pcn==0 else 0)|(args[1]&7)]
        elif command==0x10:self.fifo=[0x90]
        elif command in (7,0x0F):self.pcn=args[2] if command==0x0F else 0;self.fdc_irq=True
        elif command==0x4A:self.fifo=[0,0,0,self.pcn,0,1,2];self.fdc_irq=True
        elif command==0x56:self.fifo=[0,0,0,args[2],args[3],args[4],2];self.fdc_irq=True
        elif command in (0x45,0x46,0x4D):
            assert not self.dma_mask
            address=int.from_bytes(bytes(self.dma_bytes[4][-2:]),'little')+(self.dma_page<<16)
            count=int.from_bytes(bytes(self.dma_bytes[5][-2:]),'little')+1
            self.dma_pending=(command,args,address,count)
            self.prefetch_sent=False;self.prefetch_done=False

    def dma_complete(self):
        command,args,address,count=self.dma_pending
        count=min(count,256) if self.partial else count
        offset=(args[4]-1)*512 if command in (0x45,0x46) else 0
        # AMD19751 sections4.7/4.8: coherent master cycles require hardware
        # copyback and write invalidation. This seam does not prove UMC wiring.
        lines={a&~15 for a in range(address,address+count)}
        if self.snoop:
            for line in lines & self.l1_dirty:
                self.external_write(line,16,int.from_bytes(self.l1[line],'little'))
                self.l1_dirty.remove(line)
                self.copybacks+=1
            capacity=self.ordinary_capacity()
            for line in lines:
                index=self.index(line%capacity)
                cached=self.lines.get(index)
                if cached is not None and cached[0]==self.tag(line,capacity):
                    self.l2_writeback(index)
            if command==0x46:
                for line in lines:
                    self.l1.pop(line,None)
                    capacity=self.ordinary_capacity()
                    index=self.index(line%capacity)
                    cached=self.lines.get(index)
                    if cached is not None and cached[0]==self.tag(line,capacity):
                        del self.lines[index]
        if command==0x46:
            payload=bytes(self.disc[offset:offset+count])
            for i,value in enumerate(payload):super().write(address+i,1,value)
        else:
            payload=super().read(address,count)
            if command==0x45:self.disc[offset:offset+count]=payload
        self.dma_events.append({'command':command,'address':address,'count':count,'mode':self.dma_mode,
                                'payload':payload.hex(),'flushes':self.flushes,'prefetched':self.prefetch_done,
                                'cpu_policy':self.cpu_policy,'hardware_snoop':self.snoop,'copybacks':self.copybacks,
                                'l2_wb':self.l2_wb(),'l2_copybacks':self.l2_copybacks})
        self.fifo=[0x40 if self.partial else 0,0x20 if self.partial else 0,0,self.pcn,0,1,2]
        self.dma_pending=None

    def cpu_interrupt(self,uc,number,resume=None):
        sp=(uc.reg_read(x.UC_X86_REG_SP)-6)&0xFFFF
        ss=uc.reg_read(x.UC_X86_REG_SS)<<4
        frame=struct.pack('<HHH',uc.reg_read(x.UC_X86_REG_IP) if resume is None else resume,
                          uc.reg_read(x.UC_X86_REG_CS),uc.reg_read(x.UC_X86_REG_EFLAGS)&0xFFFF)
        uc.mem_write(ss+sp,frame);self.write(ss+sp,6,int.from_bytes(frame,'little'))
        target=self.read(number*4,4)
        uc.reg_write(x.UC_X86_REG_SP,sp)
        uc.reg_write(x.UC_X86_REG_EFLAGS,uc.reg_read(x.UC_X86_REG_EFLAGS)&~0x300)
        uc.reg_write(x.UC_X86_REG_CS,int.from_bytes(target[2:],'little'))
        uc.reg_write(x.UC_X86_REG_IP,int.from_bytes(target[:2],'little'))

    def interrupt(self,uc,number):
        if number!=0x10:return self.cpu_interrupt(uc,number)
        ax=uc.reg_read(x.UC_X86_REG_AX)
        if ax>>8==0:
            uc.mem_write(0xB8000,b' \x07'*2000)
            super().write(0x449,1,3)
            super().write(0x44A,2,80)
            super().write(0x484,1,24)
            super().write(0x485,2,16)
        elif ax>>8==0x0E:uc.report_output.append(ax&255)
        elif ax>>8==3:uc.reg_write(x.UC_X86_REG_DX,0);uc.reg_write(x.UC_X86_REG_CX,0x0607)

    def observe(self,uc,address,size):
        if address not in self.opcodes:self.opcodes[address]=bytes(uc.mem_read(address,size))
        opcode=self.opcodes[address]
        if opcode[:2] in (b'\x0F\x08',b'\x0F\x09'):
            if opcode[1]==9:
                for line in self.l1_dirty:
                    data=self.l1[line]
                    for i,value in enumerate(data):self.external_write(line+i,1,value)
                self.flushes+=1
            cpu_enabled=not uc.reg_read(x.UC_X86_REG_CR0)&0x40000000
            external_enabled=bool(self.registers.get(0x50,0)&0x80)
            self.flush_states.append((opcode[1],cpu_enabled,external_enabled))
            self.l1.clear();self.l1_dirty.clear()
            # Conservative seam: an off-L2 flush does not clear external tags.
            # The enabled flush response still needs physical confirmation.
            if external_enabled:
                if opcode[1]==9:
                    for index in list(self.l2_dirty):self.l2_writeback(index)
                self.lines.clear();self.l2_dirty.clear()
        active=self.registers.get(0x5A,0)&0xC0 or (self.qualifying and self.registers.get(0x50,0)&0x80)
        if active:
            assert not self.registers.get(0x55,0)&0x80,'Unqualified cache code fetched from shadow RAM'
            if address not in self.decoded:self.decoded[address]=next(self.decoder.disasm(bytes(uc.mem_read(address,size)),address)).mnemonic
            mnemonic=self.decoded[address]
            assert not mnemonic.startswith(('push','pop')) and mnemonic not in ('call','ret','enter','leave'),(hex(address),mnemonic)
            self.cache_interval_instructions+=1
        flags=uc.reg_read(x.UC_X86_REG_EFLAGS)
        if address==self.prefetch_ip:self.prefetch_done=True
        if address in self.key_points and self.keys and not self.queue and self.read(0x41A,2)==self.read(0x41C,2):
            key=self.keys.pop(0);self.keys_sent.append(key);self.queue.append(key)
            if getattr(self,'continuing',False):
                base=uc.reg_read(x.UC_X86_REG_FS)<<4
                self.key_log.append((key,*(self.read(base+self.state[n],1)[0] for n in ('U_PAGE','U_FOCUS','U_CHIP_SCREEN','U_FIELD')),self.read(base+self.state['U_CHIP'],10).hex()))
        if flags&0x200 and self.dma_pending is not None:
            if self.prefetch_ip is not None and not self.prefetch_sent:
                self.prefetch_sent=True;self.cpu_interrupt(uc,8)
            elif self.prefetch_ip is None or self.prefetch_done:
                self.dma_complete();self.cpu_interrupt(uc,14)
        elif flags&0x200 and self.fdc_irq:
            self.fdc_irq=False;self.cpu_interrupt(uc,14)
        elif flags&0x200 and self.queue and not self.ports.get(0x21,0)&2:
            self.cpu_interrupt(uc,9)
        elif opcode==b'\xF4' and flags&0x200:
            self.cpu_interrupt(uc,8,(uc.reg_read(x.UC_X86_REG_IP)+size)&0xFFFF)

    def index(self,address):
        address %= self.capacity
        if self.banks==2 and not self.registers[0x50]&8:
            address &= ~4
        if self.sram_alias is not None:address &= ~(1<<self.sram_alias)
        return address

    def cacheable(self,address):
        return address<self.capacity*(256 if self.registers.get(0x51,0)&1 else 128) and not 0xA0000<=address<0x100000

    def l2_wb(self):
        return bool(self.registers.get(0x50,0)&0x40)

    def tag(self,line,capacity):
        tag=(line//capacity)&(255 if self.registers.get(0x51,0)&1 else 127)
        return tag&~1 if self.tag_alias else tag

    def l2_writeback(self,index):
        if index not in self.l2_dirty:return
        tag,data=self.lines[index]
        if not self.lost_writeback:
            super().write(tag*self.ordinary_capacity()+index,16,int.from_bytes(data,'little'))
        self.l2_dirty.remove(index);self.l2_copybacks+=1

    def ordinary_capacity(self):
        code=dict.get(self.registers,0x50,0)&7
        assert 1<=code<=5,code
        return 0x10000<<(code-1)

    def l1_active(self,address):
        return self.machine is not None and not self.machine.reg_read(x.UC_X86_REG_CR0)&0x40000000 and not 0xA0000<=address<0x100000

    def read(self,address,size):
        if not self.l1_active(address):return self.external_read(address,size)
        out=bytearray()
        for a in range(address,address+size):
            line=a&~15
            out.append(self.l1_line(line)[a&15])
        return bytes(out)

    def l1_line(self,line):
        # Reported Am5x86 has 16 KiB L1; bound the seam so tests reach L2.
        if line not in self.l1:
            if len(self.l1)>=1024:
                old,data=self.l1.popitem(last=False)
                if old in self.l1_dirty:
                    self.external_write(old,16,int.from_bytes(data,'little'))
                    self.l1_dirty.remove(old)
                    self.copybacks+=1
                self.l1_evictions+=1
            self.l1[line]=bytearray(self.external_read(line,16))
        self.l1.move_to_end(line)
        return self.l1[line]

    def external_read(self,address,size):
        if self.registers.get(0x5A,0)&0x40:
            assert address<0xA0000 or address>=0x100000
            if self.kind in ('absent','floating'):return bytes([255])*size
            if self.kind=='fixed':return bytes([3])*size
            if self.kind=='stored':return super().read(address,size)
            return bytes(self.sram[self.index(a)] for a in range(address,address+size))
        if self.registers.get(0x50,0)&0x80 and self.cacheable(address):
            out=bytearray()
            for a in range(address,address+size):
                line=a&~15;capacity=self.ordinary_capacity();index=self.index(line%capacity)
                tag=self.tag(line,capacity)
                old=self.lines.get(index)
                if old is None or old[0]!=tag:
                    self.l2_writeback(index)
                    self.evictions+=int(old is not None)
                    payload=super().read(line,16)
                    cells=bytearray(16)
                    for i,value in enumerate(payload):cells[self.index(line+i)&15]=value
                    old=(tag,cells)
                    fault=self.ordinary_fault if self.ordinary_fault is not None else self.sram_fault
                    if fault is not None and index<=fault<index+16:
                        old[1][fault-index]^=1
                    self.lines[index]=old
                else:self.hits+=1;self.hit_indices.add(index)
                out.append(old[1][self.index(a)&15])
            return bytes(out)
        return super().read(address,size)

    def write(self,address,size,value):
        if self.qualifying and size==4 and 0x100000<=address<0x100000+self.capacity:
            if self.registers.get(0x5A,0)&0x40 or self.registers.get(0x50,0)&0x80:
                name={0x55AA55AA:'55',0xAA55AA55:'AA',address:'address',address^0xFFFFFFFF:'inverse'}.get(value)
                if name:
                    self.coverage[name].add(address)
                    if self.registers.get(0x50,0)&0x80:
                        self.qualification_policies.add(tuple(self.registers.get(r,0)&mask for r,mask in ((0x50,0x70),(0x51,0xF1),(0x5D,0x90),(0x61,0xC8),(0x5A,0x10))))
        if not self.l1_active(address):return self.external_write(address,size,value)
        for i,a in enumerate(range(address,address+size)):
            line=a&~15
            self.l1_line(line)[a&15]=(value>>(8*i))&255
            if self.cpu_policy=='wb':self.l1_dirty.add(line)
            else:self.external_write(a,1,(value>>(8*i))&255)

    def external_write(self,address,size,value):
        if self.registers.get(0x5A,0)&0x40:
            if self.kind=='stored':return super().write(address,size,value)
            if self.kind!='real':return
            for i,a in enumerate(range(address,address+size)):
                index=self.index(a)
                if index!=self.sram_fault:self.sram[index]=(value>>(i*8))&255
            return
        active=bool(self.registers.get(0x50,0)&0x80) and self.cacheable(address)
        if not active or not self.l2_wb():super().write(address,size,value)
        if active:
            for i,a in enumerate(range(address,address+size)):
                capacity=self.ordinary_capacity()
                index=self.index((a&~15)%capacity);tag=self.tag(a&~15,capacity)
                if self.l2_wb():self.external_read(a,1)
                old=self.lines.get(index)
                fault=self.ordinary_fault if self.ordinary_fault is not None else self.sram_fault
                cell=self.index(a)&15
                if old is not None and old[0]==tag and index+cell!=fault:
                    old[1][cell]=(value>>(8*i))&255
                    if self.l2_wb():self.l2_dirty.add(index)


class POSTHardware(SRAM):
    """External PCI VGA ROM, 8042 and absent ATA endpoints; no firmware hop replacement."""
    composed=True
    def __init__(self,**options):
        super().__init__(**options)
        self.initial_cmos=bytes(128)
        self.continuing=False
        self.kbc_command=0x5C;self.kbc_pending=None;self.output_port=0xCF
        self.pci_vga={0:0x12341111,8:0x03000000,0x0C:0}
        self.post_visits=[];self.ui_snapshots=[];self.stop=None
        self.ram_escape=True;self.escaped=False;self.setup_requested=False

    def pci_read(self,address,port,size):
        device=(address>>11)&31;offset=(address&0xFC)+(port-0xCFC)
        if device==16:values=self.registers
        elif device==12:values=None
        else:return (1<<(size*8))-1
        if values is not None:return sum(values.get(offset+i,0)<<(8*i) for i in range(size))
        value=self.pci_vga.get(offset&~3,0)
        return (value>>((offset&3)*8))&((1<<(size*8))-1)

    def pci_write(self,address,port,size,value):
        device=(address>>11)&31;offset=(address&0xFC)+(port-0xCFC)
        if device==16:
            for i in range(size):self.registers[offset+i]=(value>>(8*i))&255
            self.writes.append((offset,size,value))
        elif device==12:self.pci_vga[offset]=value

    def prepare(self,u):
        from geometry_proof import Listing
        listing=Listing(PORT/'build/hardware-tests/geometry/baios-m919.lst')
        self.cache_entry=0xF0000+listing.symbol('cache_initialize')
        self.qualify_entry=0xF0000+listing.symbol('cache_qualify')
        self.qualify_exit=0xF0000+listing.symbol('.done','cache_qualify')
        self.prime_points={0xF0000+listing.symbol('.prime_'+phase,'cache_enable'):phase for phase in ('before','after')}
        self.policy_point=0xF0000+listing.symbol('.policy','chipset_late_cache')
        self.ram_protected=0xF0000+listing.symbol('.protected','chipset_visible_ram_test')
        self.ram_done=0xF0000+listing.symbol('.done','chipset_visible_ram_test')
        self.ram_entry_policy=None
        # The VGA expansion ROM is an external device, not bAIos code.
        folder=PORT/'build/hardware-tests/cache-guests';folder.mkdir(parents=True,exist_ok=True)
        source=folder/'vga-seam.asm';image=folder/'vga-seam.bin'
        source.write_text('bits 16\norg 0\ndw 0xAA55\ndb 1\n'
                          'push ax\npush es\nxor ax,ax\nmov es,ax\nmov word [es:0x40],handler\n'
                          'mov word [es:0x42],0xC000\npop es\npop ax\nretf\nhandler: iret\n'
                          'times 511-($-$$) db 0\ndb 0\n')
        post_module().assemble(source,image,[folder])
        raw=bytearray(image.read_bytes());raw[-1]=(-sum(raw))&255;u.mem_write(0xC0000,bytes(raw))

    def incoming(self,u,port,size):
        if port==0x64:return int(bool(self.queue))|4
        if port in (0x1F7,0x177,0x3F6,0x376):return 0xFF
        return super().incoming(u,port,size)

    def outgoing(self,u,port,size,value):
        if port==0x64:
            if value==0x20:self.queue.append(self.kbc_command)
            elif value==0xAA:self.queue.append(0x55)
            elif value==0xAD:self.kbc_command|=0x10
            elif value==0xAE:self.kbc_command&=~0x10
            elif value in (0x60,0xD1):self.kbc_pending=value
        if port==0x60:
            if self.kbc_pending==0x60:self.kbc_command=value
            elif self.kbc_pending==0xD1:self.output_port=value
            else:self.queue.extend([0xFA,0xAA] if value==0xFF else [0xFA])
            self.kbc_pending=None;self.ports[port]=value;return
        super().outgoing(u,port,size,value)
        if port==0x80 and value==0xCA and self.keys and not self.setup_requested:
            self.queue.extend((0xE0,0x53));self.setup_requested=True
        if port==0x80 and value==0xFF:self.stop='POST FF';u.emu_stop()

    def observe(self,u,address,size):
        if address==self.ram_protected:
            assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
        if address==self.ram_done and self.ram_entry_policy is not None:
            assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==self.ram_entry_policy
        if address==self.cache_entry:self.qualifying=True
        if address==self.qualify_entry:self.qualifying=True
        if address==self.qualify_exit:self.qualifying=False
        if address in self.prime_points:
            phase=self.prime_points[address]
            assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==0
            assert bool(self.registers[0x50]&0x80)==(phase=='after')
            assert u.reg_read(x.UC_X86_REG_EDI)==0x100000+4*self.prime_reads[phase]
            self.prime_reads[phase]+=1
        if address==self.policy_point:
            selected=self.read((u.reg_read(x.UC_X86_REG_FS)<<4)+self.state['C_CHIP']+1,1)[0]
            assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
            assert u.reg_read(x.UC_X86_REG_EAX)&0x60000000==(0 if selected else 0x60000000)
        if self.continuing:
            if address==0xC0019:
                # Unicorn's segmented RETF returned to C-ROM's old IP. Model
                # only this external ROM return using the actual call frame.
                sp=u.reg_read(x.UC_X86_REG_SP);frame=self.read((u.reg_read(x.UC_X86_REG_SS)<<4)+sp,4)
                u.reg_write(x.UC_X86_REG_SP,sp+4)
                u.reg_write(x.UC_X86_REG_CS,int.from_bytes(frame[2:],'little'))
                u.reg_write(x.UC_X86_REG_IP,int.from_bytes(frame[:2],'little'))
                return
            point=self.points.get(address)
            if point:
                if point!='post_keyboard_wait' or point not in self.post_visits:self.post_visits.append(point)
                if point in ('chipset_visible_ram_test','setup_post_gate','chipset_late_cache'):
                    assert not self.registers[0x50]&0x80 and not self.registers.get(0x5A,0)&0x40,point
                    selected=self.read((u.reg_read(x.UC_X86_REG_FS)<<4)+self.state['C_CHIP']+1,1)[0]
                    policy=0 if selected else 0x60000000
                    assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==policy,point
                    if point=='chipset_visible_ram_test':self.ram_entry_policy=policy
                if point=='post_ui_cache':
                    phase=self.read((u.reg_read(x.UC_X86_REG_FS)<<4)+self.state['P_PHASE'],1)[0]
                    self.ui_snapshots.append({'phase':phase,'enabled':bool(self.registers[0x50]&0x80),
                                              'l1':not bool(u.reg_read(x.UC_X86_REG_CR0)&0x40000000)})
                if point=='post_notice_wait' and not self.defaults_requested:
                    self.queue.append(0x20);self.defaults_requested=True
                if point=='post_keyboard_wait' and self.ram_escape and not self.escaped:
                    base=u.reg_read(x.UC_X86_REG_FS)<<4
                    if self.read(base+self.state['P_RAM_FLAGS'],1)==b'\x01':
                        self.queue.append(1);self.escaped=True
                if point=='cache_recovery':self.defaults_requested=False
                if point=='cache_enable':self.enable_attempts+=1
                if point=='post_success_tone' and self.require_late:
                    assert 'chipset_late_cache' in self.post_visits,'Actual POST caller skipped late cache'
            if address in self.ui_returns:
                self.ui_snapshots[-1]['cells']=bytes(u.mem_read(0xB8000+14*160+48,24)).hex()
                self.ui_snapshots[-1]['l2_row']=bytes(u.mem_read(0xB8000+14*160,160)).hex()
                self.ui_snapshots[-1]['l1_cells']=bytes(u.mem_read(0xB8000+3*160+48,16)).hex()
        super().observe(u,address,size)


def initialized(**options):
    model=SRAM(**options)
    # mapped installs the external seam before executing the real reset/map/cache path.
    record,fixture=mapped(model.modules,expected=options.get('ram',16),memory=model)
    u,d,listing,state,cmos,step=fixture
    base=u.reg_read(x.UC_X86_REG_FS)<<4
    code=u.reg_read(x.UC_X86_REG_CS)<<4
    from geometry_proof import invoke
    invoke(fixture,'cache_qualify',count=5000000+model.capacity*24)
    assert not d.registers.get(0x5A,0)&0x40 and not d.registers.get(0x50,0)&0x80
    measured=d.read(base+0x1036,1)[0];flags=d.read(base+0x1038,1)[0]
    model.qualifying=False
    record.update(options=options,measured_code=measured,flags=flags,map=d.read(base+0x1037,1)[0],hits=d.hits,evictions=d.evictions,
                  coverage={k:len(v) for k,v in d.coverage.items()},ordinary_hit_indices=len(d.hit_indices),claimed_code=d.registers.get(0x50)&7)
    assert record['claimed_code']==3
    return record,fixture


def post_module():
    spec=importlib.util.spec_from_file_location('cache_native_post',PORT/'tools/test-post.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def composed(kib=64,l2=0,l1=0,record='valid',keys=(),memory=None,missing_late=False,chip=None,cpu_signature=0xDEAD04F0,rom_change=False,hardware=POSTHardware,**options):
    d=memory or hardware(kib=kib,**options)
    cmos=bytearray(post_module().nvram(types=0x40)[:128]) if memory is None else bytearray(d.saved_cmos)
    if memory is None:
        cmos[0x5D:0x68]=b'P1\x01'+bytes((3,4,1,3,0,1,0,1))
        cmos[0x68]=(-sum(cmos[0x5D:0x68]))&255
        cmos[0x69]=0x55;cmos[0x6B]=0x40;cmos[0x6C]=l1;cmos[0x6D]=l2
        cmos[0x6A]=(-0x55-0x40-l1-l2)&255
        if chip is not None:
            assert len(chip)==24
            cmos[0x69]=0x56;cmos[0x6B:0x80]=chip[:21];cmos[0x33:0x36]=chip[21:]
            cmos[0x6A]=(-0x56-sum(chip))&255
        if record=='missing':cmos[0x69]=0
        if record=='invalid':cmos[0x6D]=2;cmos[0x6A]=(-0x55-0x40-l1-2)&255
        if record=='recovery':cmos[0x69]=0xD2
    d.initial_cmos=bytes(cmos);d.continuing=False;d.qualifying=False
    d.stop=None;d.keys=list(keys);d.keys_sent=[];d.key_log=[];d.queue=[];d.escaped=False;d.setup_requested=False;d.defaults_requested=False
    d.post_visits=[];d.ui_snapshots=[];d.enable_attempts=0;d.reset_requests=[];d.require_late=True
    d.prime_reads={'before':0,'after':0};d.cache_interval_instructions=0;d.qualification_policies=set()
    row,fixture=mapped(d.modules,expected=d.modules[0][0],memory=d,cpu_signature=cpu_signature)
    u,d,listing,state,cmos,step=fixture;code=u.reg_read(x.UC_X86_REG_CS)<<4
    d.state=state;d.active_cmos=cmos;d.qualifying=False
    if rom_change:
        image=bytearray(u.mem_read(code,0x10000));image[0xFE00]^=1
        image[0xFFEF]=(image[0xFFEF]-sum(image))&255
        u.mem_write(code,bytes(image));row['mutated_system_sha256']=hashlib.sha256(image).hexdigest()
    names=('init_pic_pit','init_rtc','init_at_prerequisites','init_superio','pci_initialize','initialize_video','init_keyboard','arm_keyboard_runtime','board_a20_handoff','settings_load','chipset_apply','chipset_visible_ram_test','init_peripherals','setup_post_gate','chipset_late_cache',
           'chipset_post_ram_cache','cache_validation_reuse','cache_validation_save','cache_validation_identity','cache_qualify','cache_enable','cache_recovery','post_ui_cache','post_debug_summary','post_success_tone','setup_main','settings_save','post_keyboard_wait','post_notice_wait','post_early_setup')
    d.points={code+listing.symbol(name):name for name in names};d.points[code+listing.symbol('startup')]='startup'
    d.ui_returns=set()
    for i,line in enumerate(listing.lines):
        if 'call post_ui_cache' in line:d.ui_returns.add(code+listing.offset(i))
    d.key_points={code+listing.symbol('.input','setup_main'),code+listing.symbol('.wait','setup_confirm'),
                  code+listing.symbol('.wait','setup_choices'),code+listing.symbol('.wait','chipset_ui_choices')}
    if missing_late:
        index=next(i for i,line in enumerate(listing.lines) if 'call chipset_late_cache' in line)
        offset=listing.offset(index-1)
        image=PORT/'build/hardware-tests/geometry/baios-m919.bin'
        raw=bytearray(image.read_bytes());call=raw[0x10000+offset:0x10000+offset+3]
        assert call[0]==0xE8 and (offset+3+int.from_bytes(call[1:],'little',signed=True))&0xFFFF==listing.symbol('chipset_late_cache')
        raw[0x10000+offset:0x10000+offset+3]=b'\x90'*3
        (image.parent/'missing-late-negative.bin').write_bytes(raw)
        u.mem_write(code+offset,b'\x90'*3)
    d.continuing=True
    # Preserve the startup's existing return frame; execute the caller, not helpers.
    extra=d.modules[0][0]*0x100000*3 if cmos[0x69]==0x56 and cmos[0x71]&1 else 0
    if not d.ram_escape:extra+=d.modules[0][0]*0x100000*20
    u.emu_start(code+u.reg_read(x.UC_X86_REG_IP),code+0xFFFF,count=2000000+d.capacity*40+extra)
    assert d.stop or d.reset_requests or d.ports.get(0x80)==0xE7,(u.reg_read(x.UC_X86_REG_IP),d.post_visits,d.ports.get(0x80),d.keys,d.key_log)
    d.saved_cmos=bytes(cmos)
    row.update(measured_code=d.read((state_seg:=u.reg_read(x.UC_X86_REG_FS)<<4)+0x1036,1)[0],
               flags=d.read(state_seg+0x1038,1)[0],post_visits=d.post_visits,ui=d.ui_snapshots,
               enabled=bool(d.registers[0x50]&0x80),l1=not bool(u.reg_read(x.UC_X86_REG_CR0)&0x40000000),
               enable_attempts=d.enable_attempts,reset_requests=list(d.reset_requests),terminal=d.stop or ('reset' if d.reset_requests else 'E7'),
               ram_escaped=d.escaped)
    if row['flags']==2:
        row['cache_failure']={'stage':d.read(state_seg+0x120C,1)[0],
                              'address':int.from_bytes(d.read(state_seg+0x1208,4),'little'),
                              'screen':bytes(u.mem_read(0xB8000+22*160,160))[::2].decode('ascii'),
                              'expected':int.from_bytes(d.read(state_seg+0x1210,4),'little'),
                              'observed':int.from_bytes(d.read(state_seg+0x1214,4),'little')}
    if d.stop:
        assert d.post_visits.index('chipset_visible_ram_test')<d.post_visits.index('setup_post_gate')<d.post_visits.index('chipset_late_cache')<d.post_visits.index('post_debug_summary')
        mode='WB' if d.registers[0x50]&0x40 else 'WT'
        value=(f'{kib} KB {mode}' if row['enabled'] else f'{kib} KB Off') if row['measured_code'] else 'Disabled'
        cells=bytes(u.mem_read(0xB8000+4*160+40,24))
        assert cells[::2]==value.ljust(12).encode() and cells[1::2]==b'\x07'*12,(cells,value)
        for snap in d.ui_snapshots:
            assert bytes.fromhex(snap['l2_row'])==b' \x07'*80,snap
            l1_text=('Enabled' if snap['l1'] else 'Disabled').ljust(8)
            cells=bytes.fromhex(snap['l1_cells'])
            assert cells[::2]==l1_text.encode() and cells[1::2]==b'\x07'*8,(snap,l1_text)
        row['summary']=value
        assert d.read(state_seg+state['C_TYPES'],1)==b'\x40'
        assert d.read(state_seg+state['C_NUMLOCK'],3)==bytes((1,0,2))
        assert d.read(state_seg+state['C_SEEK'],1)==b'\x01'
        assert d.read(state_seg+state['C_HDD'],1)==b'\x01' and d.read(state_seg+state['C_SLAVE'],1)==b'\x01'
        ports=cmos[0x60:0x68]
        assert d.read(state_seg+state['C_PORTS'],8)==ports
        waits=d.read(state_seg+state['C_CHIP'],1)[0]
        assert d.registers[0x51]&0xF0==waits
        row['unrelated_fields']={'floppy':64,'ports':d.read(state_seg+state['C_PORTS'],8).hex(),
                                 'waits':waits}
    print(f'Composed cache {kib} KiB {record}: {row["terminal"]}; L2={row["enabled"]} L1={row["l1"]}',flush=True)
    return row,fixture


def policy():
    results=[]
    for kib,l2,l1,options in ((64,0,0,{}),(64,0,1,{}),(64,1,0,{}),(64,1,1,{}),
                             (128,0,1,{}),(256,0,1,{}),(512,0,1,{}),(512,1,1,{}),(1024,0,1,{}),(64,0,0,{'ram':32}),
                             (64,0,0,{'kind':'absent'})):
        row,fixture=composed(kib=kib,l2=l2,l1=l1,**options)
        expected=l2==0 and not options
        assert row['enabled']==expected and row['l1']==bool(l1),row
        assert fixture[1].enable_attempts==1
        results.append(row)
    row,fixture=composed(tag_alias=True)
    u,d,_,_,cmos,_=fixture
    assert row['flags']==2 and row['terminal']=='reset' and cmos[0x69]==0xD2 and cmos[0x36]==0x1A,row
    assert 3 in d.speaker and d.gates[0x61]&3==0
    next_row,next_fixture=composed(memory=d)
    assert not next_row['enabled'] and next_fixture[4][0x69]==0xD2
    row['recovery']=next_row;row['error_tone']=True
    # Saving Enabled again permits another qualification; recovery still disables L2.
    saved=bytearray(d.saved_cmos);saved[0x69]=0x55;saved[0x6B:0x80]=bytes(21);saved[0x33:0x36]=bytes(3)
    saved[0x6A]=(-0x55)&255;saved[0x36]=0x1A;d.saved_cmos=bytes(saved)
    persistent,_=composed(memory=d)
    assert persistent['terminal']=='reset' and not persistent['enabled'],persistent
    row['persistent']=persistent;results.append(row)
    row,fixture=composed(l1=1,cpu_policy='wb')
    u,d,listing,_,_,_=fixture
    old=DRAM.read(d,0x20000,4)
    guest(fixture,'dirty-warm',f'mov dword [dword 0x20000],0xC0DEFACE\ncall 0xF000:0x{listing.symbol("warm_reset"):04X}',reset=True)
    assert DRAM.read(d,0x20000,4)==b'\xCE\xFA\xDE\xC0' and old!=b'\xCE\xFA\xDE\xC0'
    next_row,next_fixture=composed(memory=d,l1=1)
    assert DRAM.read(d,0x20000,4)==b'\xCE\xFA\xDE\xC0'
    assert next_row['enabled'] and next_row['l1']
    row['warm_reload']=next_row;row['warm_dirty_data_restored']=True;results.append(row)
    try:composed(missing_late=True)
    except AssertionError as error:
        assert str(error)=='Actual POST caller skipped late cache',str(error)
        image=PORT/'build/hardware-tests/geometry/missing-late-negative.bin'
        results.append({'negative':'actual POST late-cache call replaced by three NOPs',
                        'expected_rejection':str(error),'mutated_rom_sha256':hashlib.sha256(image.read_bytes()).hexdigest()})
    else:raise AssertionError('Missing actual late-cache call was not detected')
    return results


def settings():
    results=[]
    for record,l2,l1 in (('valid',0,1),('valid',1,1),('invalid',0,1),('missing',0,1),('recovery',0,1)):
        row,fixture=composed(kib=128,l2=l2,l1=l1,record=record)
        if row['terminal']=='reset':
            assert record=='invalid' and fixture[1].defaults_requested,row
            reloaded,fixture=composed(kib=128,memory=fixture[1]);row['defaults_reload']=reloaded
            active=reloaded
        else:active=row
        expected=l2 if record=='valid' else 1 if record=='recovery' else 0
        expected_l1=l1 if record=='valid' else 0 if record=='recovery' else 1
        u,d,_,state,_,_=fixture;base=u.reg_read(x.UC_X86_REG_FS)<<4
        assert d.read(base+state['C_CHIP']+2,1)==bytes([expected])
        assert active['enabled']==(expected==0) and active['l1']==bool(expected_l1),active
        assert active['unrelated_fields']['waits']==(0x40 if record=='valid' else 0 if record=='recovery' else 0xF0)
        row['record']=record;results.append(row)
    navigation=[0x50]*4+[28,0x50,28,0x50]
    for name,initial,keys,expected,l1 in (
        ('edit-disabled',0,navigation+[0x4D,0x44,28],1,1),
        ('edit-enabled',1,navigation+[0x4B,0x44,28],0,1),
        ('F9-cancel',1,[0x43,1,0x44,28],1,1),
        ('F9-accept',1,[0x43,28,0x44,28],0,1)):
        row,fixture=composed(kib=128,l2=initial,l1=1,keys=keys)
        u,d,_,state,cmos,_=fixture
        assert row['terminal']=='reset' and 'setup_main' in row['post_visits'] and 'settings_save' in row['post_visits'],row
        assert not d.keys and d.keys_sent==list(keys),(d.keys,d.keys_sent)
        assert d.reset_requests==[0xFE]
        saved=bytes(cmos)
        assert cmos[0x69]==0x56 and cmos[0x6D]==expected
        assert cmos[0x6B]==(0xF0 if name=='F9-accept' else 0x40)
        assert cmos[0x6C]==l1 and (sum(cmos[0x69:0x80])+sum(cmos[0x33:0x36]))&255==0
        next_row,next_fixture=composed(kib=128,memory=d)
        u,d,_,state,cmos,_=next_fixture;base=u.reg_read(x.UC_X86_REG_FS)<<4
        assert d.read(base+state['C_CHIP']+2,1)==bytes([expected]),(name,cmos[0x69:0x70])
        assert cmos[0x69]==0x56
        assert next_row['enabled']==(expected==0) and next_row['l1']==bool(l1),next_row
        assert next_row['unrelated_fields']['waits']==(0xF0 if name=='F9-accept' else 0x40)
        assert cmos[0x38:0x40]==saved[0x38:0x40] and cmos[0x5D:0x69]==saved[0x5D:0x69]
        row.update(record=name,keys=keys,reload=next_row,unrelated_saved_records_preserved=True)
        results.append(row)
    return results


def guest(fixture,name,body,reset=False):
    u,d,listing,state,cmos,step=fixture
    folder=PORT/'build/hardware-tests/cache-guests';folder.mkdir(parents=True,exist_ok=True)
    source=folder/(name+'.asm');image=folder/(name+'.bin')
    source.write_text('bits 16\norg 0x7000\n'+body+'\nmov al,0xF9\nout 0x80,al\nhlt\n')
    post_module().assemble(source,image,[folder])
    raw=image.read_bytes();u.mem_write(0x7000,raw)
    u.ctl_remove_cache(0x7000,0x8000)
    for cache in (d.opcodes,d.decoded):
        for address in list(cache):
            if 0x7000<=address<0x8000:del cache[address]
    prefetch=raw.find(b'\x66\xA1\x00\x80')
    d.prefetch_ip=0x7000+prefetch+4 if prefetch>=0 else None
    for i,value in enumerate(raw):DRAM.write(d,0x7000+i,1,value)
    for reg,value in ((x.UC_X86_REG_CS,0),(x.UC_X86_REG_DS,0),(x.UC_X86_REG_ES,0),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x6E00),(x.UC_X86_REG_EFLAGS,0x202)):
        u.reg_write(reg,value)
    d.guest_exit=None
    u.emu_start(0x7000,0x8000,count=3000000)
    if reset:assert d.reset_requests==[0xFE]
    else:assert d.guest_exit==0xF9,(name,d.guest_exit,u.reg_read(x.UC_X86_REG_IP),d.command,d.fifo)
    u.reg_write(x.UC_X86_REG_CS,0xF000)


def dma(l2_wb=False):
    results=[]
    operations=(('write',3,False),('read',2,False),('format',5,False),('partial-read',2,True),('verify',4,False))
    cases=[(*operation,cpu,True) for cpu in (('wt',) if l2_wb else ('wt','wb')) for operation in operations]
    cases.extend((('read',2,False,'wt',False),('write',3,False,'wt' if l2_wb else 'wb',False)))
    certified=None
    for name,operation,partial,cpu,snoop in cases:
        if certified is not None:
            memory=POSTHardware(kib=128 if l2_wb else 64,cpu_policy=cpu,snoop=snoop)
            memory.saved_cmos=certified
            row,fixture=composed(kib=128 if l2_wb else 64,memory=memory)
            assert 'cache_qualify' not in row['post_visits']
        elif l2_wb:
            from timing_proof import options
            row,fixture=composed(kib=128,chip=options(l2=0,wb=True),cpu_policy=cpu,snoop=snoop)
        else:row,fixture=composed(l1=1,cpu_policy=cpu,snoop=snoop)
        assert row['enabled'] and row['l1'],row
        u,d,listing,state,cmos,step=fixture
        if certified is None:certified=d.saved_cmos
        d.partial=partial
        pattern=bytes((i*7+0xA1)&255 for i in range(512))
        # Exercise both WT publication and WB hardware copyback, then a CPU
        # prefetch before the independent master writes backing DRAM.
        source='jmp main\nirq_prefetch: push eax\nmov eax,[0x8000]\npop eax\niret\nmain: xor ax,ax\nmov ds,ax\nmov es,ax\ncli\nmov word [0x70],irq_prefetch\nmov word [0x72],0\nsti\nmov di,0x8000\nmov cx,512\nmov al,0xA1\n.fill: stosb\nadd al,7\nloop .fill\n'
        if operation==5:
            source+='mov di,0x8000\nmov cx,18\nmov eax,0x02010000\n.chrn: stosd\nadd eax,0x10000\nloop .chrn\n'
        source+=f'mov ax,0x{operation:02X}{18 if operation==5 else 1:02X}\nmov bx,0x8000\nmov cx,1\nxor dx,dx\nint 0x13\npushf\npop bx\n'
        source+='mov [0x8500],ax\nmov [0x8502],bx\nmov si,0x8000\nmov di,0x8600\nmov cx,512\nrep movsb\n'
        guest(fixture,name,source)
        returned=int.from_bytes(d.read(0x8500,2),'little');carry=int.from_bytes(d.read(0x8502,2),'little')&1
        assert carry==int(partial) and returned>>8==(0x10 if partial else 0),(name,hex(returned),carry)
        assert d.dma_mask
        if operation==4:assert not d.dma_events
        else:
            event=d.dma_events[-1]
            assert event['prefetched'],'Actual IRQ0/INT1C pre-DMA CPU read was not reached'
            assert event['mode']==(6 if operation==2 else 10)
            if operation==3:assert (bytes.fromhex(event['payload'])==pattern)==snoop
            if operation==5:assert bytes.fromhex(event['payload'])==b''.join(bytes((0,0,i,2)) for i in range(1,19))
            if operation==2:
                expected=bytes(d.disc[:256])+pattern[256:] if partial else bytes(d.disc[:512])
                assert (d.read(0x8600,512)==expected)==snoop,(name,cpu,snoop)
        results.append(dict(row,name=name,cpu_policy=cpu,hardware_snoop=snoop,returned=returned,carry=carry,
                            dma=d.dma_events,masked=True,coherent=snoop))
    return results


def early_discovery():
    class Probe(SRAM):
        def __init__(self,**options):
            super().__init__(**options)
            self.probe_writes=[]

        def external_write(self,address,size,value):
            if self.registers.get(0x5A,0)&0x40:
                code=dict.get(self.registers,0x50,0)&7
                assert size==1,(address,size)
                if address==4:assert 1<=code<=5,('bank probe before capacity',code)
                self.probe_writes.append((address,code))
            return super().external_write(address,size,value)

    results=[]
    cases=[dict(kib=kib,banks=banks) for kib,banks in ((64,1),(512,1),(512,2),(1024,2))]
    cases += [dict(kind=kind) for kind in ('absent','floating','stored')]
    for options in cases:
        d=Probe(**options)
        row,fixture=mapped(d.modules,expected=16,memory=d)
        u,_,listing,state,cmos,step=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        code=d.read(base+0x1036,1)[0]
        cache_map=d.read(base+0x1037,1)[0]
        expected={64:1,512:4,1024:5}[d.capacity//1024] if d.kind=='real' else 0
        assert code==expected and cache_map==expected+(8 if expected and d.banks==2 else 0),(options,code,cache_map)
        assert d.read(base+0x1038,1)==b'\0'
        assert not d.registers.get(0x5A,0)&0x40 and not d.registers.get(0x50,0)&0x80
        assert d.probe_writes
        row.update(options=options,measured_code=code,map=cache_map,byte_witnesses=True,bank_after_capacity=True)
        results.append(row)
    return results


def recovery_live():
    results=[]
    row,fixture=composed(kib=64,l1=1,cpu_policy='wb')
    assert row['terminal']=='POST FF' and row['enabled'] and row['l1'],row
    results.append(row)
    d=fixture[1]
    saved=bytearray(d.saved_cmos);saved[0x36]=0x1A;d.saved_cmos=saved
    d.prime_reads={'before':0,'after':0}
    row,fixture=composed(kib=64,memory=d)
    assert row['terminal']=='POST FF' and fixture[4][0x36]==0,row
    results.append(dict(row,old_recovery_notice_cleared_after_success=True))
    for options in (dict(ordinary_fault=0x100),dict(tag_alias=True),dict(alias=3)):
        row,fixture=composed(kib=64,l1=1,**options)
        u,d,listing,state,cmos,step=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        assert row['terminal']=='reset' and row['flags']==2 and cmos[0x69]==0xD2,row
        detail=row['cache_failure']
        expected=5 if 'tag_alias' in options else (3 if 'alias' in options else 1)
        assert detail['stage']==expected,detail
        if expected<=4:
            assert detail['observed']!=detail['expected'],detail
        assert fixture[4][0x36]==0x1A
        next_row,next_fixture=composed(memory=d)
        assert next_row['terminal']=='POST FF' and not next_row['enabled'],next_row
        assert 'cache_qualify' not in next_row['post_visits'] and next_fixture[4][0x69]==0xD2,next_row
        assert next_fixture[1].read(base+state['C_CHIP']+2,1)==b'\x01'
        row['recovery']=next_row
        results.append(dict(row,recovery_boot_skipped_l2=True))
    return results




def recovery_boundaries_live():
    class HeldNotice(POSTHardware):
        def __init__(self):
            super().__init__(kib=64,banks=2,ordinary_fault=0x103)
            self.non_make_polls=0;self.make_sent=False

        def prepare(self,u):
            self.notice_active=False
            super().prepare(u)

        def observe(self,u,address,size):
            if self.continuing and self.points.get(address)=='post_notice_wait':
                self.defaults_requested=True  # Suppress the ordinary fixture's automatic make.
                self.notice_active=True
            super().observe(u,address,size)

        def interrupt(self,u,number):
            if self.notice_active and number==0x16 and u.reg_read(x.UC_X86_REG_AH)==1:
                assert not self.reset_requests and not self.registers[0x50]&0x80
                base=u.reg_read(x.UC_X86_REG_FS)<<4
                assert self.read(base+self.state['C_CHIP']+2,1)==b'\x01'
                assert self.active_cmos[0x69]==0xD2 and self.active_cmos[0x36]==0x5A
                assert 3 in self.speaker
                text=bytes(u.mem_read(0xB8000+22*160,160))[::2].decode('ascii')
                assert 'Bank 0 byte 3  D24-31' in text and '00100100' in text,text
                if not self.make_sent:
                    self.non_make_polls+=1
                    if self.non_make_polls==1:self.queue.extend((0xA0,0xFA))
                    elif self.non_make_polls==3:
                        self.queue.append(0x20);self.make_sent=True
            super().interrupt(u,number)

    class LateDRAMFault(POSTHardware):
        def __init__(self,persistent):
            super().__init__(kib=64)
            self.persistent=persistent;self.runtime_checks=0

        def prepare(self,u):
            self.fault=None  # Restrict the external fault to the late runtime check.
            super().prepare(u)
            from geometry_proof import Listing
            listing=Listing(PORT/'build/hardware-tests/geometry/baios-m919.lst')
            self.runtime_point=0xF0000+listing.symbol('chipset_runtime_ram_check')

        def observe(self,u,address,size):
            if self.continuing and address==self.runtime_point:
                self.runtime_checks+=1
                self.fault=0x10000 if self.runtime_checks==1 or self.persistent else None
            super().observe(u,address,size)

    def saved(d):
        cmos=bytearray(post_module().nvram(types=0x40)[:128])
        cmos[0x69]=0x55;cmos[0x6B:0x6E]=bytes((0x40,1,0));cmos[0x6A]=(-0x55-0x40-1)&255
        cmos[0x5D:0x68]=b'P1\x01'+bytes((3,4,1,3,0,1,0,1))
        cmos[0x68]=(-sum(cmos[0x5D:0x68]))&255
        d.saved_cmos=bytes(cmos)

    results=[]
    d=HeldNotice();saved(d)
    row,fixture=composed(memory=d)
    assert row['terminal']=='reset' and d.non_make_polls==3 and d.make_sent and not d.queue,row
    assert d.reset_requests==[0xFE] and fixture[4][0x36]==0x1A
    assert d.read(0x41A,2)==d.read(0x41C,2),'Notice key was not consumed'
    next_row,_=composed(memory=d)
    assert next_row['terminal']=='POST FF' and not next_row['enabled'],next_row
    results.append(dict(row,non_make_wait_visits=3,make_consumed=True,recovery=next_row))
    for persistent in (False,True):
        d=LateDRAMFault(persistent);saved(d)
        row,fixture=composed(memory=d)
        assert row['terminal']=='reset' and d.reset_requests==[0xFE] and fixture[4][0x69]==0xD2,row
        assert fixture[4][0x36]==0x1A and not row['enabled'] and 3 in d.speaker
        next_row,next_fixture=composed(memory=d)
        assert next_row['terminal']==('E7' if persistent else 'POST FF'),next_row
        assert not next_row['reset_requests'] and not next_row['enabled'] and d.runtime_checks==2
        assert 'cache_qualify' not in next_row['post_visits'] and next_fixture[4][0x69]==0xD2
        results.append(dict(row,persistent=persistent,recovery=next_row))
    return results


def pattern_report_live():
    class SecondReadFault(POSTHardware):
        def observe(self,u,address,size):
            opcode=bytes(u.mem_read(address,size))
            if self.qualifying and opcode==bytes.fromhex('80E37F') and u.reg_read(x.UC_X86_REG_BL)==0x81:
                self.lines[0x100][1][0]^=1
            super().observe(u,address,size)

    results=[]
    for read_pass in (1,2):
        if read_pass==1:
            row,fixture=composed(kib=64,l1=1,ordinary_fault=0x100)
        else:
            d=SecondReadFault(kib=64)
            saved=bytearray(post_module().nvram(types=0x40)[:128])
            saved[0x69]=0x55;saved[0x6B:0x6E]=bytes((0x40,1,0));saved[0x6A]=(-0x55-0x40-1)&255
            d.saved_cmos=saved
            row,fixture=composed(kib=64,memory=d)
        detail=row['cache_failure']
        assert row['terminal']=='reset' and detail['stage']==1,detail
        assert detail['address']==0x100100 and detail['expected']==0x55AA55AA,detail
        assert detail['observed']!=0x55AA55AA,detail
        assert fixture[4][0x69]==0xD2 and fixture[1].defaults_requested
        results.append(row)
    return results


def ami_diagnostic_live():
    class DiagnosticRegisters(Registers):
        def get(self,key,default=None):
            if key==0x5B and self.get(0x5A,0)&0x80:
                d=self.owner
                d.events.append(('read5B',d.read_words))
                return 0 if d.bad_readback else 0x55
            return super().get(key,default)

    class DiagnosticSRAM(SRAM):
        def __init__(self,**options):
            self.bad_readback=options.pop('bad_readback',False)
            super().__init__(**options)
            self.registers=DiagnosticRegisters(self.registers);self.registers.owner=self
            self.started=False;self.finished=False;self.read_words=0;self.events=[]

        def read(self,address,size):
            if self.started and not self.finished and size==2 and address<0x10000:
                assert address==(self.read_words%0x8000)*2,(self.read_words,address)
                assert not self.machine.reg_read(x.UC_X86_REG_CR0)&0x60000000
                assert dict.get(self.registers,0x50)==6
                assert self.registers[0x51]==1,(self.registers[0x51],self.read_words,self.events,self.writes[-8:])
                self.read_words+=1
            return super().read(address,size)

        def outgoing(self,u,port,size,value):
            super().outgoing(u,port,size,value)
            if not 0xCFC<=port<=0xCFF:return
            address=self.ports.get(0xCF8,0)
            offset=(address&0xFC)+(port-0xCFC)
            if offset==0x50 and value==6 and not self.started:self.started=True
            if not self.started or self.finished:return
            if offset==0x5A:
                if value&0x80:self.events.append(('mode_on',self.read_words))
                elif self.events:
                    self.events.append(('mode_off',self.read_words));self.finished=True
            if offset==0x5B:self.events.append(('write5B',self.read_words,value))

    results=[]
    for options in (dict(kib=64),dict(kib=512),dict(kib=512,banks=2),dict(kib=64,bad_readback=True),dict(kib=64,kind='absent')):
        d=DiagnosticSRAM(**options)
        row,fixture=mapped(d.modules,expected=16,memory=d)
        u,_,_,_,_,_=fixture;base=u.reg_read(x.UC_X86_REG_FS)<<4
        assert d.read_words==9*0x8000 and d.finished
        assert d.events==[('mode_on',0x8000),('write5B',3*0x8000,0x55),('read5B',5*0x8000),
                          ('write5B',7*0x8000,0x55),('read5B',9*0x8000),('mode_off',9*0x8000)],d.events
        expected=0 if d.bad_readback or d.kind=='absent' else {64:1,512:4}[d.capacity//1024]
        assert d.read(base+0x1036,1)==bytes((expected,))
        assert d.read(base+0x1037,1)==bytes((expected+(8 if expected and d.banks==2 else 0),))
        assert not d.registers[0x5A]&0xC0 and not d.registers[0x50]&0x80
        assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
        row.update(options=options,native_word_reads=d.read_words,protocol=d.events,measured_code=expected,
                   physical_limit='Exact AMI protocol proved; hardware meaning and necessity unmeasured')
        results.append(row)
    return results


def a20_live():
    from geometry_proof import invoke

    class GatedSRAM(SRAM):
        def __init__(self,block_hold):
            super().__init__(kib=64)
            self.block_hold=block_hold
            self.guard=False

        def read(self,address,size):
            if not self.gates[0x92]&2:address &= ~0x100000
            return super().read(address,size)

        def write(self,address,size,value):
            if self.guard and address&0x100000 and not self.gates[0x92]&2:
                raise AssertionError('Cache workspace aliases live RAM with A20 off')
            return super().write(address,size,value)

        def outgoing(self,u,port,size,value):
            super().outgoing(u,port,size,value)
            if self.guard and self.block_hold and port==0x92:self.gates[port]=value&~2

    results=[]
    for blocked in (False,True):
        d=GatedSRAM(blocked)
        row,fixture=mapped(d.modules,expected=16,memory=d)
        u,_,_,_,_,_=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        d.gates[0x92]=0x20;d.guard=True
        try:
            invoke(fixture,'cache_qualify',count=5000000)
        except AssertionError as error:
            assert blocked and str(error)=='Cache workspace aliases live RAM with A20 off',error
            results.append(dict(row,blocked_hold_rejected=True));continue
        assert not blocked and d.read(base+0x1038,1)==b'\x01'
        assert d.gates[0x92]==0x20
        d.qualifying=False
        invoke(fixture,'cache_enable',count=1000000)
        assert d.read(base+0x1038,1)==b'\x05' and d.registers[0x50]&0x80
        assert d.gates[0x92]==0x20
        results.append(dict(row,a20_off_entry_qualified_enabled=True,exact_gate_restored=True))
    return results


def failure_report_live():
    class OffDRAMFault(POSTHardware):
        def __init__(self,address):
            super().__init__(kib=64)
            self.fault_address=address

        def prepare(self,u):
            super().prepare(u)
            from geometry_proof import Listing
            listing=Listing(PORT/'build/hardware-tests/geometry/baios-m919.lst')
            self.dram_check=0xF0000+listing.symbol('.dram_check','cache_qualify')

        def observe(self,u,address,size):
            super().observe(u,address,size)
            if address==self.qualify_entry:self.original=DRAM.read(self,self.fault_address,4)
            if address==self.dram_check:
                assert not self.registers[0x50]&0x80 and u.reg_read(x.UC_X86_REG_CR0)&0x40000000
                DRAM.write(self,self.fault_address,4,0xBAD0CAFE)

    results=[]
    for address in (0x8000,0x18000):
        d=OffDRAMFault(address)
        # composed with a supplied model reloads its saved CMOS.
        d.saved_cmos=post_module().nvram(types=0x40)[:128]
        saved=bytearray(d.saved_cmos)
        saved[0x69]=0x55;saved[0x6B:0x6E]=bytes((0x40,1,0));saved[0x6A]=(-0x55-0x40-1)&255
        d.saved_cmos=saved
        row,fixture=composed(kib=64,memory=d)
        detail=row['cache_failure']
        assert row['terminal']=='reset' and detail['stage']==6 and detail['address']==address,detail
        assert 'RAM data' in detail['screen'] and f'{address:08X}' in detail['screen'],detail
        assert fixture[4][0x69]==0xD2 and d.defaults_requested
        assert DRAM.read(d,address,4)==d.original
        results.append(row)
    return results


def discovery():
    results=[]
    for kib,expected in ((64,1),(128,2),(256,3),(512,4),(1024,5)):
        for banks in (1,2):
            record,fixture=initialized(kib=kib,banks=banks)
            assert record['measured_code']==expected and record['flags']==1,record
            assert record['map']==expected+(8 if banks==2 else 0),record
            assert all(n==kib*256 for n in record['coverage'].values()),record
            assert record['hits'] and record['evictions'],record
            assert record['ordinary_hit_indices']==kib*64,record
            results.append(record)
    for kind in ('absent','floating','fixed','stored'):
        record,_=initialized(kind=kind)
        assert record['measured_code']==0 and record['flags']==0,record
        results.append(record)
    for fault in (0x800,0x20800,0x7FFFC):
        record,_=initialized(fault=fault)
        assert record['measured_code']==4 and record['flags']==2,record
        results.append(record)
    for bit in (3,11):
        record,_=initialized(alias=bit)
        assert record['flags']==2,record
        results.append(record)
    # A tied capacity-select line can still provide a smaller sound map.
    record,_=initialized(alias=17)
    assert record['measured_code']==2 and record['flags']==1,record
    results.append(record)
    return results


def location_report_live():
    class DataPath(POSTHardware):
        def __init__(self, bad_bytes, **options):
            self.bad_bytes={0x100000+offset for offset in bad_bytes}
            super().__init__(**options)

        def external_read(self,address,size):
            payload=bytearray(super().external_read(address,size))
            if self.registers.get(0x50,0)&0x80:
                for i in range(size):
                    if address+i in self.bad_bytes:payload[i]^=1
            return bytes(payload)

    results=[]
    for offsets,location in (((0x100,),'Bank 0 byte 0  D0-7'),
                             ((0x103,),'Bank 0 byte 3  D24-31'),
                             ((0x107,),'Bank 1 byte 3  D24-31'),
                             ((0x100,0x103),'Bank 0 bytes 0 3')):
        d=DataPath(offsets,kib=64,banks=2,cpu_policy='wb')
        cmos=bytearray(post_module().nvram(types=0x40)[:128])
        cmos[0x69]=0x55;cmos[0x6B]=0x40;cmos[0x6C]=1;cmos[0x6D]=0
        cmos[0x6A]=(-0x55-0x40-1)&255
        d.saved_cmos=bytes(cmos)
        row,fixture=composed(kib=64,memory=d)
        assert row['terminal']=='reset' and row['cache_failure']['stage']==1,row
        assert row['cache_failure']['screen'][49:49+len(location)]==location,row
        sockets='U11-14' if location.startswith('Bank 1') else 'U20-23'
        assert row['cache_failure']['screen'][71:77]==sockets,row
        results.append(row)
    return results


def live():
    results=[]
    for l2 in (0,1):
        row,fixture=composed(kib=512,l2=l2,l1=1)
        u,d,listing,state,cmos,step=fixture
        expected=set(range(0x100000,0x180000,4))
        coverage={k:{'count':len(v),'missing':len(expected-v),'extra':len(v-expected),
                     'missing_examples':sorted(expected-v)[:8],'extra_examples':sorted(v-expected)[:8]} for k,v in d.coverage.items()}
        progress=PORT/'build/hardware-research/cache-live-progress.json'
        progress.write_text(json.dumps({'case':row,'coverage':coverage},indent=2)+'\n')
        print('Live raw coverage: '+json.dumps(coverage),flush=True)
        assert row['terminal']=='POST FF' and row['measured_code']==4,row
        assert row['enabled']==(l2==0) and row['l1'],row
        if l2==0:
            assert row['flags']==5 and d.registers[0x50]==0x84,row
            assert d.post_visits.index('chipset_post_ram_cache')<d.post_visits.index('cache_qualify')<d.post_visits.index('chipset_late_cache')<d.post_visits.index('cache_enable')
            assert all(v==expected for v in d.coverage.values()),coverage
            assert len(d.hit_indices)==512*64
            assert d.prime_reads=={'before':512*256,'after':512*256}
            assert (9,True,True) in d.flush_states
        else:
            assert 'cache_qualify' not in d.post_visits and row['flags']==0,row
            assert not d.hits and not any(d.coverage.values()) and not any(d.prime_reads.values())
        assert d.registers[0x51]&0xF0==0x40
        assert d.registers[0x55]==0xC0
        row.update(prime_reads=d.prime_reads,enabled_cpu_l2_flushes=d.flush_states.count((9,True,True)),
                   coverage={k:len(v) for k,v in d.coverage.items()},ordinary_hit_indices=len(d.hit_indices),
                   external_tag_flush_limit='enabled CPU+L2 flush modeled; physical UMC response unmeasured')
        results.append(row)
    progress.unlink()
    return results


def enable_live():
    d=POSTHardware(kib=512)
    row,fixture=mapped(d.modules,expected=16,memory=d)
    u,d,listing,state,cmos,step=fixture
    base=u.reg_read(x.UC_X86_REG_FS)<<4;code=0xF0000
    # Isolate the final guard delta; qualification belongs to cache-live.
    d.qualifying=False;d.write(base+0x1038,1,1)
    u.reg_write(x.UC_X86_REG_GS,0x10)
    saved_gs=u.reg_read(x.UC_X86_REG_GS);saved_gdtr=u.reg_read(x.UC_X86_REG_GDTR)
    d.gates[0x61]=1;saved_gate=d.gates[0x61]
    actual_reads={'before':0,'after':0};pe_entries=[]
    def read(uc,access,address,size,value,user):
        point=code+uc.reg_read(x.UC_X86_REG_IP)
        if point in d.prime_points:
            phase=d.prime_points[point]
            assert address==0x100000+actual_reads[phase]*4 and size==4,(phase,hex(address),size)
            actual_reads[phase]+=1
    def observe(uc,address,size,user):
        opcode=bytes(uc.mem_read(address,size))
        if opcode==b'\x0F\x22\xC0' and uc.reg_read(x.UC_X86_REG_EAX)&1:
            assert d.gates[0x61]&0x0C==0x0C and not uc.reg_read(x.UC_X86_REG_EFLAGS)&0x200
            pe_entries.append(address)
    u.hook_add(UC_HOOK_MEM_READ,read);u.hook_add(UC_HOOK_CODE,observe)
    for reg,value in ((x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x6F00),(x.UC_X86_REG_EFLAGS,0x47)):
        u.reg_write(reg,value)
    d.write(0x6F00,2,0xFF00)
    u.emu_start(code+listing.symbol('cache_enable'),code+0xFF00,count=2000000)
    assert u.reg_read(x.UC_X86_REG_IP)==0xFF00
    assert d.gates[0x61]==saved_gate and len(pe_entries)==1
    assert u.reg_read(x.UC_X86_REG_GS)==saved_gs and u.reg_read(x.UC_X86_REG_GDTR)==saved_gdtr
    assert u.reg_read(x.UC_X86_REG_CR0)&0x60000001==0x60000000
    assert actual_reads==d.prime_reads=={'before':512*256,'after':512*256}
    assert d.flush_states[-2:]==[(9,True,False),(9,True,True)]
    assert d.registers[0x50]==0x84 and d.read(base+0x1038,1)==b'\x05'
    row.update(prime_physical_reads=actual_reads,port61_saved_restored=saved_gate,gs_saved_restored=saved_gs,
               gdtr_saved_restored=list(saved_gdtr),pe_entries=len(pe_entries),cpu_off_return=True,
               ami_flush_order=d.flush_states[-2:],final_hb50=d.registers[0x50],
               fixture_limit='Qualification metadata deliberately seeded; complete qualification evidence is cache-live checkpoint')
    return [row]


def check(case):
    result={'cases':{'cache-recovery-boundaries-live':recovery_boundaries_live,'cache-location-report-live':location_report_live,'cache-pattern-report-live':pattern_report_live,'cache-ami-diagnostic-live':ami_diagnostic_live,'cache-a20-live':a20_live,'cache-failure-report-live':failure_report_live,'cache-recovery-live':recovery_live,'cache-early-live':early_discovery,'cache-enable-live':enable_live,'cache-live':live,'cache-discovery':discovery,'cache-policy':policy,'cache-settings':settings,'cache-dma':dma}[case]()}
    sources=('m919/src/hardware/cache.inc','m919/src/hardware/startup-core.inc','m919/src/hardware/chipset-core.inc',
             'm919/src/hardware/board-definition.inc','m919/src/hardware/post-core.inc','m919/tools/cache_proof.py','m919/tools/geometry_proof.py',
             'm919/src/hardware/timing.inc','m919/src/hardware/cache-validation.inc','m919/src/hardware/chipset-data.inc',
             'shared/src/firmware/bios.asm','shared/src/pc/crc32.inc')
    result['source_sha256']={p:hashlib.sha256((REPOSITORY/p).read_bytes()).hexdigest() for p in sources}
    target=PORT/'build/hardware-research'/f'{case}.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    if case=='cache-policy':
        result['dma_complete']=False
        target.write_text(json.dumps(result,indent=2)+'\n')
        result['dma']=dma();result['dma_complete']=True
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{case}: {len(result["cases"])} cases PASS; {target}',flush=True)
    return result


if __name__=='__main__':check(sys.argv[1] if len(sys.argv)>1 else 'cache-discovery')
