"""Focused execution of the manual-only M919 adapters; no vendor ROM inputs."""
import hashlib
import json
import struct
import sys
from collections import OrderedDict
from pathlib import Path
from unicorn import x86_const as x
from geometry_proof import DRAM, mapped, invoke, PORT
sys.path.insert(0,str(PORT.parent))
from shared.tools.rom import build, configuration, verify

class Memory(DRAM):
    """Independent ordinary WT L1 and direct-mapped WT/WB L2 devices."""
    def __init__(self,fault=None,absent=False,banks=1,kib=512,ordinary_fault=None,lost_writeback=False):
        super().__init__([(16,False,False),None,None,None])
        self.capacity=kib*1024
        self.sram=bytearray(self.capacity)
        self.fault=fault
        self.ordinary_fault=fault if ordinary_fault is None else ordinary_fault
        self.lost_writeback=lost_writeback
        self.clean_flushes=[]
        self.absent=absent
        self.banks=banks
        self.machine=None
        self.l1=OrderedDict()
        self.l2={}
        self.dirty=set()
        self.pci=0
        self.commands=[]
        self.keyboard_data=[]
        self.keyboard_replies=[]
        self.queue=[]
        self.pending=None
        self.command_byte=0x5C
        self.output=0xCF
        self.pit=0xFFFF
        self.ports={}
        self.high_changes=0
        self.hits=0
        self.qualifying=False
    def active(self,address):
        return address<0xA0000 or 0x100000<=address<16*1024*1024
    def cpu_cached(self,address):
        return self.machine is not None and not self.machine.reg_read(x.UC_X86_REG_CR0)&0x40000000 and self.active(address)
    def copyback(self):
        for index in self.dirty:
            line,data=self.l2[index]
            if not self.lost_writeback:super().write(line,16,int.from_bytes(data,'little'))
        self.dirty.clear()
    def cell(self,address):
        cell=address&15
        return cell&~4 if self.banks==2 and not self.registers.get(0x50,0)&8 else cell
    def line(self,address):
        line=address&~15
        index=line%self.capacity
        old=self.l2.get(index)
        if old is None or old[0]!=line:
            if index in self.dirty:
                super().write(old[0],16,int.from_bytes(old[1],'little'))
                self.dirty.remove(index)
            data=bytearray(super().read(line,16))
            if self.ordinary_fault is not None and index<=self.ordinary_fault<index+16:data[self.ordinary_fault-index]^=1
            self.l2[index]=(line,data)
        else:self.hits+=1
        return self.l2[index][1]
    def external_read(self,address,size):
        if self.registers.get(0x5A,0)&0x40:
            assert 0x100000<=address and address+size<=0x200000,hex(address)
            assert not self.cpu_cached(address),'L1 masks raw SRAM reads'
            if self.absent:return b'\xff'*size
            return bytes(self.sram[(a&~15)%self.capacity+self.cell(a)] for a in range(address,address+size))
        if self.registers.get(0x50,0)&0x80 and self.active(address):
            if self.absent:return b'\xff'*size
            return bytes(self.line(a)[self.cell(a)] for a in range(address,address+size))
        return super().read(address,size)
    def read(self,address,size):
        if not self.cpu_cached(address):return self.external_read(address,size)
        result=bytearray()
        for a in range(address,address+size):
            line=a&~15
            if line not in self.l1:
                if len(self.l1)==1024:self.l1.popitem(last=False)
                self.l1[line]=bytearray(self.external_read(line,16))
            self.l1.move_to_end(line)
            result.append(self.l1[line][a&15])
        return bytes(result)
    def write(self,address,size,value):
        if self.registers.get(0x5A,0)&0x40:
            assert 0x100000<=address and address+size<=0x200000,hex(address)
            assert not self.cpu_cached(address),'L1 masks raw SRAM writes'
            for i,a in enumerate(range(address,address+size)):
                index=(a&~15)%self.capacity+self.cell(a)
                if not self.absent and index!=self.fault:self.sram[index]=value>>(8*i)&255
            return
        active=self.registers.get(0x50,0)&0x80 and self.active(address)
        wb=active and self.registers.get(0x50,0)&0x40
        if not wb:super().write(address,size,value)
        for i,a in enumerate(range(address,address+size)):
            byte=(value>>(i*8))&255
            if active and not self.absent:
                line=a&~15;index=line%self.capacity
                if wb:self.line(a)
                old=self.l2.get(index)
                if old is not None and old[0]==line and a%self.capacity!=self.ordinary_fault:
                    old[1][self.cell(a)]=byte
                    if wb:self.dirty.add(index)
            if self.cpu_cached(a) and a&~15 in self.l1:
                self.l1[a&~15][a&15]=byte
    def observe(self,u,address,size):
        if self.registers.get(0x5A,0)&0x40:
            assert u.reg_read(x.UC_X86_REG_CS)==0x18,'Raw SRAM test executes from low ROM'
            assert not u.reg_read(x.UC_X86_REG_EFLAGS)&0x200,'IRQs enabled during forced hits'
        op=bytes(u.mem_read(address,min(size,2)))
        if op in (b'\x0f\x08',b'\x0f\x09'):
            if op[-1]==9 and self.registers.get(0x50,0)&0x80 and not self.dirty:
                self.clean_flushes.append(len(self.l2))
            if op[-1]==9:self.copyback()
            self.l1.clear()
            if self.registers.get(0x50,0)&0x80:
                self.l2.clear();self.dirty.clear()
    def incoming(self,u,port,size):
        if port==0x64:return int(bool(self.queue))
        if port==0x60:
            value=self.queue.pop(0) if self.queue else 0
            self.keyboard_replies.append(value)
            return value
        if port==0x40:
            self.pit=(self.pit-1000)&0xFFFF
            return self.pit&255
        return self.ports.get(port,0)
    def outgoing(self,u,port,size,value):
        if port==0xCF8:self.pci=value
        if 0xCFC<=port<=0xCFF and self.pci>>11&31==16:
            offset=(self.pci&0xFC)+port-0xCFC
            assert offset!=0x5B,'Undocumented diagnostic register used'
            assert not self.registers.get(0x5A,0)&0x80,'Undocumented transient mode used'
            if offset in (0x50,0x51) and self.registers.get(0x50,0)&0x80:
                ip=u.reg_read(x.UC_X86_REG_EIP)&0xFFFF
                # CS selector18 maps the documented high ROM alias.
                assert u.reg_read(x.UC_X86_REG_CS)==0x18,(offset,hex(ip))
                self.high_changes+=1
        if port==0x64:
            self.commands.append(value)
            assert value not in (0xA7,0xA8,0xA9,0xD3,0xD4),'AUX command issued'
            if value==0xAA:self.queue.append(0x55)
            elif value==0x20:self.queue.append(self.command_byte)
            elif value==0xD0:self.queue.append(self.output)
            elif value==0xAD:self.command_byte|=0x10
            elif value==0xAE:self.command_byte&=~0x10
            elif value in (0x60,0xD1):self.pending=value
        elif port==0x60:
            self.keyboard_data.append(value)
            if self.pending==0x60:self.command_byte=value
            elif self.pending==0xD1:self.output=value
            elif value==0xFF:self.queue.extend((0xFA,0xAA))
            self.pending=None
        self.ports[port]=value
    def interrupt(self,u,number):
        assert number==0x10,number
    def pci_read(self,address,port,size):
        registers=self.devices.get(address>>8&0xFFFF,{})
        offset=(address&0xFC)+port-0xCFC
        return sum(registers.get(offset+i,0)<<(i*8) for i in range(size))
    def pci_write(self,address,port,size,value):
        registers=self.devices.setdefault(address>>8&0xFFFF,{})
        offset=(address&0xFC)+port-0xCFC
        for i in range(size):
            if offset+i==9 and not self.compat_writable:continue
            registers[offset+i]=value>>(i*8)&255

def pci_cases(image):
    rows=[]
    for writable in (True,False):
        d=Memory()
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
        u,_,_,state,_,_=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        # Function1 exists even when function0 lacks the multifunction flag.
        d.devices={0x90:{0:0x60,1:0x10,2:0x8A,3:0x88,0xA:1,0xB:6},
                   0x91:{0:0x60,1:0x10,2:0x3A,3:0x67,4:5,8:0x10,9:0x8F,0xA:1,0xB:1}}
        d.compat_writable=writable
        d.composed=True
        u.reg_write(x.UC_X86_REG_BX,0x90)
        invoke(fixture,'board_pci_fixed_resources')
        assert u.reg_read(x.UC_X86_REG_EFLAGS)&1
        invoke(fixture,'board_pci_device')
        assert int.from_bytes(d.read(base+0x1034,2),'little')==0x91
        assert d.read(base+0x1039,1)[0]==int(writable)
        registers=d.devices[0x91]
        if writable:
            assert registers[9]==0x8A
            assert bytes(registers[i] for i in range(0x40,0x48))==bytes.fromhex('00C930FF6666BBBB')
            assert registers[4]&5==1
        else:assert registers[4]&7==0,'Rejected controller still decodes or masters the bus'
        rows.append(dict(compatibility_writes=writable,discovered_function=0x91,usable=writable))
        print('manual PCI compatibility',writable,'PASS',flush=True)
    return rows

def geometry_cases(image):
    rows=[]
    for kib,banks,absent,fault in ((256,1,False,None),(256,2,False,None),
                                   (512,2,False,None),(256,1,True,None),
                                   (256,1,False,0x1234)):
        d=Memory(kib=kib,banks=banks,absent=absent,fault=fault)
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
        u,_,_,state,_,_=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
        invoke(fixture,'chipset_defaults')
        invoke(fixture,'chipset_apply')
        excluded=bytes(u.mem_read(0xA0000,0x60000))
        invoke(fixture,'cache_qualify',count=12000000)
        flags=d.read(base+0x1038,1)[0]
        code=d.read(base+0x1036,1)[0]
        layout=d.read(base+0x1037,1)[0]
        capacity=int.from_bytes(d.read(base+0x103C,4),'little')
        if absent:
            assert flags&2 and (code,capacity)==(0,0)
        else:
            assert (code,layout,capacity)==({256:3,512:4}[kib],{256:3,512:4}[kib]|(8 if banks==2 else 0),kib*1024)
            assert flags==(1 if fault is None else 2)
        assert not d.registers[0x5A]&0x40 and not d.registers[0x50]&0x80
        assert bytes(u.mem_read(0xA0000,0x60000))==excluded
        if not absent and fault is None:
            invoke(fixture,'cache_enable')
            assert d.registers[0x50]&0xCF==layout|0x80
            assert d.read(base+0x1038,1)[0]==5
            assert not d.registers[0x5A]&0x40
        if fault is not None:
            address=int.from_bytes(d.read(base+0x1208,4),'little')
            assert address==0x100000+fault,(hex(address),hex(fault))
            assert d.read(base+0x1218,1)==b'\x02','Fault hidden by a smaller candidate'
        rows.append(dict(kib=kib,banks=banks,absent=absent,fault=fault,flags=flags,code=code,layout=layout,bytes=capacity))
        print('manual geometry',rows[-1],'PASS',flush=True)
    return rows

def ordinary_failure_case(image):
    d=Memory(kib=256,ordinary_fault=0x1234)
    _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
    u,_,_,state,_,_=fixture
    base=u.reg_read(x.UC_X86_REG_FS)<<4
    u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
    invoke(fixture,'chipset_defaults')
    invoke(fixture,'chipset_apply')
    invoke(fixture,'cache_qualify',count=12000000)
    assert d.read(base+0x1038,1)==b'\x02'
    assert d.read(base+0x1218,1)==b'\x02'
    assert d.read(base+0x1036,1)==b'\x03'
    assert not d.registers[0x50]&0x80 and not d.registers[0x5A]&0x40
    invoke(fixture,'cache_enable')
    assert not d.registers[0x50]&0x80,'Normal-traffic failure was enabled'
    print('Raw SRAM pass / ordinary cache fault rejected PASS',flush=True)
    return dict(raw_sram='pass',ordinary='rejected',enabled=False)

def normal_wt_cases(image, previous_image=None):
    class AccessFault(Memory):
        def __init__(self,where):
            super().__init__(kib=256)
            self.where=where
        def write(self,address,size,value):
            # A forced-hit narrow write fault is independent of ordinary SRAM.
            if self.where=='forced' and self.registers.get(0x5A,0)&0x40 and size==2 and address==0x102B6A:
                value|=0x400
            super().write(address,size,value)
        def external_read(self,address,size):
            value=bytearray(super().external_read(address,size))
            active=self.registers.get(0x50,0)&0x80
            forced=self.registers.get(0x5A,0)&0x40
            if active and not forced:
                assert not self.cpu_cached(address),'L1 hides ordinary qualification'
                if self.where=='ordinary' and address<=0x102B6B<address+size:
                    value[0x102B6B-address]|=4
            return bytes(value)
    cases=[('forced',image,1),('ordinary',image,2)]
    if previous_image is not None:cases.insert(0,('forced',previous_image,2))
    rows=[]
    for where,rom,expected in cases:
        d=AccessFault(where)
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=rom)
        u,_,_,state,_,_=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
        invoke(fixture,'chipset_defaults')
        invoke(fixture,'chipset_apply')
        invoke(fixture,'cache_qualify',count=12000000)
        flags=d.read(base+0x1038,1)[0]
        assert flags==expected,(where,flags,expected)
        assert d.read(base+0x1036,1)==b'\x03'
        assert not d.registers[0x50]&0x80 and not d.registers[0x5A]&0x40
        if flags==2:
            address=int.from_bytes(d.read(base+0x1208,4),'little')
            wanted=int.from_bytes(d.read(base+0x1210,4),'little')
            observed=int.from_bytes(d.read(base+0x1214,4),'little')
            assert (address,wanted,observed)==(0x102B6A,0xAA55,0xAE55)
            assert d.read(base+0x1218,1)==(b'\x01' if where=='forced' else b'\x02')
            invoke(fixture,'cache_enable')
            assert not d.registers[0x50]&0x80
        rows.append(dict(rom=str(rom),fault=where,flags=flags))
        print('ordinary WT contrast',where,expected,'PASS',flush=True)
    return rows

def writeback_cases(image):
    rows=[]
    for lost in (False,True):
        d=Memory(kib=256,lost_writeback=lost)
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
        u,_,_,state,_,_=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
        invoke(fixture,'chipset_defaults')
        d.write(base+state['C_CHIP']+3,1,0x40)
        invoke(fixture,'chipset_apply')
        invoke(fixture,'cache_qualify',count=12000000)
        flags=d.read(base+0x1038,1)[0]
        assert flags==(2 if lost else 1)
        assert not d.registers[0x50]&0x80 and not d.registers[0x5A]&0x40
        if lost:
            assert int.from_bytes(d.read(base+0x1210,4),'little')==0x6B19D4A2
            invoke(fixture,'cache_enable')
            assert not d.registers[0x50]&0x80,'Failed write-back was activated'
        else:
            invoke(fixture,'chipset_late_cache',count=1000000)
            assert d.registers[0x50]&0xC0==0xC0
            assert not d.registers[0x51]&1
            assert not u.reg_read(x.UC_X86_REG_CR0)&0x40000000
        rows.append(dict(lost_writeback=lost,flags=flags))
        print('WB qualification/copy-back',rows[-1],'PASS',flush=True)
    return rows

def writeback_prepare_cases(image, cases=(False,True)):
    """Every L2 line must have a known WT tag before the first WB write."""
    from unicorn import UC_HOOK_CODE

    class Prepared(Memory):
        def __init__(self):
            super().__init__(kib=256)
            self.last_mode=0
            self.wb_entries=0
        def outgoing(self,u,port,size,value):
            super().outgoing(u,port,size,value)
            if port==0xCFC and self.pci>>11&31==16 and self.pci&0xFC==0x50:
                if value&0xC0==0xC0 and not self.last_mode&0x40:
                    assert len(self.l2)==self.capacity//16,'WB sees uninitialized tags'
                    assert not self.dirty,'WT preparation left dirty lines'
                    self.wb_entries+=1
                self.last_mode=value

    rows=[]
    for corrupt in cases:
        d=Prepared()
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
        u,_,listing,state,_,_=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
        invoke(fixture,'chipset_defaults')
        d.write(base+state['C_CHIP']+3,1,0x40)
        invoke(fixture,'chipset_apply')
        damaged=[]
        return_site=0xF0000+listing.symbol('.real','cache_run')
        def state_fault(cpu,address,size,user):
            if address==return_site:
                if d.read(base+0x1218,1)==b'\x02' and not damaged:
                    d.write(base+0x1036,1,0)
                    damaged.append(True)
        handle=u.hook_add(UC_HOOK_CODE,state_fault) if corrupt else None
        invoke(fixture,'cache_qualify',count=12000000)
        if handle is not None:u.hook_del(handle)
        assert d.wb_entries==1
        assert d.read(base+state['C_CHIP']+2,2)==b'\x00\x40'
        assert d.read(base+0x1038,1)==(b'\x02' if corrupt else b'\x01')
        if corrupt:
            assert damaged
            observed=[int.from_bytes(d.read(base+a,4),'little') for a in (0x1208,0x1210,0x1214)]
            assert observed==[base+0x1036,3,0],observed
            invoke(fixture,'cache_enable')
            assert not d.registers[0x50]&0x80
        else:
            invoke(fixture,'chipset_late_cache',count=1000000)
            assert d.wb_entries==2
            assert d.read(base+0x1038,1)==b'\x05'
        row=dict(corrupt=corrupt,wt_tag_population='complete',wb_entries=d.wb_entries,
                 silent_geometry_loss='rejected' if corrupt else 'none')
        rows.append(row)
        print('WB preparation / geometry integrity',row,'PASS',flush=True)
    return rows


def writeback_span_case(image):
    d=Memory(kib=1024)
    _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
    u,_,_,state,_,_=fixture
    base=u.reg_read(x.UC_X86_REG_FS)<<4
    u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
    invoke(fixture,'chipset_defaults')
    d.write(base+state['C_CHIP']+3,1,0x40)
    d.write(base+state['S_EXTENDED_KIB32'],4,1024)
    invoke(fixture,'chipset_apply')
    invoke(fixture,'cache_qualify',count=100000)
    assert d.read(base+0x1038,1)==b'\x02'
    assert d.read(base+0x1218,1)==b'\x03'
    values=[int.from_bytes(d.read(base+a,4),'little') for a in (0x1208,0x1210,0x1214)]
    assert values==[0,0x300000,0x200000],values
    assert not d.registers[0x50]&0x80
    print('WB qualification refuses incomplete reference fill span PASS',flush=True)
    return dict(span=values,enabled=False)


def tag_cases(image, baseline=None, cases=None):
    class ReadTagFault(Memory):
        def __init__(self,fault=0,range_fault=None):
            super().__init__(kib=256)
            self.tag_fault=fault
            self.range_fault=range_fault
            self.alias_reads=0
        def external_read(self,address,size):
            enabled=self.registers.get(0x50,0)&0x80
            forced=self.registers.get(0x5A,0)&0x40
            line=address&~15
            old=self.l2.get(line%self.capacity)
            if enabled and not forced and self.tag_fault and old is not None:
                if old[0]!=line and ((old[0]^line)&~self.tag_fault)==0:
                    self.alias_reads+=1
                    start=address&15
                    assert start+size<=16
                    return bytes(old[1][start:start+size])
            data=bytearray(super().external_read(address,size))
            if enabled and not forced and self.range_fault is not None:
                if address<=self.range_fault<address+size:
                    data[self.range_fault-address]^=1
            return bytes(data)

    rows=[]
    if cases is None:
        cases=[(image,False,0,None,1),(image,True,0,None,1),
               (image,False,0x200000,None,2),(image,False,0,0xFF8000,2)]
        if baseline is not None:cases.insert(0,(baseline,False,0x200000,None,1))
    for rom,wb,fault,range_fault,wanted in cases:
        d=ReadTagFault(fault,range_fault)
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=rom)
        u,_,_,state,_,_=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
        invoke(fixture,'chipset_defaults')
        d.write(base+state['C_CHIP']+3,1,0x40 if wb else 0)
        invoke(fixture,'chipset_apply')
        excluded=bytes(u.mem_read(0xA0000,0x60000))
        invoke(fixture,'cache_qualify',count=12000000)
        flags=d.read(base+0x1038,1)[0]
        assert flags==wanted,(wb,fault,flags,wanted)
        assert bytes(u.mem_read(0xA0000,0x60000))==excluded
        assert not d.registers[0x50]&0x80 and not d.registers[0x5A]&0x40
        values=[]
        if wanted==2:
            assert d.read(base+0x1218,1)==b'\x04'
            values=[int.from_bytes(d.read(base+a,4),'little') for a in (0x1208,0x1210,0x1214)]
            if fault:
                assert d.alias_reads and values[1]^values[2]==fault,values
            else:
                assert values[0]==range_fault and values[1]^values[2]==1,values
            invoke(fixture,'cache_enable')
            assert not d.registers[0x50]&0x80
        row=dict(rom=str(rom),wb=wb,tag_fault=fault,range_fault=range_fault,flags=flags,alias_reads=d.alias_reads,tuple=values)
        rows.append(row)
        print('Cache tag-address contrast',row,'PASS',flush=True)
    return rows


def normal_register_cases(image, baseline=None):
    raw=(PORT/'reference/other-roms/8810AIO.32J').read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='7ddabc826f82e295086fe04e2f462145f20d8c51911864a77c2c74aaf079499e'
    for reg,value in ((0x5A,4),(0x5D,0x20)):
        row=b'\x01'+bytes((reg,0xFF))+bytes((value,))*15
        assert raw.find(row,0x13C16,0x13DA9)>=0
    # The initial table is not the handoff state: cold POST C0 adds09 to HB5A.
    assert raw[0x129D1:0x129DC]==bytes.fromhex('B0 5A E8 46 73 80 CC 09 E8 43 73')
    final5a=4|raw[0x129D8]
    rows=[]
    for rom in ([baseline] if baseline is not None else [])+[image]:
        for reset5d in (0x0F,0x4F):
            d=Memory(kib=256)
            d.registers.update({0x5A:0x2B,0x5D:reset5d})
            _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=rom)
            u,_,_,state,_,_=fixture
            base=u.reg_read(x.UC_X86_REG_FS)<<4
            normal=(d.registers[0x5A]&0xDF,d.registers[0x5D]&0xB0)
            if rom==baseline:
                assert normal==(0x0B,0)
                rows.append(dict(rom=str(rom),reset5d=reset5d,missing_reference_state=True))
                continue
            assert normal==(final5a,0x20),normal
            assert d.registers[0x5D]&0x4F==reset5d&0x4F
            u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
            invoke(fixture,'chipset_defaults')
            for policy,parity in ((0,0),(0x10,1),(0x80,0),(0x90,1)):
                # An owner reapply must recover normal state after a stale overlay.
                d.registers[0x5D]=reset5d|0x90
                d.registers[0x5A]=0x2B
                d.write(base+state['C_CHIP']+4,1,policy)
                d.write(base+state['C_CHIP']+6,1,parity)
                invoke(fixture,'chipset_apply_timing')
                assert d.registers[0x5D]&0xB0==0x20|policy
                assert d.registers[0x5D]&0x4F==reset5d&0x4F
                assert d.registers[0x5A]&0xDF==final5a|(0x10 if parity else 0)
                rows.append(dict(rom=str(rom),reset5d=reset5d,policy=policy,parity=parity,
                                 hb5a=d.registers[0x5A],hb5d=d.registers[0x5D]))
    print('Reference normal-register state / reset contrast / timing and parity owners PASS',flush=True)
    return rows


def revision_control_cases(image, baseline=None):
    # am8887 F000:27C7/27E1: actual revision04 requires04 even when FPM is selected.
    # The source bytes and native guards are retained in the register evidence.
    rows=[]
    for rom in ([baseline] if baseline is not None else [])+[image]:
        for revision in ((4,) if rom==baseline else (3,4,5)):
            d=Memory(kib=256)
            d.registers[8]=revision
            _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=rom,revision=revision)
            u,_,_,state,_,_=fixture
            base=u.reg_read(x.UC_X86_REG_FS)<<4
            u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
            invoke(fixture,'chipset_defaults')
            geometry=d.registers[0x61]&0x30
            for request in ((0,) if rom==baseline else range(4)):
                for retained in ((0,) if rom==baseline else (0,4)):
                    d.registers[0x61]=geometry|0x83|retained
                    d.write(base+state['C_CHIP']+5,1,request)
                    before=d.registers.get(0x62,0)
                    invoke(fixture,'chipset_apply_timing')
                    expected=geometry|3|retained|(8 if request&2 else 0)
                    if revision==4:
                        if rom!=baseline:expected|=4
                        if request&1:expected|=0xC0
                    assert d.registers[0x61]==expected,(revision,request,retained,d.registers[0x61],expected)
                    assert d.registers.get(0x62,0)==before,'Device-number mapping changed'
                    rows.append(dict(rom=str(rom),revision=revision,request=request,retained=retained,hb61=expected,
                                     missing_reference_state=rom==baseline))
    print('Revision04 FPM/EDO normal control / older-newer revisions / geometry preservation PASS',flush=True)
    return rows


def settings_roundtrip_cases(image):
    rows=[]
    for wb in (False,True):
        d=Memory(kib=256)
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
        u,_,_,state,cmos,_=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        # F9 replaces the draft through the same owner as both real menus.
        d.write(base+state['U_CHIP']+3,1,0x40)
        invoke(fixture,'setup_defaults')
        assert d.read(base+state['U_CHIP']+2,2)==b'\x00\x40'
        if not wb:
            d.write(base+state['U_CHIP_SCREEN'],1,1)
            d.write(base+state['U_FIELD'],1,2)
            d.write(base+state['U_CHIP_VALUE'],1,1) # Explicit WT contrasts with the WB default.
            invoke(fixture,'chipset_ui_commit')
            assert d.read(base+state['U_CHIP']+2,2)==b'\x00\x00'
        invoke(fixture,'chipset_settings_save')
        assert not u.reg_read(x.UC_X86_REG_EFLAGS)&1
        assert cmos[0x69]==0x57
        for i in range(24):d.write(base+state['C_CHIP']+i,1,0xA5)
        invoke(fixture,'chipset_settings_load')
        assert d.read(base+state['C_CHIP']+2,2)==bytes((0,0x40 if wb else 0))
        invoke(fixture,'chipset_apply')
        invoke(fixture,'cache_qualify',count=12000000)
        assert d.read(base+0x1038,1)==b'\x01'
        invoke(fixture,'chipset_late_cache',count=1000000)
        assert d.read(base+0x1038,1)==b'\x05'
        assert d.read(base+0x1036,1)==b'\x03'
        assert d.registers[0x50]&0xC0==(0xC0 if wb else 0x80)
        rows.append(dict(f9=True,selected='WB' if wb else 'WT',cmos_reload=True,l2='enabled',size=256))
        print('F9/save/reload/activation',rows[-1],'PASS',flush=True)
    # Continue the live WB fixture through the actual persistent recovery reader.
    cmos[0x69]=0xD2
    invoke(fixture,'settings_load')
    invoke(fixture,'chipset_apply')
    invoke(fixture,'chipset_late_cache')
    assert d.read(base+state['C_CHIP']+1,2)==b'\x00\x01'
    assert not d.registers[0x50]&0x80
    assert u.reg_read(x.UC_X86_REG_CR0)&0x40000000
    rows.append(dict(recovery_record='D2',l1='off',l2='off'))
    print('Persistent recovery / effective caches off PASS',flush=True)
    return rows

def vga_aperture_cases(image,apertures=(0x8000,0x10000,0,0xC000,0x20000,None)):
    class VGA(Memory):
        def __init__(self,aperture):
            super().__init__(kib=256)
            self.aperture=aperture
            self.vga_entries=0
            self.probe=False
            self.compat_writable=True
            self.devices={0x60:{0:0x33,1:0x53,4:3,0xB:3,0x30:1,0x32:0x0C}}
            self.seq_index=0x15
            self.seq={1:0x29,0x15:0xA5}
        def pci_read(self,address,port,size):
            bdf=address>>8&0xFFFF
            offset=(address&0xFC)+port-0xCFC
            if bdf==0x80:return sum(self.registers.get(offset+i,0)<<(8*i) for i in range(size))
            if bdf==0x60 and offset==0x30 and self.probe:return (-self.aperture)&0xFFFFF800
            return super().pci_read(address,port,size)
        def pci_write(self,address,port,size,value):
            bdf=address>>8&0xFFFF
            offset=(address&0xFC)+port-0xCFC
            if bdf==0x80:
                for i in range(size):self.registers[offset+i]=value>>(8*i)&255
                return
            if bdf==0x60 and offset==0x30:self.probe=value==0xFFFFFFFE
            super().pci_write(address,port,size,value)
        def outgoing(self,u,port,size,value):
            if port==0x3C4:self.seq_index=value
            elif port==0x3C5:self.seq[self.seq_index]=value
            if port==0xEE and value==0x5A:
                if 0x60 in self.devices:
                    assert self.pci_read(0x6030,0xCFC,4)==0xC0001
                    assert self.devices[0x60][4]==3
                self.vga_entries+=1
            super().outgoing(u,port,size,value)
        def incoming(self,u,port,size):
            if port==0x3C4:return self.seq_index
            if port==0x3C5:return self.seq.get(self.seq_index,0)
            return super().incoming(u,port,size)
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
    rows=[]
    for aperture in apertures:
        extent=aperture if aperture in (0x8000,0x10000) else 0x8000
        d=VGA(aperture or 0)
        if aperture is None:d.devices={}
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
        d.composed=True
        u=fixture[0]
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        for offset,value in ((0x1000,0xFFFF if aperture is None else 0x60),(0x103A,0xC800)):
            for i,b in enumerate(struct.pack('<H',value)):d.write(base+offset+i,1,b)
        rom=bytearray(0x8000)
        # Actual provider installs INT10 and marks its single initialization.
        rom[:17]=bytes.fromhex('55AA40A30006C706420000C0B05AE6EECB')
        rom[-1]=(-sum(rom))&255
        u.mem_write(0xC0000,bytes(rom))
        if extent==0x10000:
            u.mem_write(0xC8000,bytes(rom))
        else:
            isa=bytearray(0x800)
            isa[:8]=bytes.fromhex('55AA04B0A5E6EDCB')
            isa[-1]=(-sum(isa))&255
            u.mem_write(0xC8000,bytes(isa))
            u.mem_write(0xC8800,b'\xff'*0x7800)
        u.mem_write(0xD0000,b'\xff'*0x10000)
        copied=[]
        source=bytes(u.mem_read(0xC0000,extent))
        def shadow_write(cpu,access,address,size,value,user):
            offset=address-0xC0000
            assert value==int.from_bytes(source[offset:offset+size],'little')
            copied.append((address,size))
        copy_hook=u.hook_add(UC_HOOK_MEM_WRITE,shadow_write,None,0xC0000,0xCFFFF)
        # Work around only Unicorn's external-provider RETF emulation.
        resume=[]
        def provider_return(cpu,address,size,user):
            if address==0xC0010 or address==0xC8007 and extent==0x8000:
                sp=cpu.reg_read(x.UC_X86_REG_SP)
                ip,cs=struct.unpack('<HH',d.read((cpu.reg_read(x.UC_X86_REG_SS)<<4)+sp,4))
                resume.append((ip,cs,sp+4))
                cpu.emu_stop()
        handle=u.hook_add(UC_HOOK_CODE,provider_return)
        code=u.reg_read(x.UC_X86_REG_CS)<<4
        def execute(name):
            u.reg_write(x.UC_X86_REG_CS,code>>4)
            u.reg_write(x.UC_X86_REG_SS,0)
            u.reg_write(x.UC_X86_REG_SP,0x6F00)
            for i,b in enumerate(struct.pack('<H',0xFF00)):d.write(0x6F00+i,1,b)
            u.reg_write(x.UC_X86_REG_EFLAGS,0x247)
            u.emu_start(code+fixture[2].symbol(name),code+0xFF00,count=1000000)
            while resume:
                ip,cs,sp=resume.pop(0)
                u.reg_write(x.UC_X86_REG_CS,cs)
                u.reg_write(x.UC_X86_REG_SP,sp)
                u.emu_start((cs<<4)+ip,code+0xFF00,count=500000)
            assert u.reg_read(x.UC_X86_REG_IP)==0xFF00,name
        execute('initialize_video')
        u.hook_del(copy_hook)
        assert not u.reg_read(x.UC_X86_REG_EFLAGS)&1
        assert int.from_bytes(d.read(base+0x103A,2),'little')==0xC000+extent//16
        assert sum(size for _,size in copied)==extent
        assert min(address for address,_ in copied)==0xC0000
        assert max(address+size for address,size in copied)==0xC0000+extent
        assert bytes(u.mem_read(0xC0000,extent))==source
        assert d.registers[0x54]&0x0E==(0x0E if extent==0x10000 else 2)
        if aperture is not None:
            assert d.pci_read(0x6030,0xCFC,4)==0xC0000 and d.devices[0x60][4]==3
        assert int.from_bytes(d.read(0x600,2),'little')==(0 if aperture is None else 0x60)
        assert d.vga_entries==1
        assert d.seq_index==0x15 and d.seq=={1:9,0x15:0xA5},'Reset display blank was not released'
        execute('option_rom_discovery')
        u.hook_del(handle)
        assert d.vga_entries==1,'VGA initialized again through a mirrored ROM'
        assert d.ports.get(0xED)==(0xA5 if extent==0x8000 else None)
        rows.append(dict(pci_aperture=aperture,effective_extent=extent,legacy_header=0x8000,
                         real_isa_c800=extent==0x8000,vga_entries=d.vga_entries,returned=True))
        print('VGA initialization / aperture / late ROM scan',rows[-1],'PASS',flush=True)
    return rows


def l1_protocol_cases(image):
    from unicorn import UC_HOOK_INSN
    rows=[]
    cases=[('AuthenticAMD',0x04F4,0xF3,0xF1),('AuthenticAMD',0x04E4,0xF1,0xF3),
           ('AuthenticAMD',0x0480,0xF3,0xF3),('GenuineIntel',0x04F4,0xF3,0xF3)]
    for vendor,signature,initial,wanted in cases:
        d=Memory(kib=256)
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
        u,_,_,state,_,_=fixture
        def cpuid(cpu,user):
            leaf=cpu.reg_read(x.UC_X86_REG_EAX)
            if leaf==0:
                raw=vendor.encode()
                cpu.reg_write(x.UC_X86_REG_EAX,1)
                for reg,part in ((x.UC_X86_REG_EBX,raw[:4]),(x.UC_X86_REG_EDX,raw[4:8]),(x.UC_X86_REG_ECX,raw[8:])):
                    cpu.reg_write(reg,int.from_bytes(part,'little'))
            else:
                cpu.reg_write(x.UC_X86_REG_EAX,signature)
                for reg in (x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX):cpu.reg_write(reg,0)
            return True
        u.hook_add(UC_HOOK_INSN,cpuid,None,1,0,x.UC_X86_INS_CPUID)
        u.reg_write(x.UC_X86_REG_EAX,0xA5A50000|initial)
        u.reg_write(x.UC_X86_REG_EBX,0x12345678)
        invoke(fixture,'chipset_l1_protocol')
        assert u.reg_read(x.UC_X86_REG_EAX)==0xA5A50000|wanted
        assert u.reg_read(x.UC_X86_REG_EBX)==0x12345678
        assert u.reg_read(x.UC_X86_REG_EFLAGS)&0x247==0x247
        if vendor=='AuthenticAMD' and signature==0x04F4:
            base=u.reg_read(x.UC_X86_REG_FS)<<4
            for wb in (False,True):
                u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
                invoke(fixture,'chipset_defaults')
                d.write(base+state['C_CHIP']+3,1,0x40 if wb else 0)
                invoke(fixture,'chipset_apply')
                assert not d.registers[0x51]&2
                invoke(fixture,'cache_qualify',count=12000000)
                assert d.read(base+0x1038,1)==b'\x01'
                assert not d.registers[0x51]&2
                invoke(fixture,'chipset_late_cache',count=1000000)
                assert d.read(base+0x1038,1)==b'\x05'
                assert d.registers[0x50]&0xC0==(0xC0 if wb else 0x80)
                assert not d.registers[0x51]&2
                assert not u.reg_read(x.UC_X86_REG_CR0)&0x40000000
        rows.append(dict(vendor=vendor,signature=signature,initial=initial,result=wanted))
        print('CPU L1 protocol',rows[-1],'PASS',flush=True)
    return rows

def cache_cases(image):
    rows=[]
    for fault,absent,banks in ((None,False,1),(None,False,2),(0x1234,False,1),(None,True,1)):
        d=Memory(fault,absent,banks)
        _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
        u,_,listing,state,cmos,_=fixture
        base=u.reg_read(x.UC_X86_REG_FS)<<4
        u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
        invoke(fixture,'chipset_defaults')
        invoke(fixture,'chipset_apply')
        assert d.registers[0x51]&0xF0==0,'Default is not three DRAM waits'
        assert d.registers[0x50]&0xF0==0,'L2 is active or starts with fast timing'
        low=bytes(u.mem_read(0xA0000,0x60000))
        old_es=u.reg_read(x.UC_X86_REG_ES)
        invoke(fixture,'cache_qualify',count=10000000)
        flags=d.read(base+0x1038,1)[0]
        assert flags==(1 if fault is None and not absent else 10 if absent else 2),(fault,absent,flags)
        assert bytes(u.mem_read(0xA0000,0x60000))==low,'VGA/ROM bytes changed'
        assert u.reg_read(x.UC_X86_REG_ES)==old_es
        assert not d.registers[0x50]&0x80 and not d.registers[0x5A]&0xC0
        if flags==1:
            assert bool(d.read(base+0x1037,1)[0]&8)==(banks==2)
            assert d.hits>0,'Ordinary L2 was never exercised'
            for wb in (False,True):
                d.write(base+state['C_CHIP']+3,1,0x40 if wb else 0)
                invoke(fixture,'cache_enable',count=1000000)
                assert d.registers[0x50]&0x80
                assert bool(d.registers[0x50]&0x40)==wb
                assert not d.registers[0x51]&1  # The selected reference uses 7+1 tags in both policies.
                assert d.read(base+0x1038,1)[0]&4
                # Subsequent policy changes start from a flushed, off baseline.
                d.copyback();d.registers[0x50]&=0x7F
        rows.append(dict(fault=fault,absent=absent,banks=banks,flags=flags,high_rom_changes=d.high_changes,ordinary_hits=d.hits,vga_rom_preserved=True))
        print('manual cache',fault,absent,'PASS',flush=True)
    return rows


def no_aux_cases(image):
    rows=[]
    d=Memory(kib=256)
    _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
    u,_,_,state,_,_=fixture
    base=u.reg_read(x.UC_X86_REG_FS)<<4
    for saved in (False,True):
        invoke(fixture,'setup_defaults')
        if saved:
            d.write(base+state['U_PORTS'],1,3)
            d.write(base+state['U_PORTS']+state['P_MOUSE'],1,1)
        invoke(fixture,'settings_save')
        assert not u.reg_read(x.UC_X86_REG_EFLAGS)&1
        invoke(fixture,'settings_load')
        assert d.read(base+state['C_PORTS'],1)==bytes((3 if saved else 1,))
        assert d.read(base+state['C_PORTS']+state['P_MOUSE'],1)==b'\x00'
        d.commands.clear();d.keyboard_data.clear();d.keyboard_replies.clear()
        d.command_byte=0
        invoke(fixture,'init_keyboard',count=20000000)
        assert 0xFF in d.keyboard_data
        assert d.keyboard_replies[-2:]==[0xFA,0xAA]
        assert d.commands[-1]==0xAE and d.ports[0x80]==0xC9
        invoke(fixture,'arm_keyboard_runtime')
        keyboard_policy=d.command_byte
        assert keyboard_policy&0x41==0x41 and not keyboard_policy&0x10
        invoke(fixture,'board_mouse_no_aux')
        invoke(fixture,'board_keyboard_handoff')
        assert d.command_byte==keyboard_policy
        assert not set(d.commands)&{0xA7,0xA8,0xA9,0xD3,0xD4}
        assert d.ports[0xA1]&0x10 and not int.from_bytes(d.read(0x410,2),'little')&4
        assert d.read(base+0xB4,2)==b'\x00\x00'
        rows.append(dict(saved_policy=saved,mouse_disabled=True,keyboard_reset=True,
                         keyboard_enabled=True,aux_commands=[]))
        print('Default/saved policy / keyboard / no-AUX handoff',rows[-1],'PASS',flush=True)
    return rows


def tuning_cases(image,shared=True):
    _,cfg=configuration(PORT)
    host,isa=cfg['platform']['host_pci_device'],cfg['platform']['isa_pci_device']
    class Tuning(Memory):
        def __init__(self):
            super().__init__(kib=512)
            self.isa={}
            self.tuning_writes=[]
        def pci_read(self,address,port,size):
            registers=self.registers if address>>11&31==host else self.isa
            offset=(address&0xFC)+port-0xCFC
            return sum(registers.get(offset+i,0)<<(8*i) for i in range(size))
        def pci_write(self,address,port,size,value):
            device=address>>11&31
            assert device in (host,isa)
            registers=self.registers if device==host else self.isa
            offset=(address&0xFC)+port-0xCFC
            for i in range(size):
                registers[offset+i]=value>>(8*i)&255
                self.tuning_writes.append((device,offset+i,registers[offset+i]))
    d=Tuning()
    _,fixture=mapped(d.modules,expected=16,memory=d,rom_image=image)
    u,_,listing,state,cmos,_=fixture
    d.composed=True
    base=u.reg_read(x.UC_X86_REG_FS)<<4
    # Independent register/choice oracles from the retained AMI/Award bindings.
    controls=[(host,0x53,0x40,7,0,[0,0x40]),(host,0x51,8,7,1,[None,8,0]),
        (host,0x60,8,7,3,[None,0,8]),(host,0x5A,1,7,5,[1,0]),
        (host,0x5A,4,7,6,[4,0]),(host,0x5A,2,7,7,[0,2]),(host,0x5A,0x20,8,6,[None,0x20,0]),
        (isa,0x40,4,9,2,[0,4]),(isa,0x40,3,10,0,[None,2,0,1]),
        (isa,0x41,2,8,0,[None,0,2]),(isa,0x41,4,8,2,[None,0,4]),
        (isa,0x46,0x10,8,4,[None,0,0x10]),(isa,0x56,3,11,0,[1,0,2]),
        (isa,0x56,0x0C,11,2,[None,0,0x0C,8,4]),(isa,0x57,3,11,5,[3,2,1,0]),
        (isa,0xA4,3,10,2,[None,2,0,1])]
    seed_host=dict(d.registers)
    seed_host.update({0x51:0xAE,0x53:(d.registers[0x53]&0x3F)|0xC0,0x5A:0x2D,0x60:0xF6})
    seed_isa={0x40:0xB5,0x41:0xE6,0x46:0xF3,0x56:0xAD,0x57:0xB7,0xA4:0xA2}
    rows=[]
    for control in [None]+[(c,n) for c in controls for n in range(len(c[-1]))]:
        d.registers=dict(seed_host);d.isa=dict(seed_isa);d.tuning_writes.clear()
        u.reg_write(x.UC_X86_REG_DI,state['C_CHIP'])
        invoke(fixture,'chipset_defaults')
        if control:
            c,n=control
            d.write(base+state['C_CHIP']+c[3],1,n<<c[4])
        u.reg_write(x.UC_X86_REG_SI,state['C_CHIP'])
        invoke(fixture,'chipset_valid')
        assert not u.reg_read(x.UC_X86_REG_EFLAGS)&1
        expected={host:dict(seed_host),isa:dict(seed_isa)}
        writes=[]
        for c in controls:
            device,reg,mask,offset,shift,values=c
            selected=(d.read(base+state['C_CHIP']+offset,1)[0]>>shift)&(1 if len(values)==2 else 7 if len(values)==5 else 3)
            value=values[selected]
            if value is None:continue
            expected[device][reg]=(expected[device][reg]&~mask)|value
            writes.append((device,reg,expected[device][reg]))
        invoke(fixture,'chipset_apply_tuning')
        assert d.registers==expected[host] and d.isa==expected[isa],control
        assert d.tuning_writes==writes,control
        rows.append(dict(control=None if control is None else [control[0][0],control[0][1],control[0][2]],
                         choice=None if control is None else control[1],masks_preserved=True))
    # Invalid checksummed selections must never reach a lookup-table overrun.
    for offset,value in ((7,6),(7,0x18),(8,3),(8,0x0C),(8,0x30),(8,0xC0),(11,3),(11,0x14),(16,12),(16,0xC0),(17,0x0D),(17,0xD0)):
        u.reg_write(x.UC_X86_REG_DI,state['C_CHIP']);invoke(fixture,'chipset_defaults')
        d.write(base+state['C_CHIP']+offset,1,value)
        u.reg_write(x.UC_X86_REG_SI,state['C_CHIP']);invoke(fixture,'chipset_valid')
        assert u.reg_read(x.UC_X86_REG_EFLAGS)&1,(offset,value)
    def word(address):return int.from_bytes(u.mem_read(0xF0000+address,2),'little')
    def string(address):return bytes(u.mem_read(0xF0000+address,64)).split(b'\0')[0].decode('ascii')
    import re
    def natural(value):return [(0,int(p)) if p.isdigit() else (1,p.lower()) for p in re.split(r'(\d+)',value)]
    groups=listing.symbol('chipset_groups');counts=listing.symbol('chipset_group_counts')
    field_count=0
    for screen in range(7):
        group=word(groups+screen*2);count=u.mem_read(0xF0000+counts+screen,1)[0]
        for field in range(count):
            descriptor=group+field*14
            offset,shift,mask=bytes(u.mem_read(0xF0000+descriptor+2,3))
            choices=word(descriptor+5);values=word(descriptor+7)
            expected_labels=[string(word(values+raw*2)) for raw in range(choices)]
            shown=[]
            for raw in range(choices):
                u.reg_write(x.UC_X86_REG_DI,state['U_CHIP']);invoke(fixture,'chipset_defaults')
                before=bytearray(d.read(base+state['U_CHIP'],24))
                before[offset]=(before[offset]&~(mask<<shift))|(raw<<shift)
                for i,b in enumerate(before):d.write(base+state['U_CHIP']+i,1,b)
                d.write(base+state['U_CHIP_SCREEN'],1,screen+1);d.write(base+state['U_FIELD'],1,field)
                invoke(fixture,'chipset_ui_parameters')
                position=d.read(base+state['U_CHIP_VALUE'],1)[0]
                table=u.reg_read(x.UC_X86_REG_SI)
                label=string(word(table+position*2))
                assert label==expected_labels[raw],(screen,field,raw,label,expected_labels)
                shown.append((position,label))
                invoke(fixture,'chipset_ui_commit')
                assert d.read(base+state['U_CHIP'],24)==bytes(before)
            displayed=[label for _,label in sorted(shown)]
            assert len(set(displayed))==choices and displayed==sorted(displayed,key=natural),displayed
            field_count+=1
    assert field_count==45
    # Old57 prefix and new controls both survive real save/readback/reload.
    for record in (bytes.fromhex('F0010060900300000003')+bytes(14),
                   bytes.fromhex('0001004000000012AA070A520103')+bytes(10),
                   bytes.fromhex('0001004000000012AA070A52010301FCA6B30F01')+bytes(4)):
        for i,b in enumerate(record):d.write(base+state['U_CHIP']+i,1,b)
        invoke(fixture,'chipset_settings_save');assert not u.reg_read(x.UC_X86_REG_EFLAGS)&1
        for i in range(24):d.write(base+state['C_CHIP']+i,1,0)
        invoke(fixture,'chipset_settings_load')
        assert d.read(base+state['C_CHIP'],24)==record
        assert cmos[0x69]==0x57
    # The shared disk page sorts display positions without rewriting old codes.
    ide_fields=[(0,[0,1],['Disabled','Enabled']),
                (7,[0,1,2,3],['Auto','Normal','Large','LBA']),
                (8,list(range(9)),['Auto','Disabled','2 sectors','4 sectors','8 sectors','16 sectors','32 sectors','64 sectors','128 sectors']),
                (9,[0,1],['Enabled','Disabled']),
                (10,[0,1],['Disabled','Enabled']),
                (11,list(range(6)),['Auto','0','1','2','3','4'])]
    ide_ui_cases=0
    for device in range(4):
        for field,raws,labels in ide_fields:
            displayed=[]
            for raw in raws:
                u.reg_write(x.UC_X86_REG_DI,state['U_IDE']);invoke(fixture,'ide_defaults')
                d.write(base+state['U_IDE_DEVICE'],1,device)
                d.write(base+state['U_PAGE'],1,1);d.write(base+state['U_FIELD'],1,field)
                address=base+state['U_IDE']+1+12*device
                if field==0:
                    enabled=state['U_HDD'] if device==0 else state['U_SLAVE'] if device==1 else state['U_IDE']+49+device-2
                    d.write(base+enabled,1,raw)
                elif field==10:d.write(base+state['U_CHIP']+13,1,(15&~(1<<device))|(raw<<device))
                elif field==11:
                    d.write(base+state['U_CHIP']+20,1,(255&~(3<<(device*2)))|((raw&3)<<(device*2)))
                    d.write(base+state['U_CHIP']+23,1,(raw>>2)<<device)
                else:d.write(address+{7:1,8:2,9:3}[field],1,raw)
                before_ide=d.read(base+state['U_IDE'],51);before_chip=d.read(base+state['U_CHIP'],24)
                invoke(fixture,'ide_ui_parameters')
                position=d.read(base+state['U_CHIP_VALUE'],1)[0]
                table=u.reg_read(x.UC_X86_REG_SI)
                label=string(word(table+position*2))
                assert label==labels[raw],(device,field,raw,label)
                displayed.append((position,label))
                u.reg_write(x.UC_X86_REG_AL,position)
                invoke(fixture,'setup_enum_store')
                assert d.read(base+state['U_IDE'],51)==before_ide
                assert d.read(base+state['U_CHIP'],24)==before_chip
                ide_ui_cases+=1
            shown=[label for _,label in sorted(displayed)]
            assert shown==sorted(shown,key=natural) and len(set(shown))==len(raws),shown
    if shared:
        before_ports=dict(d.ports)
        for i in range(3):d.write(base+0x27A+i,1,0)
        u.reg_write(x.UC_X86_REG_AX,0x5300);u.reg_write(x.UC_X86_REG_BX,0)
        invoke(fixture,'int15',iret=True)
        assert u.reg_read(x.UC_X86_REG_AX)==0x0102 and u.reg_read(x.UC_X86_REG_BX)==0x504D
        assert not u.reg_read(x.UC_X86_REG_EFLAGS)&1 and d.ports==before_ports
        from unicorn import UC_HOOK_MEM_WRITE
        extended_writes=[]
        handle=u.hook_add(UC_HOOK_MEM_WRITE,lambda cpu,access,address,size,value,user:extended_writes.append(address),None,0x100000,0xFFFFFF)
        for address,value in ((state['P_PHASE'],1),(state['P_RAM_FLAGS'],0),(state['S_SETUP_REQUEST'],0)):
            d.write(base+address,1,value)
        for address in (0x41A,0x41C):d.write(address,2,0x1E)
        before_size=d.read(base+state['S_EXTENDED_KIB32'],4)
        invoke(fixture,'chipset_visible_ram_test',count=30000000)
        u.hook_del(handle)
        assert not extended_writes and d.read(base+state['P_RAM_FLAGS'],1)[0]&4
        assert d.read(base+state['S_EXTENDED_KIB32'],4)==before_size
    print('Tuning register cases:',len(rows),'PASS; sorted chipset:',field_count,'; IDE:',ide_ui_cases,'; record57:3',flush=True)
    return dict(register_cases=rows,sorted_ui_fields=field_count,ide_ui_cases=ide_ui_cases,record57_roundtrips=3,unchanged_shared_checks=shared)


def run():
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    checks={'cache':cache_cases,'pci':pci_cases,'revision':revision_control_cases,
            'settings':settings_roundtrip_cases,'vga-aperture':vga_aperture_cases,
            'ordinary-failure':ordinary_failure_case,'writeback':writeback_cases,
            'l1-protocol':l1_protocol_cases,'no-aux':no_aux_cases,'tuning':tuning_cases}
    parser.add_argument('--image',type=Path)
    parser.add_argument('--case',choices=tuple(checks),action='append')
    args=parser.parse_args()
    image=args.image.resolve() if args.image else Path(build(PORT,'build/tests/manual-rebuild/image')['path'])
    folder=PORT/'build/tests/manual-rebuild'
    folder.mkdir(parents=True,exist_ok=True)
    for name in args.case or checks:
        rows=checks[name](image)
        (folder/f'{name}.json').write_text(json.dumps(rows,indent=2)+'\n')
    verify(PORT,image)


if __name__=='__main__':run()
