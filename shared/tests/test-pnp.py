"""Independent scanner and far callers for the shared PnP BIOS interface."""
import argparse
from functools import cache
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
from shared.tools.post_fixture import migrated_base
from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

spec=importlib.util.spec_from_file_location('pnp_settings',Path(__file__).with_name('test-pnp-settings.py'))
settings=importlib.util.module_from_spec(spec)
spec.loader.exec_module(settings)
PORTS=('m919','pb430','presario-800')
OUTPUT='build/tests/pnp-runtime'
M919_MASKS=[0xF0,1,1,0x70,0x90,3,1,0xFF,0xFF,7,0x0F,0x7F,1,0x0F,1,0xFC,0xFF,0xFF,0x0F,1,0xFF,1,3,0x1F]


def isa_machine(port,bus,output='build/tests/pnp-runtime',conventional_kib=None):
    class Machine(settings.Settings):
        def __init__(self,bus):
            self.bus=bus
            super().__init__(port,output)
            self.listing.symbol=cache(self.listing.symbol)
            if port=='pb430':
                sys.path.insert(0,str(ROOT/'pb430/tools'))
                import core_proof
                self.controller=object.__new__(core_proof.ACC)
                self.controller.registers=bytearray([0xA5])*256;self.controller.registers[2]=0xB9
                self.controller.acc_index=0;self.controller.acc_writes=[];self.controller.delay_writes=[]
                self.payload_rom=self.image.read_bytes()[0x8000:0x10000]
                self.payload_shadow=bytearray(b'\xD6'*0x8000)
                self.cpu.hook_add(UC_HOOK_MEM_READ,self.payload_read,None,0xE8000,0xEFFFF)
                self.cpu.hook_add(UC_HOOK_MEM_WRITE,self.payload_write,None,0xE8000,0xEFFFF)
                self.cpu.mem_write(0x413,struct.pack('<H',self.base>>10))
            if port=='presario-800':
                physical=self.image.with_name('baios-presario800-vga60.bin').read_bytes()
                assert len(physical)==0x20000
                # Actual D824 model:256KiB high mapping, selected128KiB repeated.
                self.cpu.mem_map(0xFFFC0000,0x40000)
                self.cpu.mem_write(0xFFFC0000,physical+physical)
                self.cpu.mem_write(0xEC000,b'\xD6'*0x4000)
                self.port92=0;self.nmi=False;self.high_reads=0
                self.cpu.hook_add(UC_HOOK_MEM_READ,self.high_alias,None,0xFFFEC000,0xFFFEFFFF)
                self.cpu.mem_write(0x413,struct.pack('<H',self.base>>10))
            if conventional_kib is not None:self.cpu.mem_write(0x413,struct.pack('<H',conventional_kib))
            if port in ('m919','pb430','presario-800'):assert super().call('pnp_module_install')
        def high_alias(self,cpu,access,address,size,value,unused):
            assert self.port92&2 and self.nmi and not cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200
            self.high_reads+=size
        def interrupt(self,cpu,vector,unused):
            if hasattr(self,'runtime_interrupt') and self.runtime_interrupt(cpu,vector):return
            if vector==0x15:
                Caller.inject(self,'int15',cpu.reg_read(x.UC_X86_REG_IP))
                return
            return super().interrupt(cpu,vector,unused)
        def payload_read(self,cpu,access,address,size,value,unused):
            offset=address-0xE8000
            source=self.payload_shadow if self.controller.registers[2]&8 else self.payload_rom
            cpu.mem_write(address,bytes(source[offset:offset+size]))
        def payload_write(self,cpu,access,address,size,value,unused):
            if not self.controller.registers[2]&0x20:
                offset=address-0xE8000
                self.payload_shadow[offset:offset+size]=value.to_bytes(size,'little')
        def call(self,name,**registers):
            if ((port=='m919' and (name.startswith('pnp_') or name=='settings_nv6_retire')) or
                (port in ('pb430','presario-800') and (name.startswith(('pnp_isa_','pnp_delay_','pnp_claim_','pnp_work_','pnp_bus_','pnp_census','pnp_initialize_','pnp_discover_')) or name in ('pnp_pit_sample','pnp_prepare','pnp_finish','pnp_resource_next','pnp_stream_byte','pnp_normalize_event','pnp_eisa_id_valid','pnp_replay','pnp_place_ldn','pnp_candidate','pnp_try_ldn','pnp_solve','pnp_program','pnp_seed','pnp_reserve','pnp_map_node','pnp_rom_resources','settings_nv6_retire')))) and name not in ('settings_nv6_retire','pnp_journal_release','pnp_rom_enter','pnp_module_install','pnp_post_invoke','pnp_publish','pnp_early','pnp_finish_entry','pnp_pci_initialize'):
                if name=='pnp_publish_finish':return super().call(name,**registers)
                registers['BX']=self.listing.symbol(name)
                name='pnp_post_invoke'
            return super().call(name,**registers)
        def inp(self,cpu,port,size,unused):
            if port in getattr(self.bus,'ports',{}):return self.bus.ports[port]
            if hasattr(self.bus,'pci') and 0xCFC<=port<=0xCFF:
                return self.bus.pci.read(self.bus.pci_address,port,size)
            if hasattr(self,'port92') and port==0x92:return self.port92
            if hasattr(self,'controller') and port==0xF3:return self.controller.port_in(cpu,port,size,unused)
            value=self.bus.input(port,size)
            return super().inp(cpu,port,size,unused) if value is None else value
        def out(self,cpu,port,size,value,unused):
            if port in getattr(self.bus,'ports',{}):self.bus.ports[port]=value;return
            if hasattr(self.bus,'pci') and port==0xCF8:
                self.bus.pci_address=value;return
            if hasattr(self.bus,'pci') and 0xCFC<=port<=0xCFF:
                self.bus.pci.write(self.bus.pci_address,port,size,value);return
            if hasattr(self,'port92') and port==0x92:self.port92=value;return
            if hasattr(self,'port92') and port==0x70:self.nmi=bool(value&128)
            if hasattr(self,'controller') and port in (0xF2,0xF3,0xED):
                return self.controller.port_out(cpu,port,size,value,unused)
            if not self.bus.output(port,size,value):super().out(cpu,port,size,value,unused)
    return Machine(bus)


def isa_transport(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    def call(m,name,**registers):
        return m.call(name,DX=m.bus.read_port or 0x203,ES=0x2000,DI=0x100,**registers)
    tested=[];empty_budgets=[]
    for amount in (0,1,3):
        cards=[Card(serial(b'\x41\xD0\x12\x34',n+1)) for n in range(amount)]
        bus=Bus(cards,{0x20B:'checksum'})
        m=isa_machine(port,bus,output)
        budgets=[]
        for reset in ('cold','retained_warm'):
            started=bus.ticks
            if reset=='retained_warm':
                # Model retained OS-assigned CSNs; actual Reset CSN must discard them.
                for n,card in enumerate(cards):card.csn=(19,7,254)[n];card.state='wait'
            call(m,'pnp_isa_reset')
            assert all(card.csn==0 for card in cards)
            found=[];read_port=0x20B
            while True:
                call(m,'pnp_isa_wake_zero')
                m.call('pnp_isa_read_port',DX=read_port)
                m.cpu.mem_write(0x200FF,b'\xC5'+b'\xA6'*9+b'\xD3')
                if not m.call('pnp_isa_isolate',DX=read_port,ES=0x2000,DI=0x100):
                    if not found and m.cpu.reg_read(x.UC_X86_REG_AH) and read_port==0x20B:
                        read_port=0x20F;continue
                    break
                identity=bytes(m.cpu.mem_read(0x20100,9))
                assert bytes(m.cpu.mem_read(0x200FF,1))==b'\xC5' and bytes(m.cpu.mem_read(0x20109,1))==b'\xD3'
                found.append(identity)
                assert len(found)<=255
                m.call('pnp_isa_write',AX=(len(found)<<8)|6,DX=read_port)
                assert call(m,'pnp_isa_resource_byte') and m.cpu.reg_read(x.UC_X86_REG_AL)==0x79
                assert call(m,'pnp_isa_resource_byte') and m.cpu.reg_read(x.UC_X86_REG_AL)==0
                reads=bus.resource_reads
                assert call(m,'pnp_isa_reopen',AX=len(found))
                assert bus.resource_reads-reads==9,'Reopen must skip precisely nine bytes'
                assert call(m,'pnp_isa_resource_byte') and m.cpu.reg_read(x.UC_X86_REG_AL)==0x79
            order=sorted([c.identity for c in cards],key=lambda data:tuple((byte>>bit)&1 for byte in data for bit in range(8)),reverse=True)
            assert found==order and read_port==(0x20F if amount else 0x20B)
            call(m,'pnp_isa_wait_key')
            assert all(card.state=='wait' for card in cards)
            assert not m.writes,'ISA transport changed persistent settings'
            if not amount:
                elapsed=(bus.ticks-started)/1193182
                assert .018<elapsed<.021,('Empty bus PIT budget',elapsed)
                empty_budgets.append(elapsed)
            tested.append((amount,reset,len(found),read_port))
        if cards:
            call(m,'pnp_isa_key');call(m,'pnp_isa_reopen',AX=1)
            bus.never_ready=True
            before=bus.resource_reads
            assert not call(m,'pnp_isa_resource_byte') and bus.resource_reads==before
            call(m,'pnp_isa_wait_key')
    return {'scope':'transport foundation, not full P2 POST/census/allocation proof',
            'cases':tested,'exact_key_reset_responding72bits_silent64bits_crc_port_relocation':True,
            'direct_and_reopened_stream_readiness_and_invalid_prefix_checksum':True,
            'PIT_minimum_delays_and_timeout':True,'empty_scan_PIT_seconds':empty_budgets,'persistent_writes':0}


def mode3_delays(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus
    tested=[]
    for phase in (0,0x7FE0,0xFFE0):
        for name,minimum in (('pnp_delay_250us',299),('pnp_delay_1ms',1194),('pnp_delay_2ms',2387)):
            bus=Bus();m=isa_machine(port,bus,output);bus.ticks=phase
            before=bus.ticks;m.call(name)
            elapsed=bus.ticks-before
            assert minimum<=elapsed<=minimum+48,(phase,name,elapsed)
            tested.append({'input_clock_phase':phase,'owner':name,'actual_input_clocks':elapsed,
                           'microseconds':elapsed*1000000/1193182})
    return {'actual_mode3_two_decrements_per_input_clock':True,'wrap_and_reload':tested}


def memory_register_boundaries(port):
    from shared.tools.isa_pnp_proof import Card,serial
    prefix=b'\x0A\x10\0\x82\x03\0ISA';ldn=b'\x15\x41\xD0\x05\0\x01'
    def card(n,body,ldns=1):
        return Card(serial(b'\x41\xD0\xFF\xFF',n),prefix+body+b'\x79\0',ldns=ldns,memory_upper=True)
    def m24(lo,hi,length,alignment=256):
        return b'\x81\x09\0\x04'+struct.pack('<HHHH',lo>>8,hi>>8,alignment,length>>8)
    def m32(base,length):return b'\x86\x09\0\x04'+struct.pack('<II',base,length)
    tested=[]
    for family in (24,32):
        desc=m24 if family==24 else lambda lo,hi,length:m32(lo,length)
        top=0x1000000 if family==24 else 0x100000000
        c=card(1,ldn+desc(top-0x1000,top-0x1000,0x1000)+ldn+desc(top-0x2000,top-0x2000,0x1000),2)
        later=card(2,ldn+b'\x4B\xE0\x03\x08')
        m,bus=allocation_fixture(port,[c,later])
        assert [c.registers[n][0x30] for n in (0,1)]==[0,1]
        assert later.registers[0][0x30]==1
        regs=c.registers[1];start=0x40 if family==24 else 0x76;width=2 if family==24 else 4
        scale=256 if family==24 else 1
        base=int.from_bytes(bytes(regs[start+n] for n in range(width)),'big')*scale
        limit=int.from_bytes(bytes(regs[start+width+1+n] for n in range(width)),'big')*scale
        assert base==top-0x2000 and limit==top-0x1000 and regs[start+width]&1
        assert not any(csn==c.csn and n==0 and reg!=0x30 for csn,n,reg,value in bus.config_writes)
        tested.append({'family':family,'overflow_LDN_inactive':True,'neighbor_base':base,'neighbor_exclusive_limit':limit})
    for alignment in (1,3):
        fixed=card(1,ldn+m32(0xD0000,1))
        moving=card(2,ldn+m24(0xD0000,0xD0100,0x100,alignment))
        m,bus=allocation_fixture(port,[fixed,moving]);regs=moving.registers[0]
        assert fixed.registers[0][0x30]==1
        assert regs[0x30]==int(alignment==1)
        if alignment==1:
            base=(regs[0x40]<<16)|(regs[0x41]<<8)
            limit=(regs[0x43]<<16)|(regs[0x44]<<8)
            assert base==0xD0100 and limit==0xD0200 and base&255==0
            assert set(range(base,limit)).isdisjoint({0xD0000})
        else:
            assert not any(csn==moving.csn and reg!=0x30 for csn,n,reg,value in bus.config_writes)
        tested.append({'24bit_alignment':alignment,'actual_registers':dict(regs),'fixed_one_byte_owner':dict(fixed.registers[0])})
    return {'actual_allocator_seed_census_replay_commit':tested,'Activate_last':True}


def resource_framing(port='mp386',output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    identity=serial(b'\x41\xD0\x12\x34',1)
    ldn=b'\x15\x41\xD0\x00\x01\x01'
    version=b'\x0A\x10\0'
    tested=[]
    def run(stream,expected,valid):
        bus=Bus([Card(identity,stream,csn=1)])
        bus.pause=False
        m=isa_machine(port,bus,output)
        m.call('pnp_isa_key');m.call('pnp_isa_read_port',DX=0x203)
        assert m.call('pnp_isa_reopen',AX=1,DX=0x203)
        m.cpu.mem_write(0x201FF,b'\xC5'+bytes(21)+b'\xD3')
        events=[]
        while True:
            success=m.call('pnp_resource_next',DX=0x203,ES=0x2000,DI=0x200)
            if not success:
                assert not valid
                break
            event=bytes(m.cpu.mem_read(0x20200,21))
            tag=event[0];length=int.from_bytes(event[2:4],'little')
            events.append((tag,length))
            assert bytes(m.cpu.mem_read(0x201FF,1))==b'\xC5' and bytes(m.cpu.mem_read(0x20215,1))==b'\xD3'
            if tag==0x79:
                assert valid
                break
        assert events==expected,(events,expected)
        assert not m.writes
    for length in (255,256,65535):
        prefix=version+b'\x82'+struct.pack('<H',length)+b'A'*length+ldn+b'\x4B\x20\x03\x04'
        prefix+=b'\x84\x00\x01'+b'V'*256+ldn
        for checksum in ('zero','valid','invalid'):
            value=0 if checksum=='zero' else (-sum(prefix)-0x79)&255
            if checksum=='invalid':value=(value+1)&255 or 1
            stream=prefix+bytes((0x79,value))
            expected=[(0x0A,2),(0x82,length),(0x15,5),(0x4B,3),(0x84,256),(0x15,5)]
            if checksum!='invalid':expected += [(0x79,1)]
            run(stream,expected,checksum!='invalid')
            tested.append((length,checksum))
    for malformed in (b'\x81\x08\0'+bytes(8),b'\x24'+bytes(4),b'\x83\x03\0ABC',b'\x85\x10\0'+bytes(16)):
        run(version+malformed+ b'\x79\0',[(0x0A,2)],False)
    for tag,length in ((0x81,9),(0x85,17),(0x86,9)):
        stream=version+ldn+bytes((tag,length,0))+bytes(length)+b'\x79\0'
        run(stream,[(0x0A,2),(0x15,5),(tag,length),(0x79,1)],True)
    return {'scope':'stream framing, not allocation/semantic validation','metadata_lengths_and_End_checksums':tested,
            'known_memory_forms':3,'malformed_lengths':4,'full_payload_canaries':True}


def journal_boundaries(port='mp386',output='build/tests/pnp-runtime'):
    tested=[]
    for allocated in (1024,8192):
        from shared.tools.isa_pnp_proof import Bus
        m=isa_machine(port,Bus(),output);m.allocated=allocated
        m.cpu.mem_write(m.base,b'\xC7'*allocated)
        if port=='m919':m.call('pnp_module_install')
        m.cpu.mem_write(0x413,struct.pack('<H',512))
        before=bytes(m.cpu.mem_read(m.base,allocated))
        assert m.call('pnp_journal_begin')
        assert m.call('pnp_journal_allocate',ECX=96)
        first=m.cpu.reg_read(x.UC_X86_REG_EAX)
        assert first==0x80000-96 and int.from_bytes(m.cpu.mem_read(0x413,2),'little')==511
        if port=='pb430':
            assert m.call('pnp_journal_allocate',ECX=first-0x40000)
            assert m.cpu.reg_read(x.UC_X86_REG_EAX)==0x40000
            assert m.call('pnp_journal_allocate',ECX=0x10000)
        else:assert m.call('pnp_journal_allocate',ECX=first-0x10000)
        assert m.cpu.reg_read(x.UC_X86_REG_EAX)==0x10000
        state=bytes(m.cpu.mem_read(m.base,allocated));bda=bytes(m.cpu.mem_read(0x413,2))
        for extra in (1,0,0xFFFFFFFF):
            assert not m.call('pnp_journal_allocate',ECX=extra)
            assert bytes(m.cpu.mem_read(m.base,allocated))==state and bytes(m.cpu.mem_read(0x413,2))==bda
        m.call('pnp_journal_release')
        assert int.from_bytes(m.cpu.mem_read(0x413,2),'little')==512
        assert bytes(m.cpu.mem_read(m.base,0x320))==before[:0x320]
        assert bytes(m.cpu.mem_read(m.base+0x340,allocated-0x340))==before[0x340:]
        assert m.call('pnp_journal_begin');assert m.call('pnp_journal_allocate',ECX=96)
        m.cpu.mem_write(0x413,struct.pack('<H',509)) # Actual returning consumer reserves below arena.
        assert m.call('pnp_journal_allocate',ECX=96)
        assert m.cpu.reg_read(x.UC_X86_REG_EAX)==509*1024-96
        m.call('pnp_journal_release')
        assert int.from_bytes(m.cpu.mem_read(0x413,2),'little')==509,'Released another memory owner'
        assert not m.writes
        tested.append(allocated)
    return {'scope':'journal owner, not full P2 POST lifetime proof','allocated_EBDA_canaries':tested,
            'last_fit_minimum_excess_and_overflow_atomic':True,'BDA_accounting_and_external_owner_release':True}


def resource_domains(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus
    m=isa_machine(port,Bus(),output)
    rows=[(0x47,struct.pack('<BHHBB',1,0x310,0x330,16,8),(2,1,0,0x310,0x330,16,8,0)),
          (0x4B,struct.pack('<HB',0x3BC,3),(2,0,0,0x3BC,0x3BC,1,3,0)),
          (0x22,struct.pack('<H',0x204),(3,1,0,0x204,0,0,0,0)),
          (0x23,struct.pack('<HB',0x200,4),(3,4,0,0x200,0,0,0,0)),
          (0x2A,b'\xA0\x19',(4,0x19,0,0xA0,0,0,0,4)),
          (0x2A,b'\x10\x08',(4,8,0,0x10,0,0,0,4)),
          (0x81,struct.pack('<BHHHH',0x14,0xC00,0xE00,0,0x100),(1,0x14,0,0xC0000,0xE0000,65536,65536,0)),
          (0x85,struct.pack('<BIIII',0x14,0xC0000,0xE0000,65536,65536),(1,0x14,4,0xC0000,0xE0000,65536,65536,0)),
          (0x86,struct.pack('<BII',0x1C,0xF0000000,0x1000),(1,0x1C,4,0xF0000000,0xF0000000,1,0x1000,0)),
          (0x47,struct.pack('<BHHBB',0,0x300,0x320,0,0),(2,0,1,0,0,1,0,0)),
          (0x22,b'\0\0',(3,1,1,0,0,0,0,0)),(0x2A,b'\0\0',(4,0,1,0,0,0,0,4)),
          (0x86,struct.pack('<BII',0,0,0),(1,0,5,0,0,1,0,0)),
          (0x23,b'\0\0\xFF',(3,1,1,0,0,0,0,0)),
          (0x2A,b'\0\xFF',(4,0,1,0,0,0,0,4)),
          (0x81,struct.pack('<BHHHH',255,65535,0,65535,0),(1,0,1,0,0,1,0,0)),
          (0x85,struct.pack('<BIIII',255,0xFFFFFFFF,0,0xFFFFFFFF,0),(1,0,5,0,0,1,0,0)),
          (0x86,struct.pack('<BII',255,0xFFFFFFFF,0),(1,0,5,0,0,1,0,0))]
    for ordinal,(tag,data,values) in enumerate(rows,1):
        m.cpu.mem_write(0x20200,bytes((tag,0))+struct.pack('<H',len(data))+data)
        m.cpu.mem_write(0x203FF,b'\xC5'+b'\xA6'*24+b'\xD3')
        assert m.call('pnp_normalize_event',ES=0x2000,DI=0x200,GS=0x2000,SI=0x400)
        kind,info,flags,minimum,maximum,alignment,length,selected=values
        wanted=struct.pack('<4B5I',kind,0,info,flags,minimum,maximum,alignment,length,selected)
        actual=bytes(m.cpu.mem_read(0x20400,24))
        assert actual==wanted,(port,ordinal,hex(tag),actual.hex(),wanted.hex())
        assert bytes(m.cpu.mem_read(0x203FF,1))==b'\xC5' and bytes(m.cpu.mem_read(0x20418,1))==b'\xD3'
    invalid=[(0x47,struct.pack('<BHHBB',2,0x300,0x320,1,8)),
             (0x47,struct.pack('<BHHBB',1,0x330,0x300,1,8)),(0x4B,b'\0\x04\x01'),
             (0x23,b'\0\x02\x10'),(0x2A,b'\x01\x80'),(0x2A,b'\x01\x03'),
             (0x81,struct.pack('<BHHHH',0x18,0xC00,0xE00,0,0x100))]
    for tag,data in invalid:
        m.cpu.mem_write(0x20200,bytes((tag,0))+struct.pack('<H',len(data))+data)
        assert not m.call('pnp_normalize_event',ES=0x2000,DI=0x200,GS=0x2000,SI=0x400)
    for identity,valid in [(b'\x41\xD0\xFF\xFF',True),(b'\x04\x43\0\0',True),
                           (b'\xC1\xD0\0\0',False),(b'\x01\xD0\0\0',False),
                           (b'\x41\xC0\0\0',False),(b'\x6D\xD0\0\0',False)]:
        m.cpu.mem_write(0x20200,identity)
        assert m.call('pnp_eisa_id_valid',ES=0x2000,DI=0x200)==valid
    return {'scope':'normalization/ID owner; census/host selection not yet complete',
            'valid_domains':len(rows),'malformed_descriptors':len(invalid),'EISA_ID_cases':6,
            'all32bit_fields_no_truncation':True,'null_slots_and24byte_canaries':True}


def resource_ledger(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus
    m=isa_machine(port,Bus(),output)
    if port in ('m919','mp386'):
        m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        assert m.call('pnp_journal_begin')
    assert not m.call('pnp_claim_query',AX=0x201,EDX=0x300,ECX=8),'Missing ledger must not claim an address is free'
    assert m.call('pnp_work_begin')
    live={}
    def add(kind,base,length,owner,info=1,null=False,record=None):
        if record is None:
            assert m.call('pnp_journal_allocate',ECX=32)
            record=m.cpu.reg_read(x.UC_X86_REG_EAX)
        raw=bytearray(32);raw[0]=kind;raw[2]=info;raw[3]=int(null)
        struct.pack_into('<I',raw,16,length);struct.pack_into('<I',raw,20,base);struct.pack_into('<I',raw,28,owner)
        m.cpu.mem_write(record,bytes(raw))
        assert m.call('pnp_claim_add',EAX=record)
        live[record]=(kind,base,length,owner,info,null)
        return record
    def remove(owner):
        assert m.call('pnp_claim_remove_owner',ESI=owner)
        for record,row in list(live.items()):
            if row[3]==owner:del live[record]
    def expanded(base,length,decode):
        return set(range(base,base+length)) if decode else {at for at in range(65536) if ((at-base)&1023)<length}
    def query(kind,base,length,info=1):
        expected=False
        for k,b,n,o,i,null in live.values():
            if null or k!=kind or not length:continue
            if kind==2:expected |= bool(expanded(base,length,info&1)&expanded(b,n,i&1))
            elif kind==1:expected |= base<b+n and b<base+length
            else:expected |= base==b
        assert (not m.call('pnp_claim_query',AX=(kind<<8)|info,EDX=base,ECX=length))==expected,(port,kind,base,length,info)
        return expected
    add(3,2,1,1) # Internal PIC cascade stays PIC2, never an external-ISA alias.
    assert not query(3,9,1)
    add(3,9,1,2);assert query(3,9,1);remove(2)
    assert not query(3,9,1) and query(3,2,1)
    add(4,4,1,3);add(4,2,1,4);assert query(4,4,1) and query(4,2,1)
    first=add(2,0x350,16,10);add(2,0x358,16,11);add(2,0x700,8,12)
    remove(10)
    assert not query(2,0x350,8) and query(2,0x357,2) and query(2,0x700,8)
    remove(11);assert not query(2,0x350,24) and query(2,0x700,8)
    add(2,0x360,8,10,record=first)
    cursor=bytes(m.cpu.mem_read(m.base+0x320,4))
    assert m.call('pnp_claim_add',EAX=first) and bytes(m.cpu.mem_read(m.base+0x320,4))==cursor
    add(2,0x300,16,20,info=0)
    add(2,0x3FC,8,21,info=0) #10-bit decode interval wraps across its alias boundary.
    for base in (0x2FF,0x300,0x30F,0x310,0x3FB,0x3FF,0x400,0xC2FF,0xC300,0xC310,0xFC00):
        for length in (0,1,2,16,0x400):
            if base+length<=65536:
                query(2,base,length);query(2,base,length,0)
    add(1,0xC0000,0x4000,30);add(1,0xC2000,0x4000,31);add(1,0xE0000,0x4000,32)
    remove(30)
    assert not query(1,0xC0000,0x2000) and query(1,0xC1FFF,2) and query(1,0xE0000,1)
    add(1,0xFFFFF000,0x1000,33)
    assert query(1,0xFFFFFFFF,1) and not query(1,0xFFFFEFFF,1)
    add(2,0x900,16,40,null=True);assert not query(2,0x900,16)
    assert not m.writes
    return {'scope':'ledger owner; ISA selector/final router integration pending',
            'complete10bit_alias_sets':True,'last_byte_and_4GiB_boundaries':True,
            'overlap_union_individual_release_and_later_window':True,
            'owner_rollback_reuses_records':True,'internal_PIC2_does_not_own_external_IRQ9':True}


def card_census(port,output='build/tests/pnp-runtime',exhaustion=False,cases=None):
    selected=set(cases or ('valid','malformed','empty','relocation'))
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    version=b'\x0A\x10\0'+b'\x82\x03\0ISA'
    def device(identity=b'\x41\xD0\x05\0',flags=1):return b'\x15'+identity+bytes((flags,))
    def finish(prefix,checksum='zero'):
        value=0 if checksum=='zero' else (-sum(prefix)-0x79)&255
        if checksum=='bad':value=(value+1)&255 or 1
        return prefix+bytes((0x79,value))
    alternatives=b''.join(bytes((0x31,priority,0x4B))+struct.pack('<HB',base,8)
                           for priority,base in ((2,0x310),(1,0x320),(0,0x330),(1,0x340)))+b'\x38'
    stream=version+device()+alternatives+b'\x1C\x41\xD0\x05\0'
    stream+=b'\x82\x00\x01'+b'A'*256+device()+b'\x22\0\0'+device(b'\x41\xD0\x07\0')
    streams=[finish(stream,'valid'),finish(stream),finish(version+device(b'\x41\xD0\x04\0'))]
    identities=[serial(b'\x41\xD0\xFF\xFF',1),serial(b'\x41\xD0\xFF\xFF',2),serial(b'\x41\xD0\0\0',3)]
    def run(cards,valid,conflicts=None,expected_port=0x20B):
        bus=Bus(cards,conflicts);bus.pause=False
        m=isa_machine(port,bus,output)
        if port in ('m919','mp386'):
            m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));assert m.call('pnp_journal_begin')
        assert m.call('pnp_work_begin')
        # Existing LPT2 has a read-only status-port overlap with ADDRESS279h.
        # Its baseline claim remains; bus ownership must not reject it.
        assert m.call('pnp_journal_allocate',ECX=32)
        baseline=m.cpu.reg_read(x.UC_X86_REG_EAX)
        resource=bytearray(32);resource[0]=2
        struct.pack_into('<I',resource,16,3);struct.pack_into('<I',resource,20,0x278);struct.pack_into('<I',resource,28,1)
        m.cpu.mem_write(baseline,bytes(resource));assert m.call('pnp_claim_add',EAX=baseline)
        before=bytes(m.cpu.mem_read(m.base,m.allocated));bda=bytes(m.cpu.mem_read(0x4AD,83))
        assert m.call('pnp_census')==valid
        root=int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little')
        raw=bytes(m.cpu.mem_read(root,32))
        assert raw[18]==len(cards) and int.from_bytes(raw[16:18],'little')==(expected_port if cards else 0)
        assert bool(raw[19])==(not valid)
        if cards:
            io=list(bus.transactions)
            for base in (expected_port,0x279,0xA79):
                assert not m.call('pnp_claim_query',AX=0x201,EDX=base,ECX=1)
            assert bus.transactions==io
        assert all(not registers[0x30] for card in cards for registers in card.registers.values())
        assert all(card.state=='wait' for card in cards)
        assert bytes(m.cpu.mem_read(m.base,0x320))==before[:0x320]
        assert bytes(m.cpu.mem_read(m.base+0x340,m.allocated-0x340))==before[0x340:]
        assert bytes(m.cpu.mem_read(0x4AD,83))==bda and not m.writes
        nodes=[];cursor=int.from_bytes(raw[8:12],'little')
        while cursor:
            record=bytes(m.cpu.mem_read(cursor,52));nodes.append((cursor,record))
            cursor=int.from_bytes(record[:4],'little')
        card_records={};cursor=int.from_bytes(raw[4:8],'little')
        while cursor:
            record=bytes(m.cpu.mem_read(cursor,32));card_records[record[17]]=record
            cursor=int.from_bytes(record[:4],'little')
        return m,bus,raw,nodes,card_records
    tested=[]
    if 'valid' in selected:
        for warm in (False,True):
            cards=[Card(identity,data,csn=(19,7,254)[n] if warm else 0,ldns=(3,3,1)[n],powerup_active=True)
                   for n,(identity,data) in enumerate(zip(identities,streams))]
            m,bus,root,nodes,records=run(cards,True)
            assert len(nodes)==7 and int.from_bytes(root[24:28],'little')==7
            assert [records[n][8:17] for n in (1,2,3)]==identities
            assert all(records[n][19]==1 for n in records)
            assert [row[24] for ptr,row in nodes]==[0,1,2,0,1,2,0]
            for ptr,row in (nodes[0],nodes[3]):
                cursor=int.from_bytes(row[12:16],'little');order=[]
                while cursor:
                    alt=bytes(m.cpu.mem_read(cursor,16));order.append((alt[8],int.from_bytes(alt[4:8],'little')))
                    cursor=int.from_bytes(alt[:4],'little')
                assert order==[(0,2),(1,1),(1,3),(2,0)],order
            tested.append('retained_warm' if warm else 'cold')
    # A malformed card cannot hide the later independent card, and no invalid
    # prefix leaves any of its power-up logical decodes active.
    if 'malformed' in selected:
        for bad in (finish(stream,'bad'),finish(version+device()+b'\x30'),
                    finish(version+device()+b'\x38'),
                    finish(version+device()+b'\x81\x09\0'+bytes(9)+device()+b'\x85\x11\0'+bytes(17))):
            cards=[Card(identities[0],bad,ldns=3,powerup_active=True),Card(identities[2],streams[2],powerup_active=True)]
            m,bus,root,nodes,records=run(cards,False)
            assert records[1][19]&0x80 and records[2][19]==1
            assert nodes[-1][1][20:24]==b'\x41\xD0\x04\0'
            tested.append('bad_stream_then_distinct_card')
    if 'empty' in selected:
        run([],True);tested.append('empty_actual_census_invalid_readport')
    if 'relocation' in selected:
        run([Card(identities[0],streams[0],ldns=3,powerup_active=True)],True,
            {0x20B:'checksum'},0x20F)
        tested.append('firmware_response_bad_checksum_relocation_and_bus_owner')
    if exhaustion:
        many=version+b''.join(device() for _ in range(256))
        cards=[Card(serial(b'\x41\xD0\xFF\xFF',n+1),finish(many),ldns=256,powerup_active=True) for n in range(4)]
        m,bus,root,nodes,records=run(cards,False)
        assert int.from_bytes(root[24:28],'little')==1024 and len(nodes)<1024
        assert all((csn,255,0x30,0) in bus.config_writes for csn in range(1,5))
        tested.append('natural_arena_exhaustion_all1024_LDNs_processed')
    return {'scope':'actual ISA reset/isolation/complete census owner; board startup/selection pending',
            'cases':tested,'duplicate_prefix_and_later_distinct':True,'stable_priority_and_source_order':True,
            'deactivate_all_and_WaitForKey':True,'no_persistent_or_public_snapshot_writes':True}


def resource_selection(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    version=b'\x0A\x10\0\x82\x03\0ISA'
    def device(flags):return b'\x15\x41\xD0\x05\0'+bytes((flags,))
    fixed=lambda base:b'\x4B'+struct.pack('<HB',base,8)
    variable=b'\x47\x01'+struct.pack('<HHBB',0x300,0x310,16,8)
    stream=version+device(0)+fixed(0x310)+device(1)+variable
    stream+=b'\x82\x00\x01'+b'M'*256+device(1)+fixed(0x300)+b'\x79\0'
    card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream,ldns=3,powerup_active=True)
    bus=Bus([card]);bus.pause=False
    m=isa_machine(port,bus,output)
    if port in ('m919','mp386'):
        m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));assert m.call('pnp_journal_begin')
    assert m.call('pnp_work_begin') and m.call('pnp_census')
    assert m.call('pnp_solve')
    root=int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little')
    cursor=int.from_bytes(m.cpu.mem_read(root+8,4),'little');nodes=[]
    while cursor:
        row=bytes(m.cpu.mem_read(cursor,564));nodes.append(row)
        cursor=int.from_bytes(row[:4],'little')
    assert len(nodes)==3
    assert [bool(row[26]&1) for row in nodes]==[False,True,True]
    assert [int.from_bytes(row[72:76],'little') for row in nodes[1:]]==[0x310,0x300]
    assert all(not registers[0x30] for registers in card.registers.values())
    assert card.state=='wait' and bus.resource_reads>len(stream)*3 and not m.writes
    m.call('pnp_program')
    assert [card.registers[n][0x30] for n in range(3)]==[0,1,1]
    assert [(card.registers[n].get(0x60,0)<<8)|card.registers[n].get(0x61,0) for n in (1,2)]==[0x310,0x300]
    assert all(bus.config_writes.index((card.csn,n,0x30,1))>bus.config_writes.index((card.csn,n,0x61,base&255))
               for n,base in ((1,0x310),(2,0x300)))
    assert card.state=='wait' and not m.writes
    return {'joint_required_A_or_B_then_fixed_A':True,'earlier_optional_waits':True,
            'actual_reopen_full_stream_and_unchanged_hardware_until_commit':True}


def resource_programming(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    tested=[]
    for family in (24,32,'fixed32'):
        for upper in (False,True):
            info=4 if upper else 0
            if family==24:memory=b'\x81\x09\0'+bytes((info,))+struct.pack('<HHHH',0x1000,0x1000,0,0x100)
            elif family==32:memory=b'\x85\x11\0'+bytes((info,))+struct.pack('<IIII',0x100000,0x100000,0x10000,0x10000)
            else:memory=b'\x86\x09\0'+bytes((info,))+struct.pack('<II',0x100000,0x10000)
            if family==24:null=b'\x81\x09\0\xFF'+struct.pack('<HHHH',0xFFFF,0,0xFFFF,0)
            elif family==32:null=b'\x85\x11\0\xFF'+struct.pack('<IIII',0xFFFFFFFF,0,0xFFFFFFFF,0)
            else:null=b'\x86\x09\0\xFF'+struct.pack('<II',0xFFFFFFFF,0)
            stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x03'+null+memory
            stream+=b'\x47\x01'+bytes(6)+b'\x4B\x88\x03\x08'
            stream+=b'\x23\0\0\xF0\x23\x04\0\x09\x2A\0\xFF\x2A\x22\x12\x79\0'
            card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream,memory_upper=upper)
            bus=Bus([card]);bus.pause=False;m=isa_machine(port,bus,output)
            if port in ('m919','mp386'):
                m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));assert m.call('pnp_journal_begin')
            assert m.call('pnp_work_begin') and m.call('pnp_census')
            m.call('pnp_solve');m.call('pnp_program');regs=card.registers[0]
            assert regs[0x30]==1 and regs[0x31]==0
            assert bytes(regs[a] for a in range(0x60,0x64))==b'\0\0\x03\x88'
            assert [regs[a] for a in range(0x70,0x76)]==[0,2,2,2,4,5]
            if family==24:
                assert bytes(regs[a] for a in range(0x40,0x45))==bytes((0,0,int(upper),0,0))
                assert bytes(regs[a] for a in range(0x48,0x4D))==(b'\x10\0'+bytes((int(upper),))+(b'\x11\0' if upper else b'\xFF\0'))
            else:
                assert bytes(regs[a] for a in range(0x76,0x7F))==bytes(4)+bytes((int(upper),))+bytes(4)
                assert bytes(regs[a] for a in range(0x80,0x89))==(b'\0\x10\0\0'+bytes((int(upper),))+(b'\0\x11\0\0' if upper else b'\xFF\xFF\0\0'))
            assert bus.config_writes[-1]==(1,0,0x30,1) and card.state=='wait'
            assert not m.call('pnp_claim_query',AX=0x300,EDX=9,ECX=1)
            assert m.call('pnp_claim_query',AX=0x300,EDX=2,ECX=1)
            tested.append((family,'upper' if upper else 'mask'))
    return {'actual_register_arithmetic':tested,'null_ordinals_and_second_IRQ_DMA':True,
            'external_ISA2_owns_PIC9':True,'Activate_last_no_filler_writes':True}


def onboard_map(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus
    m=isa_machine(port,Bus([]),output)
    m.call('settings_load')
    m.put('S_EXTENDED_KIB',struct.pack('<H',7168))
    if port=='m919':m.cpu.mem_write(m.base+0xDC,struct.pack('<I',7168))
    policy=bytearray(15)
    struct.pack_into('<H',policy,0,1<<15);policy[2]=1<<2
    struct.pack_into('<HHHHH',policy,3,0x300,16,0x310,16,1<<7)
    m.put('C_PNP',bytes(policy))
    m.call('pnp_publish')
    if port in ('m919','mp386'):
        m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));assert m.call('pnp_journal_begin')
    assert m.call('pnp_work_begin') and m.call('pnp_seed')
    root=int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little')
    assert not m.cpu.mem_read(root+19,1)[0]
    for kind,base,length in ((2,0x60,1),(2,0x64,1),(2,0x70,2),(1,0x200000,1),
                             (2,0x300,16),(2,0x310,16),(1,0xDC000,0x4000),(3,15,1),(4,2,1)):
        assert not m.call('pnp_claim_query',AX=(kind<<8)|1,EDX=base,ECX=length),(port,kind,base)
    # PIC internal cascade2 remains distinct from external ISA2/PIC9.
    assert not m.call('pnp_claim_query',AX=0x300,EDX=2,ECX=1)
    return {'same_actual_P1_encoder':True,'full_manual_windows_and_later_memory':True,
            'PIC_internal_cascade_owner_preserved':True,'no_persistent_writes':not m.writes}


def static_resources(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    def rom(base,index,cycle=False,irq=None):
        raw=bytearray(2048);raw[:3]=b'\x55\xAA\x04';struct.pack_into('<H',raw,0x1A,0x40)
        raw[0x40:0x44]=b'TEST';raw[0x44:0x46]=b'\x07\x01';struct.pack_into('<H',raw,0x46,0x60)
        raw[0x49]=(-sum(raw[0x40:0x50]))&255
        raw[0x60:0x66]=b'$PnP\x01\x02';struct.pack_into('<H',raw,0x66,0x40 if cycle else 0)
        raw[0x6A:0x6E]=b'\x41\xD0\xFF\xFF';struct.pack_into('<H',raw,0x7E,0x200)
        raw[0x69]=(-sum(raw[0x60:0x80]))&255
        allocated=b'\x4B'+struct.pack('<HB',base,8)+b'\x22'+struct.pack('<H',1<<((9+index) if irq is None else irq))+b'\x79\0'
        node=struct.pack('<HB4s3sH',12+len(allocated)+4,0,b'\x41\xD0\x05\0',bytes(3),3)+allocated+b'\x79\0\x79\0'
        # Real independent option code copies its own static bytes into ES:DI.
        # BDA-adjacent marker is test RAM, never firmware-owned public state.
        code=bytes.fromhex('1E0E1F')+b'\xBE\x40\x02\xB9'+struct.pack('<H',len(node))+bytes.fromhex('FCF3A41F50B0008ED8FE06')+struct.pack('<H',0x5A0+index)+bytes.fromhex('58CB')
        raw[0x200:0x200+len(code)]=code;raw[0x240:0x240+len(node)]=node
        raw[-1]=(-sum(raw))&255
        return bytes(raw)
    tested=[]
    for malformed in (False,True):
        m=isa_machine(port,Bus([]),output)
        if port in ('m919','mp386'):
            m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));assert m.call('pnp_journal_begin')
        assert m.call('pnp_work_begin')
        for index,segment in enumerate((0xC800,0xD000,0xD800)):
            m.cpu.mem_write(segment<<4,rom(0x380+index*16,index,malformed and index==0,2 if index==0 else None))
        assert m.call('pnp_rom_resources',AX=0)
        assert bytes(m.cpu.mem_read(0x5A0,3))==bytes((0 if malformed else 1,1,1))
        assert m.call('pnp_claim_query',AX=0x300,EDX=9,ECX=1)==malformed
        assert m.call('pnp_claim_query',AX=0x300,EDX=2,ECX=1),'External static IRQ2 must not own PIC cascade2'
        assert m.call('pnp_claim_query',AX=0x100,EDX=0xC8000,ECX=2048),'Prepass must not claim fixed extents'
        assert m.call('pnp_rom_resources',AX=1)
        assert bytes(m.cpu.mem_read(0x5A0,3))==bytes((0 if malformed else 1,1,1)),'Extent pass must not recall vectors'
        assert not m.call('pnp_claim_query',AX=0x100,EDX=0xC8000,ECX=2048),'Independent live ROM remains owned'
        for index in range(3):
            assert m.call('pnp_claim_query',AX=0x201,EDX=0x380+index*16,ECX=8)==bool(malformed and index==0)
        root=int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little')
        assert not m.cpu.mem_read(root+19,1)[0]  # Rejected chain never became a provider.
        assert not m.writes
        tested.append('cyclic_first_then_later_distinct' if malformed else 'duplicate_prefix_and_later_distinct')
    stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B\xE0\x03\x08\x79\0'
    bus=Bus([Card(serial(b'\x41\xD0\xFF\xFF',1),stream)]);bus.pause=False
    m=isa_machine(port,bus,output);m.cpu.mem_write(0xC8000,rom(0x203,0))
    m.call('settings_load');m.call('pnp_publish')
    if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
    m.call('pnp_prepare')
    assert bus.read_port==0x20B,'Independent static I/O must exclude203/207 before isolation'
    assert bytes(m.cpu.mem_read(0x5A0,1))==b'\x01','Vector executes once across both scanner modes'
    assert bus.cards[0].registers[0][0x30]==1
    return {'actual_validated_generic_chain_and_static_vectors':tested,'minimum1024_buffer':True,
            'independent_full_report_ownership':True,'pre_census_static_IO_excludes_first_read_ports':True,
            'post_census_live_extents_without_vector_recall':True,'no_initialization_or_persistent_writes':True}


def clear_retirement(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus
    tested=[]
    ordinal=65 if port=='m919' else 58
    logical=settings.PAYLOAD_INDICES[ordinal]
    for failed in (None,logical,0x35):
        m=isa_machine(port,Bus([]),output)
        m.call('settings_load');m.call('setup_defaults');m.draft()
        policy=bytearray(15);policy[0]=0x88;policy[2]=0xA2
        struct.pack_into('<HHHHH',policy,3,0x300,16,0x330,16,0xA05);policy[13:]=b'\x01\x01'
        m.put('U_PNP',policy);assert m.call('settings_save')
        m.call('settings_load');m.call('pnp_publish')
        m.put('U_PNP',bytes(range(15)))
        if port=='mp386':m.nvram[0x229]=0xD2
        else:m.cmos[0x69]=0xD2
        m.cmos[0x36]=0x71;m.cmos[0x37]=0xB5
        before=m.snapshot();old=decode_saved(m);draft=m.get('U_PNP',15);m.writes.clear()
        if failed is not None:m.fail=('nvram',0x200+failed-0x40) if port=='mp386' and failed>=0x40 else ('cmos',failed)
        assert m.call('settings_nv6_retire')==(failed is None)
        observed=decode_saved(m)
        expected=bytearray(policy);expected[14]=int(failed is not None)
        assert observed[0]['C_PNP']==expected
        assert observed[1]==old[1]
        for name in ('C_IDE','C_PORTS','C_CHIP'):assert observed[0][name]==old[0][name]
        assert m.get('C_PNP',15)==expected and m.get('U_PNP',15)==draft
        assert m.logical(0x69)==0xD2 and m.cmos[0x36]==0x71 and m.cmos[0x37]==0xB5
        allowed={('cmos',0x35),('nvram',0x200+logical-0x40) if port=='mp386' else ('cmos',logical)}
        if port=='m919':allowed|={('cmos',0x2E),('cmos',0x2F)}
        assert all((kind,at) in allowed for kind,at,value in m.writes),m.writes
        if failed is not None:assert m.snapshot()==before
        tested.append('success' if failed is None else f'verified_rollback_{failed:02X}')
    class Unverifiable(Bus):
        enabled=False;armed=False
        def output(self,p,size,value):
            if self.enabled and p==0x71 and m.index==logical:self.armed=True
            return super().output(p,size,value)
        def input(self,p,size):
            if self.armed and p==0x71 and m.index==logical:return m.cmos[logical]^1
            return super().input(p,size)
    bus=Unverifiable();m=isa_machine(port,bus,output)
    m.call('settings_load');m.call('setup_defaults');m.draft()
    policy=bytearray(15);policy[14]=1;m.put('U_PNP',policy);assert m.call('settings_save')
    m.call('settings_load');m.call('pnp_publish');m.cmos[0x36]=0x71;m.cmos[0x69]=0xD2
    bus.enabled=True
    assert not m.call('settings_nv6_retire') and bus.armed
    assert m.get('C_ERROR')[0]&4 and m.get('C_PNP',15)[14]==1
    assert m.cmos[0x36]==0x71 and m.cmos[0x69]==0xD2
    tested.append('rollback_readback_unverifiable_storage_error_pending_preserved')
    return {'existing_NV6_owner_complete_backup_and_exact_retirement_writes':tested,
            'base_unrelated_policy_D2_markers_and_distinct_draft_preserved':True,
            'power_loss_during_publication_uses_existing_invalid_record_semantics':True}


def packet_journal_lifetime(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus
    m=isa_machine(port,Bus([]),output)
    if port in ('m919','mp386'):
        m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));assert m.call('pnp_journal_begin')
    assert m.call('pnp_work_begin')
    if port=='mp386':m.cpu.mem_write(m.base+0x338,bytes.fromhex('341200F0'))
    control=bytes(m.cpu.mem_read(m.base+0x320,28))
    m.cpu.mem_write(m.base+0x33E,b'\xA5\x5A')
    m.cpu.mem_write(m.base+0x3E3,b'\0') # Actual slave controller disabled, packet reset still runs.
    m.call('ata_identify_selected',FS=(m.base+0x200)>>4)
    assert bytes(m.cpu.mem_read(m.base+0x33E,2))==bytes(2)
    assert bytes(m.cpu.mem_read(m.base+0x320,28))==control
    return {'actual_slave_packet_reset':True,'new_module_pointer338_33B_preserved':True,
            'old33C_33F_collision_regression':True}


def allocation_finish(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B\xE0\x03\x08\x22\0\x08\x2A\x02\x08\x79\0'
    bus=Bus([Card(serial(b'\x41\xD0\xFF\xFF',1),stream)]);bus.pause=False
    m=isa_machine(port,bus,output);m.call('settings_load');m.call('setup_defaults');m.draft()
    policy=bytes(14)+b'\x01';m.put('U_PNP',policy);assert m.call('settings_save')
    m.call('settings_load');m.put('S_EXTENDED_KIB',struct.pack('<H',3072))
    if port=='m919':m.cpu.mem_write(m.base+0xDC,struct.pack('<I',3072))
    m.call('pnp_publish')
    if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
    assert m.call('pnp_prepare')
    root=int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little')
    assert m.cpu.mem_read(root+18,2)==b'\x01\0'
    assert bus.cards[0].registers[0][0x30]==1
    control=bytes(m.cpu.mem_read(m.base+0x320,28))
    m.call('ata_identify_selected',FS=(m.base+0x200)>>4)
    assert bytes(m.cpu.mem_read(m.base+0x320,28))==control
    m.call('pnp_publish');m.call('pnp_finish_entry')
    assert bytes(m.cpu.mem_read(0x4FB,3))==b'\x01\x0B\x02'
    assert decode_saved(m)[0]['C_PNP']==bytes(15)
    assert m.get('U_PNP',15)==policy
    assert not any(m.cpu.mem_read(m.base+0x330,4))
    assert not any(m.cpu.mem_read(m.base+0x338,4))
    assert int.from_bytes(m.cpu.mem_read(m.base+0x334,4),'little')
    assert int.from_bytes(m.cpu.mem_read(0x413,2),'little')==m.base>>10
    return {'actual_prepare_assignment_slave_packet_owner_and_finish':True,'actual_count_port_and_verified_Clear':True,
            'release_restores_memory_and_keeps_distinct_draft':True}


def retained_isa_rom(port,output='build/tests/pnp-runtime'):
    """The expansion ROM really disappears on LDN disable and returns on Activate."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    base=0xC8000
    rom=bytearray(2048);rom[:4]=b'\x55\xAA\x04\xCB';struct.pack_into('<H',rom,0x1A,0x40)
    rom[0x40:0x46]=b'$PnP\x01\x02';rom[0x4A:0x4E]=b'\x41\xD0\xFF\xFF'
    rom[0x49]=(-sum(rom[0x40:0x60]))&255;rom[-1]=(-sum(rom))&255
    memory=b'\x86\x09\0\x44'+struct.pack('<II',base,len(rom))
    stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01'+memory+b'\x79\0'
    card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream,powerup_active=True,memory_upper=True)
    bus=Bus([card]);bus.pause=False;m=isa_machine(port,bus,output)
    visible=[]
    def mapped(cpu,access,address,size,value,unused):
        regs=card.registers[0]
        actual=int.from_bytes(bytes(regs.get(at,0) for at in range(0x76,0x7A)),'big') if 0x76 in regs else base
        responds=bool(regs[0x30] and actual==base)
        visible.append(responds)
        cpu.mem_write(address,bytes(rom[address-base:address-base+size]) if responds else b'\xFF'*size)
    for warm in (False,True):
        # Independent POST workspaces, with the same retained external card.
        m=isa_machine(port,bus,output);visible.clear()
        m.call('settings_load');m.call('pnp_publish')
        if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        hook=m.cpu.hook_add(UC_HOOK_MEM_READ,mapped,None,base,base+len(rom)-1)
        try:
            m.call('pnp_prepare')
            assert visible and any(visible),'Power-up ROM must really be visible to the first scan'
            assert (1,0,0x30,0) in bus.config_writes,'Census must really disable this LDN'
            assert card.registers[0][0x30]==1,'The card must not self-conflict against its retained power-up ROM'
            assert int.from_bytes(bytes(card.registers[0][at] for at in range(0x76,0x7A)),'big')==base
            m.call('pnp_finish_entry');m.call('pnp_publish')
        finally:m.cpu.hook_del(hook)
    return {'actual_powerup_visibility_disable_reassignment_and_activation':True,
            'cold_and_retained_warm':True,'no_ID_dedup_or_onboard_owner_release':True}


def manual_irq_alias(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    results=[]
    for irq in (2,9,None):
        stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x22\x04\x02\x79\0'
        card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream)
        bus=Bus([card]);bus.pause=False;m=isa_machine(port,bus,output)
        m.call('settings_load');m.call('setup_defaults');m.draft()
        policy=bytearray(15)
        if irq is not None:struct.pack_into('<H',policy,0,1<<irq)
        m.put('U_PNP',policy);assert m.call('settings_save')
        m.call('settings_load');m.call('pnp_publish')
        if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        m.call('pnp_prepare')
        assert card.registers[0][0x30]==int(irq is None),(port,irq,card.registers)
        assert not m.call('pnp_claim_query',AX=0x300,EDX=2,ECX=1),'Internal PIC cascade remains owned'
        if irq is None:assert card.registers[0][0x70] in (2,9)
        results.append({'saved_manual_IRQ':irq,'actual_Activate':card.registers[0][0x30]})
    return {'actual_saved_policy_load_seed_and_assignment':results,'external_2_and_9_share_PIC9':True,
            'individual_release_allows_assignment':True,'internal_cascade2_unchanged':True}


def pci_precedence(output='build/tests/pnp-runtime'):
    """Actual PCI allocator must leave the required ISA fixed aperture available."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    from shared.tools.pci_proof import PCI,Endpoint
    results=[]
    for pci_first in (False,True):
        stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01'
        stream+=b'\x47\x01'+struct.pack('<HHBB',0xC010,0xC010,1,16)+b'\x79\0'
        card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream)
        bus=Bus([card]);bus.pause=False
        endpoint=Endpoint(bars={0x10:0xFFFFFFF1})
        bus.pci=PCI({0x60:endpoint});bus.pci_address=0
        m=isa_machine('m919',bus,output)
        m.call('settings_load');m.call('pnp_publish')
        m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        if pci_first:
            assert m.call('pnp_journal_begin') and m.call('pnp_work_begin') and m.call('pnp_seed')
            m.call('pci_initialize')
            assert m.call('pnp_census');m.call('pnp_solve');m.call('pnp_program')
        else:
            m.call('pnp_prepare');m.call('pci_initialize')
        bar=endpoint.read(0x10,4)&~3
        if pci_first:
            assert bar==0xC010 and card.registers[0][0x30]==0
        else:
            assert card.registers[0][0x30]==1 and bar==0xC030,(card.registers,hex(bar))
            assert bytes(card.registers[0][at] for at in (0x60,0x61))==b'\xC0\x10'
        results.append({'PCI_first':pci_first,'actual_BAR':hex(bar),'actual_ISA_active':card.registers[0][0x30]})
    return {'required_before_relocatable_PCI':results,'whole_initializer_reorder_would_steal_required_resource':True}


def selected_vga_resources(output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    from shared.tools.pci_proof import PCI,Endpoint
    results=[]
    for name,display,rom_kind in (('absent',False,'absent'),('selected_PCI',True,'valid'),
                                 ('selected_ISA',False,'valid'),('invalid_ISA',False,'invalid'),
                                 ('PCI_without_ROM',True,'absent')):
        device=b'\x15\x41\xD0\x05\0\x01'
        io=lambda lo,hi,align,length:b'\x47\x01'+struct.pack('<HHBB',lo,hi,align,length)
        memory=b'\x85\x11\0\0'+struct.pack('<IIII',0xA0000,0xD0000,0x10000,0x10000)
        stream=b'\x0A\x10\0\x82\x03\0ISA'+device+io(0x7C0,0x7E0,16,8)+device+io(0x3B8,0x3BC,4,4)+device+memory+b'\x79\0'
        card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream,ldns=3)
        endpoint=Endpoint(cls=0x030000,rom_mask=0xFFFF8000)
        bus=Bus([card]);bus.pause=False;bus.pci=PCI({0x60:endpoint} if display else {});bus.pci_address=0
        m=isa_machine('m919',bus,output)
        # Execute the real RAM-ready state/IVT owner, including its FFFF VGA
        # sentinel. Stop before unrelated SMM/cache/POST hardware owners.
        for reg,value in dict(CS=0xF000,ESP=0x486,EBP=0x800000,EFLAGS=2).items():m.cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
        entry=0xF0000+m.listing.symbol('.ram_ready','startup');end=0xF0000+m.listing.symbol('board_smm_startup')
        m.cpu.emu_start(entry,end,count=30000)
        assert (m.cpu.reg_read(x.UC_X86_REG_CS)<<4)+m.cpu.reg_read(x.UC_X86_REG_IP)==end
        m.base=int.from_bytes(m.cpu.mem_read(0x40E,2),'little')<<4;m.allocated=m.cpu.mem_read(m.base,1)[0]*1024
        assert m.cpu.mem_read(m.base+0x1000,2)==b'\xFF\xFF'
        m.call('init_pic_pit');m.call('settings_load');m.call('setup_defaults');m.draft();assert m.call('settings_save')
        rom=bytearray(32768);rom[:4]=b'\x55\xAA\x40\xCB';rom[-1]=(-sum(rom))&255
        if rom_kind=='invalid':rom[-1]^=1
        observed=[]
        def mapped(cpu,access,address,size,value,unused):
            decoded=rom_kind!='absent' and (not display or bool(endpoint.read(4,2)&2 and endpoint.read(0x30,4)&1))
            observed.append(decoded);cpu.mem_write(address,bytes(rom[address-0xC0000:address-0xC0000+size]) if decoded else b'\xFF'*size)
        hook=m.cpu.hook_add(UC_HOOK_MEM_READ,mapped,None,0xC0000,0xC7FFF)
        try:m.call('pnp_early')
        finally:m.cpu.hook_del(hook)
        actual=int.from_bytes(m.cpu.mem_read(m.base+0x1000,2),'little');assert actual==(0x60 if display else 0xFFFF)
        assert any(op[:4]==('read',0x60,8,4) for op in bus.pci.accesses),'Actual PCI class discovery missing'
        active=display or rom_kind=='valid'
        expected_io=(0x7E0,0x3BC) if active else (0x7C0,0x3B8)
        actual_io=tuple(card.registers[n][0x60]<<8|card.registers[n][0x61] for n in (0,1))
        actual_memory=int.from_bytes(bytes(card.registers[2][at] for at in range(0x76,0x7A)),'big')
        expected_memory=(0xD0000 if rom_kind=='valid' else 0xC0000) if active else 0xA0000
        assert actual_io==expected_io and actual_memory==expected_memory,(name,actual,actual_io,actual_memory)
        assert all(card.registers[n][0x30]==1 for n in range(3))
        root=int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little');pointer=int.from_bytes(m.cpu.mem_read(root,4),'little');claims=[]
        while pointer:
            row=bytes(m.cpu.mem_read(pointer,32));claims.append((row[0],row[2],int.from_bytes(row[20:24],'little'),int.from_bytes(row[16:20],'little'),int.from_bytes(row[28:32],'little')))
            pointer=int.from_bytes(row[24:28],'little')
        legacy=[row for row in claims if row in ((2,0,0x3B0,12,1),(2,0,0x3C0,32,1),(1,0,0xA0000,0x20000,1))]
        assert len(legacy)==(3 if active else 0),(name,legacy)
        results.append({'case':name,'real_initial_sentinel':0xFFFF,'actual_selected_BDF':actual,'actual_legacy_claims':legacy,
                        'actual_IO_bases':actual_io,'actual_memory_base':actual_memory,'all3_LDNs_active':True,
                        'actual_VGA_ROM_decode':any(observed),'actual_PCI_writes':endpoint.writes})
    return results


def pci_fixed_rom(output='build/tests/pnp-runtime'):
    """ROM visibility follows actual PCI command/ROM BAR writes, before ISA."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    from shared.tools.pci_proof import PCI,Endpoint
    results=[]
    for display in (False,True):
        stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01'
        stream+=b'\x86\x09\0\x44'+struct.pack('<II',0xC0000,0x8000)+b'\x79\0'
        card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream,memory_upper=True)
        bus=Bus([card]);bus.pause=False
        endpoint=Endpoint(cls=0x030000 if display else 0x020000,rom_mask=0xFFFF8000)
        bus.pci=PCI({0x60:endpoint});bus.pci_address=0
        m=isa_machine('m919',bus,output)
        m.cpu.mem_write(m.base+0x1000,b'\xFF\xFF') # Actual reset's M_VGA_BDF sentinel.
        m.cpu.mem_write(m.base+0x101E,b'\0')
        m.call('settings_load');m.call('setup_defaults');m.draft();assert m.call('settings_save')
        m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        rom=bytearray(32768);rom[:4]=b'\x55\xAA\x40\xCB';rom[-1]=(-sum(rom))&255
        visible=[]
        def mapped(cpu,access,address,size,value,unused):
            responds=bool(endpoint.read(4,2)&2 and endpoint.read(0x30,4)&1)
            visible.append(responds)
            cpu.mem_write(address,bytes(rom[address-0xC0000:address-0xC0000+size]) if responds else b'\xFF'*size)
        hook=m.cpu.hook_add(UC_HOOK_MEM_READ,mapped,None,0xC0000,0xC7FFF)
        try:m.call('pnp_early')
        finally:m.cpu.hook_del(hook)
        assert card.registers[0][0x30]==int(not display)
        assert any(visible)==display
        assert bool(endpoint.read(0x30,4)&1)==display
        assert not any(offset in range(0x10,0x28) for offset,size,value in endpoint.writes),'No early relocatable BAR allocation'
        results.append({'display':display,'actual_ROM_BAR':hex(endpoint.read(0x30,4)),
                        'actual_ISA_Activate':card.registers[0][0x30]})
    return {'existing_fixed_VGA_owner_before_ISA':results,'actual_decode_drives_live_extent':True}


def pci_vga_first_use(output='build/tests/pnp-runtime'):
    """Early selected ROM remains decoded after the actual BAR allocator."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    from shared.tools.pci_proof import PCI,Endpoint
    chosen=Endpoint(cls=0x030000,rom_mask=0xFFFF8000)
    other=Endpoint(cls=0x030000,rom_mask=0xFFFF8000)
    class VideoBus(Bus):
        def input(self,p,size):
            if p==0x8F0:
                assert chosen.read(4,2)&2 and chosen.read(0x30,4)==0xC0001
                self.witness.append((m.cpu.reg_read(x.UC_X86_REG_CS),m.cpu.reg_read(x.UC_X86_REG_IP)))
                return 0x5A
            return super().input(p,size)
    stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01'
    stream+=b'\x86\x09\0\x04'+struct.pack('<II',0xC0000,0x8000)+b'\x79\0'
    card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream,memory_upper=True)
    bus=VideoBus([card]);bus.pause=False;bus.witness=[];bus.pci=PCI({0x60:chosen,0x68:other});bus.pci_address=0
    m=isa_machine('m919',bus,output)
    # The existing option-ROM return owner uses the board's fixed POST state
    # segment. Match actual startup, rather than the generic settings fixture.
    state=bytes(m.cpu.mem_read(m.base,m.allocated));m.base=0x9E000
    m.cpu.mem_write(m.base,state);m.cpu.mem_write(0x40E,struct.pack('<H',m.base>>4))
    m.cpu.mem_write(m.base+0x1000,b'\xFF\xFF');m.cpu.mem_write(m.base+0x101E,b'\0')
    m.call('settings_load');m.call('setup_defaults');m.draft();assert m.call('settings_save')
    m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));m.cpu.mem_write(0x40,struct.pack('<HH',0,0xF000))
    rom=bytearray(32768);rom[:3]=b'\x55\xAA\x40'
    code=bytes.fromhex('501EBAF008EC31C08ED8C70640000001C706420000C01F58CB')
    rom[3:3+len(code)]=code;rom[0x100]=0xCF;rom[-1]=(-sum(rom))&255
    visibility=[]
    def mapped(cpu,access,address,size,value,unused):
        decoded=bool(chosen.read(4,2)&2 and chosen.read(0x30,4)==0xC0001)
        visibility.append(decoded)
        cpu.mem_write(address,bytes(rom[address-0xC0000:address-0xC0000+size]) if decoded else b'\xFF'*size)
    hook=m.cpu.hook_add(UC_HOOK_MEM_READ,mapped,None,0xC0000,0xC7FFF)
    try:
        m.call('pnp_early')
        assert chosen.read(0x30,4)==0xC0001 and card.registers[0][0x30]==0
        assert not bus.witness
        m.call('pci_initialize')
        writes=[v for at,size,v in chosen.writes if at==0x30]
        assert writes[0]==0 and 0xC0001 in writes and 0 in writes[writes.index(0xC0001)+1:] and writes[-1]==0xC0001,writes
        assert chosen.read(0x30,4)==0xC0001 and other.read(0x30,4)==0
        assert m.cpu.mem_read(m.base+0x1000,2)==b'\x60\0'
        try:assert m.call('initialize_video')
        except Exception as error:
            raise AssertionError(('VGA execution',hex(m.cpu.reg_read(x.UC_X86_REG_CS)),hex(m.cpu.reg_read(x.UC_X86_REG_IP)),
                                  hex(m.cpu.reg_read(x.UC_X86_REG_SS)),hex(m.cpu.reg_read(x.UC_X86_REG_SP)),bus.witness)) from error
    finally:m.cpu.hook_del(hook)
    assert bus.witness and all(cs==0xC000 for cs,ip in bus.witness)
    assert m.cpu.mem_read(0x40,4)==b'\0\x01\0\xC0'
    assert card.registers[0][0x30]==0 and other.read(0x30,4)==0
    return {'actual_early_PCI_allocation_VGA_first_use':True,'selected_BDF':0x60,'other_VGA_not_selected':0x68,
            'selected_ROM_BAR_writes':writes,'actual_ROM_IO_witness':bus.witness,
            'decode_gated_reads':len(visibility),'final_INT10':'C000:0100','conflicting_ISA_inactive':True}


def pci_final_routing(output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    from shared.tools.pci_proof import PCI,Endpoint
    stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x22\0\x08\x79\0'
    bus=Bus([Card(serial(b'\x41\xD0\xFF\xFF',1),stream)]);bus.pause=False
    endpoint=Endpoint(pin=1,bars={0x10:0xFFFFFFF1})
    bridge=Endpoint(identity=0x88861060,cls=0x060100)
    bridge.raw[0x43:0x48]=b'\xA5'*5
    bus.pci=PCI({0x60:endpoint,0x90:bridge});bus.pci_address=0
    bus.ports={0x4D0:0xFF,0x4D1:0xFF}
    m=isa_machine('m919',bus,output)
    m.call('settings_load');m.call('setup_defaults');m.draft()
    policy=bytearray(15);struct.pack_into('<H',policy,0,1<<10)
    m.put('U_PNP',policy);assert m.call('settings_save');m.call('settings_load');m.call('pnp_publish')
    m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));m.call('pnp_prepare')
    assert bus.cards[0].registers[0][0x70]==11 and bus.cards[0].registers[0][0x71]==2
    m.call('pci_initialize');m.call('board_pci_runtime_policy')
    line=endpoint.read(0x3C,1);elcr=bus.ports[0x4D0]|bus.ports[0x4D1]<<8
    assert line not in (10,11,0xFF) and 0<line<16
    assert not elcr&(1<<11),'Actual late writer reintroduced level on allocated ISA edge'
    assert elcr&(1<<10),'Manual exclusion must not invent a signal type or clear peer level'
    assert elcr&(1<<line),'Actual PCI line must have level routing'
    assert bridge.raw[0x46]&0xF0==0xA0 and bridge.raw[0x47]&0xF0==0xA0
    assert bus.cards[0].registers[0][0x30]==1
    return {'actual_PCI_line':line,'actual_ELCR':f'{elcr:04X}','allocated_ISA11_edge_and_manual10_peer_preserved':True,
            'actual_southbridge_peer_bits_and_Activate_preserved':True}


def pci_manual_windows(output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    from shared.tools.pci_proof import PCI,Endpoint
    tested=[]
    for reserved in (False,True):
        stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B\xE0\x03\x08\x79\0'
        bus=Bus([Card(serial(b'\x41\xD0\xFF\xFF',1),stream)]);bus.pause=False
        endpoint=Endpoint(bars={0x10:0xFFFFFFF1});bus.pci=PCI({0x60:endpoint});bus.pci_address=0
        m=isa_machine('m919',bus,output);m.call('settings_load');m.call('setup_defaults');m.draft()
        policy=bytearray(15)
        if reserved:struct.pack_into('<HHHH',policy,3,0xC01F,1,0xC030,16)
        m.put('U_PNP',policy);assert m.call('settings_save');m.call('settings_load');m.call('pnp_publish')
        m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10));before=m.snapshot();m.writes.clear()
        m.call('pnp_prepare');m.call('pci_initialize')
        base=endpoint.read(0x10,4)&~3
        assert base==(0xC050 if reserved else 0xC010),hex(base)
        assert endpoint.read(4,2)&7==1 and bus.cards[0].registers[0][0x30]==1
        assert m.snapshot()==before and not m.writes
        tested.append({'manual_last_byte_and_later_window':reserved,'actual_BAR':hex(base),'actual_IO_decode_only':True})
    return {'real_Save_load_map_existing_PCI_allocator':tested,'ISA_and_both_manual_windows_disjoint':True}


def early_port_ownership(port,output='build/tests/pnp-runtime'):
    """Actual saved disable/readdress must change external decode before census."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    from shared.tools.peripheral_proof import UART
    tested=[]
    for selector in (1,0,3):
        model=None
        if port=='m919':
            sys.path.insert(0,str(ROOT/port/'tools'))
            import sio_proof
            model=sio_proof.SIO(kib=64,ram=4,kind='real')
        elif port=='presario-800':
            os.environ['BAIOS_BUILD_DIRECTORY']=output
            sys.path.insert(0,str(ROOT/port/'tools'))
            import importlib
            ports=importlib.import_module('test-ports');ports.rtc.BUILD=ROOT/port/output
            model=ports.Ports();model.warm_continuation()
        def decoded(base):
            if port=='m919':return bool(model.uart(base))
            if port=='pb430':return base in m.controller.uart_mapping()
            return base in model.devices()[0]
        class Routed(Bus):
            first_route=None
            def input(self,p,size):
                if port=='m919' and (p in (0x108,0x109) or model.uart(p)):
                    return model.incoming(m.cpu,p,size)
                if port=='presario-800' and (p in (0x3F0,0x3F1) or any(a<=p<a+8 for a in (0x3F8,0x3E8))):
                    return model.port_in(m.cpu,p,size,None)
                return super().input(p,size)
            def output(self,p,size,value):
                if p==0x279 and self.first_route is None:self.first_route=(decoded(0x3F8),decoded(0x3E8))
                if port=='m919' and (p in (0x108,0x109) or model.uart(p)):
                    model.outgoing(m.cpu,p,size,value);return True
                if port=='presario-800' and (p in (0x3F0,0x3F1) or any(a<=p<a+8 for a in (0x3F8,0x3E8))):
                    model.port_out(m.cpu,p,size,value,None);return True
                return super().output(p,size,value)
        stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B\xF8\x03\x08\x79\0'
        bus=Routed([Card(serial(b'\x41\xD0\xFF\xFF',1),stream)]);bus.pause=False
        m=isa_machine(port,bus,output)
        if port=='pb430':m.controller.devices_uart=[UART(),UART()];m.controller.extra_uarts={}
        if port=='presario-800':model.cpu=m.cpu
        m.call('settings_load');m.call('setup_defaults');m.draft()
        values=bytearray(m.get('U_PORTS',8));values[0]=1;values[2]=1
        m.put('U_PORTS',values);assert m.call('settings_save');m.call('settings_load');m.call('ports_apply')
        assert decoded(0x3F8),'Real baseline adapter must establish old decode'
        m.draft();values[0]=selector;m.put('U_PORTS',values);assert m.call('settings_save')
        if port!='m919':m.call('pnp_journal_release')
        else:m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        before=m.snapshot();m.writes.clear()
        guard_base=m.base+m.allocated
        guard_before=bytes(m.cpu.mem_read(guard_base,0x10000-m.allocated))
        def work_bounds(cpu,access,address,size,value,unused):
            raise AssertionError(('Decoder wrote outside allocated state/stack',hex(address),size))
        guard=m.cpu.hook_add(UC_HOOK_MEM_WRITE,work_bounds,None,guard_base,m.base+0xFFFF)
        try:m.call('pnp_early')
        finally:m.cpu.hook_del(guard)
        assert bytes(m.cpu.mem_read(guard_base,len(guard_before)))==guard_before
        expected=(selector==1,selector==3)
        assert bus.first_route==expected,(port,selector,bus.first_route)
        assert (decoded(0x3F8),decoded(0x3E8))==expected
        if bus.cards[0].registers[0][0x30]!=int(selector!=1):
            root=int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little');ptr=int.from_bytes(m.cpu.mem_read(root,4),'little');claims=[]
            while ptr:
                claim=bytes(m.cpu.mem_read(ptr,32));claims.append((claim[0],int.from_bytes(claim[20:24],'little'),int.from_bytes(claim[16:20],'little'),int.from_bytes(claim[28:32],'little')));ptr=int.from_bytes(claim[24:28],'little')
            raise AssertionError((port,selector,bus.cards[0].registers,m.get('C_PORTS',8).hex(),claims))
        assert m.snapshot()==before and not m.writes
        tested.append({'saved_selector':selector,'actual_decode_before_first_ISA_IO':expected,
                       'actual_ISA_Activate':bus.cards[0].registers[0][0x30]})
    return {'existing_adapter_changes_before_map_and_census':tested,'no_probe_or_NV_writes':True}


def pb_fixed_video(output='build/tests/pnp-runtime',cases=None):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    import importlib
    sys.path.insert(0,str(ROOT/'pb430/tools'));core=importlib.import_module('core_proof')
    image=ROOT/'pb430'/output/'baios-pb430.bin';results=[]
    for external,base in (cases or ((False,0xC0000),(False,0xD0000),(True,0xC0000))):
        stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x86\x09\0\x44'+struct.pack('<II',base,32768)+b'\x79\0'
        card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream,memory_upper=True)
        bus=Bus([card]);bus.pause=False
        saved=settings.Settings('pb430',output);saved.call('settings_load');saved.call('setup_defaults');saved.draft();saved.put('U_POST_DELAY',b'\0')
        chip=bytearray(saved.get('U_CHIP',24));chip[6]=1;saved.put('U_CHIP',chip);assert saved.call('settings_save')
        m=core.ACC(image,bytes(saved.cmos),isa_bus=bus,external_video=external)
        provider=bytearray(2048);provider[:4]=b'\x55\xAA\x04\xCB';provider[-1]=(-sum(provider))&255
        if external:m.cpu.mem_write(0xC0000,bytes(provider))
        calls=[];m.code_observer=lambda mm,address:calls.append(address) if address==0xC0003 else None
        m.stop_address=0xF0000+m.listing.symbol('initialize_video');m.cold_boot()
        expected_active=int(base!=0xC0000)
        assert card.registers[0][0x30]==expected_active,('Fixed VGA decode not admitted before ISA',external,hex(base),card.registers,hex(m.registers[2]))
        assert not calls,'Preallocation executed a video ROM'
        selected=bytes(provider) if external else image.read_bytes()[:32768]
        assert bytes(m.cpu.mem_read(0xC0000,len(selected)))==selected
        if not external:assert m.registers[2]&1
        results.append({'external':external,'required_ISA_base':hex(base),'actual_Activate':expected_active,
                        'selected_ROM_bytes_exact':True,'no_early_ROM_execution':True})
    return {'actual_reset_fixed_video_before_ISA':results}


def pb_scratch_lifetime(output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus
    m=isa_machine('pb430',Bus(),output);m.call('settings_load')
    assert m.call('pnp_work_begin')
    cursor,end=struct.unpack('<II',m.cpu.mem_read(m.base+0x320,8))
    assert m.call('pnp_journal_allocate',ECX=cursor-0x40010)
    assert m.cpu.reg_read(x.UC_X86_REG_EAX)==0x40010
    m.cpu.mem_write(0x40010,b'\xA5'*(cursor-0x40010))
    assert m.call('pnp_journal_allocate',ECX=32)
    low=m.cpu.reg_read(x.UC_X86_REG_EAX);assert low==0x1FFE0
    m.cpu.mem_write(low,b'\x5A'*32)
    spans=[(low,bytes(m.cpu.mem_read(low,0x20000-low))),
           (0x40000,bytes(m.cpu.mem_read(0x40000,end-0x40000)))]
    chip=bytearray(m.get('C_CHIP',24));chip[3]=1;chip[10:13]=b'\x01\x01\x01';m.put('C_CHIP',chip)
    m.controller.registers[2]&=~0x1E
    m.call('chipset_apply')
    assert all(bytes(m.cpu.mem_read(address,len(data)))==data for address,data in spans)
    assert bytes(m.cpu.mem_read(0x30000,16))==m.image.read_bytes()[0x10000:0x10010]
    # Returning consumers can report a lower ceiling beneath the scratch hole.
    m.cpu.mem_write(0x413,struct.pack('<H',96))
    assert m.call('pnp_journal_allocate',ECX=32)
    assert m.cpu.reg_read(x.UC_X86_REG_EAX)==96*1024-32
    return {'actual_allocator_skips_exact20000_3FFFF':True,'actual_chipset_apply_shadow_staging_preserves_all_live_intervals':True,
            'actual_F000_staged_bytes':True,'returning_memory_ceiling_below_hole_preserved':True}


def resource_capabilities(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    class Observed(Bus):
        def __init__(self,cards):super().__init__(cards);self.io=[]
        def output(self,p,size,value):self.io.append((p,size,value));return super().output(p,size,value)
    prefix=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01'
    rows=[('DMA8',b'\x2A\x22\x08',1),('DMA16',b'\x2A\x22\x12',5),
          ('no_count',b'\x2A\x02\0',None),('wrong_width_count',b'\x2A\x20\x0A',None)]
    rows += [(f'master_speed_{speed}',b'\x2A\x02'+bytes((4|speed,)),1) for speed in (0,0x20,0x40,0x60)]
    rows += [(f'slave_speed_{speed}',b'\x2A\x02'+bytes((8|speed,)),1) for speed in (0,0x20,0x40,0x60)]
    rows += [('edge',b'\x23\0\x08\x01',11),('edge_and_alternate',b'\x23\0\x08\x09',11),
             ('alternate_only',b'\x23\0\x08\x08',None)]
    tested=[]
    for name,resource,selected in rows:
        card=Card(serial(b'\x41\xD0\xFF\xFF',1),prefix+resource+b'\x79\0')
        bus=Observed([card]);bus.pause=False;m=isa_machine(port,bus,output)
        m.call('settings_load');m.call('pnp_publish')
        if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        bus.io.clear();m.call('pnp_prepare');regs=card.registers[0]
        assert all(p in (0x279,0xA79,0x43,0x84,0x80) for p,size,value in bus.io),'Metadata programmed unrelated host timing/DMA'
        assert regs[0x30]==int(selected is not None),(name,regs)
        if selected is not None:
            assert regs[0x74 if resource[0]==0x2A else 0x70]==selected,(name,regs)
            if resource[0]!=0x2A:assert regs[0x71]==2
        tested.append(name)
    return {'actual_channel_width_count_speed_and_master_intersection':tested,
            'advertised_edge_preferred_alternate_only_backtracks':True,'no_host_timing_or_DMA_programming':True}


def allocation_policy(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    tested=[]
    for os_policy,release in ((0,False),(0,True),(1,True)):
        prefix=b'\x0A\x10\0\x82\x03\0ISA'
        device=lambda flags:b'\x15\x41\xD0\x05\0'+bytes((flags,))
        fixed=lambda base:b'\x4B'+struct.pack('<HB',base,8)
        stream=prefix+device(1)+fixed(0x3E0)+device(0)+fixed(0x350)+device(0)+fixed(0x360)+b'\x79\0'
        card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream,ldns=3)
        bus=Bus([card]);bus.pause=False;m=isa_machine(port,bus,output)
        m.call('settings_load');m.call('setup_defaults');m.draft()
        policy=bytearray(15);struct.pack_into('<HHHH',policy,3,0x350,0 if release else 16,0x358,16)
        policy[13]=os_policy;m.put('U_PNP',policy);assert m.call('settings_save')
        m.call('settings_load');m.call('pnp_publish')
        if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        m.call('pnp_prepare')
        assert [card.registers[n][0x30] for n in range(3)]==[1,int(release and not os_policy),0]
        assert not m.call('pnp_claim_query',AX=0x201,EDX=0x360,ECX=8),'Later overlapping reservation lost'
        tested.append({'OS':os_policy,'first_window_released':release,'Activate':[card.registers[n][0x30] for n in range(3)]})
    return {'real_verified_Save_load_union_release_and_policy':tested}


def setup_journal_lifetime(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B\xE0\x03\x08\x79\0'
    bus=Bus([Card(serial(b'\x41\xD0\xFF\xFF',1),stream)]);bus.pause=False
    m=isa_machine(port,bus,output)
    m.call('settings_load');m.call('setup_defaults');m.draft()
    policy=bytearray(15);struct.pack_into('<HH',policy,3,0x350,8);policy[14]=1
    m.put('U_PNP',policy);m.put('U_POST_DELAY',[0]);assert m.call('settings_save')
    m.call('settings_load');m.call('pnp_publish')
    if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
    m.call('pnp_prepare')
    cursor,end=struct.unpack('<II',m.cpu.mem_read(m.base+0x320,8))
    journal=bytes(m.cpu.mem_read(cursor,end-cursor));control=bytes(m.cpu.mem_read(m.base+0x320,28))
    saved=m.snapshot();m.writes.clear()
    # Input is the established IRQ1 owner's request; execute the actual early gate.
    m.put('S_SETUP_REQUEST',b'\x01');m.keys=[27,13]
    m.call('post_early_setup')
    assert not m.keys and m.snapshot()==saved and not m.writes
    assert bytes(m.cpu.mem_read(cursor,end-cursor))==journal
    assert bytes(m.cpu.mem_read(m.base+0x320,28))==control
    m.call('ata_identify_selected',FS=(m.base+0x200)>>4)
    assert bytes(m.cpu.mem_read(cursor,end-cursor))==journal
    m.put('S_SETUP_REQUEST',b'\x01')
    m.keys=[0x5000]*5+[9,13]+[0x5000]*10+[0x4D00,0x4400,13]
    reset=[]
    hook=m.cpu.hook_add(UC_HOOK_CODE,lambda u,a,z,v:(reset.append(a),u.emu_stop()),None,
        0xF0000+m.listing.symbol('warm_reset'),0xF0000+m.listing.symbol('warm_reset'))
    try:
        try:m.call('post_early_setup')
        except AssertionError:
            if not reset:raise
    finally:m.cpu.hook_del(hook)
    assert reset and not m.keys
    expected=bytearray(policy);expected[:2]=b'\0\x80'
    assert decode_saved(m)[0]['C_PNP']==expected
    assert bytes(m.cpu.mem_read(cursor,end-cursor))==journal
    return {'actual_early_gate_Discard_preserves_active_code_journal_and_later_disk':True,
            'actual_early_gate_Save_changes_policy_and_reaches_reset':True,
            'saved_cmos':bytes(m.cmos).hex(),'saved_nv':bytes(m.nvram[0x200:0x240]).hex()}


def natural_capacity(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    prefix=b'\x0A\x10\0\x82\x03\0ISA';device=b'\x15\x41\xD0\x05\0\x01'
    def run(amount,kib):
        card=Card(serial(b'\x41\xD0\xFF\xFF',1),prefix+device*amount+b'\x79\0',ldns=amount,powerup_active=True)
        bus=Bus([card]);bus.pause=False;m=isa_machine(port,bus,output,kib)
        m.call('settings_load');m.call('setup_defaults');m.draft()
        policy=bytearray(15);policy[14]=1;m.put('U_PNP',policy);m.put('U_HALT',b'\x01');assert m.call('settings_save')
        m.call('settings_load');m.call('pnp_publish');before=m.snapshot();m.writes.clear()
        m.cpu.mem_write(0xFFF0,b'FLOOR-CANARY')
        m.call('pnp_prepare')
        root=int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little')
        assert root
        data=bytes(m.cpu.mem_read(root,32));status=data[19]
        assert int.from_bytes(data[24:28],'little')==amount,'Capacity exhaustion truncated census'
        assert (1,amount-1,0x30,0) in bus.config_writes
        assert bytes(m.cpu.mem_read(0xFFF0,12))==b'FLOOR-CANARY'
        assert m.snapshot()==before and not m.writes,'Rebuild must not publish progress'
        used=kib*1024-int.from_bytes(m.cpu.mem_read(m.base+0x320,4),'little')
        m.call('pnp_finish_entry')
        runtime=bool(int.from_bytes(m.cpu.mem_read(m.base+0x334,4),'little'))
        assert decode_saved(m)[0]['C_PNP'][14]==int(bool(status) or not runtime)
        assert int.from_bytes(m.cpu.mem_read(0x413,2),'little')==(m.base>>10 if runtime else kib)
        return status,used
    status,used=run(1,512);assert not status
    kib=64+(used+1023)//1024
    amount=1;last=None
    while True:
        status,consumed=run(amount,kib)
        if status:
            assert last is not None
            return {'accounted_available_KiB':kib,'last_fit_LDNs':last,'first_conforming_excess_LDNs':amount,
                    'expanded_code_and_journal_charged':True,'full_census_deactivation_no_false_Clear_no_corruption':True}
        last=amount;amount+=1


def rebuild_clear(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    prefix=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01'
    def stream(base,bad=False):
        data=prefix+b'\x4B'+struct.pack('<HB',base,8)
        value=(-sum(data)-0x79)&255
        if not value:data+=b'\x71\x01';value=(-sum(data)-0x79)&255
        assert value
        if bad:value=(value+1)&255 or 1
        return data+bytes((0x79,value))
    card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream(0x3E0,True),powerup_active=True)
    bus=Bus([card]);bus.pause=False
    tested=[]
    for index,(name,base,bad,active,pending) in enumerate((('bad_End',0x3E0,True,0,1),
            ('valid_next_rebuild',0x3E0,False,1,0),('valid_unassignable',0x350,False,0,0))):
        m=isa_machine(port,bus,output)
        m.call('settings_load');m.draft();m.put('U_HALT',b'\x01')
        policy=bytearray(15);struct.pack_into('<HH',policy,3,0x350,8);policy[14]=1
        m.put('U_PNP',policy);assert m.call('settings_save')
        m.cmos[0x69]=0xD2;m.cmos[0x36]=0x71;m.cmos[0x37]=0xA0
        m.call('settings_load');m.call('pnp_publish')
        if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        card.resources=stream(base,bad);card.csn=0x71;card.state='sleep'
        before=decode_saved(m);m.writes.clear();m.call('pnp_prepare')
        root=int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little')
        assert bool(m.cpu.mem_read(root+19,1)[0])==bad
        assert card.csn==1 and card.registers[0][0x30]==active
        m.call('pnp_publish');m.call('pnp_finish_entry');after=decode_saved(m)
        expected=bytearray(policy);expected[14]=pending
        assert after[0]['C_PNP']==expected and after[1]==before[1]
        for field in ('C_IDE','C_PORTS','C_CHIP'):assert after[0][field]==before[0][field]
        assert m.cmos[0x69]==0xD2 and m.cmos[0x36:0x38]==b'\x71\xA0'
        if bad:assert not m.writes
        tested.append({'case':name,'actual_Activate':active,'pending_Clear':pending,'fresh_CSN':card.csn})
    return {'actual_ISA_reset_isolation_parse_program_finish_verified_retirement':tested,
            'all_unrelated_logical_settings_and_recovery_markers_preserved':True}


def dependent_alternatives(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    prefix=b'\x0A\x10\0\x82\x03\0ISA';device=b'\x15\x41\xD0\x05\0\x01'
    stream=prefix+device+b'\x31\0\x4B\0\x03\x08\x22\x10\0'
    stream+=b'\x31\x01\x4B\x10\x03\x08\x22\0\x08\x38'+device+b'\x4B\0\x03\x08\x79\0'
    card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream,ldns=2)
    bus=Bus([card]);bus.pause=False;m=isa_machine(port,bus,output)
    m.call('settings_load');m.call('pnp_publish')
    if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
    m.call('pnp_prepare')
    assert [card.registers[n][0x30] for n in range(2)]==[1,1]
    for n,base in ((0,0x310),(1,0x300)):
        assert bytes(card.registers[n][at] for at in (0x60,0x61))==base.to_bytes(2,'big')
    assert card.registers[0][0x70]==11
    return {'preferred_IO_then_blocked_IRQ_rolled_back':True,'next_whole_tuple_and_later_LDN':True,
            'joint_required':resource_selection(port,output)}


def logical_limits(port,output='build/tests/pnp-runtime'):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    prefix=b'\x0A\x10\0\x82\x03\0ISA';device=b'\x15\x41\xD0\x05\0\x01'
    tested=[]
    for kind,limit,filler in [('memory',4,b'\x86\x09\0'+b'\xFF'*5+bytes(4)),
                              ('IO',8,b'\x4B\0\0\0'),('IRQ',2,b'\x23\0\0\xFF'),('DMA',2,b'\x2A\0\xFF')]:
        for extra in (0,1):
            stream=prefix+device+filler*(limit+extra)+device+b'\x4B\xE0\x03\x08\x79\0'
            cards=[Card(serial(b'\x41\xD0\xFF\xFF',1),stream,ldns=2),
                   Card(serial(b'\x41\xD0\xFF\xFF',2),prefix+device+b'\x4B\x88\x03\x08\x79\0')]
            bus=Bus(cards);bus.pause=False;m=isa_machine(port,bus,output)
            m.call('settings_load');m.call('pnp_publish')
            if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
            m.call('pnp_prepare')
            assert cards[0].registers[0][0x30]==1-extra,(kind,extra,cards[0].registers)
            assert cards[0].registers[1][0x30]==1 and cards[1].registers[0][0x30]==1
            assert bytes(cards[0].registers[1][at] for at in (0x60,0x61))==b'\x03\xE0'
            tested.append((kind,limit+extra))
    return {'hardware_slot_maximum_and_one_excess':tested,'null_ordinals_not_dropped':True,
            'later_distinct_LDN_and_equal_ID_card_retained':True}


def allocation_fixture(port,cards,policy=None,bus=None,configure=None,draft=None):
    """Real complete allocator entry; only external device input is authored."""
    from shared.tools.isa_pnp_proof import Bus
    bus=bus if bus is not None else Bus(cards)
    m=isa_machine(port,bus,OUTPUT)
    m.call('settings_load');m.call('setup_defaults');m.draft()
    if policy is not None:m.put('U_PNP',policy)
    if draft is not None:draft(m)
    assert m.call('settings_save')
    m.call('settings_load')
    # Existing RAM producer's 8MiB description, never a candidate allocation.
    m.put('S_EXTENDED_KIB',struct.pack('<H',7168))
    if port=='m919':m.cpu.mem_write(m.base+0xDC,struct.pack('<I',7168))
    m.call('pnp_publish')
    if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
    if configure is not None:configure(m)
    before=m.snapshot();m.writes.clear()
    m.call('pnp_prepare')
    assert m.snapshot()==before and not m.writes
    assert all(card.state=='wait' for card in cards)
    for card in cards:
        for n,row in card.registers.items():
            activations=[i for i,event in enumerate(bus.config_writes) if event==(card.csn,n,0x30,1)]
            if row[0x30]:
                assert activations
                assert all(i<activations[-1] for i,event in enumerate(bus.config_writes)
                           if event[:2]==(card.csn,n) and event[2]!=0x30)
    return m,bus


def allocation_causal(port,groups=None):
    """Census/replay/seed/solve/program proofs; no disconnected ledger oracle."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    selected=set(groups or ('identity','reopen','metadata','ordinals','io','memory','family','malformed','static','manual'))
    version=b'\x0A\x10\0\x82\x03\0ISA'
    device=lambda product=0x0500:b'\x15\x41\xD0'+product.to_bytes(2,'big')+b'\x01'
    fixed=lambda base,length=8:b'\x4B'+struct.pack('<HB',base,length)
    variable=lambda lo,hi,align=16,length=8,decode=1:b'\x47'+struct.pack('<BHHBB',decode,lo,hi,align,length)
    def card(number,body,**kw):
        return Card(serial(b'\x41\xD0\xFF\xFF',number),version+body+b'\x79\0',**kw)
    def io(row,ordinal=0):return row.get(0x60+ordinal*2,0)<<8|row.get(0x61+ordinal*2,0)
    def rows(cards):return [{str(n):dict(row) for n,row in c.registers.items()} for c in cards]
    results={}
    if 'identity' in selected:
        tested=[]
        for amount,warm in ((0,False),(1,False),(3,False),(3,True)):
            cards=[card(n+1,device()+fixed(0x300+n*0x10)+b'\x1C\x41\xD0\x05\0'+
                        device(0x0500 if n<2 else 0x0700)+fixed(0x340+n*0x10),ldns=2,
                        csn=(19,7,254)[n] if warm else 0,powerup_active=True) for n in range(amount)]
            m,bus=allocation_fixture(port,cards)
            ordered=sorted(cards,key=lambda c:tuple((v>>bit)&1 for v in c.identity for bit in range(8)),reverse=True)
            assert [c.csn for c in ordered]==list(range(1,amount+1))
            for n,c in enumerate(cards):
                assert [c.registers[i][0x30] for i in (0,1)]==[1,1]
                assert [io(c.registers[i]) for i in (0,1)]==[0x300+n*16,0x340+n*16]
            tested.append({'amount':amount,'retained_nonsequential_CSN':warm,'actual_registers':rows(cards)})
        class BadIsolation(Bus):
            def input(self,p,size):
                if p==self.read_port and self.address==1:
                    self.conflicts[p]='checksum' if any(c.csn for c in self.cards) else 'no-pair'
                    if not self.after:self.conflicts[p]='checksum' if p==0x20B else None
                return super().input(p,size)
        failures=[]
        for after in (False,True):
            cards=[card(1,device()+fixed(0x300)),card(2,device()+fixed(0x310))]
            bus=BadIsolation(cards);bus.after=after
            if after:
                # First isolation is valid; corrupt only the subsequent checksum.
                original=bus.input
                def incoming(p,size):
                    if p==bus.read_port and bus.address==1 and not any(c.csn for c in cards):
                        return Bus.input(bus,p,size)
                    return original(p,size)
                bus.input=incoming
            m,bus=allocation_fixture(port,cards,bus=bus)
            assert bus.read_port==(0x20B if after else 0x20F)
            assert sum(bool(c.csn) for c in cards)==(1 if after else 2)
            for n,c in enumerate(cards):
                assert c.registers[0][0x30]==int(bool(c.csn))
                if c.csn:assert io(c.registers[0])==0x300+n*16
            failures.append({'checksum_after_valid':after,'actual_read_port':bus.read_port,'actual_registers':rows(cards)})
        results['M1_M2']={'collections':tested,'isolation_checksum_boundary':failures}
    if 'reopen' in selected:
        class PrefixBus(Bus):
            def __init__(self,cards,invalid):
                super().__init__(cards);self.invalid=invalid;self.bytes=[];self.ready_log=[]
            def output(self,p,size,value):
                if p==0xA79 and self.address==3:self.bytes.append([])
                return super().output(p,size,value)
            def input(self,p,size):
                address=self.address;cursor=self.selected.cursor if self.selected else -1
                value=super().input(p,size)
                if p==self.read_port and address==5:self.ready_log.append(value)
                if p==self.read_port and address==4:
                    if cursor==8:value=0xA5 if self.invalid else self.selected.identity[8]
                    self.bytes[-1].append((cursor,value))
                return value
        actual=[];registers=[]
        for invalid in (False,True):
            cards=[card(1,device()+variable(0x300,0x310)+device()+fixed(0x300),ldns=2)]
            bus=PrefixBus(cards,invalid);m,bus=allocation_fixture(port,cards,bus=bus)
            streams=[stream for stream in bus.bytes if stream]
            immediate=[s for s in streams if s[0][0]==9];reopened=[s for s in streams if s[0][0]==0]
            assert immediate and reopened,(streams,bus.transactions[-20:],cards[0].registers)
            assert all([at for at,value in s[:9]]==list(range(9)) and s[9][0]==9 and s[9][1]==0x0A for s in reopened)
            assert all(s[8][1]==(0xA5 if invalid else cards[0].identity[8]) for s in reopened)
            assert len(bus.ready_log)==2*bus.resource_reads and bus.ready_log==[0,1]*bus.resource_reads
            assert [io(cards[0].registers[n]) for n in (0,1)]==[0x310,0x300]
            registers.append(rows(cards));actual.append({'invalid_ninth':invalid,'reopened_streams':len(reopened),
                'immediate_streams':len(immediate),'resource_bytes':bus.resource_reads,'readiness_polls':bus.status_reads})
        assert registers[0]==registers[1]
        results['M4']={'actual_replay_and_joint_selection':actual,'identical_final_registers':registers[0]}
    if 'metadata' in selected:
        tested=[]
        for length in (255,256):
            c=card(1,device()+fixed(0x300)+b'\x82'+struct.pack('<H',length)+b'M'*length+
                   device(0x0700)+fixed(0x310),ldns=2)
            m,bus=allocation_fixture(port,[c]);assert [io(c.registers[n]) for n in (0,1)]==[0x300,0x310]
            assert all(c.registers[n][0x30]==1 for n in (0,1))
            tested.append({'metadata_bytes':length,'actual_registers':rows([c]),'stream_reads':bus.resource_reads})
        results['M6']=tested
    if 'ordinals' in selected:
        tested=[]
        for null_form in ('none','general_ignored_fields','fixed_valid_base'):
            filler=null_form!='none'
            # Clarification6.2.2.8: length0 ignores information, inverted
            # min/max and alignment. The fixed4Bh contrast retains its valid
            #10-bit base; no unqualified reserved-base exception is assumed.
            io_null=(variable(0xFFFF,0,255,0,255) if null_form=='general_ignored_fields' else fixed(0x3E0,0))
            null=io_null+b'\x23\0\0\xFF\x2A\0\xFF' if filler else b''
            c=card(1,device()+null+fixed(0x388)+b'\x22\0\x08\x2A\x02\x08'+
                   b'\x1C\x41\xD0\x05\0'+device()+fixed(0x3E0),ldns=2)
            m,bus=allocation_fixture(port,[c]);r=c.registers[0];ordinal=int(filler)
            assert r[0x30]==c.registers[1][0x30]==1 and io(r,ordinal)==0x388,(port,null_form,rows([c]))
            assert r[0x70+ordinal*2]==11 and r[0x74+ordinal]==1
            if filler:
                assert io(r)==0 and r[0x70]==0 and r[0x74]==4
                assert all((c.csn,0,at,0) in bus.config_writes for at in (0x60,0x61))
            assert io(c.registers[1])==0x3E0
            tested.append({'null_fillers':filler,'null_form':null_form,'raw_IO_descriptor':io_null.hex() if filler else None,
                           'actual_registers':rows([c]),'actual_resource_stream_bytes':bus.resource_reads,
                           'actual_IO_program_writes':[r for r in bus.config_writes if 0x60<=r[2]<=0x63]})
        results['M5']=tested
        invalid=[]
        for name,bad in (('general_reserved_information',variable(0x300,0x300,16,8,255)),
                         ('general_inverted_range',variable(0x310,0x300)),
                         ('fixed_reserved_base_nonnull',fixed(0xFFFF))):
            c=card(1,device()+bad+fixed(0x388)+device()+fixed(0x3E0),ldns=2,powerup_active=True)
            m,bus=allocation_fixture(port,[c])
            assert all(not c.registers[n][0x30] for n in (0,1)),(port,name,rows([c]))
            assert not any(0x60<=r[2]<=0x6F for r in bus.config_writes),bus.config_writes
            invalid.append({'case':name,'nonnull_still_rejected_before_program':True,'actual_registers':rows([c])})
        results['M5_nonnull_IO_validation']=invalid
    if 'io' in selected:
        tested=[]
        # All exclusions come through actual saved manual policy and pnp_seed.
        cases=[('16bit_high_alias',1,0xC300,0xC310,16,8,0x300,8,0xC300),
               ('10bit_high_alias',0,0xC300,0xC310,16,8,0x300,8,0xC310),
               ('last_byte',1,0x340,0x350,16,8,0x347,1,0x350),
               ('adjacent_end',1,0x340,0x350,16,8,0x348,1,0x340),
               ('alignment',1,0x341,0x360,16,8,0x350,8,0x360),
               ('end_ffff',1,0xFFF0,0xFFF8,8,8,0xFFF0,8,0xFFF8)]
        for name,decode,lo,hi,align,length,blocked,count,expected in cases:
            policy=bytearray(15);struct.pack_into('<HH',policy,3,blocked,count)
            c=card(1,device()+variable(lo,hi,align,length,decode))
            def quiet_uart(m):
                ports=bytearray(m.get('U_PORTS',6));ports[0]=0;m.put('U_PORTS',ports)
            m,bus=allocation_fixture(port,[c],policy,draft=quiet_uart if name=='end_ffff' else None)
            assert c.registers[0][0x30]==1 and io(c.registers[0])==expected,(name,c.registers)
            expanded=(set(range(expected,expected+length)) if decode else
                      {a for a in range(65536) if ((a-expected)&1023)<length})
            assert not expanded&set(range(blocked,blocked+count))
            candidates=[a for a in range(lo,hi+1) if a%align==0 and a+length<=65536]
            feasible=[a for a in candidates if not ((set(range(a,a+length)) if decode else
                      {v for v in range(65536) if ((v-a)&1023)<length})&set(range(blocked,blocked+count)))]
            assert expected==feasible[0],(name,feasible)
            tested.append({'case':name,'actual_base':expected,'expanded_decoded_addresses':len(expanded)})
        results['M7']=tested
    if 'memory' in selected:
        tested=[]
        for family in (24,32,'fixed32'):
            for upper in (False,True):
                info=4 if upper else 0
                if family==24:desc=b'\x81\x09\0'+bytes((info,))+struct.pack('<HHHH',0xC00,0xE00,0,0x100)
                elif family==32:desc=b'\x85\x11\0'+bytes((info,))+struct.pack('<IIII',0xC0000,0xE0000,0x10000,0x10000)
                else:desc=b'\x86\x09\0'+bytes((info,))+struct.pack('<II',0xD0000,0x10000)
                policy=bytearray(15);struct.pack_into('<H',policy,11,0x00F)
                blocked=(b'\x86\x09\0'+bytes((info,))+struct.pack('<II',0xC0000,0x10000)) if family=='fixed32' else b''
                c=card(1,(device()+blocked if blocked else b'')+device()+desc,
                       ldns=2 if blocked else 1,memory_upper=upper)
                m,bus=allocation_fixture(port,[c],policy)
                if blocked:assert c.registers[0][0x30]==0
                r=c.registers[int(bool(blocked))];assert r[0x30]==1
                start=0x40 if family==24 else 0x76
                width=2 if family==24 else 4;scale=256 if family==24 else 1
                base=int.from_bytes(bytes(r[start+n] for n in range(width)),'big')*scale
                end_or_mask=int.from_bytes(bytes(r[start+width+1+n] for n in range(width)),'big')*scale
                assert base==0xD0000 and r[start+width]&1==int(upper)
                assert end_or_mask==(0xE0000 if upper else (0xFF0000 if family==24 else 0xFFFF0000))
                assert not set(range(base,base+0x10000))&set(range(0xC0000,0xD0000))
                assert not m.call('pnp_claim_query',AX=0x100,EDX=0x100000,ECX=1),'Real seeded installed RAM missing'
                tested.append({'family':family,'upper_limit':upper,'actual_base':base,'actual_limit_or_mask':end_or_mask})
        ram=b'\x85\x11\0\0'+struct.pack('<IIII',0x100000,0x900000,0x10000,0x10000)
        c=card(1,device()+ram);m,bus=allocation_fixture(port,[c])
        assert c.registers[0][0x30]==1
        actual=int.from_bytes(bytes(c.registers[0][at] for at in range(0x76,0x7A)),'big')
        assert actual==0x800000,'Installed8MiB RAM must exclude every earlier candidate'
        tested.append({'installed_RAM_exclusion':True,'actual_base':actual})
        results['M8']=tested
    if 'family' in selected:
        tested=[]
        for mixed in (False,True):
            mem24=lambda base:b'\x81\x09\0\0'+struct.pack('<HHHH',base>>8,base>>8,0x4000,0x40)
            later=(b'\x86\x09\0\0'+struct.pack('<II',0xCC000,0x4000)) if mixed else mem24(0xCC000)
            first=card(1,device()+mem24(0xC8000)+device()+later,ldns=2,powerup_active=True)
            independent=card(2,device(0x0700)+fixed(0x3E0))
            m,bus=allocation_fixture(port,[first,independent])
            assert [first.registers[n][0x30] for n in (0,1)]==[int(not mixed)]*2,(mixed,first.registers)
            assert independent.registers[0][0x30]==1 and io(independent.registers[0])==0x3E0
            tested.append({'different_later_family':mixed,'actual_registers':rows([first,independent])})
        results['M9']=tested
    if 'malformed' in selected:
        tested=[]
        for name,body in [('short_memory',device()+fixed(0x300)+b'\x81\x08\0'+bytes(8)),
                          ('invalid_LDN_ID',device()+fixed(0x300)+b'\x15\xC1\xD0\0\0\x01'),
                          ('end_without_start',device()+fixed(0x300)+b'\x38'),
                          ('unclosed_dependent',device()+fixed(0x300)+b'\x30\x4B\x10\x03\x08')]:
            first=card(1,body,ldns=2,powerup_active=True)
            later=card(2,device(0x0700)+fixed(0x300))
            m,bus=allocation_fixture(port,[first,later])
            assert not any(r[0x30] for r in first.registers.values())
            assert later.registers[0][0x30]==1 and io(later.registers[0])==0x300
            assert not any(csn==first.csn and reg==0x30 and value==1 for csn,n,reg,value in bus.config_writes)
            tested.append({'case':name,'actual_registers':rows([first,later])})
        results['M10']=tested
    if 'static' in selected:
        tested=[]
        for present in (False,True):
            allocated=fixed(0x300)+fixed(0x300)+fixed(0x310)+fixed(0x350)+b'\x79\0'
            node=struct.pack('<HB4s3sH',16+len(allocated),0,b'\x41\xD0\x05\0',bytes(3),3)+allocated+b'\x79\0\x79\0'
            raw=bytearray(2048);raw[:3]=b'\x55\xAA\x04'
            struct.pack_into('<H',raw,0x1A,0x40);raw[0x40:0x46]=b'$PnP\x01\x02'
            struct.pack_into('<H',raw,0x5E,0x200);raw[0x49]=(-sum(raw[0x40:0x60]))&255
            code=bytes.fromhex('1E0E1FBE4002B9')+struct.pack('<H',len(node))+bytes.fromhex('FCF3A41F50B0008ED8FE06A00558CB')
            raw[0x200:0x200+len(code)]=code;raw[0x240:0x240+len(node)]=node;raw[-1]=(-sum(raw))&255
            c=card(1,device()+variable(0x300,0x320)+device()+fixed(0x350)+device(0x0700)+fixed(0x360),ldns=3)
            def configure(m):
                if present:m.cpu.mem_write(0xC8000,bytes(raw))
            m,bus=allocation_fixture(port,[c],configure=configure)
            assert bytes(m.cpu.mem_read(0x5A0,1))==bytes((int(present),))
            assert [c.registers[n][0x30] for n in range(3)]==[1,int(not present),1]
            assert io(c.registers[0])==(0x320 if present else 0x300) and io(c.registers[2])==0x360
            tested.append({'complete_report_present':present,'vector_calls':int(present),'actual_registers':rows([c])})
        results['M12']=tested
    if 'manual' in selected:
        tested=[]
        policy=bytearray(15);policy[2]=(1<<3)|(1<<1)
        struct.pack_into('<H',policy,11,(1<<6)|(1<<4))
        mem=lambda base:b'\x86\x09\0\0'+struct.pack('<II',base,0x4000)
        c=card(1,device()+b'\x2A\x02\x08'+device()+b'\x2A\x08\x08'+
               device()+mem(0xD0000)+device()+mem(0xD8000),ldns=4)
        m,bus=allocation_fixture(port,[c],policy)
        before=decode_saved(m)
        for released in (False,True):
            if released:
                m.call('pnp_finish_entry')
                # Real menu -> DMA1 Available -> D0000 Available -> F10/reset.
                m.ui([0x5000]*5+[9,0x5000,13,0x5000,0x4D00,27,
                     0x5000,0x5000,13]+[0x5000]*4+[0x4D00,0x4400,13])
                assert m.reset and not m.keys
                policy[2]&=~(1<<1);struct.pack_into('<H',policy,11,1<<6)
                m.call('settings_load');m.call('pnp_publish');assert m.call('pnp_module_install')
                m.call('pnp_prepare')
            assert [c.registers[n][0x30] for n in range(4)]==[int(released),0,int(released),0]
            if released:assert c.registers[0][0x74]==1
            saved=decode_saved(m)
            assert saved[0]['C_PNP']==policy
            assert saved[1]==before[1]
            for field in ('C_IDE','C_PORTS','C_CHIP'):assert saved[0][field]==before[0][field]
            tested.append({'released_DMA1_and_D0000':released,'later_DMA3_D8000_retained':True,'actual_registers':rows([c])})
        results['M13']=tested
    return results


def mp_negative(output='build/tests/pnp-runtime'):
    """Forward correction: ordinary legacy/NV6 settings, no MP PnP adoption."""
    class Ordinary(settings.Settings):
        def __init__(self):
            self.io=[]
            super().__init__('mp386',output)
        def inp(self,cpu,port,size,unused):
            self.io.append(('in',port,size))
            return super().inp(cpu,port,size,unused)
        def out(self,cpu,port,size,value,unused):
            self.io.append(('out',port,size))
            return super().out(cpu,port,size,value,unused)
    fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports']['mp386']
    legacy=(bytes.fromhex(fixture['cmos']),bytes(0x200)+bytes.fromhex(fixture['nvram_0200_023f'])+bytes(0xFDC0))
    previous=fixture['previous_nv6'];saved_cmos=bytearray(legacy[0]);saved_nv=bytearray(legacy[1])
    for at,value in previous['cmos_patch']:saved_cmos[at]=value
    saved_nv[0x200:0x240]=bytes.fromhex(previous['nvram_0200_023f'])
    policy=bytes.fromhex(previous['expected_PnP'])
    seeds=[('legacy',legacy),('previous_nv6',(bytes(saved_cmos),bytes(saved_nv)))]
    for name,persistent in seeds:
        m=Ordinary();m.cmos[:],m.nvram[:]=persistent
        m.put('C_PNP',b'\xC5'*15);m.put('U_PNP',b'\xDA'*15)
        before=m.snapshot();m.call('settings_load')
        assert m.snapshot()==before and not m.writes
        assert m.get('C_PNP',15)==b'\xC5'*15 and m.get('U_PNP',15)==b'\xDA'*15
        for field in ('C_IDE','C_PORTS','C_CHIP'):
            expected=bytes.fromhex(fixture['expected'][field]);assert m.get(field,len(expected))==expected,(name,field)
        m.draft();m.put('U_PNP',b'\xFF'*15)
        assert m.call('settings_save'),'Ordinary Save must ignore unsupported PnP drafts'
        decoded=decode_saved(m)
        assert decoded[0]['C_PNP']==(policy if name=='previous_nv6' else bytes(15))
        m.call('settings_load')
        for field in ('C_IDE','C_PORTS','C_CHIP'):
            expected=bytes.fromhex(fixture['expected'][field]);assert m.get(field,len(expected))==expected
        for owner in ('ide_settings_save','ports_settings_save','chipset_settings_save'):
            assert m.call(owner)
            assert decode_saved(m)[0]['C_PNP']==decoded[0]['C_PNP']
        assert m.get('C_PNP',15)==b'\xC5'*15 and m.get('U_PNP',15)==b'\xFF'*15
        assert bytes(m.nvram[0x240:0x300])==persistent[1][0x240:0x300]
        saved=m.snapshot();m.writes.clear();m.ui([0x5000]*7+[27,13])
        assert not m.reset and not m.writes and m.snapshot()==saved
        assert m.screen and all(b'Plug and Play' not in screen and b'Clear ESCD' not in screen for screen in m.screen)
        assert not any(port in (0x279,0xA79) for op,port,size in m.io)
    raw=m.image.read_bytes();assert b'$PnP' not in raw and not scan(raw)
    assert b'BAIPNP2' not in raw
    for label in ('pnp_real_entry','pnp_pm_entry','pnp_ui_draw','pnp_early','pnp_publish','pnp_settings_valid','settings_nv6_pnp_load'):
        for index,line in enumerate(m.listing.lines):
            if not re.search(r'(?<![\w.])'+label+r':\s*$',line):continue
            for following in m.listing.lines[index+1:]:
                if '%endif' in following or re.search(r'(?<![\w.])\b\w+:\s*$',following):break
                assert not re.match(r'\s*\d+\s+[0-9A-F]{8}\s+[0-9A-F\[]',following),('Unexpected MP PnP owner',label)
    spec=importlib.util.spec_from_file_location('pnp_mp_build',ROOT/'mp386/tools/build.py')
    owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner);owner.validate(m.image)
    fixed=json.loads((ROOT/'shared/tests/fixtures/pnp-placement-p1.json').read_text())['mp386_fixed_compatibility']
    assert hashlib.sha256(raw[fixed['start']:fixed['end']]).hexdigest()==fixed['sha256']
    return {'no_installation_controls_hooks_or_ISA_protocol':True,'actual_ordinary_Save_load_components':True,
            'legacy_and_previous_NV6_full_logical_compatibility':True,'inert_bytes_preserved_and_drafts_ignored':True,
            'actual_all_six_menu_pages_and_Discard':True,'fixed_video_normal_wrapper_lanes':True,
            'size':len(raw),'sum32':f'{sum(raw):08X}','sha256':hashlib.sha256(raw).hexdigest()}


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



def prepare_partial(port):
    output=OUTPUT+'/partial'
    if port=='presario-800':
        subprocess.run(['pwsh','-NoProfile','-File',str(ROOT/port/'tools/build.ps1'),
                        '-OutputDirectory',output,'-PnpPartialTest'],check=True,stdout=sys.stderr)
    elif port=='pb430':
        spec=importlib.util.spec_from_file_location('pnp_pb_partial_build',ROOT/port/'tools/build.py')
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
        owner.run(output,defines=('EMULATOR_PNP_PARTIAL',))
    else:build(port,output,('EMULATOR_PNP_PARTIAL',))
    machine=settings.Settings(port,output)
    assert not scan(machine.image.read_bytes())
    return {'installation_absent':True,'sha256':hashlib.sha256(machine.image.read_bytes()).hexdigest()}

def scan(raw):
    """No listing/symbol input: installation checks follow the public ROM contract."""
    return [raw[at:at+33] for at in range(0,len(raw)-32,16)
            if raw[at:at+4]==b'$PnP' and raw[at+4:at+6]==b'\x10\x21'
            and sum(raw[at:at+33])&255==0]


class Caller(settings.Settings):
    def __init__(self,port,mode='real',persistent=None,active=None,switches=0):
        assert port in PORTS,'MP has a separate no-PnP contract'
        self.switches=switches
        super().__init__(port,OUTPUT)
        fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
        self.cmos[:]=bytes.fromhex(fixture['cmos'])
        self.nvram[0x200:0x240]=bytes.fromhex(fixture['nvram_0200_023f'])
        if persistent is not None:self.cmos[:],self.nvram[:]=persistent
        self.call('settings_load')
        if persistent is None:
            # Author a zero-pause base with the real codec; keep legacy extensions.
            self.put('C_POST_DELAY',b'\0')
            self.call('settings_base_active_pack',DI=0x2000)
            base=bytes(self.cpu.mem_read(0x2000,8))
            for at,value in zip((0x10,*range(0x39,0x40)),base):self.cmos[at]=value
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
                       SS=self.stack,CS=self.code,ESP=self.stack_offset,EFLAGS=getattr(self,'caller_flags',0xED7))
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
        cpu.mem_write(0x10200,getattr(self,'return_opcode',b'\xF4'))
        before={name:cpu.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in registers}
        descriptor_state=tuple(cpu.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in ('CR0','GDTR','IDTR'))
        stopped=[]
        def stop(u,address,size,_):stopped.append(address);u.emu_stop()
        hook=cpu.hook_add(UC_HOOK_CODE,stop,None,0x10200,0x10200)
        self.public_active=True
        try:
            entry=struct.unpack_from('<H',self.header,13 if self.mode=='real' else 17)[0]
            if hasattr(self,'execute'):self.execute((self.code<<4)+entry,0x100000,1000000)
            else:cpu.emu_start((self.code<<4)+entry,0x100000,count=1000000)
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
        block=[];dependent=False;closed=False;starts=0
        while True:
            tag=node[at]
            if tag&128:
                length=int.from_bytes(node[at+1:at+3],'little');head=3
            else:length=tag&7;head=1
            end=at+head+length
            assert end<=len(node),(identity,at,tag,length,len(node))
            block.append((tag,node[at+head:end]))
            data=node[at+head:end]
            if tag in (0x30,0x31):
                assert len(blocks)==1 and not closed,'Dependent alternatives must be consecutive Starts and one final End'
                dependent=True;starts+=1
            elif tag==0x38:
                assert dependent and not closed,'Unexpected/repeated EndDependent'
                dependent=False;closed=True
            if tag==0x4B:assert int.from_bytes(data[:2],'little')<0x400,'FixedLocationIO reserved address bits'
            if tag==0x47:
                assert len(data)==7 and data[0] in (0,1)
                minimum=int.from_bytes(data[1:3],'little');maximum=int.from_bytes(data[3:5],'little')
                assert minimum==maximum and data[5]==0
                if minimum or data[6]:assert data[0]==1,'16-bit IO decode capability'
            at=end
            if tag==0x79:
                assert not dependent and closed==bool(starts),'Missing final EndDependent'
                break
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
    assert c.logical(0x38)==ord('B') and base[1]==ord('8') and base[2] in (5,6)
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
    result={mode:information_services_mode(port,mode) for mode in ('real','ss16','ss32')}
    if OUTPUT=='build/tests/pnp-runtime':result['actual_ISA_producer']=allocation_information(port)
    return result


def allocation_information(port):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    results=[]
    for count in (0,3):
        cards=[]
        for n,base in enumerate((0x3E0,0x388,0x330)[:count]):
            stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B'+struct.pack('<HB',base,8)+b'\x79\0'
            cards.append(Card(serial(b'\x41\xD0\xFF\xFF',n+1),stream))
        bus=Bus(cards,{0x203:'no-pair',0x207:'checksum'});bus.pause=False
        m=isa_machine(port,bus,OUTPUT);m.call('settings_load');m.call('pnp_publish')
        if port=='m919':m.cpu.mem_write(0x413,struct.pack('<H',m.base>>10))
        m.call('pnp_prepare');m.call('pnp_publish')
        entry,segment=struct.unpack('<HH',m.cpu.mem_read(m.base+0x338,4))
        source=(m.image.with_name('baios-presario800-vga60.bin') if port=='presario-800' else m.image).read_bytes()
        module_start=source.index(b'BAIPNP2\0')
        private_size=struct.unpack_from('<H',source,module_start+8)[0]
        private_base=(segment<<4)+(module_start if port=='m919' else 0)
        m.call('pnp_finish_entry')
        assert not any(m.cpu.mem_read(m.base+0x338,4))
        frozen=bytes(m.cpu.mem_read(0x4AD,83));expected=bytes((1,count))+struct.pack('<HH',0x20B if count else 0,0)
        for mode in ('real','ss16','ss32'):
            c=Caller(port,mode,m.snapshot());c.cpu.mem_write(0x4AD,frozen)
            def private_fetch(*args):raise AssertionError('Released private module fetched by public Fn40')
            guard=c.cpu.hook_add(UC_HOOK_CODE,private_fetch,None,private_base,private_base+private_size-1)
            c.cpu.mem_write(0x20100,b'\xCC'*12);before=c.snapshot();c.io.clear();c.writes.clear()
            try:assert c.far(0x40,[0x100,c.buffer,c.bios])==0
            finally:c.cpu.hook_del(guard)
            assert bytes(c.cpu.mem_read(0x20100,12))==expected+b'\xCC'*6
            assert not c.io and not c.writes and c.snapshot()==before
        results.append({'actual_CSN_count':count,'read_port':0x20B if count else 0,'released_before_public_calls':True})
    return {'real_ss16_ss32_exact_six_bytes':results,'no_public_ISA_or_storage_IO':True}


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
        assert int.from_bytes(c.cpu.mem_read(0x20108,2),'little')=={'m919':75,'mp386':42,'pb430':58,'presario-800':58}[port]
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


def dependent_node_groups(port):
    fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
    saved_ports=bytearray.fromhex(fixture['expected']['C_PORTS'])
    saved_dma=bool(bytes.fromhex(fixture['expected']['C_CHIP'])[22]&2) if port=='m919' else False
    producer=settings.Settings(port,OUTPUT)
    producer.cmos[:]=bytes.fromhex(fixture['cmos']);producer.nvram[0x200:0x240]=bytes.fromhex(fixture['nvram_0200_023f'])
    producer.call('settings_load');producer.draft();assert producer.call('settings_save')
    persistent=producer.snapshot()
    lpt=9 if port=='presario-800' else 10;fdc=lpt+1
    routes={8:(0,(1,3) if port=='m919' else (1,2,3,4)),
            lpt:(3,(2,3) if port=='m919' else (1,2,3)),fdc:(5,(1,))}
    if port!='presario-800':routes[9]=(1,(2,4) if port=='m919' else (1,2,3,4))
    if port in ('pb430','presario-800'):routes[len(inventory(port))-1]=(6,(1,))
    cases=[(pair,mode,dma,True) for pair in (0,1)
           for mode in (range(3) if port=='m919' else (saved_ports[4],))
           for dma in ((0,2) if port=='m919' else (0,))]
    cases.append((saved_ports[2],saved_ports[4],2*saved_dma,False))
    outputs=[]
    for pair,mode,dma,enabled in cases:
        active_ports=bytearray(saved_ports);active_ports[2]=pair;active_ports[4]=mode
        if not enabled:
            for at in (0,1,3,5,6):active_ports[at]=0
        def active(m):
            m.put('C_PORTS',active_ports)
            if port=='m919':
                chip=bytearray(m.get('C_CHIP',24));chip[22]=(chip[22]&~2)|dma;m.put('C_CHIP',chip)
        c=Caller(port,'ss32',persistent=persistent,active=active);maximum_seen=0;count=0
        for view,ports,dmachoice in ((1,active_ports,bool(dma)),(2,saved_ports,saved_dma)):
            for handle in range(len(inventory(port))):
                status,node,next_handle=get_node(c,handle,view);assert status==0
                identity,attrs,blocks=decode(node)
                possible=[]
                if handle in routes:
                    field,choices=routes[handle]
                    for value in choices:
                        candidate=bytearray(ports);candidate[field]=value
                        expected=resource_oracle(port,candidate,True,dma1=dmachoice)[handle]
                        possible.append((0x30,b''));possible.extend(expected)
                    possible.append((0x38,b''))
                possible.append((0x79,b'\0'))
                assert blocks[1]==possible,(port,view,handle,pair,mode,dma,enabled,blocks[1],possible)
                length=12+sum((3 if tag&128 else 1)+len(data) for block in blocks for tag,data in block)
                assert len(node)==length and node[2]==handle
                maximum_seen=max(maximum_seen,len(node));count+=1
        c.cpu.mem_write(0x20100,b'\xCC'*12)
        assert c.far(0,[0x100,c.buffer,0x108,c.buffer,c.bios])==0
        reported=int.from_bytes(c.cpu.mem_read(0x20108,2),'little')
        assert reported==maximum_seen==({'m919':75,'pb430':58,'presario-800':58}[port])
        outputs.append({'pair':pair,'LPT_mode':mode,'DMA_choice':dma,'enabled':enabled,
                        'actual_public01_nodes_and_views':count,'actual_maximum':reported})
    # Exercise real public static Set/reload for every advertised routing choice.
    # Disable peers first through that same API, so a serial choice does not
    # collide with the other UART's independently saved resource.
    c=Caller(port,'ss32');next_ports=bytearray(saved_ports);roundtrips=[]
    def wire(items):
        return b''.join(bytes((tag,))+(struct.pack('<H',len(data)) if tag&128 else b'')+data for tag,data in items)
    def save(handle,value):
        field,choices=routes[handle];candidate=bytearray(next_ports);candidate[field]=value
        expected=resource_oracle(port,candidate,True,dma1=saved_dma)[handle]
        current=get_node(c,handle,1)[1];node=bytearray(get_node(c,handle,2)[1]);encoded=wire(expected)
        node[12:12+len(encoded)]=encoded;c.cpu.mem_write(0x20200,bytes(node))
        assert c.far(2,[handle,0x200,c.buffer,2,c.bios])==0,(port,handle,value)
        next_ports[field]=value
        actual=get_node(c,handle,2)[1]
        assert decode(actual)[2][0]==expected+[(0x79,b'\0')]
        assert get_node(c,handle,1)[1]==current
        assert decode_saved(c)[0]['C_PORTS'][field]==value
        roundtrips.append((handle,value))
    for handle in routes:save(handle,0)
    for handle,(field,choices) in routes.items():
        for value in choices:save(handle,value)
        save(handle,0)
    return {'complete_public_possible_blocks':outputs,'all_public_static_route_roundtrips':roundtrips,
            'one_final_EndDependent_per_nonempty_set':True,'Current_unchanged_by_static_Set':True}


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
    return {'count':count,'maximum':maximum,'identities':ids,'three_descriptor_blocks':True,'complete_independent_nodes':complete_nodes(port),
            'dependent_groups':dependent_node_groups(port),**irq,**routing}


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
        assert base==migrated_base(port,bytes(saved[0][i] for i in [0x10,*range(0x39,0x40)]))
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


def saved_control_preservation(port,persistent):
    """A valid schema6 publication must retain explicit nondefault base controls."""
    ui=settings.ui_model(port,OUTPUT)
    ui.cmos[:],ui.nvram[:]=persistent
    ui.call('settings_load')
    old_base=bytes(ui.logical(i) for i in [0x10,*range(0x39,0x40)])
    ui.put('C_POST_DELAY',b'\x02') # Ten seconds, distinct from migrated five.
    if port=='m919':ui.put('C_VIDEO_ORDER',b'\x00') # ISA/PCI, distinct from PCI/ISA.
    ui.ui([0x4400,13])
    assert ui.reset
    expected=bytearray(old_base)
    expected[2]=6
    expected[7]=(old_base[7]&~0x38)|0x10
    expected[5]=-(ord('B')+sum(value for i,value in enumerate(expected) if i!=5))&255
    c=Caller(port,'ss32',ui.snapshot())
    before,base,payload=decode_saved(c)
    assert base==expected,(base.hex(),expected.hex())
    assert c.get('C_POST_DELAY')==b'\x02'
    if port=='m919':assert c.get('C_VIDEO_ORDER')==b'\x00'
    request=get_node(c,8,2)[1]
    c.cpu.mem_write(0x20200,request)
    prior=c.snapshot()
    assert c.far(2,[8,0x200,c.buffer,2,c.bios])==0
    after,new_base,new_payload=decode_saved(c)
    assert (after,new_base,new_payload)==(before,bytes(expected),payload)
    settings.check_mutation(port,prior,c.snapshot(),c.writes,'settings_save')
    loaded=settings.Settings(port,OUTPUT)
    loaded.cmos[:],loaded.nvram[:]=c.snapshot();loaded.call('settings_load')
    assert loaded.get('C_POST_DELAY')==b'\x02'
    if port=='m919':assert loaded.get('C_VIDEO_ORDER')==b'\x00'
    return {'schema':6,'POST_delay_seconds':10,'video_order':'ISA/PCI' if port=='m919' else 'not applicable',
            'complete_base_payload_unchanged':True,'actual_reader_reloaded':True}


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
    old_base=bytes(before[0][i] for i in [0x10,*range(0x39,0x40)])
    expected_base=migrated_base(port,old_base)
    assert base==expected_base,(port,base.hex(),bytes(expected_base).hex())
    assert bytes(c.cpu.mem_read(c.base,c.allocated))==draft
    settings.check_mutation(port,before,c.snapshot(),c.writes,'settings_save')
    reset=restarted(c)
    if port!='mp386':
        c.cpu.mem_write(0x20200,original)
        assert c.far(2,[8,0x200,c.buffer,3,c.bios])==0
        assert get_node(c,8,2)[1]==original
    # Real Setup Save/Discard changes the same record owner and pending policy.
    ui=settings.ui_model(port,OUTPUT)
    ui.cmos[:],ui.nvram[:]=c.snapshot()
    ui.call('settings_load')
    policy=settings.ui_checks(ui)
    controls_proof=saved_control_preservation(port,ui.snapshot())
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
            'manual_clear_recovery_preserved':True,'saved_schema6_controls':controls_proof,'reset':reset,'first_legacy_D2':recovery_proof,
            'invalid_nv6_next_fallback':invalid_next(port),'public_commit_contracts':public_commit_contracts(port),'causal_routing':causal_routing(port)}


def startup(port,cmos,nv,causal=False,pnp_bus=None,phases=(False,True),external_video=False,expect_first_active=True):
    """Real reset/application/publication, using the existing board hardware seams."""
    import importlib
    def cad_scratch(cpu):
        base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
        end=base+cpu.mem_read(base,1)[0]*1024
        for low,high in ((0x80000,0x80004),(0x6F00,0x7000)):
            assert high<=base or low>=end,('CAD stimulus overlaps advertised EBDA',base,end,low,high)
    sys.path.insert(0,str(ROOT/port/'tools'))
    image=ROOT/port/OUTPUT/('baios-presario800-system.rom' if port=='presario-800' else f'baios-{port}.bin')
    saved=bytearray.fromhex(cmos)
    # The legacy fixture captures settings, not a live century clock provider.
    saved[0x32]=0x20
    saved=bytes(saved)
    publication_listing=settings.Listing(image.with_suffix('.lst'))
    publication_begin=0xF0000+publication_listing.symbol('pnp_publish')
    publication_end=0xF0000+publication_listing.symbol('pnp_post_summary_complete')
    try:
        finish_entry=0xF0000+publication_listing.symbol('pnp_finish_entry')
        finish_atomic_end=0xF0000+publication_listing.symbol('.atomic_end','pnp_finish_entry')
    except (AssertionError,KeyError,StopIteration):finish_entry=finish_atomic_end=-1
    if port!='mp386':assert finish_entry>=0 and finish_atomic_end>=0,'Candidate lacks required finish observation sites'
    startup_end=(publication_end if port in ('presario-800','m919') else
                 0xF0000+publication_listing.symbol('int19'))
    progress={0xF0000+publication_listing.symbol(name):name for name in
              ('settings_load','chipset_apply','chipset_visible_ram_test','init_peripherals',
               'chipset_late_cache','pnp_publish','post_debug_summary')}
    if port=='presario-800':
        video_entry=0xF0000+next(int(match[1],16) for line in publication_listing.lines
            if 'call pnp_rom_enter' in line and
            (match:=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line)))
    else:video_entry=0xF0000+publication_listing.symbol('initialize_video')
    progress[video_entry]='initialize_video'
    snapshots=[]
    persistent_snapshots=[]
    boundaries=[]
    hardware=[]
    transition=[]
    journal_trace=[]
    finish_observations=[]
    original_memory=[]
    finishing=[False]
    finish_atomic=[False]
    finish_writes=[]
    finish_irq_frames=[]
    finish_irq_writes=[]
    finish_input_writes=[]
    notice_begin=publication_listing.row('post_error_notice')
    notice_end=publication_listing.row('post_notice_wait',notice_begin)
    clear_sites=[0xF0000+int(match[1],16) for line in publication_listing.lines[notice_begin:notice_end]
                 if 'mov [0x041A], ax' in line and
                 (match:=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line))]
    assert clear_sites,'No keyboard-queue clear found in the actual notice code'
    consume_site=0xF0000+publication_listing.symbol('.store_head','int16')
    irq_hooked=set()
    def finish_irq(cpu,address,size,unused):
        if not finish_atomic[0]:return
        ss=cpu.reg_read(x.UC_X86_REG_SS);sp=cpu.reg_read(x.UC_X86_REG_SP)
        ip,cs,_=struct.unpack('<HHH',cpu.mem_read((ss<<4)+sp,6))
        frame=(ss,(sp+6)&0xFFFF,(cs<<4)+ip)
        finish_irq_frames.append(frame)
        def returned(cpu,address,size,unused):
            if finish_irq_frames and finish_irq_frames[-1]==frame and (cpu.reg_read(x.UC_X86_REG_SS),cpu.reg_read(x.UC_X86_REG_SP),address)==frame:
                finish_irq_frames.pop()
        cpu.hook_add(UC_HOOK_CODE,returned,None,frame[2],frame[2])
    placement_observations=[]
    module_live=[None]
    live_journal=[None]
    private_fetches=[0]
    early_fetches=[0]
    before_video=[True]
    invoke_entry=0xF0000+publication_listing.symbol('pnp_post_invoke') if pnp_bus is not None else -1
    if pnp_bus is not None:
        physical=(image.with_name('baios-presario800-vga60.bin') if port=='presario-800' else image).read_bytes()
        source_at=(physical.index(b'BAIPNP2\0') if port=='m919' else 0x8000 if port=='pb430' else 0xC000)
        module_size=struct.unpack_from('<H',physical,source_at+8)[0]
        if port=='presario-800':
            from shared.tools.post_module import inspect_bank
            source_bank=physical[source_at:source_at+0x4000]
            expected_module,module_info=inspect_bank(source_bank)
        else:expected_module=physical[source_at:source_at+module_size]
    def private_fetch(cpu,address,size,unused):
        if module_live[0] is not None and module_live[0]<=address<module_live[0]+module_size:
            private_fetches[0]+=1
            if before_video[0]:early_fetches[0]+=1
    bank_copied=[]
    bank_copy_entry=(0xF0000+publication_listing.symbol('.checksum','pnp_module_install') if port=='presario-800' and pnp_bus is not None else -1)
    finish_address=0xE0000+publication_listing.symbol('pnp_finish') if pnp_bus is not None and port=='m919' else -1
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
        if pnp_bus is not None and hasattr(pnp_bus,'after_post'):pnp_bus.after_post()
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
    def phase_complete():
        if pnp_bus is not None and hasattr(pnp_bus,'after_each_post'):
            listing=m.pnp_listing if port=='m919' else m.listing if port=='pb430' else publication_listing
            pnp_bus.after_each_post(m,m.cpu if port!='m919' else cpu,listing)
    escape=[False]
    ram_entry=0xF0000+publication_listing.symbol('chipset_visible_ram_test')
    keyboard_boundary=0xF0000+publication_listing.symbol('post_keyboard_wait')
    notice_entry=0xF0000+publication_listing.symbol('post_notice_wait')
    settings_entry=0xF0000+publication_listing.symbol('settings_load')
    notice_acknowledged=[False]
    active=[False]
    writes=[]
    def memory(cpu,access,address,size,value,unused):
        if active[0] and 0x400<=address<0x510:
            writes.extend(range(address,address+size))
        if finish_atomic[0] and 0x400<=address<0x510:
            # Incomplete-publication notices run real timer/keyboard IRQs.
            pc=cpu.reg_read(x.UC_X86_REG_CS)*16+cpu.reg_read(x.UC_X86_REG_IP)
            if not finish_irq_frames and pc in (*clear_sites,consume_site):
                assert address==0x41A and size==2
                if pc in clear_sites:expected=int.from_bytes(cpu.mem_read(0x41C,2),'little')
                else:
                    expected=int.from_bytes(cpu.mem_read(0x41A,2),'little')+2
                    if expected==0x3E:expected=0x1E
                    assert cpu.reg_read(x.UC_X86_REG_DS)==0x40
                assert value==expected
                finish_input_writes.extend(range(address,address+size))
            else:(finish_irq_writes if finish_irq_frames else finish_writes).extend(range(address,address+size))
    def close_publication():
        active[0]=False
        assert set(writes)==set(range(0x4AD,0x500)),('snapshot bounds',writes)
        boundaries.append([min(writes),max(writes)])
    def observe(cpu,address,listing):
        if pnp_bus is not None and getattr(pnp_bus,'runtime_continue',False):return
        if address==settings_entry:
            notice_acknowledged[0]=False
        if pnp_bus is not None and port in ('pb430','presario-800') and address==notice_entry and not notice_acknowledged[0]:
            assert 'PnP incomplete; rebuild kept.' in m.console[-400:] and m.console.endswith(
                'Press any key to continue or Delete for Setup.\r\n'),('unexpected POST notice',m.console[-400:])
            m.script.append(28)
            notice_acknowledged[0]=True
        if pnp_bus is not None and hasattr(pnp_bus,'observe_startup'):
            pnp_bus.observe_startup(m,cpu,address,listing)
        if pnp_bus is not None and (address in progress or address==finish_address):
            base=cpu.reg_read(x.UC_X86_REG_FS)<<4
            control=bytes(cpu.mem_read(base+0x320,32))
            journal_trace.append((progress.get(address,'actual_private_finish'),control.hex()))
            print('JOURNAL',journal_trace[-1],file=sys.stderr,flush=True)
        if address==ram_entry:escape[0]=False
        if port!='m919' and address==keyboard_boundary and not escape[0]:
            base=cpu.reg_read(x.UC_X86_REG_FS)<<4
            if bytes(cpu.mem_read(base+0x50,1))==b'\x01':
                m.pending.append(1) # Real external Escape, consumed by IRQ1.
                escape[0]=True
        if address in progress:print(port,progress[address],file=sys.stderr,flush=True)
        if address==bank_copy_entry and cpu.reg_read(x.UC_X86_REG_CX)==0x4000:
            copied=cpu.reg_read(x.UC_X86_REG_ES)<<4
            assert bytes(cpu.mem_read(copied,0x4000))==source_bank,'Actual AH87 output differs from final serialized bank'
            bank_copied.append(copied)
        if pnp_bus is not None and address==invoke_entry and module_live[0] is None:
            base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
            entry,segment=struct.unpack('<HH',cpu.mem_read(base+0x338,4))
            module_live[0]=(segment<<4)+(source_at if port=='m919' else 0)
            assert bytes(cpu.mem_read(module_live[0],len(expected_module)))==expected_module
        if pnp_bus is not None and address==video_entry:
            before_video[0]=False
            base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
            entry,segment=struct.unpack('<HH',cpu.mem_read(base+0x338,4))
            module_live[0]=(segment<<4)+(source_at if port=='m919' else 0)
            assert bytes(cpu.mem_read(module_live[0],len(expected_module)))==expected_module
            expected=(expect_first_active(len(placement_observations)) if callable(expect_first_active) else expect_first_active)
            assert all(bool(card.registers[0][0x30])==expected for card in pnp_bus.cards),'Assignment/policy must precede video'
            root=int.from_bytes(cpu.mem_read(base+0x330,4),'little')
            root_data=bytes(cpu.mem_read(root,32))
            node=int.from_bytes(root_data[8:12],'little');stored=0;seen=set()
            while node:
                assert node not in seen;seen.add(node);stored+=1
                node=int.from_bytes(cpu.mem_read(node,4),'little')
            cursor,end=struct.unpack('<II',cpu.mem_read(base+0x320,8))
            spans=[(cursor,end)]
            if port=='pb430':spans=[(lo,hi) for lo,hi in ((cursor,min(end,0x20000)),(max(cursor,0x40000),end)) if lo<hi]
            live_journal[0]=[(lo,bytes(cpu.mem_read(lo,hi-lo))) for lo,hi in spans]
            placement_observations.append({'actual_module_linear':module_live[0],'complete_source_bytes_equal':True,
                'required_active_before_video':expected,'external_video':external_video,
                'original_KiB':int.from_bytes(cpu.mem_read(base+0x328,2),'little'),
                'journal_cursor':int.from_bytes(cpu.mem_read(base+0x320,4),'little'),
                'actual_LDN_count':int.from_bytes(root_data[24:28],'little'),'stored_LDN_count':stored,
                'reconstruction_status':root_data[19],'actual_private_fetches_before_video':early_fetches[0]})
        if pnp_bus is not None and address==finish_entry:
            assert module_live[0] is not None
            assert bytes(cpu.mem_read(module_live[0],len(expected_module)))==expected_module,'Returning consumers/RAM/final writers damaged code'
            assert all(bytes(cpu.mem_read(lo,len(data)))==data for lo,data in live_journal[0]),'Returning consumers/RAM/final writers damaged live journal'
        if address==publication_begin:
            active[0]=True;writes.clear()
            if pnp_bus is not None:
                base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
                if not any(cpu.mem_read(base+0x330,4)):
                    module_live[0]=None;before_video[0]=True;early_fetches[0]=0
            if not original_memory:
                original_memory.append(int.from_bytes(cpu.mem_read(0x413,2),'little'))
        if address==finish_entry and active[0]:
            close_publication()
            finishing[0]=finish_atomic[0]=True;finish_writes.clear();finish_irq_writes.clear();finish_input_writes.clear()
            assert not finish_irq_frames
            if id(cpu) not in irq_hooked:
                irq_hooked.add(id(cpu))
                for label in ('int08','int09'):
                    entry=0xF0000+listing.symbol(label)
                    cpu.hook_add(UC_HOOK_CODE,finish_irq,None,entry,entry)
        if address==finish_atomic_end:
            finish_atomic[0]=False
        if address==publication_end:
            if active[0]:close_publication()
            if finishing[0]:
                finishing[0]=False
                assert not finish_irq_frames,'Finish returned inside an IRQ frame'
                allowed={0x40E,0x40F,0x413,0x414,0x4FB,0x4FC,0x4FD,0x4EE if port=='m919' else 0x4E7}
                assert set(finish_writes)<=allowed,('finish bounds',finish_writes)
                assert {0x4FB,0x4FC,0x4FD}<=set(finish_writes)
                base=cpu.reg_read(x.UC_X86_REG_FS)<<4
                assert not any(cpu.mem_read(base+0x320,8))
                assert not any(cpu.mem_read(base+0x32C,8))
                assert not any(cpu.mem_read(base+0x338,4))
                relative=int.from_bytes(cpu.mem_read(base+0x334,4),'little')
                runtime=(bool(relative) and bytes(cpu.mem_read(base+relative,4))==b'PNP3')
                ceiling=base>>10 if runtime else original_memory[0]
                assert int.from_bytes(cpu.mem_read(0x413,2),'little')==ceiling
                finish_observations.append({'writes':sorted(set(finish_writes)),
                    'actual_IRQ_writes':sorted(set(finish_irq_writes)),
                    'actual_notice_input_writes':sorted(set(finish_input_writes)),
                    'restored_conventional_KiB':ceiling,'original_conventional_KiB':original_memory[0],
                    'runtime_published':runtime,'advertised_runtime_KiB':cpu.mem_read(base,1)[0],
                    'released_control':True,'ISA':bytes(cpu.mem_read(0x4FB,3)).hex()})
            if port=='presario-800':
                m.base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
                m.segment=m.base>>4
            snapshots.append(bytes(cpu.mem_read(0x4AD,83)).hex())
            persistent_snapshots.append((bytes(nv_cmos) if port=='m919' else bytes(m.cmos)).hex())
            if causal or pnp_bus is not None:hardware.append(hardware_state())
        if address==startup_end and port!='presario-800':
            cpu.emu_stop()
    startup_budget=50000000+1024*sum(len(card.registers)**2 for card in getattr(pnp_bus,'cards',()))
    if port=='mp386':
        fixture=importlib.import_module('fixture')
        m=fixture.Tiger(image,cache=False)
        m.cmos[:]=saved
        if causal:m.disk_switches=0x42
        m.nvram[0x200:0x240]=bytes.fromhex(nv)
        listing=m.listing
        m.cpu.hook_add(UC_HOOK_MEM_WRITE,memory,begin=0x400,end=0x50F)
        m.code_observer=lambda mm,address:observe(mm.cpu,address,listing)
        for warm in phases:
            if warm:
                m.sys_flag=4
                m.seed_physical(0,0x472,b'\x34\x12')
            try:m.boot(warm=warm,count=50000000)
            except AssertionError as error:
                assert error.args[0][0]=='no signed boot' and len(snapshots)==1+warm,str(error)
    elif port=='pb430':
        timing=importlib.import_module('test-timing-setup')
        class Hardware(timing.ACC):
            def __init__(self,image,payload=None):
                super().__init__(image,payload,isa_bus=pnp_bus,external_video=external_video)
                if pnp_bus is not None and hasattr(pnp_bus,'video_rom'):
                    self.cpu.mem_write(0xC0000,pnp_bus.video_rom)
            def interrupt(self,cpu,vector,unused):
                if vector==0x10 and getattr(pnp_bus,'execute_video_interrupt',False):
                    return importlib.import_module('core_proof').rtc.Clock.interrupt(self,cpu,vector,unused)
                return super().interrupt(cpu,vector,unused)
            def code(self,cpu,address,size,unused):
                if self.starting and address==0xC0003 and pnp_bus is not None and hasattr(pnp_bus,'video_rom'):
                    # Execute the authored external device's instructions. The
                    # ordinary retained-ROM seam remains opaque elsewhere.
                    if self.code_observer:self.code_observer(self,address)
                    return
                return super().code(cpu,address,size,unused)
        m=timing.model(image,cls=Hardware)
        m.cmos[:]=saved
        m.stop_address=startup_end
        m.cpu.hook_add(UC_HOOK_MEM_WRITE,memory,begin=0x400,end=0x50F)
        if pnp_bus is not None:m.cpu.hook_add(UC_HOOK_CODE,private_fetch,None,0x10000,0x9FFFF)
        m.code_observer=lambda mm,address:observe(mm.cpu,address,m.listing)
        m.cpu.hook_add(UC_HOOK_CODE,lambda u,a,z,v:observe(u,a,m.listing),None,ram_entry,ram_entry)
        for warm in phases:
            if not warm:m.cold_boot();between()
            else:
                if getattr(pnp_bus,'actual_cad',False):
                    cad_scratch(m.cpu)
                    m.irq_scans((0x1D,0x38,0xE0,0x53),guest=0x80000)
                    assert m.reset_pending,'Actual Ctrl+Alt+Del did not produce a reset pulse'
                    m.complete_reset(count=300000000)
                    pnp_bus.actual_cad=False
                    phase_complete()
                    continue
                m.sys_flag=4
                m.cpu.mem_write(0x472,b'\x34\x12')
                m.reset_pending=True
                m.complete_reset(count=300000000)
            phase_complete()
    elif port=='presario-800':
        os.environ['BAIOS_BUILD_DIRECTORY']=OUTPUT
        chipset=importlib.import_module('test-chipset')
        from shared.tools.post_fixture import bind_rtc_candidate
        bind_rtc_candidate(chipset.setup.rtc,image)
        chipset.BUILD=image.parent
        m=chipset.setup.production_post_model(peripherals=True,isa_bus=pnp_bus)
        if pnp_bus is not None:m.startup_native_owners=('chipset_visible_ram_test',)
        m.cmos[:]=saved
        m.publish_peripherals=True
        m.startup_observer=lambda mm,name:escape.__setitem__(0,False) if name=='chipset_visible_ram_test' else None
        listing=settings.Listing(image.with_suffix('.lst'))
        m.cpu.hook_add(UC_HOOK_MEM_WRITE,memory,begin=0x400,end=0x50F)
        if pnp_bus is not None:m.cpu.hook_add(UC_HOOK_CODE,private_fetch,None,0x10000,0x9FFFF)
        begin=0xF0000+listing.symbol('pnp_publish')
        end=0xF0000+listing.symbol('pnp_post_summary_complete')
        for address in {begin,end,startup_end,keyboard_boundary,notice_entry,finish_entry,video_entry,invoke_entry,bank_copy_entry}:
            if address<0:continue
            m.cpu.hook_add(UC_HOOK_CODE,lambda u,a,z,v:observe(u,a,listing),None,address,address)
        for warm in phases:
            if not warm:
                m.startup(reset=True,production_controls=True,through_publication=True);between()
            else:
                if getattr(pnp_bus,'actual_cad',False):
                    cad_scratch(m.cpu)
                    m.scans((0x1D,0x38,0xE0,0x53),guest=0x80000)
                    assert m.warm,'Actual Ctrl+Alt+Del did not reach warm entry'
                    pnp_bus.actual_cad=False
                m.warm=True
                m.startup(production_controls=True,through_publication=True)
            phase_complete()
    else:
        cache=importlib.import_module('cache_proof')
        geometry=importlib.import_module('geometry_proof')
        if causal or pnp_bus is not None:
            sio=importlib.import_module('sio_proof')
        class Hardware(cache.POSTHardware):
            def __init__(self,**kwargs):
                super().__init__(**kwargs)
                if causal or pnp_bus is not None:self.routing=sio.SIO(kib=64,ram=4,kind='real')
            def interrupt(self,cpu,number):
                if number==0x10 and getattr(pnp_bus,'execute_video_interrupt',False):
                    return self.cpu_interrupt(cpu,number)
                return super().interrupt(cpu,number)
            def prepare(self,cpu):
                super().prepare(cpu)
                if pnp_bus is not None and hasattr(pnp_bus,'video_rom'):
                    cpu.mem_write(0xC0000,pnp_bus.video_rom)
            def pci_read(self,address,port,size):
                if pnp_bus is not None and hasattr(pnp_bus,'video_rom') and not getattr(pnp_bus,'pci_video',False) and (address>>8)&0xFFFF==0x60:
                    return (1<<(size*8))-1 # Authored ISA display, PCI display absent.
                if pnp_bus is not None and hasattr(pnp_bus,'pci') and (address>>8)&0xFFFF in pnp_bus.pci.endpoints:
                    return pnp_bus.pci.read(address,port,size)
                return super().pci_read(address,port,size)
            def pci_write(self,address,port,size,value):
                if pnp_bus is not None and hasattr(pnp_bus,'pci') and (address>>8)&0xFFFF in pnp_bus.pci.endpoints:
                    return pnp_bus.pci.write(address,port,size,value)
                return super().pci_write(address,port,size,value)
            def incoming(self,cpu,port,size):
                if pnp_bus is not None:
                    value=pnp_bus.input(port,size)
                    if value is not None:return value
                if (causal or pnp_bus is not None) and (port in (0x108,0x109) or self.routing.uart(port) or self.routing.parallel(port)):
                    return self.routing.incoming(cpu,port,size)
                return super().incoming(cpu,port,size)
            def outgoing(self,cpu,port,size,value):
                if pnp_bus is not None and pnp_bus.output(port,size,value):return
                if (causal or pnp_bus is not None) and (port in (0x108,0x109) or self.routing.uart(port) or self.routing.parallel(port)):
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
        for warm in phases:
            m.continuing=False
            m.escaped=False
            m.defaults_requested=False
            if warm:
                if getattr(pnp_bus,'runtime_reset_owners',False):m.reset_requests.clear()
                if getattr(pnp_bus,'actual_cad',False):
                    cad_scratch(cpu)
                    m.queue.extend((0x1D,0x38,0xE0,0x53))
                    cpu.mem_write(0x80000,b'\xFB\xF4\xEB\xFD')
                    for reg,value in dict(CS=0x8000,IP=0,SS=0,SP=0x7000,EFLAGS=0x202).items():
                        cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
                    step.execute(0x80000,0x80004,2000000)
                    assert m.reset_requests,'Actual Ctrl+Alt+Del did not produce KBC reset'
                    pnp_bus.actual_cad=False
                elif getattr(pnp_bus,'runtime_reset_owners',False):
                    for reg,value in dict(CS=0xF000,SS=0,SP=0x7000,EFLAGS=0x202).items():
                        cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
                    step.execute(0xF0000+m.pnp_listing.symbol('warm_reset'),0xFFFFF,2000000)
                    assert m.reset_requests,'Actual warm_reset did not produce a KBC reset'
                else:m.write(0x472,2,0x1234)
            _,fixture=geometry.mapped(m.modules,expected=4,memory=m,rom_image=image)
            cpu,m,listing,state,nv_cmos,step=fixture
            if warm and getattr(pnp_bus,'continue_setup_reset',False):m.reset_requests.clear()
            m.pnp_execute=step.execute
            m.state=state
            cpu.hook_add(UC_HOOK_MEM_WRITE,memory,begin=0x400,end=0x50F)
            if pnp_bus is not None:cpu.hook_add(UC_HOOK_CODE,private_fetch,None,0xE0000,0xEFFFF)
            m.continuing=True
            step.execute(0xF0000+cpu.reg_read(x.UC_X86_REG_IP),0xFFFFF,startup_budget)
            m.initial_cmos=bytes(nv_cmos)
            if getattr(pnp_bus,'continue_setup_reset',False):
                # The external 8042 reset pulse stopped the current CPU. Reuse
                # the normal physical-reset constructor with retained DRAM/RTC;
                # no firmware startup or Setup continuation is substituted.
                while m.reset_requests:
                    pnp_bus.setup_reset_pulses.extend(m.reset_requests)
                    assert len(pnp_bus.setup_reset_pulses)==1,'Unexpected repeated Setup reset'
                    m.reset_requests.clear()
                    m.continuing=False
                    _,fixture=geometry.mapped(m.modules,expected=4,memory=m,rom_image=image)
                    cpu,m,listing,state,nv_cmos,step=fixture
                    m.pnp_execute=step.execute;m.state=state
                    cpu.hook_add(UC_HOOK_MEM_WRITE,memory,begin=0x400,end=0x50F)
                    cpu.hook_add(UC_HOOK_CODE,private_fetch,None,0xE0000,0xEFFFF)
                    m.continuing=True
                    step.execute(0xF0000+cpu.reg_read(x.UC_X86_REG_IP),0xFFFFF,startup_budget)
                    m.initial_cmos=bytes(nv_cmos)
            if not warm:between()
            phase_complete()
    assert len(snapshots)==len(phases),(port,len(snapshots),
        {name:cpu.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in ('CS','IP','SS','SP')} if port=='m919' else {},
        getattr(m,'stop',None),getattr(m,'reset_requests',None))
    final_cmos=bytes(nv_cmos) if port=='m919' else bytes(m.cmos)
    final_nv=bytes(m.nvram) if port=='mp386' else bytes(0x10000)
    return {'snapshots':snapshots,'persistent_snapshots':persistent_snapshots,'publication_boundaries':boundaries,'cold_warm_actual_startup':True,
            'cmos':final_cmos.hex(),'nvram_0200_023f':final_nv[0x200:0x240].hex(),
            'hardware':hardware,'static_transition':transition,
            'ISA_registers':[{str(n):dict(row) for n,row in card.registers.items()} for card in pnp_bus.cards] if pnp_bus else [],
            'journal_trace':journal_trace,'finish_observations':finish_observations,
            'placement_observations':placement_observations,'private_code_fetches':private_fetches[0],
            'actual_native_startup_hops':getattr(m,'startup_hops',[]),'actual_serialized_AH87_source_copies':bank_copied,'M919_startup_instruction_budget':startup_budget if port=='m919' else None}


def allocation_startup(port,external_video=False,phases=(False,True),saved_setup=None):
    """Portable actual reset/lifetime proof; use opaque external cache/video devices."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    m=settings.Settings(port,OUTPUT)
    if saved_setup is None:
        m.call('settings_load');m.call('setup_defaults');m.draft();m.put('U_POST_DELAY',b'\0')
        policy=bytearray(15);struct.pack_into('<H',policy,0,1<<15)
        struct.pack_into('<HH',policy,3,0x350,8);policy[14]=1
        m.put('U_PNP',policy);assert m.call('settings_save')
    else:
        m.cmos[:]=bytes.fromhex(saved_setup['saved_cmos'])
        m.nvram[0x200:0x240]=bytes.fromhex(saved_setup['saved_nv'])
        policy=decode_saved(m)[0]['C_PNP']
    before=decode_saved(m)
    stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B\xE0\x03\x08\x22\0\x08\x2A\x02\x08\x79\0'
    bus=Bus([Card(serial(b'\x41\xD0\xFF\xFF',1),stream,powerup_active=True)]);bus.pause=False
    result=startup(port,bytes(m.cmos).hex(),bytes(m.nvram[0x200:0x240]).hex(),pnp_bus=bus,
                   phases=phases,external_video=external_video)
    assert all(bytes.fromhex(row)[78:81]==b'\x01\x0B\x02' for row in result['snapshots'])
    assert len(result['finish_observations'])==len(phases)
    assert len(result['placement_observations'])==len(phases) and result['private_code_fetches']>0
    m.cmos[:]=bytes.fromhex(result['cmos'])
    expected=bytearray(policy);expected[14]=0
    after=decode_saved(m)
    assert after[0]['C_PNP']==expected
    assert after[1]==before[1]
    for field in ('C_IDE','C_PORTS','C_CHIP'):assert after[0][field]==before[0][field]
    assert bus.cards[0].registers[0][0x30]==1
    result['complete_saved_policy_except_verified_Clear_unchanged']=True
    result['source_image_sha256']=hashlib.sha256(m.image.read_bytes()).hexdigest()
    return result


def pci_manual_oracle(reserved):
    """Independent complete decoded sets; no candidate ROM ledger reads."""
    claims=[]
    # Explicit saved default peripheral selectors used by this test producer.
    for n,node in enumerate(resource_oracle('m919',bytes((1,2,1,2,0,1,0,1)),True)):
        for tag,data in node:
            if tag==0x4B:
                base,length=struct.unpack('<HB',data)
                addresses={a for a in range(65536) if ((a-base)&1023)<length}
            elif tag==0x47:
                info,base,maximum,alignment,length=struct.unpack('<BHHBB',data)
                assert base==maximum and info==1
                addresses=set(range(base,base+length))
            else:continue
            if addresses:claims.append((f'onboard_node_{n}',addresses))
    claims.append(('required_ISA',set(range(0xC010,0xC020))))
    if reserved:
        claims.extend([('manual_last_byte',{0xC03F}),('later_manual_window',set(range(0xC050,0xC060)))])
    candidates=[]
    for base in range(0xC000,0x10000,16):
        interval=set(range(base,base+16))
        owners=[name for name,addresses in claims if interval&addresses]
        candidates.append({'base':base,'conflicting_independent_owners':owners})
        if not owners:return base,candidates
    raise AssertionError('Authored PCI case has no feasible interval')


def runtime_rom(number,status=0x120,unknown=True,bcv=0x200,disconnect=0x220,bev=0,indicators=4,counter=False):
    """Authored external ROM, independent wire fields and actual x86 entry."""
    raw=bytearray(2048);raw[:3]=b'\x55\xAA\x04'
    at=0x600+number*16
    code=bytes.fromhex('1E5031C08ED858A3')+struct.pack('<H',at)
    for opcode,off in ((b'\x89\x1E',2),(b'\x89\x16',4),(b'\x8C\x06',6),(b'\x89\x3E',8)):
        code+=opcode+struct.pack('<H',at+off)
    if counter:code+=b'\xFF\x06'+struct.pack('<H',0x680+number*2)
    code+=b'\xB8'+struct.pack('<H',status)+b'\x1F\xCB'
    raw[3:6]=b'\xE9'+struct.pack('<h',0x100-6)
    raw[0x100:0x100+len(code)]=code
    struct.pack_into('<H',raw,0x1A,0x40 if unknown else 0x60)
    if unknown:
        raw[0x40:0x46]=b'TEST\x07\x01';struct.pack_into('<H',raw,0x46,0x60)
        raw[0x49]=(-sum(raw[0x40:0x50]))&255
    raw[0x60:0x66]=b'$PnP\x01\x02';raw[0x6A:0x6E]=b'\x41\xD0\x05\0'
    raw[0x75]=indicators;struct.pack_into('<HHH',raw,0x76,bcv,disconnect,bev)
    raw[0x69]=(-sum(raw[0x60:0x80]))&255
    for off in (bcv,disconnect,bev):
        if off:raw[off]=0xCB
    raw[-1]=(-sum(raw))&255
    return bytes(raw)


def runtime_promotion(port):
    """Actual allocation/discovery/private finish -> resident overlap copy."""
    from shared.tools.isa_pnp_proof import Bus
    m=isa_machine(port,Bus(),OUTPUT)
    for n,seg in enumerate((0xC800,0xD000)):
        m.cpu.mem_write(seg<<4,runtime_rom(n))
    m.call('settings_load');m.call('setup_defaults');m.draft();m.put('U_POST_DELAY',b'\0')
    policy=bytearray(15);policy[14]=1;m.put('U_PNP',policy);assert m.call('settings_save')
    if port!='m919':m.call('pnp_journal_release') # Constructor-only copied bank.
    m.call('pnp_early')
    m.call('option_rom_discovery')
    for n in range(2):
        ax,bx,dx,es,di=struct.unpack('<5H',m.cpu.mem_read(0x600+n*16,10))
        assert (ax,bx,dx,es,di)==(0xFFFF,0xFFFF,0xFFFF,0xF000,m.listing.symbol('pnp_installation')),(n,ax,bx,dx,es,di)
    old=m.base;prefix=m.allocated
    m.cpu.mem_write(old+0x27A,b'\x03\x02\x02')
    m.cpu.mem_write(0x104,struct.pack('<HH',0xE0,(old>>4)+0x20))
    m.cpu.mem_write(0x118,struct.pack('<HH',0x5678,0x1234))
    m.cpu.mem_write(0x475,b'\x03');m.cpu.mem_write(0x4C,struct.pack('<HH',0x1234,0xABCD))
    old_prefix=bytes(m.cpu.mem_read(old,prefix));original_kib=int.from_bytes(m.cpu.mem_read(old+0x328,2),'little')
    source_start,source_end=struct.unpack('<II',m.cpu.mem_read(old+0x320,8))
    resident=0xF0000+m.listing.symbol('pnp_promote_runtime')
    entered=[];writes=[]
    def code(cpu,address,size,unused):
        entered.append((cpu.reg_read(x.UC_X86_REG_CS),address))
    def write(cpu,access,address,size,value,unused):
        if old+0x320<=address and address+size<=old+0x33C:return
        if ((address<old+prefix and address+size>old) or
            (address<source_end and address+size>source_start)):
            writes.append((bool(entered),address,size))
    a=m.cpu.hook_add(UC_HOOK_CODE,code,None,resident,resident)
    b=m.cpu.hook_add(UC_HOOK_MEM_WRITE,write)
    try:m.call('pnp_finish_entry')
    finally:m.cpu.hook_del(a);m.cpu.hook_del(b)
    base=int.from_bytes(m.cpu.mem_read(0x40E,2),'little')<<4
    size=m.cpu.mem_read(base,1)[0]*1024
    assert base<old and base+size==old+prefix,(port,hex(base),size,hex(old),prefix,
        bytes(m.cpu.mem_read(old+0x320,28)).hex(),m.get('C_ERROR').hex())
    assert entered and all(cs==0xF000 for cs,address in entered)
    assert all(after for after,address,size in writes),'Overlapping write preceded resident return'
    relative=int.from_bytes(m.cpu.mem_read(base+0x334,4),'little')
    assert relative==prefix
    header=bytes(m.cpu.mem_read(base+relative,60))
    assert header[:4]==b'PNP3' and int.from_bytes(header[4:8],'little')==2
    records=bytes(m.cpu.mem_read(base+relative+60,48))
    assert [struct.unpack_from('<HH',records,i*24) for i in range(2)]==[(0xC800,0x60),(0xD000,0x60)]
    assert all(struct.unpack_from('<H',records,i*24+10)[0]==0x120 for i in range(2))
    assert m.cpu.mem_read(base+0x27A,3)==b'\x03\x02\x02'
    assert m.cpu.mem_read(0x104,4)==struct.pack('<HH',0xE0,(base>>4)+0x20)
    assert m.cpu.mem_read(0x118,4)==b'\x78\x56\x34\x12'
    assert m.cpu.mem_read(0x475,1)==b'\x03' and m.cpu.mem_read(0x4C,4)==b'\x34\x12\xCD\xAB'
    assert int.from_bytes(m.cpu.mem_read(0x413,2),'little')==base>>10
    assert not any(m.cpu.mem_read(base+0x338,4))
    assert m.call('check_disk_buffer',EAX=base+prefix-1,EDX=base+prefix+1)==False
    assert m.call('check_disk_buffer',EAX=base+size,EDX=base+size+512)
    m.base=base;m.allocated=size;m.call('settings_load')
    assert m.get('C_PNP',15)[14]==0
    return {'actual_early_discovery_finish_promotion':True,'original_KiB':original_kib,'old_EBDA':old,'new_EBDA':base,
            'prefix_bytes':prefix,'advertised_bytes':size,'complete_records':records.hex(),
            'resident_before_overlap':entered,'overlapping_writes':len(writes),'native_only_FDPT_rebase':True,
            'external_disk_count_hook_and_APM_preserved':True,'actual_tail_buffer_guard':True,'Clear_retired_after_publication':True}


def runtime_assemble(port,name,source):
    """Only authored external devices/loaders, never a substituted BIOS hop."""
    import shutil
    work=ROOT/port/OUTPUT/'runtime-fixtures';work.mkdir(parents=True,exist_ok=True)
    asm=work/(name+'.asm');binary=asm.with_suffix('.bin');asm.write_text(source)
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    subprocess.run([nasm,'-f','bin','-o',str(binary),str(asm)],check=True)
    return binary.read_bytes()


def runtime_provider(port,number,action='boot',status=0x120,bcv=True,bev=False,indicators=4,bev_action='return',witness_port=None,init_witness=False,strict_chs=False):
    witness=0x900+number*32
    source=f'''bits 16
org 0
db 55h,0AAh,4
jmp init
times 1Ah-($-$$) db 0
dw header
times 60h-($-$$) db 0
header:
db '$PnP',1,2
dw 0
db 0,0
dd 0500D041h
dw 0,0
db 0,0,0,{indicators}
dw {"connect" if bcv else "0"},disconnect,{"bootstrap" if bev else "0"},0,0
init:
push ds
{"push ax" if init_witness else ""}
xor ax,ax
mov ds,ax
{f'pop ax' if init_witness else ''}
{f'mov [{0x600+number*16}],ax' if init_witness else ''}
{f'mov [{0x602+number*16}],bx' if init_witness else ''}
{f'mov [{0x604+number*16}],dx' if init_witness else ''}
{f'mov [{0x606+number*16}],es' if init_witness else ''}
{f'mov [{0x608+number*16}],di' if init_witness else ''}
inc word [{witness}]
pop ds
mov ax,{status}
retf
connect:
push ds
push ax
xor ax,ax
mov ds,ax
pop ax
mov [{witness+8}],ax
mov [{witness+10}],bx
mov [{witness+12}],dx
mov [{witness+14}],es
mov [{witness+16}],di
inc word [{witness+2}]
mov al,[475h]
add al,80h
mov [{witness+18}],al
inc byte [475h]
mov word [4Ch],disk
mov [4Eh],cs
mov word [60h],alien_hook
mov [62h],cs
mov word [64h],alien_hook
mov [66h],cs
pop ds
retf
disconnect:
push ds
xor ax,ax
mov ds,ax
inc word [{witness+4}]
pop ds
retf
alien_hook:
inc word [cs:0] ; Must never execute: BIOS recaptures managed continuation.
iret
bootstrap:
push ds
push ax
xor ax,ax
mov ds,ax
pop ax
mov [{witness+8}],ax
mov [{witness+10}],bx
mov [{witness+12}],dx
mov [{witness+14}],es
mov [{witness+16}],di
inc word [{witness+6}]
pop ds
{"retf" if bev_action=='return' else 'int 18h' if bev_action=='int18' else 'int 19h'}
disk:
push bp
mov bp,sp
push ds
{'push ax' if strict_chs else ''}
xor ax,ax
mov ds,ax
{'pop ax' if strict_chs else ''}
cmp dl,[{witness+18}]
jne failed
{f'''cmp ah,0
je strict_reset
mov [{witness+22}],dx
mov [{witness+24}],cx
mov [{witness+26}],ax
mov [{witness+28}],es
mov [{witness+30}],bx
cmp dh,0
jne failed
cmp cx,1
jne failed
cmp ax,0201h
jne failed
cmp bx,7C00h
jne failed''' if strict_chs else ''}
inc word [{witness+20}]
'''
    if action!='cf':
        if action=='retry':source+='cmp byte [6EFh],1\njne failed\n'
        source+='''push si
push di
push cx
push cs
pop ds
mov si,sector
mov di,bx
mov cx,256
cld
rep movsw
pop cx
pop di
pop si
and word [ss:bp+6],0FFFEh
pop ds
pop bp
iret
'''
    source+='''failed:
or word [ss:bp+6],1
pop ds
pop bp
iret
'''
    if strict_chs:source+='''strict_reset:
and word [ss:bp+6],0FFFEh
pop ds
pop bp
iret
'''
    source+='''
sector:
xor ax,ax
mov ds,ax
'''
    source+=f'mov word [6F0h],{number+1}\n'
    if action in ('int18','int19'):
        source+='''mov ax,2222h
mov ds,ax
mov es,ax
mov fs,ax
mov ss,ax
mov sp,400h
std
cli
'''+('int 18h\n' if action=='int18' else 'int 19h\n')
    if witness_port is not None:source+=f'mov al,{number+1}\nout {witness_port},al\n'
    source+='hlt\n'+f'times 510-($-sector) db {number+1}\ndw '+('0' if action=='unsigned' else '0AA55h')+'\ntimes 2048-($-$$) db 0\n'
    raw=bytearray(runtime_assemble(port,f'provider-{number}-{action}-{status}-{bcv}-{bev}-{bev_action}-{witness_port}-{init_witness}'+('-strict-CHS' if strict_chs else ''),source))
    raw[0x69]=(-sum(raw[0x60:0x80]))&255;raw[-1]=(-sum(raw))&255
    return bytes(raw)


def runtime_external_machine(port,actions=('int18','boot'),statuses=None,images=None):
    from shared.tools.isa_pnp_proof import Bus
    m=isa_machine(port,Bus(),OUTPUT)
    m.cpu.mem_write(0x600,b'\xCC'*10)
    for n,action in enumerate(actions):
        image=images[n] if images else runtime_provider(port,n,action,status=(statuses or [0x120]*len(actions))[n])
        m.cpu.mem_write((0xC800+n*0x100)<<4,image)
    m.call('settings_load');m.call('setup_defaults');m.draft();m.put('U_POST_DELAY',b'\0')
    m.put('U_HALT',b'\x01')
    assert m.call('settings_save')
    if port!='m919':m.call('pnp_journal_release')
    m.call('pnp_early');m.call('option_rom_discovery')
    m.runtime_post_intervals=struct.unpack('<II',m.cpu.mem_read(m.base+0x320,8))
    m.call('pnp_finish_entry')
    m.base=int.from_bytes(m.cpu.mem_read(0x40E,2),'little')<<4
    m.allocated=m.cpu.mem_read(m.base,1)[0]*1024
    runtime_attach_interrupts(m)
    m.cpu.mem_write(0x475,b'\x01') # Independently installed native80 is earlier.
    m.cpu.mem_write(0x1000,b'\xCF') # External pre-existing reset provider.
    m.cpu.mem_write(0x4C,struct.pack('<HH',0x1000,0))
    for field,value in (('C_BOOT',4),('C_BOOT_SECOND',0),('C_BOOT_THIRD',0),('C_BOOT_FOURTH',0)):
        m.put(field,bytes((value,)))
    return m


def runtime_attach_interrupts(m):
    def interrupt(cpu,vector):
        if vector not in (0x08,0x09,0x12,0x13,0x16,0x18,0x19,0x1C):return False
        flags=cpu.reg_read(x.UC_X86_REG_EFLAGS)
        sp=(cpu.reg_read(x.UC_X86_REG_SP)-6)&65535;ss=cpu.reg_read(x.UC_X86_REG_SS)
        cpu.mem_write((ss<<4)+sp,struct.pack('<HHH',cpu.reg_read(x.UC_X86_REG_IP),cpu.reg_read(x.UC_X86_REG_CS),flags&65535))
        off,seg=struct.unpack('<HH',cpu.mem_read(vector*4,4))
        cpu.reg_write(x.UC_X86_REG_SP,sp);cpu.reg_write(x.UC_X86_REG_EFLAGS,flags&~0x300)
        cpu.reg_write(x.UC_X86_REG_CS,seg);cpu.reg_write(x.UC_X86_REG_IP,off)
        return True
    m.runtime_interrupt=interrupt
    # External8042 command-byte protocol for the existing late handoff owner.
    queue=[];command=[0x43];write_command=[False]
    original_in,original_out=m.bus.input,m.bus.output
    def kbc_in(port,size):
        if port==0x64:return int(bool(queue))
        if port==0x60:return queue.pop(0) if queue else 0
        return original_in(port,size)
    def kbc_out(port,size,value):
        if port==0x64:
            if value==0x20:queue.append(command[0])
            elif value==0x60:write_command[0]=True
            return True
        if port==0x60 and write_command[0]:command[0]=value;write_command[0]=False;return True
        return original_out(port,size,value)
    m.bus.input,m.bus.output=kbc_in,kbc_out
    m.runtime_kbc_queue=queue


def runtime_execute_boot(m, *, fdc_attached=False):
    handoffs=[];terminal=[]
    retry=0xF0000+m.listing.symbol('boot_retry')
    def code(cpu,address,length,unused):
        if address==0x7C00:handoffs.append(tuple(cpu.reg_read(getattr(x,'UC_X86_REG_'+r)) for r in ('DL','ES','DI')))
        if address==retry:terminal.append('retry');cpu.emu_stop()
        elif (address<0x80000 or address in getattr(m,'runtime_loader_halts',())) and bytes(cpu.mem_read(address,1))==b'\xF4':terminal.append('loader');cpu.emu_stop()
    h=m.cpu.hook_add(UC_HOOK_CODE,code)
    fdc_hook=None
    if not fdc_attached:floppy,fdc_hook=runtime_floppy_device(m,None)
    try:
        for reg,value in dict(CS=0xF000,DS=0,ES=0,FS=m.base>>4,SS=0,SP=0x7000,EFLAGS=0x202).items():m.cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
        (m.execute(0xF0000+m.listing.symbol('int19'),0xFFFFF,8000000) if hasattr(m,'execute') else m.cpu.emu_start(0xF0000+m.listing.symbol('int19'),0xFFFFF,count=8000000))
    finally:
        m.cpu.hook_del(h)
        if fdc_hook is not None:m.cpu.hook_del(fdc_hook)
    assert len(terminal)==1,('boot did not reach terminal',hex(m.cpu.reg_read(x.UC_X86_REG_CS)),hex(m.cpu.reg_read(x.UC_X86_REG_IP)))
    return {'terminal':terminal[0],'handoffs':handoffs}


def runtime_handoff_external(port,action):
    m=runtime_external_machine(port,(action,'boot'))
    handoffs=[];private=[]
    def code(cpu,address,size,unused):
        if address==0x7C00:
            handoffs.append(tuple(cpu.reg_read(getattr(x,'UC_X86_REG_'+r)) for r in ('DL','ES','DI')))
        if address<0xF0000 and cpu.reg_read(x.UC_X86_REG_CS) not in (0,0xC800,0xC900):private.append(address)
        if address<0x80000 and bytes(cpu.mem_read(address,1))==b'\xF4':cpu.emu_stop()
    hook=m.cpu.hook_add(UC_HOOK_CODE,code)
    try:
        for reg,value in dict(CS=0xF000,DS=0,ES=0,FS=m.base>>4,SS=0,SP=0x7000,EFLAGS=0x202).items():
            m.cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
        m.cpu.emu_start(0xF0000+m.listing.symbol('int19'),0xFFFFF,count=1000000)
    finally:m.cpu.hook_del(hook)
    assert int.from_bytes(m.cpu.mem_read(0x6F0,2),'little')==2,(port,action,hex(m.cpu.reg_read(x.UC_X86_REG_IP)))
    witnesses=[struct.unpack('<16H',m.cpu.mem_read(0x900+n*32,32)) for n in range(2)]
    assert [w[:3] for w in witnesses]==[(1,1,1),(1,1,0)],witnesses
    assert all(w[4:9]==(4,0xFFFF,0xFFFF,0xF000,m.listing.symbol('pnp_installation')) for w in witnesses),witnesses
    assert [w[9]&255 for w in witnesses]==[0x81,0x81],witnesses
    assert all(h==(0x81,0xF000,m.listing.symbol('pnp_installation')) for h in handoffs),handoffs
    assert not private,private[:10]
    return {'action':action,'actual_discovery_promotion_connect_read_loader_continuation':True,
            'witnesses':witnesses,'handoffs':handoffs,'one_disconnect_first_only':True,'no_private_fetch':True}


def runtime_strict_chs(port):
    image=runtime_provider(port,0,strict_chs=True)
    m=runtime_external_machine(port,('boot',),images=(image,))
    result=runtime_execute_boot(m)
    witness=struct.unpack('<16H',m.cpu.mem_read(0x900,32))
    assert witness[11:]==(0x81,1,0x0201,0,0x7C00),(port,'F2 C0/H0/S1 read',witness,result)
    assert result['terminal']=='loader' and result['handoffs']==[(0x81,0xF000,m.listing.symbol('pnp_installation'))]
    assert witness[:3]==(1,1,0) and witness[10]==1
    end=image.rfind(b'\x55\xAA')+2
    expected=image[end-512:end]
    assert len(expected)==512 and bytes(m.cpu.mem_read(0x7C00,512))==expected
    return {'strict_external_C0_H0_S1_driver':True,'actual_DX_CX_AX_ES_BX':witness[11:],
            'actual_read_once':witness[10],'full_sector_sha256':hashlib.sha256(expected).hexdigest(),'actual_handoff':result}


def runtime_relocation(port):
    m=runtime_external_machine(port,('int18','boot'))
    old,size=m.base,m.allocated;new=0x60000;relocated=[];reads=[];handoffs=[]
    m.cpu.mem_write(0x104,struct.pack('<HH',0xE0,(old>>4)+0x20))
    m.cpu.mem_write(0x118,struct.pack('<HH',0x5678,0x1234))
    m.cpu.mem_write(old+0x27A,b'\x03\x02\x02')
    bcv=int.from_bytes(m.cpu.mem_read(0xC9060+0x16,2),'little')
    def code(cpu,address,length,unused):
        if address==0xC9000+bcv and not relocated:
            data=bytes(cpu.mem_read(old,size));cpu.mem_write(new,data)
            cpu.mem_write(0x40E,struct.pack('<H',new>>4));cpu.mem_write(0x413,struct.pack('<H',new>>10))
            cpu.mem_write(old,b'\xA7'*size);m.base=new;m.allocated=size;relocated.append(True)
        if address==0x7C00:handoffs.append((cpu.reg_read(x.UC_X86_REG_DL),cpu.reg_read(x.UC_X86_REG_ES),cpu.reg_read(x.UC_X86_REG_DI)))
        if address<0x80000 and bytes(cpu.mem_read(address,1))==b'\xF4':cpu.emu_stop()
    def read(cpu,access,address,length,value,unused):
        if relocated and old<=address<old+size:reads.append(address)
    a=m.cpu.hook_add(UC_HOOK_CODE,code);b=m.cpu.hook_add(UC_HOOK_MEM_READ,read)
    try:
        for reg,value in dict(CS=0xF000,DS=0,ES=0,FS=old>>4,SS=0,SP=0x7000,EFLAGS=0x202).items():m.cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
        m.cpu.emu_start(0xF0000+m.listing.symbol('int19'),0xFFFFF,count=1000000)
    finally:m.cpu.hook_del(a);m.cpu.hook_del(b)
    assert relocated and not reads,reads[:10]
    assert m.cpu.mem_read(0x6F0,2)==b'\x02\0'
    assert m.cpu.mem_read(0x104,4)==struct.pack('<HH',0xE0,(new>>4)+0x20)
    assert m.cpu.mem_read(0x118,4)==b'\x78\x56\x34\x12'
    assert m.cpu.mem_read(new+0x27A,3)==b'\x03\x02\x02'
    # Actual INT15/C1 handler resolves the current public base after relocation.
    m.cpu.mem_write(0x1200,b'\xB8\x00\xC1\xCD\x15\xF4')
    m.cpu.reg_write(x.UC_X86_REG_CS,0);m.cpu.reg_write(x.UC_X86_REG_IP,0x1200)
    m.cpu.reg_write(x.UC_X86_REG_SS,0);m.cpu.reg_write(x.UC_X86_REG_SP,0x7000)
    m.cpu.emu_start(0x1200,0x1206,count=20000)
    assert m.cpu.reg_read(x.UC_X86_REG_ES)==new>>4
    relative=int.from_bytes(m.cpu.mem_read(new+0x334,4),'little')
    assert m.call('check_disk_buffer',EAX=new+relative-1,EDX=new+relative+1)==False
    assert m.call('check_disk_buffer',EAX=new+size,EDX=new+size+512)
    return {'actual_second_BCV_external_relocation':True,'only_advertised_bytes_copied':size,
            'old_region_poisoned_and_unused':True,'current_C1_and_tail_guard':True,
            'native_only_FDPT_alias_rebased':True,'external_FDPT_and_APM_preserved':True,'handoffs':handoffs}



def runtime_public_current(port,model,cpu,listing,bus):
    """OS callers on the actual produced CPU; no constructor/load/publication."""
    import types
    class OSCPU:
        def __getattr__(self,name):return getattr(cpu,name)
        def mem_write(self,address,data):
            cpu.mem_write(address,data)
            if port=='m919' and address<0xA0000:
                for at in range(0,len(data),4):
                    piece=data[at:at+4];model.write(address+at,len(piece),int.from_bytes(piece,'little'))
    operating=OSCPU();context=cpu.context_save()
    base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4;size=cpu.mem_read(base,1)[0]*1024
    frozen=bytes(cpu.mem_read(0x4AD,83));live=bytes(cpu.mem_read(base,size))
    headers=scan(bytes(cpu.mem_read(0xF0000,65536)));assert len(headers)==1
    results={}
    try:
        for mode in ('real','ss16','ss32'):
            cpu.context_restore(context)
            c=object.__new__(Caller)
            for name,value in dict(cpu=operating,port=port,listing=listing,base=base,allocated=size,
                header=headers[0],mode=mode,public_active=False,caller_flags=0xCD7,return_opcode=b'\x90',
                buffer=0x2000 if mode=='real' else 0x58,bios=0x40 if mode=='real' else 0x48,
                stack=0x3000 if mode=='real' else 0x68,code=0xF000 if mode=='real' else 0x28,
                return_code=0x1000 if mode=='real' else 0x38,
                stack_offset=0xABCD7080 if mode!='ss32' else 0x100D0).items():setattr(c,name,value)
            if mode!='real':
                gdt=bytearray(0x78)
                for selector,address,length,access,flags in (
                    (0x28,0xF0000,65536,0x9A,0),(0x38,0x10000,65536,0x9A,0),
                    (0x48,0x400,65536,0x92,0),(0x58,0x20000,65536,0x92,0),
                    (0x68,0x30000,0x30000 if mode=='ss32' else 65536,0x92,0x40 if mode=='ss32' else 0)):
                    gdt[selector:selector+8]=descriptor(address,length,access,flags)
                operating.mem_write(0x6000,bytes(gdt));cpu.reg_write(x.UC_X86_REG_GDTR,(0,0x6000,len(gdt)-1,0))
                cpu.reg_write(x.UC_X86_REG_CR0,cpu.reg_read(x.UC_X86_REG_CR0)|1)
                cpu.reg_write(x.UC_X86_REG_CS,c.return_code)
                loader=bytes.fromhex('FAB858008ED88EC08EE08EE8B868008ED0')
                operating.mem_write(0x10300,loader)
                cpu.emu_start(0x300+(c.return_code<<4),0x10300+len(loader),count=100)
            else:
                # Actual MOV reloads the OS's real-mode segment caches; host
                # setters can retain unreal attributes from the board RAM path.
                cpu.reg_write(x.UC_X86_REG_CS,c.return_code)
                loader=bytes.fromhex('FAB800208ED88EC08EE08EE8B800308ED0')
                operating.mem_write(0x10300,loader)
                cpu.emu_start(0x10300,0x10300+len(loader),count=100)
            c.far=types.MethodType(Caller.far,c)
            if port=='m919' and mode=='real':c.execute=model.pnp_execute
            forbidden=[];ports=[]
            def read(uc,access,address,length,value,unused):forbidden.append(address)
            def write(uc,access,address,length,value,unused):
                assert address+length<=0xC0000 or address>=0x100000,('public ROM write',mode,address,
                    *[uc.reg_read(getattr(x,'UC_X86_REG_'+r)) for r in ('CS','IP','SS','ESP','FS','GS')])
            def io(uc,address,length,unused):
                code=bytes(uc.mem_read(address,min(length,8))).lstrip(b'\x66\x67')
                if code and code[0] in (0xE6,0xE7,0xEE,0xEF):
                    portno=code[1] if code[0] in (0xE6,0xE7) else uc.reg_read(x.UC_X86_REG_DX)
                    ports.append(portno)
            hooks=[cpu.hook_add(UC_HOOK_MEM_READ,read,None,base,base+size-1),
                   cpu.hook_add(UC_HOOK_MEM_WRITE,write),cpu.hook_add(UC_HOOK_CODE,io)]
            try:
                operating.mem_write(0x20100,b'\xCC'*16)
                assert c.far(0,[0x100,c.buffer,0x108,c.buffer,c.bios])==0
                count=cpu.mem_read(0x20100,1)[0];maximum=int.from_bytes(cpu.mem_read(0x20108,2),'little')
                assert 10<=count<=20 and 18<=maximum<=128
                status,node,next_handle=get_node(c,0,1);assert status==0 and decode(node)[0]=='PNP0000'
                operating.mem_write(0x20200,node)
                assert c.far(2,[0,0x200,c.buffer,1,c.bios])==0
                operating.mem_write(0x20100,b'\xCC'*12)
                assert c.far(0x40,[0x100,c.buffer,c.bios])==0
                actual=bytes(cpu.mem_read(0x20100,12))
                expected=bytes((1,len(bus.cards)))+struct.pack('<HH',bus.read_port if bus.cards else 0,0)
                assert actual==expected+b'\xCC'*6,(mode,actual.hex(),expected.hex())
                before=len(ports)
                for function in (9,10,0x41,0x42,0x43):assert c.far(function)==0x82
                assert len(ports)==before
                assert c.far(0x1234)==0x81
                assert not forbidden and 0x71 not in ports and 0x279 not in ports and 0xA79 not in ports
                results[mode]={'count_BYTE':count,'max_WORD':maximum,'first_node':decode(node)[0],
                    'unchanged_Current_Set_success':True,'ISA_six_bytes':actual[:6].hex(),
                    'optional82_no_mutation':True,'same_produced_CPU':True,
                    'full_Caller_far_state_canaries':True}
            finally:
                for hook in hooks:cpu.hook_del(hook)
            assert bytes(cpu.mem_read(0x4AD,83))==frozen
            assert bytes(cpu.mem_read(base,size))==live
    finally:cpu.context_restore(context)
    return {'independent_actual_ROM_scan':headers[0].hex(),'actual_base':base,'modes':results}

def runtime_boot_current(port,model,cpu,listing,bus,expected_marker,expected_drive=0x81,handoff_count=1):
    before=len(bus.loader_markers);handoffs=[]
    def entry(uc,address,length,unused):
        if address==0x7C00:handoffs.append(tuple(uc.reg_read(getattr(x,'UC_X86_REG_'+r)) for r in ('DL','ES','DI')))
    hook=cpu.hook_add(UC_HOOK_CODE,entry,None,0x7C00,0x7C00)
    try:
        base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
        for reg,value in dict(CS=0xF000,DS=0,ES=0,FS=base>>4,SS=0,SP=0x7000,EFLAGS=0x202).items():
            cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
        at=0xF0000+listing.symbol('int19')
        if port=='m919':model.pnp_execute(at,0xFFFFF,8000000)
        else:cpu.emu_start(at,0xFFFFF,count=8000000)
    finally:cpu.hook_del(hook)
    assert bus.loader_markers[before:]==[expected_marker],(port,bus.loader_markers[before:],hex(cpu.reg_read(x.UC_X86_REG_IP)))
    assert handoffs==[(expected_drive,0xF000,listing.symbol('pnp_installation'))]*handoff_count,handoffs
    return {'actual_marker':expected_marker,'handoff':handoffs,'same_produced_CPU':True}

def runtime_chain(port):
    causes=('forward','backward','cycle','later-bad','zero-length','short-PnP','bad-checksum','bad-callback','bad-string','legacy')
    images=[];valid=[]
    for number,cause in enumerate(causes):
        raw=bytearray(runtime_rom(number,status=0))
        if cause=='backward':
            raw[0x80:0x90]=raw[0x40:0x50];raw[0x40:0x50]=bytes(16);struct.pack_into('<H',raw,0x1A,0x80)
        elif cause=='cycle':struct.pack_into('<H',raw,0x66,0x40)
        elif cause=='later-bad':struct.pack_into('<H',raw,0x66,0x7F8)
        elif cause=='zero-length':raw[0x65]=0
        elif cause=='short-PnP':raw[0x65]=1
        elif cause=='bad-checksum':raw[0x69]^=1
        elif cause=='bad-callback':struct.pack_into('<H',raw,0x76,0x800)
        elif cause=='bad-string':struct.pack_into('<H',raw,0x6E,0x7F0);raw[0x7F0:]=b'\x01'*16
        elif cause=='legacy':struct.pack_into('<H',raw,0x1A,0)
        if cause not in ('bad-checksum','zero-length','short-PnP'):
            raw[0x69]=0;raw[0x69]=(-sum(raw[0x60:0x80]))&255
        # Keep the deliberately unterminated final string nonzero at the footer.
        footer=0x700 if cause=='bad-string' else len(raw)-1
        raw[footer]=0;raw[footer]=(-sum(raw))&255
        images.append((0xC800+number*0x80,bytes(raw)))
        valid.append(cause in ('forward','backward','legacy'))
    marker=len(causes)+1
    images.append((0xC800+len(causes)*0x80,runtime_provider(port,len(causes),witness_port=0xE9)))
    phase=[]
    def completed(port,model,cpu,listing,bus):
        expected=[(len(phase)+1)*int(good) for good in valid]+[len(phase)+1]
        assert bus.initializations==expected,(port,bus.initializations,expected)
        result={'public_calls':runtime_public_current(port,model,cpu,listing,bus),
                'boot':runtime_boot_current(port,model,cpu,listing,bus,marker),
                'actual_initialization_counts':list(bus.initializations)}
        phase.append(result);return result
    post=runtime_startup_snapshot(port,phases=(False,True),rom_images=images,
        boot_order=(4,0,0,0),post_action=completed,snapshot_name='p3-chain-post')
    assert len(phase)==2
    return {'causes':dict(zip(causes,valid)),'cold_and_warm_same_run_to_saved_Other_sector':phase,
            'actual_startup':post.startup_evidence,'all_later_physical_provider_reachable':True}


def early_display_entry(port,pnp_aware=False):
    """Actual cold selection/ROM init/first POST mode3, before Setup/Summary."""
    if port=='presario-800':return {'selected_retained_display':'unchanged; no selectable PCI display'}
    from shared.tools.isa_pnp_proof import Bus
    source="""bits 16
org 0
db 55h,0AAh,64
jmp init
times 1Ah-($-$$) db 0
dw HEADER_POINTER
times 60h-($-$$) db 0
header: db '$PnP',1,2
dw 0
db 0,0
dd 0900D041h
dw 0,0
db 0,0,0,1
dw connect,0,0,0,0
times 100h-($-$$) db 0
init:
mov dx,ds
xor bx,bx
mov ds,bx
mov [600h],ax
mov [602h],dx
mov [604h],es
mov [606h],di
inc word [608h]
INIT_TAIL
connect:
xor bx,bx
mov ds,bx
mov [60Ah],ax
install:
mov word [40h],handler
mov [42h],cs
mov ax,88h
retf
times 200h-($-$$) db 0
handler:
push ds
push bx
xor bx,bx
mov ds,bx
cmp ax,3
jne .done
inc word [60Ch]
.done:
pop bx
pop ds
iret
times 32768-($-$$) db 0
"""
    source=source.replace('HEADER_POINTER','header' if pnp_aware else '0')
    source=source.replace('INIT_TAIL','mov ax,88h\nretf' if pnp_aware else 'jmp install')
    raw=bytearray(runtime_assemble(port,'early-display-'+str(int(pnp_aware)),source))
    if pnp_aware:raw[0x69]=(-sum(raw[0x60:0x80]))&255
    raw[-1]=(-sum(raw))&255
    class Complete(Exception):pass
    class Display(Bus):
        def __init__(self):
            super().__init__([]);self.video_rom=bytes(raw);self.pci_video=True
            self.execute_video_interrupt=True;self.entries=[];self.first_post=False;self.proved=None
        def observe_startup(self,model,cpu,address,listing):
            if not self.entries:
                self.entries=[0xF0000+listing.symbol(name) for name in ('post_ui_begin','post_header','setup_main','post_debug_summary')]
            if address in self.entries[2:]:raise AssertionError('Setup/Summary preceded first POST video')
            if address==self.entries[0]:
                from shared.tools.post_fixture import installed_address
                self.entries[1]=installed_address(listing,cpu.mem_read,'post_header')
                self.first_post=True
            if address==self.entries[1] and self.first_post:
                words=struct.unpack('<7H',cpu.mem_read(0x600,14))
                expected_bdf=0x60 if port=='m919' else 0xFFFF
                assert words[0]==expected_bdf and words[4]==1,words
                if pnp_aware:
                    assert words[2]==0xF000 and bytes(cpu.mem_read(0xF0000+words[3],4))==b'$PnP',words
                    assert words[5]==2,words
                else:assert words[1:4]==(0,0,0),words
                assert words[6]>0 and bytes(cpu.mem_read(0x42,2))==b'\x00\xC0',words
                self.proved={'entry_AX_DS_ES_DI':words[:4],'initializations':words[4],
                    'BCV_role':words[5],'actual_mode3_calls_before_Setup_or_Summary':words[6],
                    'actual_first_post_ui_begin':True,'real_PnP_pointer':pnp_aware}
                raise Complete
    bus=Display();saved=settings.Settings(port,OUTPUT)
    saved.call('settings_load');saved.call('setup_defaults');saved.draft();saved.put('U_POST_DELAY',b'\0');saved.put('U_HALT',b'\x01')
    assert saved.call('settings_save')
    try:startup(port,bytes(saved.cmos).hex(),'',pnp_bus=bus,phases=(False,),external_video=True)
    except Complete:pass
    assert bus.proved is not None
    return bus.proved


def runtime_display(port):
    if port=='presario-800':return {'alternative_display':'not-applicable; selected retained Cirrus owner',
        'fixed_display_actual_POST':'runtime_media executes retained32KiB clear/fill/copy/whole-ROM validation/INT10 and final promotion'}
    from shared.tools.isa_pnp_proof import Bus
    source='''bits 16
org 0
db 55h,0AAh,64
jmp init
times 1Ah-($-$$) db 0
dw header
times 60h-($-$$) db 0
header: db '$PnP',1,2
dw 0
db 0,0
dd 0900D041h
dw 0,0
db 0,0,0,1
dw connect,0,0,0,0
times 100h-($-$$) db 0
init:
push ds
xor ax,ax
mov ds,ax
inc word [600h]
mov [606h],es
mov [608h],di
pop ds
mov ax,88h
retf
times 200h-($-$$) db 0
connect:
push ds
push ax
xor ax,ax
mov ds,ax
pop ax
mov [60Ah],ax
inc word [602h]
mov word [40h],handler
mov [42h],cs
pop ds
retf
times 240h-($-$$) db 0
handler:
push ds
push ax
xor ax,ax
mov ds,ax
inc word [604h]
pop ax
cmp ax,1130h
jne .done
push cs
pop es
mov bp,300h
mov cx,16
mov dx,24
.done:
pop ds
iret
times 32768-($-$$) db 0
'''
    raw=bytearray(runtime_assemble(port,'selected-pnp-display',source))
    decoy=bytearray(runtime_rom(7));raw[0x4000:0x4000+len(decoy)]=decoy
    raw[0x69]=(-sum(raw[0x60:0x80]))&255;raw[-1]=(-sum(raw))&255
    class Display(Bus):
        def __init__(self):
            super().__init__([]);self.video_rom=bytes(raw);self.installed=False;self.last=None
            self.execute_video_interrupt=True
            self.loader_markers=[];self.runtime_continue=False
            self.record=None;self.wrong_guard=None;self.record_check=None;self.guard_verified=False;self.commit_pending=False
        def observe_startup(self,model,cpu,address,listing):
            self.last=cpu;self.model=model;self.listing=listing
            if not self.installed:
                cpu.mem_write(0xC8000,runtime_provider(port,0,witness_port=0xE9));self.installed=True
                self.finish_address=0xF0000+listing.symbol('pnp_finish_entry')
                def selected(uc,address,length,unused):
                    base=int.from_bytes(uc.mem_read(0x40E,2),'little')<<4
                    self.record=int.from_bytes(uc.mem_read(base+0x334,4),'little')
                    row=bytes(uc.mem_read(self.record,28))
                    assert struct.unpack_from('<H',row,4)[0]==0xC000
                    self.original_next=int.from_bytes(row[:4],'little')
                    self.wrong_guard=(self.record>>4,bytes(uc.mem_read(self.record>>4,32)))
                def guard(uc,access,address,length,value,unused):
                    if self.wrong_guard and not self.guard_verified:
                        low,_=self.wrong_guard
                        assert address+length<=low or address>=low+32,('F1 wrong-normalization write',self.record,address,length,value)
                        if address==self.record+17:
                            assert length==1 and value==5
                            self.commit_pending=True
                def committed(uc,address,length,unused):
                    if self.commit_pending:
                        row=bytes(uc.mem_read(self.record,28));low,original=self.wrong_guard
                        assert row[17]==5 and int.from_bytes(row[:4],'little')==self.original_next
                        assert bytes(uc.mem_read(low,32))==original
                        self.guard_verified=True;self.commit_pending=False
                cpu.hook_add(UC_HOOK_CODE,selected,None,0xC0200,0xC0200)
                cpu.hook_add(UC_HOOK_MEM_WRITE,guard)
                cpu.hook_add(UC_HOOK_CODE,committed)
            if self.record is not None and address==self.finish_address:
                row=bytes(cpu.mem_read(self.record,28));low,original=self.wrong_guard
                assert row[17]==5 and int.from_bytes(row[:4],'little')==self.original_next
                assert self.guard_verified
                base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
                pointer=int.from_bytes(cpu.mem_read(base+0x334,4),'little');links=[]
                while pointer:
                    assert pointer not in [a for a,b in links]
                    following=int.from_bytes(cpu.mem_read(pointer,4),'little');links.append((pointer,following));pointer=following
                assert len(links)==2 and links[-1][0]==self.record and links[-1][1]==self.original_next
                self.record_check={'selected_pointer':self.record,'flags':row[17],'original_next':self.original_next,
                    'actual_complete_links':links,'wrong_normalization_guard':low,'guard_sha256':hashlib.sha256(original).hexdigest()}
        def output(self,p,size,value):
            if p==0xE9:self.loader_markers.append(value);self.last.emu_stop();return True
            return super().output(p,size,value)
    bus=Display()
    saved=settings.Settings(port,OUTPUT);saved.call('settings_load');saved.call('setup_defaults');saved.draft();saved.put('U_POST_DELAY',b'\0')
    for field,value in (('U_BOOT',4),('U_BOOT_SECOND',0),('U_BOOT_THIRD',0),('U_BOOT_FOURTH',0)):saved.put(field,bytes((value,)))
    saved.put('U_HALT',b'\x01');assert saved.call('settings_save')
    evidence=startup(port,bytes(saved.cmos).hex(),'',pnp_bus=bus,phases=(False,),external_video=True)
    words=struct.unpack('<6H',bus.last.mem_read(0x600,12))
    assert words[0:2]==(1,1) and words[2]>0 and words[5]==2,words
    assert words[3]==0xF000 and bytes(bus.last.mem_read(0xF0000+words[4],4))==b'$PnP'
    assert bus.last.mem_read(0x670,2)==b'\0\0','Interior selected-extent decoy initialized'
    assert bus.last.mem_read(0x900,2)==b'\x01\0','Adjacent physical provider lost'
    assert bus.record_check is not None
    prior=bus.last.mem_read(0x475,1)[0];bus.runtime_continue=True
    stop=getattr(bus.model,'stop_address',None)
    if stop is not None:bus.model.stop_address=-1
    try:boot=runtime_boot_current(port,bus.model,bus.last,bus.listing,bus,1,0x80+prior)
    finally:
        bus.runtime_continue=False
        if stop is not None:bus.model.stop_address=stop
    return {'init_once':True,'Video2_BCV_once_before_actual_INT10':True,'witness':words,
            'complete_selected_extent_excludes_internal_decoy':True,'adjacent_provider_once':True,'actual_startup':evidence,
            'selected_actual_record_and_unrelated_low_RAM':bus.record_check,
            'same_selected_extent_run_to_later_sector':boot}


def runtime_pci_instances(port):
    if port!='m919':return {'PCI_deployment':'not-applicable; no PCI ROM deployment owner'}
    sys.path.insert(0,str(ROOT/'m919/tools'))
    from pci_rom_proof import ROMHardware
    from pci_proof import compose,invoke
    class Hardware(ROMHardware):
        def __init__(self,**options):
            super().__init__(**options)
            self.pci.endpoints[0x60].rom_mask=0xFFFF8000
            self.loader_markers=[]
        def outgoing(self,cpu,port,size,value):
            if port==0xE9:self.loader_markers.append(value);cpu.emu_stop();return
            return super().outgoing(cpu,port,size,value)
        def observe(self,cpu,address,size):
            self.last_cpu=cpu
            if 0xE3185<=address<0xE33E0:
                if not hasattr(self,'private_trace'):self.private_trace=[]
                if len(self.private_trace)<120:self.private_trace.append([hex(address),*[cpu.reg_read(getattr(x,'UC_X86_REG_'+r)) for r in ('AX','DX','DS','SI','ECX','EFLAGS')]])
            if address==0xC0003:
                self.vga_entered=True
            if address==0xE3185:self.outer_input=bytes(cpu.mem_read(0xC0000,32)).hex()
            return super().observe(cpu,address,size)
        def prepare(self,cpu):
            super().prepare(cpu)
            raw=bytearray(32768);raw[:2048]=runtime_provider(port,0,'cf',init_witness=True)
            raw[2]=64;struct.pack_into('<H',raw,0x18,0x40)
            raw[0x40:0x58]=b'PCIR'+struct.pack('<HHHHBBBBHHBBH',0x1106,0x3249,0,0x18,0,0x85,1,1,64,0,0,0x80,0)
            raw[0x4000:0x4800]=runtime_rom(7,unknown=False,counter=True)
            raw[-1]=(-sum(raw[:-1]))&255;self.card_rom=bytes(raw)
            # Same product identity, separate physical instance outside both
            # selected VGA and deployed PCI extents.
            self.isa=runtime_provider(port,1,'cf',init_witness=True);cpu.mem_write(0xC8000,self.isa)
            self.dbase[0x8000:0x8800]=runtime_provider(port,2,witness_port=0xE9,init_witness=True)
            cpu.mem_write(0xD8000,bytes(self.dbase[0x8000:0x8800]))
    hardware=Hardware(mask=0xFFFF8000);hardware.rom_image=ROOT/port/OUTPUT/'baios-m919.bin'
    saved=settings.Settings(port,OUTPUT);saved.call('settings_load');saved.call('setup_defaults');saved.draft();saved.put('U_POST_DELAY',b'\0')
    chip=bytearray(saved.get('U_CHIP',24));chip[2]=chip[12]=1;saved.put('U_CHIP',chip)
    for field,value in (('U_BOOT',4),('U_BOOT_SECOND',0),('U_BOOT_THIRD',0),('U_BOOT_FOURTH',0)):saved.put(field,bytes((value,)))
    assert saved.call('settings_save')
    try:row,fixture=compose(hardware,saved=saved.cmos)
    except Exception:
        cpu=hardware.last_cpu;base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
        diagnostic={'vga_entered':getattr(hardware,'vga_entered',False),'vga_sum8':sum(cpu.mem_read(0xC0000,32768))&255,
            'INT10':bytes(cpu.mem_read(0x40,4)).hex(),'registers':hardware.registers,
            'control':bytes(cpu.mem_read(base+0x320,32)).hex(),'provider_events':hardware.provider_events,
            'CS_IP':[cpu.reg_read(x.UC_X86_REG_CS),cpu.reg_read(x.UC_X86_REG_IP)]}
        diagnostic['private_trace']=getattr(hardware,'private_trace',[])
        diagnostic['outer_input']=getattr(hardware,'outer_input',None)
        (ROOT/port/OUTPUT/'runtime-pci-failure.json').write_text(json.dumps(diagnostic,indent=2));raise
    cpu,model,listing,*_=fixture
    assert hardware.stop=='POST FF',row
    # The actual POST already performs the late scanner and resident promotion.
    at=struct.unpack('<5H',cpu.mem_read(0x600,10))
    assert at[0]==0x68 and at[1:3]==(0xFFFF,0xFFFF),at
    assert at[3]==0xF000 and bytes(cpu.mem_read(0xF0000+at[4],4))==b'$PnP'
    for number in (1,2):assert cpu.mem_read(0x600+number*16,2)==b'\xFF\xFF'
    assert [int.from_bytes(cpu.mem_read(0x900+n*32,2),'little') for n in range(3)]==[1,1,1]
    assert cpu.mem_read(0x670,2)==b'\0\0','Deployed-extent decoy initialized'
    base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
    relative=int.from_bytes(cpu.mem_read(base+0x334,4),'little')
    header=bytes(cpu.mem_read(base+relative,60));count=int.from_bytes(header[4:8],'little')
    records=[bytes(cpu.mem_read(base+relative+60+24*n,24)) for n in range(count)]
    selected=[struct.unpack_from('<H',r,0)[0] for r in records]
    assert selected.count(0xD000)==selected.count(0xC800)==selected.count(0xD800)==1,selected
    copied=bytes(cpu.mem_read(0xD0000,32768))
    assert copied==hardware.card_rom,'Complete deployed immutable ROM differs'
    assert not hardware.card.read(0x30,4)&1
    before=bytes(cpu.mem_read(base+relative,60+24*count));invoke(fixture,'option_rom_discovery')
    assert bytes(cpu.mem_read(base+relative,60+24*count))==before
    model.pnp_execute=fixture[-1].execute
    prior=cpu.mem_read(0x475,1)[0]
    boot=runtime_boot_current(port,model,cpu,listing,hardware,3,0x80+prior)
    assert [int.from_bytes(cpu.mem_read(0x902+n*32,2),'little') for n in range(3)]==[1,1,1]
    assert [int.from_bytes(cpu.mem_read(0x904+n*32,2),'little') for n in range(3)]==[1,1,0]
    return {'actual_POST':row,'PCI_BDF':0x68,'entry_witness':at,'instance_segments':selected,
            'same_ID_distinct_physical_instances_retained':True,'complete_deployed_extent_decoy_skipped':True,
            'ROMBAR_disabled_shadow_retained':True,'late_reentry_no_duplicate':True,
            'same_PCI_deployment_and_late_extent_to_terminal_sector':boot}

def runtime_disk_modules(port):
    import importlib
    os.environ['BAIOS_BUILD_DIRECTORY']=OUTPUT
    sys.path.insert(0,str(ROOT/'presario-800/tools'))
    cd=importlib.import_module('test-cdboot');ide=importlib.import_module('test-ide-options')
    from shared.tools.post_fixture import bind_rtc_candidate
    image=ROOT/port/OUTPUT/('baios-presario800-system.rom' if port=='presario-800' else f'baios-{port}.bin')
    bind_rtc_candidate(cd.setup.rtc,image)
    return cd,ide


def runtime_startup_snapshot(port,phases=(False,),cards=(),policy=None,relocate_first=False,actions=('cf','boot'),snapshot_name='runtime-post-memory',actual_cad=False,rom_images=None,boot_order=None,post_action=None,bad_read_ports=None,expect_active=None,seed_edit=None,observer=None,external_video=False,native_sector=None):
    """One actual cold POST with real media discovery, shared by runtime rows."""
    from shared.tools.isa_pnp_proof import Bus
    from shared.tools.pci_proof import PCI,Endpoint
    cd,ide=runtime_disk_modules(port)
    disk=cd.Packet([None,cd.disc(media=0)])
    if native_sector is not None:
        assert len(native_sector)==512 and native_sector[-2:]==b'\x55\xAA'
        disk.disk_words.update({(0,n):value for n,value in enumerate(struct.unpack('<256H',native_sector))})
    saved=settings.Settings(port,OUTPUT);saved.call('settings_load');saved.call('setup_defaults');saved.draft()
    saved.put('U_HALT',b'\x01')
    saved.put('U_POST_DELAY',b'\0')
    saved.put('U_TYPES',b'\x40')
    if boot_order is not None:
        for field,value in zip(('U_BOOT','U_BOOT_SECOND','U_BOOT_THIRD','U_BOOT_FOURTH'),boot_order):saved.put(field,bytes((value,)))
    if policy is not None:saved.put('U_PNP',policy)
    if port in ('m919','pb430'):
        chip=bytearray(saved.get('U_CHIP',24));chip[12 if port=='m919' else 6]=1;saved.put('U_CHIP',chip)
    if seed_edit is not None:seed_edit(saved)
    assert saved.call('settings_save')
    addresses={name:0xF0000+saved.listing.symbol(name) for name in
               ('pnp_publish','pnp_finish_entry','pnp_incomplete_callback','int19','post_debug_summary','pnp_post_summary_complete')}
    if rom_images is None:rom_images=[(0xC800+n*0x100,runtime_provider(port,n,action)) for n,action in enumerate(actions)]
    class Devices(Bus):
        def __init__(self):
            super().__init__(cards,bad_read_ports);self.installed=False;self.captured=None;self.runtime_continue=False
            self.initial_budgets=[];self.initializations=[0]*len(rom_images);self.hooked=set();self.relocation=None
            self.phase_results=[];self.loader_markers=[]
            self.incomplete=[];self.finish_roots=[]
            self.actual_cad=actual_cad
            self.runtime_reset_owners=True
            if port=='m919':self.pci=PCI({0x91:Endpoint(identity=0x673A1060,cls=0x010100)})
        def input(self,p,size):
            if 0x1F0<=p<=0x1F7 or p==0x3F6:return disk.port_in(disk.cpu,p,size,None)
            return super().input(p,size)
        def output(self,p,size,value):
            if p==0xE9:
                self.loader_markers.append(value);self.latest[1].emu_stop();return True
            if 0x1F0<=p<=0x1F7 or p==0x3F6:disk.port_out(disk.cpu,p,size,value,None);return True
            return super().output(p,size,value)
        def observe_startup(self,model,cpu,address,listing):
            self.latest=(model,cpu,listing,address)
            if observer is not None:observer(model,cpu,address,listing,self)
            disk.cpu=cpu
            if address==addresses['pnp_publish'] and not any(cpu.mem_read((int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4)+0x330,4)):
                self.initial_budgets.append(int.from_bytes(cpu.mem_read(0x413,2),'little'))
                if id(cpu) not in self.hooked:
                    for index,(segment,image) in enumerate(rom_images):
                        def initialized(cpu,address,size,unused,index=index):self.initializations[index]+=1
                        at=(segment<<4)+3
                        cpu.hook_add(UC_HOOK_CODE,initialized,None,at,at)
                    self.hooked.add(id(cpu))
                    def incomplete(cpu,address,size,unused):self.incomplete.append(address)
                    at=addresses['pnp_incomplete_callback'];cpu.hook_add(UC_HOOK_CODE,incomplete,None,at,at)
                for segment,image in rom_images:cpu.mem_write(segment<<4,image)
                self.installed=True
            if address==addresses['pnp_finish_entry']:
                base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
                self.post_intervals=struct.unpack('<II',cpu.mem_read(base+0x320,8))
                root=int.from_bytes(cpu.mem_read(base+0x330,4),'little')
                self.finish_roots.append(bytes(cpu.mem_read(root,32)).hex())
            terminal='int19' if port=='pb430' else 'pnp_post_summary_complete'
            if address==addresses[terminal]:self.captured=(model,cpu,listing)
        def after_each_post(self,model,cpu,listing):
            if post_action is None:return
            self.runtime_continue=True
            stop=getattr(model,'stop_address',None)
            if stop is not None:model.stop_address=-1
            try:self.phase_results.append(post_action(port,model,cpu,listing,self))
            finally:
                self.runtime_continue=False
                if stop is not None:model.stop_address=stop
        def after_post(self):
            if not relocate_first or self.relocation is not None:return
            model,cpu,listing=self.captured
            old=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
            size=cpu.mem_read(old,1)[0]*1024;new=0x90000
            data=bytes(cpu.mem_read(old,size))
            def put(address,payload):
                cpu.mem_write(address,payload)
                if port=='m919':
                    for at in range(0,len(payload),4):model.write(address+at,len(payload[at:at+4]),int.from_bytes(payload[at:at+4],'little'))
            put(new,data);put(0x40E,struct.pack('<H',new>>4));put(0x413,struct.pack('<H',new>>10))
            put(old,b'\xA7'*size)
            if port=='presario-800':model.base=new;model.segment=new>>4
            self.relocation={'old':old,'new':new,'copied_only_advertised_bytes':size}
    bus=Devices()
    try:evidence=startup(port,bytes(saved.cmos).hex(),'',pnp_bus=bus,phases=phases,external_video=external_video,expect_first_active=(not bool(cards)) if expect_active is None else expect_active)
    except Exception as error:
        if hasattr(bus,'latest'):
            model,cpu,listing,address=bus.latest
            failure={'error':repr(error),'PC':{name:cpu.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in ('CS','IP','SS','SP','AX','BX','CX','DX','FS')},
                     'console':getattr(model,'console',''),'last_observed':address,
                     'hops':getattr(model,'startup_hops',[]),'disk_commands':disk.selected_commands}
            (ROOT/port/OUTPUT/'runtime-startup-failure.json').write_text(json.dumps(failure,indent=2))
        raise
    evidence['actual_ROM_initializations']=bus.initializations
    evidence['actual_before_module_available_KiB']=bus.initial_budgets
    evidence['external_relocation_between_POST_and_reset']=bus.relocation
    evidence['actual_incomplete_notice_entries']=bus.incomplete
    evidence['actual_complete_P2_roots_before_finish']=bus.finish_roots
    evidence['actual_after_each_POST']=bus.phase_results
    evidence['actual_loader_IO_markers']=bus.loader_markers
    assert bus.captured and disk.selected_commands
    model,cpu,listing=bus.captured;bus.runtime_continue=True
    # As in the established CD→FDC fixture, continue the COMPLETE produced
    # public memory state on a flat external device fixture. No settings,
    # vectors, device records or runtime fields are fabricated or reloaded.
    snapshot=bytes(cpu.mem_read(0,0x100000))
    work=ROOT/port/OUTPUT
    (work/(snapshot_name+'.bin')).write_bytes(snapshot)
    metadata={'image_sha256':hashlib.sha256(saved.image.read_bytes()).hexdigest(),
              'snapshot_sha256':hashlib.sha256(snapshot).hexdigest(),
              'post_intervals':bus.post_intervals,'startup':evidence}
    if hasattr(bus,'pci'):metadata['PCI']={str(bdf):bytes(device.raw).hex() for bdf,device in bus.pci.endpoints.items()}
    metadata['FDC']={'dor':getattr(model,'fdc_dor',getattr(model,'ports',{}).get('dor',0)),
                     'positions':list(model.positions) if hasattr(model,'positions') else [getattr(model,'pcn',0),0]}
    (work/(snapshot_name+'.json')).write_text(json.dumps(metadata,indent=2))
    if post_action is not None:
        from types import SimpleNamespace
        return SimpleNamespace(cpu=cpu,base=int.from_bytes(snapshot[0x40E:0x410],'little')<<4,
                               startup_evidence=evidence)
    driver=runtime_resume_snapshot(port,snapshot,metadata,disk,getattr(bus,'pci',None),model)
    assert driver.cpu.mem_read(0x475,1)==b'\x01',('Native discovery failed',port,disk.selected_commands)
    return driver


def runtime_resume_snapshot(port,snapshot,metadata,disk,pci=None,model=None):
    """Continue an actual produced snapshot; never infer native BIOS records."""
    from shared.tools.isa_pnp_proof import Bus
    assert hashlib.sha256(snapshot).hexdigest()==metadata['snapshot_sha256']
    driver=isa_machine(port,Bus(),OUTPUT)
    assert hashlib.sha256(driver.image.read_bytes()).hexdigest()==metadata['image_sha256']
    driver.cpu.mem_write(0,snapshot)
    driver.base=int.from_bytes(snapshot[0x40E:0x410],'little')<<4
    driver.allocated=snapshot[driver.base]*1024
    runtime_attach_interrupts(driver)
    if pci is not None:driver.bus.pci=pci
    driver.runtime_post_intervals=metadata['post_intervals'];driver.native_device=disk
    driver.native_model=model;driver.startup_evidence=metadata['startup']
    driver.external_FDC=metadata.get('FDC')
    driver.cmos[:]=bytes.fromhex(metadata['startup']['cmos'])
    import copy
    driver.post_seed=(snapshot,metadata,type(disk),copy.deepcopy({k:v for k,v in vars(disk).items() if k!='cpu'}),copy.deepcopy(pci))
    runtime_native_device(driver)
    return driver



def runtime_load_post(port,snapshot_name='runtime-post-memory'):
    """Reuse the last task-owned actual POST snapshot with its captured devices."""
    from shared.tools.pci_proof import PCI,Endpoint
    cd,_=runtime_disk_modules(port);disk=cd.Packet([None,cd.disc(media=0)])
    work=ROOT/port/OUTPUT
    raw=(work/(snapshot_name+'.bin')).read_bytes();metadata=json.loads((work/(snapshot_name+'.json')).read_text())
    endpoints={}
    for bdf,config in metadata.get('PCI',{}).items():
        device=Endpoint();device.raw[:]=bytes.fromhex(config);endpoints[int(bdf)]=device
    return runtime_resume_snapshot(port,raw,metadata,disk,PCI(endpoints) if endpoints else None)

def runtime_clone_post(m):
    import copy
    raw,metadata,kind,values,pci=m.post_seed
    disk=object.__new__(kind);vars(disk).update(copy.deepcopy(values))
    return runtime_resume_snapshot(m.port,raw,metadata,disk,copy.deepcopy(pci))


def runtime_native_device(m):
    cd,ide=runtime_disk_modules(m.port)
    existing=hasattr(m,'native_device')
    disk=m.native_device if existing else ide.Disk(('ata','absent'))
    disk.cpu=m.cpu
    inp,out=m.bus.input,m.bus.output
    def incoming(port,size):
        if 0x1F0<=port<=0x1F7 or port==0x3F6:return disk.port_in(m.cpu,port,size,None)
        if 0x170<=port<=0x177 or port==0x376:return (1<<(size*8))-1
        return inp(port,size)
    def outgoing(port,size,value):
        if 0x1F0<=port<=0x1F7 or port==0x3F6:disk.port_out(m.cpu,port,size,value,None);return True
        return out(port,size,value)
    m.bus.input,m.bus.output=incoming,outgoing
    if not existing:
        m.cpu.mem_write(0x4C,struct.pack('<HH',m.listing.symbol('int13'),0xF000))
        m.call('ata_detect_primary')
    assert m.cpu.mem_read(0x475,1)==b'\x01'
    return cd,disk


def runtime_handoff_native(port,m=None,action='int18'):
    if m is None:m=runtime_external_machine(port,('cf','boot'))
    cd,disk=runtime_native_device(m)
    start,end=m.runtime_post_intervals
    # Loader owns this memory only after the actual final release. Erase the
    # real former journal, then execute the real loader INT18 continuation.
    count=min(min(end,m.base)-start,0xFFF0)//2
    sector=runtime_assemble(port,'native-reuse-loader-'+action,f'''bits 16
org 7C00h
mov ax,{start>>4}
mov es,ax
mov di,{start&15}
mov cx,{count}
mov ax,0A7A7h
rep stosw
xor ax,ax
mov ds,ax
mov word [6F2h],1234h
int {"19h" if action=='int19' else "18h"}
hlt
times 510-($-$$) db 0
dw 0AA55h
''')
    disk.disk_words.update({(0,n):v for n,v in enumerate(struct.unpack('<256H',sector))})
    m.put('C_BOOT',b'\x02');m.put('C_BOOT_SECOND',b'\x04')
    floppy,fdc_hook=runtime_floppy_device(m,None)
    handoffs=[]
    def code(cpu,address,length,unused):
        if address==0x7C00:
            handoffs.append((cpu.reg_read(x.UC_X86_REG_DL),cpu.reg_read(x.UC_X86_REG_ES),cpu.reg_read(x.UC_X86_REG_DI),bytes(cpu.mem_read(0x902,2))))
        if address<0x80000 and bytes(cpu.mem_read(address,1))==b'\xF4':cpu.emu_stop()
    h=m.cpu.hook_add(UC_HOOK_CODE,code)
    try:
        for reg,value in dict(CS=0xF000,DS=0,ES=0,FS=m.base>>4,SS=0,SP=0x7000,EFLAGS=0x202).items():m.cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
        (m.execute(0xF0000+m.listing.symbol('int19'),0xFFFFF,8000000) if hasattr(m,'execute') else m.cpu.emu_start(0xF0000+m.listing.symbol('int19'),0xFFFFF,count=8000000))
    finally:
        m.cpu.hook_del(h)
        m.cpu.hook_del(fdc_hook)
    assert m.cpu.mem_read(0x6F2,2)==b'\x34\x12'
    assert m.cpu.mem_read(0x6F0,2)==b'\x02\0'
    assert handoffs[0]==(0x80,0xF000,m.listing.symbol('pnp_installation'),b'\0\0'),handoffs
    assert handoffs[-1][0]==0x81 and disk.taskfiles, (handoffs,disk.taskfiles)
    assert m.cpu.mem_read(start,count*2)==b'\xA7'*(count*2)
    return {'actual_native_ATA_read_and_loader_interrupt':action,'released_journal_overwritten':[start,count*2],
            'native_before_any_IPL_connection':True,'handoffs':[(a,b,c,d.hex()) for a,b,c,d in handoffs],
            'actual_taskfiles':disk.taskfiles,'later_distinct_provider':True}



def runtime_disk_ownership(port,post):
    m=runtime_clone_post(post);cd,disk=runtime_native_device(m)
    old,size=m.base,m.allocated;new=0x60000
    native13=bytes(m.cpu.mem_read(0x4C,4));native41=bytes(m.cpu.mem_read(0x104,4))
    assert int.from_bytes(native41[2:],'little')==old>>4
    external46=struct.pack('<HH',0x5678,0x1234);m.cpu.mem_write(0x118,external46)
    m.cpu.mem_write(new,bytes(m.cpu.mem_read(old,size)))
    m.cpu.mem_write(0x40E,struct.pack('<H',new>>4));m.cpu.mem_write(0x413,struct.pack('<H',new>>10))
    m.cpu.mem_write(old,b'\xA7'*size);m.base=new;m.allocated=size
    m.cpu.mem_write(0x6EF,b'\x01') # Authored provider media is now available.
    # Preserve this legal external relocation for actual CD continuation too.
    import copy
    snapshot=bytes(m.cpu.mem_read(0,0x100000));metadata=copy.deepcopy(post.post_seed[1])
    metadata['snapshot_sha256']=hashlib.sha256(snapshot).hexdigest()
    m.post_seed=(snapshot,metadata,*post.post_seed[2:])
    source=runtime_assemble(port,'native-after-relocation',"""bits 16
org 7C00h
xor ax,ax
mov ds,ax
mov word [6F2h],1234h
int 18h
hlt
times 510-($-$$) db 0
dw 0AA55h
""")
    disk.disk_words.update({(0,n):word for n,word in enumerate(struct.unpack('<256H',source))})
    m.put('C_BOOT',b'\x02');m.put('C_BOOT_SECOND',b'\x04')
    observed=[]
    def code(cpu,address,length,unused):
        if address==0x7C00 and not observed:
            observed.append((bytes(cpu.mem_read(0x104,4)),bytes(cpu.mem_read(0x118,4)),bytes(cpu.mem_read(0x4C,4)),cpu.reg_read(x.UC_X86_REG_DL)))
    h=m.cpu.hook_add(UC_HOOK_CODE,code)
    try:result=runtime_execute_boot(m)
    finally:m.cpu.hook_del(h)
    assert observed==[(native41[:2]+struct.pack('<H',new>>4),external46,native13,0x80)],observed
    assert m.cpu.mem_read(0x6F2,2)==b'\x34\x12' and m.cpu.mem_read(0x6F0,2)==b'\x02\0'
    assert m.cpu.mem_read(old,size)==b'\xA7'*size
    wrapped=runtime_handoff_cd(port,m,expected_native_fdpt=native41[:2]+struct.pack('<H',new>>4),
                               external_fdpt=external46)
    return {'actual_native_publication_then_legal_complete_relocation':True,
            'native_only_FDPT_rebased_external_pointer_hook_count_retained':True,
            'native80_to_later81':result,'relocated_CD_source_chain_and_teardown':wrapped,
            'old_advertised_region_unused':True}


def runtime_saved_priority(port,post):
    """Persist priority at a real pre-release Setup gate, then reset and boot.

    Setup is a POST service; the earlier post-release direct-call fixture did
    not represent an admitted product entry. Keep the actual priority/connection
    oracle, using the common composed gate and external media proof instead.
    """
    spec=importlib.util.spec_from_file_location('footprint_priority',Path(__file__).with_name('test-rom-footprint.py'))
    owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
    owner.OUTPUT=OUTPUT;owner.pnp.OUTPUT=OUTPUT
    return [owner.setup_continuation(port,'early',order) for order in ((2,4,0,0),(4,2,0,0))]


def runtime_apm(port,mode):
    """Use the existing OS caller/descriptor machinery on produced firmware."""
    import importlib
    from types import MethodType,SimpleNamespace
    m=runtime_external_machine(port,('cf','boot'))
    runtime_disk_modules(port)
    owner=importlib.import_module('test-apm')
    os_client=SimpleNamespace(cpu=m.cpu,mode=0,halts=[],contract=None)
    for name in ('api','run','enter','real','protected_irq'):
        setattr(os_client,name,MethodType(getattr(owner.Apm,name),os_client))
    def registers(self):return {r:self.cpu.reg_read(getattr(x,'UC_X86_REG_'+r)) for r in owner.REGS}
    def setup(self,flags=0x202):
        for reg,value in dict(CS=0x9000,IP=0,DS=0,ES=0,FS=0x1234,GS=0x5678,SS=0,SP=0x6FFE,EFLAGS=flags).items():self.cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
    os_client.state=MethodType(registers,os_client);os_client.setup=MethodType(setup,os_client)
    def api(function,**kwargs):
        result=os_client.api(function,**kwargs);assert not result['cf'],(port,mode,function,result)
        return result
    outputs=() if mode==1 else ('EAX','EBX','ECX','ESI','EDI') if mode==2 else ('EAX','EBX','ECX','EDX','ESI','EDI')
    result=api(mode,outputs=outputs)
    if mode!=1:
        contract={'offset':result['bx'] if mode==2 else result['ebx'],
                  'data':result['cx'] if mode==2 else result['dx'],'code':result['ax'],
                  'length':result['si'] if mode==2 else result['esi']&65535,'data_length':result['di']}
        if mode==3:contract.update(code16=result['cx'],length16=result['esi']>>16)
        assert contract['data']==m.base>>4 and 0<contract['data_length']<=m.allocated
        os_client.contract=contract;os_client.enter(mode)
    api(0x0E,cx=0x0102,outputs=('EAX',))
    old,size=m.base,m.allocated;new=0x60000
    original=bytes(m.cpu.mem_read(old,size));m.cpu.mem_write(new,original)
    m.cpu.mem_write(0x40E,struct.pack('<H',new>>4));m.cpu.mem_write(0x413,struct.pack('<H',new>>10))
    if mode!=1:
        # The OS owns this returned mapping and reloads it for the new base.
        m.cpu.mem_write(0x600+os_client.data_selector,owner.descriptor(new,os_client.contract['data_length'],0x92))
    m.cpu.mem_write(old,b'\xA7'*size);m.base=new;m.allocated=size
    reads=[]
    def read(cpu,access,address,length,value,unused):
        if old<=address<old+size:reads.append(address)
    h=m.cpu.hook_add(UC_HOOK_MEM_READ,read)
    try:
        api(0x0E,cx=0x0101,outputs=('EAX',));api(4)
        if mode!=1:os_client.real()
        # Reconnect through the actual current-base real interface.
        result=api(1);api(4)
    finally:m.cpu.hook_del(h)
    assert not reads,reads[:10]
    assert m.cpu.mem_read(new+0x334,4)==original[0x334:0x338]
    relative=int.from_bytes(original[0x334:0x338],'little')
    assert m.cpu.mem_read(new+relative,size-relative)==original[relative:]
    assert m.cpu.mem_read(old,size)==b'\xA7'*size
    return {'mode':mode,'actual_connect_and_calls':True,'returned_contract':getattr(os_client,'contract',None),
            'OS_descriptor_updated_after_complete_EBDA_relocation':mode!=1,
            'actual_disconnect_reconnect_current_base':True,'provider_state_preserved_old_base_unused':True}


def runtime_floppy_device(m,media):
    import importlib
    runtime_disk_modules(m.port);legacy=importlib.import_module('test-legacy-disk')
    floppy=legacy.floppy_buffer_model(m.base>>4,media=media);floppy.cpu=m.cpu
    source=getattr(m,'native_model',None)
    if getattr(m,'external_FDC',None):
        floppy.fdc_dor=m.external_FDC['dor'];floppy.positions=list(m.external_FDC['positions'])
    if source is not None:
        floppy.fdc_dor=getattr(source,'fdc_dor',getattr(source,'ports',{}).get('dor',floppy.fdc_dor))
        if hasattr(source,'positions'):floppy.positions=list(source.positions)
    incoming,outgoing=m.bus.input,m.bus.output
    def inp(port,size):
        if port in (0x3F4,0x3F5,0x3F7):return floppy.port_in(m.cpu,port,size,None)
        return incoming(port,size)
    def out(port,size,value):
        if port in (4,5,0x0A,0x0B,0x0C,0x81,0x3F2,0x3F5,0x3F7):floppy.port_out(m.cpu,port,size,value,None);return True
        return outgoing(port,size,value)
    m.bus.input,m.bus.output=inp,out
    # The established FDC/DMA fixture's external IRQ and timer delivery. Both
    # events enter the actual produced IVT; no firmware wait is replaced.
    def event(cpu,address,size,unused):
        if floppy.fdc_irq and cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200:
            floppy.fdc_irq=False;legacy.rtc.Clock.interrupt(floppy,cpu,0x0E,None)
        elif address>=0xE0000 and size==1 and bytes(cpu.mem_read(address,1))==b'\xF4':
            cpu.reg_write(x.UC_X86_REG_IP,(cpu.reg_read(x.UC_X86_REG_IP)+1)&65535)
            legacy.rtc.Clock.interrupt(floppy,cpu,8,None)
    hook=m.cpu.hook_add(UC_HOOK_CODE,event)
    return floppy,hook


def runtime_handoff_floppy(port,post):
    m=runtime_clone_post(post)
    start,end=m.runtime_post_intervals;count=min(min(end,m.base)-start,0xFFF0)//2
    loader=runtime_assemble(port,'floppy-reuse-loader',f'''bits 16
org 7C00h
mov ax,{start>>4}
mov es,ax
mov di,{start&15}
mov cx,{count}
mov ax,0A7A7h
rep stosw
xor ax,ax
mov ds,ax
mov word [6F2h],0F10Fh
int 18h
hlt
times 510-($-$$) db 0
dw 0AA55h
''')
    floppy,hook=runtime_floppy_device(m,loader*18)
    m.put('C_BOOT',b'\x01');m.put('C_BOOT_SECOND',b'\x04')
    try:result=runtime_execute_boot(m,fdc_attached=True)
    finally:m.cpu.hook_del(hook)
    assert m.cpu.mem_read(0x6F2,2)==b'\x0F\xF1'
    assert m.cpu.mem_read(0x6F0,2)==b'\x02\0'
    assert result['handoffs'][0]==(0,0xF000,m.listing.symbol('pnp_installation'))
    assert result['handoffs'][-1][0]==0x81
    assert any(row[0]==0x46 for row in floppy.fdc_log)
    assert m.cpu.mem_read(start,count*2)==b'\xA7'*(count*2)
    result.update(actual_FDC_DMA_read_and_loader_INT18=True,actual_FDC_commands=floppy.fdc_log,
                  released_journal_overwritten=[start,count*2],later_distinct_provider=True)
    return result


def runtime_buffer_native_floppy(port,m):
    cd,disk=runtime_native_device(m)
    ata_payload=bytes((n*37+0x29)&255 for n in range(512))
    fdc_payload=bytes((n*17+0x53)&255 for n in range(512))
    disk.disk_words.update({(0,n):word for n,word in enumerate(struct.unpack('<256H',ata_payload))})
    floppy,hook=runtime_floppy_device(m,fdc_payload*18)
    base,size=m.base,m.allocated;before=bytes(m.cpu.mem_read(base,size))
    prefix=int.from_bytes(before[0x334:0x338],'little')
    def preserved():
        after=bytes(m.cpu.mem_read(base,size))
        assert after[prefix:]==before[prefix:]
        assert after[0x27A:0x27D]==before[0x27A:0x27D]
        assert after[0x2F0:0x33C]==before[0x2F0:0x33C]
    tested=[]
    def poison(address):
        bounds=(bytes(m.cpu.mem_read(address-16,16)),bytes(m.cpu.mem_read(address+512,16)))
        m.cpu.mem_write(address,b'\xE7'*512)
        return bounds
    def transferred(address,drive,trace,bounds):
        expected=ata_payload if drive==0x80 else fdc_payload
        assert bytes(m.cpu.mem_read(address,512))==expected,(port,drive,'adjacent payload')
        assert (bytes(m.cpu.mem_read(address-16,16)),bytes(m.cpu.mem_read(address+512,16)))==bounds
        if drive==0x80:
            commands=disk.taskfiles[trace:]
            assert len(commands)==1 and commands[0][0]==0 and commands[0][1] in (0x20,0xC4) and commands[0][2:]==(0,1),commands
            assert disk.transfer_words==256
        else:
            commands=floppy.fdc_log[trace:]
            assert any(row[0]==0x46 and row[4]==1 for row in commands),commands
            assert floppy.dma_address==address and floppy.dma_count==511
            assert floppy.transferred==expected
        return {'full_512byte_payload_sha256':hashlib.sha256(expected).hexdigest(),
                'actual_read_commands':commands,'PIO_words':256 if drive==0x80 else None,
                'actual_DMA_address':address if drive==0 else None,'DMA_bytes':512 if drive==0 else None,
                'separately_poisoned_destination_and_boundary_canaries':True}
    try:
        for drive in (0x80,0):
            for address,reject in ((base+prefix,True),(base-512,False)):
                m.caller_buffers=[] if reject else [(address,address+512)]
                trace=len(disk.taskfiles) if drive==0x80 else len(floppy.fdc_log)
                bounds=None if reject else poison(address)
                carry,ax=cd.api(m,2,al=1,dl=drive,bx=address&15,es=address>>4)
                assert carry==reject,(port,drive,hex(address),carry,hex(ax),floppy.fdc_log,floppy.fdc_senses,floppy.positions)
                if reject:assert trace==(len(disk.taskfiles) if drive==0x80 else len(floppy.fdc_log))
                accepted=None if reject else transferred(address,drive,trace,bounds)
                preserved()
                tested.append({'drive':drive,'address':address,'rejected':reject,'AX':ax,'accepted_transfer':accepted})
        # Native EDD transfer and parameter output share the actual advertised
        # range guard; keep their real parameter blocks and installed INT13.
        for address,reject in ((base+prefix,True),(base-512,False)):
            m.caller_buffers=[] if reject else [(address,address+512)]
            trace=len(disk.taskfiles);bounds=None if reject else poison(address)
            m.cpu.mem_write(0x20500,struct.pack('<BBHHHQ',16,0,1,address&15,address>>4,0))
            carry,ax=cd.api(m,0x42,dl=0x80,ds=0x2000,si=0x500)
            assert carry==reject,(port,'EDD',address,carry,hex(ax))
            if reject:assert trace==len(disk.taskfiles)
            accepted=None if reject else transferred(address,0x80,trace,bounds)
            preserved()
            tested.append({'owner':'EDD','address':address,'rejected':reject,'AX':ax,'accepted_transfer':accepted})
    finally:m.cpu.hook_del(hook);m.caller_buffers=[]
    return {'actual_native_CHS_EDD_and_FDC_DMA_owners':tested,'complete_provider_tail_policy_controls_APM_preserved':True}



def runtime_parameter_buffers(port,post):
    m=runtime_clone_post(post);cd,disk=runtime_native_device(m)
    # Independent external ATA input:131072 sectors,16 heads,63 sectors/track.
    # The produced fixture saves Auto translation, whose established small-LBA
    # logical geometry is32 heads/63 sectors (different from raw IDENTIFY).
    # This medium holds65 complete logical cylinders. No BIOS record or output
    # supplies these expectations; ATA sectors in this device are512 bytes.
    identify=disk.payloads[0]
    assert (struct.unpack_from('<H',identify,6)[0],struct.unpack_from('<H',identify,12)[0],
            struct.unpack_from('<I',identify,120)[0])==(16,63,131072)
    expected=struct.pack('<HHIIIQH',26,2,65,32,63,131072,512)
    relative=int.from_bytes(m.cpu.mem_read(m.base+0x334,4),'little')
    tail=bytes(m.cpu.mem_read(m.base+relative,m.allocated-relative))
    results=[]
    for address,reject in ((m.base+m.allocated-2,True),(m.base-26,False)):
        # The required input size word occupies only aligned tail padding in
        # the refusal case; compare the complete caller-supplied pre-call bytes.
        length=2 if reject else 26
        original=bytes(m.cpu.mem_read(address,length))
        boundaries=None if reject else (bytes(m.cpu.mem_read(address-16,16)),bytes(m.cpu.mem_read(address+26,16)))
        m.cpu.mem_write(address,struct.pack('<H',26)+(b'' if reject else b'\xE7'*24))
        before=bytes(m.cpu.mem_read(m.base+relative,m.allocated-relative))
        m.caller_buffers=[] if reject else [(address,address+26)]
        carry,ax=cd.api(m,0x48,dl=0x80,ds=address>>4,si=address&15)
        assert carry==reject,(port,address,carry,hex(ax))
        assert bytes(m.cpu.mem_read(m.base+relative,m.allocated-relative))==before
        output=None
        if not reject:
            output=bytes(m.cpu.mem_read(address,26))
            assert output==expected,(port,'AH48 actual parameters',output.hex(),expected.hex())
            assert (bytes(m.cpu.mem_read(address-16,16)),bytes(m.cpu.mem_read(address+26,16)))==boundaries
        m.cpu.mem_write(address,original)
        assert bytes(m.cpu.mem_read(m.base+relative,m.allocated-relative))==tail
        results.append({'buffer':address,'rejected':reject,'AX':ax,'complete_output':output.hex() if output else None,
                        'independent_geometry_capacity_sector_size':None if reject else [65,32,63,131072,512],
                        'poisoned_non_input_bytes_and_preserved_canaries':not reject})
    m.caller_buffers=[]
    return {'actual_AH48':results,'complete_runtime_tail_preserved':True}


def runtime_relocated_buffer_apis(port,post):
    import copy
    m=runtime_clone_post(post)
    old,size=m.base,m.allocated;new=0x60000
    m.cpu.mem_write(new,bytes(m.cpu.mem_read(old,size)))
    m.cpu.mem_write(0x40E,struct.pack('<H',new>>4));m.cpu.mem_write(0x413,struct.pack('<H',new>>10))
    m.cpu.mem_write(old,b'\xA7'*size);m.base=new;m.allocated=size
    snapshot=bytes(m.cpu.mem_read(0,0x100000));metadata=copy.deepcopy(post.post_seed[1])
    metadata['snapshot_sha256']=hashlib.sha256(snapshot).hexdigest()
    m.post_seed=(snapshot,metadata,*post.post_seed[2:])
    m.cpu.mem_write(0x1500,bytes.fromhex('CD12A3B006B800C1CD158C06B206F4'))
    for reg,value in dict(CS=0,IP=0x1500,DS=0,SS=0,SP=0x7000,EFLAGS=0x202).items():
        m.cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
    m.cpu.emu_start(0x1500,0x150F,count=100000)
    kib,segment=struct.unpack('<HH',m.cpu.mem_read(0x6B0,4))
    assert kib==new>>10 and segment==new>>4,(port,kib,segment,new>>10,new>>4,
        bytes(m.cpu.mem_read(0x48,4)).hex(),bytes(m.cpu.mem_read(0x413,2)).hex())
    assert m.cpu.mem_read(new,1)[0]*1024==size
    old_reads=[]
    def read(cpu,access,address,length,value,unused):
        if old<=address<old+size:old_reads.append(address)
    hook=m.cpu.hook_add(UC_HOOK_MEM_READ,read)
    try:transfers=runtime_buffer_native_floppy(port,m)
    finally:m.cpu.hook_del(hook)
    parameters=runtime_parameter_buffers(port,m)
    assert not old_reads and m.cpu.mem_read(old,size)==b'\xA7'*size
    return {'actual_INT12_KiB':kib,'actual_C1_segment':segment,'actual_BDA_base':new,
            'advertised_bytes':size,'copied_only_advertised_region':True,
            'native_CHS_EDD_FDC':transfers,'native_AH48':parameters,
            'old_region_poisoned_and_unused':True}

def runtime_handoff_cd(port,post,media=0,action='int19',expected_native_fdpt=None,external_fdpt=None):
    m=runtime_clone_post(post);cd,disk=runtime_native_device(m)
    image=cd.disc(media=media)
    read=("mov si,dap\nmov ax,4200h\nint 13h\n" if media==0 else
          "mov ax,0201h\nmov cx,2\nint 13h\n")
    loader=runtime_assemble(port,f'cd-loader-{media}-{action}',f'''bits 16
org 7C00h
xor ax,ax
mov ds,ax
mov [6F8h],dl
mov ax,2000h
mov es,ax
xor bx,bx
{read}
pushf
pop word [6F6h]
mov [6F4h],ax
mov word [6F2h],5678h
int {"18h" if action=='int18' else "19h"}
hlt
dap: db 16,0
dw 1,0,2000h
dq 22
times 510-($-$$) db 0
dw 0AA55h
''')
    image[21*2048:21*2048+512]=loader;disk.images[1]=image
    m.put('C_BOOT',b'\x03');m.put('C_BOOT_SECOND',b'\x04')
    native_hook=bytes(m.cpu.mem_read(0x4C,4));native_fdpt=bytes(m.cpu.mem_read(0x104,4))
    if expected_native_fdpt is not None:native_fdpt=expected_native_fdpt
    first_bcv=0xC8000+int.from_bytes(m.cpu.mem_read(0xC8076,2),'little');clean=[]
    def code(cpu,address,size,unused):
        if address==first_bcv:
            assert bytes(cpu.mem_read(0x4C,4))==native_hook
            assert bytes(cpu.mem_read(0x104,4))==native_fdpt
            if external_fdpt is not None:assert bytes(cpu.mem_read(0x118,4))==external_fdpt
            assert cpu.mem_read(m.base+0x298,1)==b'\0'
            assert cpu.mem_read(0x475,1)==b'\x01'
            clean.append(True)
    h=m.cpu.hook_add(UC_HOOK_CODE,code)
    floppy,fdc_hook=runtime_floppy_device(m,None)
    try:result=runtime_execute_boot(m,fdc_attached=True)
    finally:
        m.cpu.hook_del(h)
        m.cpu.hook_del(fdc_hook)
    drive=0xE0 if media==0 else 0
    assert m.cpu.mem_read(0x6F2,2)==b'\x78\x56'
    assert m.cpu.mem_read(0x6F8,1)==bytes((drive,))
    assert int.from_bytes(m.cpu.mem_read(0x6F6,2),'little')&1==0
    expected=image[22*2048:23*2048] if media==0 else image[21*2048+512:21*2048+1024]
    assert m.cpu.mem_read(0x20000,len(expected))==expected
    assert clean==[True]
    assert result['handoffs'][0]==(drive,0xF000,m.listing.symbol('pnp_installation'))
    assert result['handoffs'][-1][0]==0x81 and m.cpu.mem_read(0x6F0,2)==b'\x02\0'
    result.update(media=media,actual_packet_catalog_image_and_separate_RETF=True,
                  actual_loaded_image_INT13_read_and_loader_interrupt=action,
                  prior_native_hook_FDPT_and_count_restored_before_next_BCV=True,
                  packet_commands=[(u,p.hex()) for u,p in disk.packet_log])
    return result


def runtime_buffer_cd(port,post):
    results=[]
    for bad_load in (False,True):
        m=runtime_clone_post(post);cd,disk=runtime_native_device(m)
        base,size=m.base,m.allocated;relative=int.from_bytes(m.cpu.mem_read(base+0x334,4),'little')
        protected=bytes(m.cpu.mem_read(base+relative,size-relative))
        disk.images[1]=cd.disc(media=0,segment=(base+relative)>>4 if bad_load else 0)
        m.put('C_BOOT',b'\x03');m.put('C_BOOT_SECOND',b'\x04')
        reached=[]
        def first(cpu,address,length,unused):reached.append(True);cpu.emu_stop()
        h=m.cpu.hook_add(UC_HOOK_CODE,first,None,0x7C00,0x7C00)
        floppy,fdc_hook=runtime_floppy_device(m,None)
        try:
            for reg,value in dict(CS=0xF000,DS=0,ES=0,FS=base>>4,SS=0,SP=0x7000,EFLAGS=0x202).items():m.cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
            m.cpu.emu_start(0xF0000+m.listing.symbol('int19'),0xFFFFF,count=8000000)
        finally:
            m.cpu.hook_del(h)
            m.cpu.hook_del(fdc_hook)
        after=bytes(m.cpu.mem_read(base+relative,size-relative))
        assert reached and after[:8]==protected[:8] and after[40:48]==protected[40:48] and after[50:52]==protected[50:52] and after[60:]==protected[60:],(bad_load,reached,
            [(i,a,b) for i,(a,b) in enumerate(zip(protected,after)) if a!=b][:20],
            hex(m.cpu.reg_read(x.UC_X86_REG_CS)),hex(m.cpu.reg_read(x.UC_X86_REG_IP)))
        if bad_load:
            count=int.from_bytes(after[4:8],'little')
            assert int.from_bytes(after[8:12],'little')==count and int.from_bytes(after[12:16],'little')==count and after[16]==3
            assert m.cpu.reg_read(x.UC_X86_REG_DL)==0x81
            assert m.cpu.mem_read(base+0x298,1)==b'\0'
            results.append({'catalog_load_overlaps_tail':True,'actual_fallback_provider_DL':0x81})
            continue
        assert m.cpu.mem_read(base+0x298,1)==b'\x01'
        for address,reject in ((base+relative,True),(base-2048,False)):
            m.caller_buffers=[] if reject else [(address,address+2048)]
            before=len(disk.packet_log)
            m.cpu.mem_write(0x20500,struct.pack('<BBHHHQ',16,0,1,address&15,address>>4,22))
            carry,ax=cd.api(m,0x42,dl=0xE0,ds=0x2000,si=0x500)
            assert carry==reject,(port,'CD',address,carry,hex(ax))
            if reject:assert len(disk.packet_log)==before
            after=bytes(m.cpu.mem_read(base+relative,size-relative))
            assert after[:8]==protected[:8] and after[40:48]==protected[40:48] and after[50:52]==protected[50:52] and after[60:]==protected[60:]
            results.append({'public_CD_buffer':address,'rejected':reject,'AX':ax})
        m.caller_buffers=[]
    return {'actual_catalog_load_and_public_CD_guard':results,'complete_runtime_tail_preserved':True}


def runtime_media(port,post=None):
    if post is None:post=runtime_startup_snapshot(port)
    result={'actual_startup':post.startup_evidence}
    work=ROOT/port/OUTPUT/'runtime-media-results.json'
    work.write_text(json.dumps(result,indent=2))
    checks=(('native_floppy_buffers',lambda:runtime_buffer_native_floppy(port,runtime_clone_post(post))),
            ('native_parameters',lambda:runtime_parameter_buffers(port,post)),
            ('native',lambda:runtime_handoff_native(port,runtime_clone_post(post))),
            ('floppy',lambda:runtime_handoff_floppy(port,post)),
            ('CD_E0',lambda:runtime_handoff_cd(port,post)),
            ('CD_00',lambda:runtime_handoff_cd(port,post,2,'int18')),
            ('CD_buffers',lambda:runtime_buffer_cd(port,post)))
    for name,check in checks:
        print(port,'runtime',name,file=sys.stderr,flush=True)
        result[name]=check();work.write_text(json.dumps(result,indent=2))
    return result


def runtime_reset(port,cad=False,used=False):
    policy=bytearray(15);struct.pack_into('<H',policy,0,1<<5);policy[2]=1<<3
    struct.pack_into('<HH',policy,3,0x350,8);struct.pack_into('<H',policy,11,1<<5);policy[14]=1
    options={};phase=[]
    if used:
        from shared.tools.isa_pnp_proof import Card,serial
        cards=[]
        for n,base in enumerate((0x330,0x338)):
            stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B'+struct.pack('<HB',base,8)+b'\x79\0'
            cards.append(Card(serial(b'\x41\xD0\xFF\xFF',n+1),stream,powerup_active=True))
        def completed(port,model,cpu,listing,bus):
            base=int.from_bytes(cpu.mem_read(0x40E,2),'little')<<4
            relative=int.from_bytes(cpu.mem_read(base+0x334,4),'little')
            header=bytes(cpu.mem_read(base+relative,60));count=int.from_bytes(header[4:8],'little')
            assert header[8:19]==bytes(11),('stale cursor/connection',header.hex())
            assert header[20:40]==bytes(20) and header[52:60]==bytes(8)
            records=[bytes(cpu.mem_read(base+relative+60+n*24,24)) for n in range(count)]
            providers=[r for r in records if int.from_bytes(r[:2],'little') in (0xC800,0xC900)]
            assert len(providers)==2 and [int.from_bytes(r[10:12],'little') for r in providers]==[0x120]*2
            assert all(cpu.mem_read(vector+2,2)==b'\0\xF0' for vector in (0x4C,0x60,0x64))
            assert len(bus.cards)==2 and bus.read_port!=0x203 and all(c.registers[0][0x30] for c in bus.cards)
            public=runtime_public_current(port,model,cpu,listing,bus)
            boot=runtime_boot_current(port,model,cpu,listing,bus,2,handoff_count=2)
            after=bytes(cpu.mem_read(base+relative,60))
            assert struct.unpack_from('<II',after,8)==(3,3) # Selected VGA is a non-IPL first record.
            assert after[16]&3==3 and cpu.mem_read(0x475,1)==b'\x02'
            result={'fresh_header_before_attempt':header.hex(),'fresh_provider_relationships':[r.hex() for r in records],
                'same_CPU_public_calls':public,'actual_attempts_then_noninitial_connection':boot,
                'used_header_before_next_reset':after.hex(),'actual_ISA':[{'identity':c.identity.hex(),'CSN':c.csn,'registers':c.registers} for c in bus.cards]}
            phase.append(result);return result
        options=dict(cards=cards,rom_images=((0xC800,runtime_provider(port,0,'int18')),
            (0xC900,runtime_provider(port,1,witness_port=0xE9))),boot_order=(4,0,0,0),
            post_action=completed,bad_read_ports={0x203:'no-pair'},expect_active=True)
    post=runtime_startup_snapshot(port,phases=(False,True,True),policy=policy,relocate_first=True,
                                  snapshot_name='p3-used-reset-post' if used else 'runtime-reset-post',actual_cad=cad,**options)
    result=post.startup_evidence
    assert len(result['snapshots'])==len(result['finish_observations'])==3
    budgets=result['actual_before_module_available_KiB']
    assert len(budgets)==3 and len(set(budgets))==1,budgets
    assert result['actual_ROM_initializations']==[3,3],result['actual_ROM_initializations']
    sizes=[r['advertised_runtime_KiB'] for r in result['finish_observations']]
    ceilings=[r['restored_conventional_KiB'] for r in result['finish_observations']]
    assert len(set(sizes))==len(set(ceilings))==1,(sizes,ceilings)
    assert all(r['runtime_published'] for r in result['finish_observations'])
    assert result['external_relocation_between_POST_and_reset']
    expected=bytearray(policy);expected[14]=0
    if used:
        saved=settings.Settings(port,OUTPUT);saved.cmos[:]=bytes.fromhex(result['cmos'])
        assert decode_saved(saved)[0]['C_PNP']==expected
    else:assert decode_saved(post)[0]['C_PNP']==expected
    return {'cold_plus_two_actual_warm_startups':result,'actual_CtrlAltDel_first_reset':cad,'stable_original_budget_and_runtime_extent':True,
            'relocated_old_instance_ended_and_complete_fresh_provider_set':True,'saved_manual_policy_preserved':True,
            'actual_used_state_multicard_phases':phase}


def runtime_retry(port,post=None):
    if post is None:post=runtime_startup_snapshot(port,actions=('cf','retry'),snapshot_name='runtime-retry-post')
    m=runtime_clone_post(post)
    floppy,fdc_hook=runtime_floppy_device(m,None)
    for field,value in (('C_BOOT',4),('C_BOOT_SECOND',0),('C_BOOT_THIRD',0),('C_BOOT_FOURTH',0)):
        m.put(field,bytes((value,)))
    m.runtime_kbc_queue.append(0x1E) # Arrived before the exhausted retry epoch.
    assert runtime_execute_boot(m,fdc_attached=True)['terminal']=='retry'
    before=[struct.unpack('<16H',m.cpu.mem_read(0x900+n*32,32))[:3] for n in range(2)]
    assert before==[(1,1,1),(1,1,1)],before
    m.cpu.mem_write(0x6EF,b'\x01') # External media becomes readable; no BIOS change.
    waits=[];loaded=[];forbidden=[]
    lo,hi=m.runtime_post_intervals
    def code(cpu,address,length,unused):
        if lo<=address<hi:forbidden.append(address)
        if address==0x7C00:loaded.append(cpu.reg_read(x.UC_X86_REG_DL))
        if bytes(cpu.mem_read(address,1))==b'\xF4':
            if address>=0xF0000:waits.append(address)
            cpu.emu_stop()
    h=m.cpu.hook_add(UC_HOOK_CODE,code)
    try:
        def run(count=2000000):
            at=(m.cpu.reg_read(x.UC_X86_REG_CS)<<4)+m.cpu.reg_read(x.UC_X86_REG_IP)
            m.cpu.emu_start(at,0xFFFFF,count=count)
        run()
        assert waits and not loaded
        for _ in range(2):
            # Real IRQ0 wakes HLT; time and media alone cannot consume the gate.
            m.cpu.reg_write(x.UC_X86_REG_IP,m.cpu.reg_read(x.UC_X86_REG_IP)+1)
            assert m.runtime_interrupt(m.cpu,8)
            run()
            assert not loaded and [struct.unpack('<16H',m.cpu.mem_read(0x900+n*32,32))[:3] for n in range(2)]==before
        m.runtime_kbc_queue.append(0x30)
        m.cpu.reg_write(x.UC_X86_REG_IP,m.cpu.reg_read(x.UC_X86_REG_IP)+1)
        assert m.runtime_interrupt(m.cpu,9)
        run(8000000)
    finally:
        m.cpu.hook_del(h)
        m.cpu.hook_del(fdc_hook)
    assert loaded==[0x81] and m.cpu.mem_read(0x6F0,2)==b'\x02\0',(loaded,waits,
        hex(m.cpu.reg_read(x.UC_X86_REG_CS)),hex(m.cpu.reg_read(x.UC_X86_REG_IP)),
        bytes(m.cpu.mem_read(0x417,0x27)).hex(),m.runtime_kbc_queue,
        [struct.unpack('<16H',m.cpu.mem_read(0x900+n*32,32))[:3] for n in range(2)])
    after=[struct.unpack('<16H',m.cpu.mem_read(0x900+n*32,32))[:3] for n in range(2)]
    assert after==[(1,2,2),(1,2,1)],after
    assert not forbidden
    return {'actual_startup':post.startup_evidence,'stale_scan_and_two_timer_wakes_did_not_retry':True,
            'fresh_IRQ1_INT16_reopened_once':True,'before':before,'after':after,'actual_DL':loaded,
            'no_POST_reinitialization_or_private_fetch':True}


def runtime_capacity(port,baseline):
    from shared.tools.isa_pnp_proof import Card,serial
    initial=baseline.startup_evidence['placement_observations'][0]
    assert initial['actual_LDN_count']==initial['stored_LDN_count']==0
    kib=initial['original_KiB']
    # The authored producers are selectedC000 plus two independent C800/C900
    # images. Their three extent claims occur after census; each image retains
    # one28B record. Baseline is an actual normal memory/placement producer.
    before_census=initial['journal_cursor']+3*32
    relative=int.from_bytes(baseline.cpu.mem_read(baseline.base+0x334,4),'little')
    prefix=baseline.cpu.mem_read(baseline.base+relative+19,1)[0]*1024
    staging=(prefix+60+3*24+1023)&~1023
    def fits(amount):
        cursor=before_census
        def take(size):
            nonlocal cursor
            candidate=cursor-size
            if port=='pb430' and candidate<0x40000 and cursor>0x20000:candidate=0x20000-size
            cursor=candidate
            return cursor>=0x10000
        groups=[];remaining=amount
        while remaining:
            count=min(remaining,256);identity=serial(b'\x41\xD0\xFF\xFF',len(groups)+1)
            groups.append((tuple((byte>>bit)&1 for byte in identity for bit in range(8)),count));remaining-=count
        for _,count in sorted(groups,reverse=True):
            if not take(32):return False
            for _ in range(count):
                if not take(564):return False
        for _ in range(3):
            if not take(32):return False
        for _ in range(3):
            if not take(28):return False
        return take(staging)
    maximum=0
    while fits(maximum+1):maximum+=1
    results=[]
    for amount in (maximum,maximum+1):
        remaining=amount;cards=[]
        while remaining:
            count=min(remaining,256)
            stream=b'\x0A\x10\0\x82\x03\0ISA'+b'\x15\x41\xD0\x05\0\0'*count+b'\x79\0'
            cards.append(Card(serial(b'\x41\xD0\xFF\xFF',len(cards)+1),stream,ldns=count,powerup_active=True));remaining-=count
        policy=bytearray(15);policy[13:]=b'\x01\x01'
        print(port,'runtime capacity',amount,'LDNs',file=sys.stderr,flush=True)
        post=runtime_startup_snapshot(port,cards=cards,policy=policy)
        evidence=post.startup_evidence;observed=evidence['placement_observations'][0]
        root=bytes.fromhex(evidence['actual_complete_P2_roots_before_finish'][0])
        assert observed['actual_LDN_count']==observed['stored_LDN_count']==amount
        assert observed['reconstruction_status']==root[19]==0,'Earlier P2 failure cannot stand in for retention capacity'
        assert int.from_bytes(root[24:28],'little')==amount
        assert all(not row[0x30] for card in cards for row in card.registers.values())
        fit=amount==maximum
        finish=evidence['finish_observations'][0]
        assert finish['runtime_published']==fit,(port,amount,maximum,finish)
        assert bool(evidence['actual_incomplete_notice_entries'])==(not fit)
        assert decode_saved(post)[0]['C_PNP'][14]==int(not fit)
        if fit:
            relative=int.from_bytes(post.cpu.mem_read(post.base+0x334,4),'little')
            assert post.cpu.mem_read(post.base+relative,8)==b'PNP3\x03\0\0\0'
            post.put('C_BOOT',b'\x04')
            result=runtime_execute_boot(post)
            assert result['terminal']=='loader' and post.cpu.mem_read(0x6F0,2)==b'\x02\0'
        else:
            assert not any(post.cpu.mem_read(post.base+0x334,8))
            assert post.get('C_ERROR')[0]&0x40
        results.append({'LDNs':amount,'cards':len(cards),'P2_complete':True,'runtime_fit':fit,
                        'actual_startup_finish':evidence,'pending_Clear':int(not fit)})
    return {'actual_normal_memory_KiB':kib,'LDN_bytes':564,'card_bytes':32,
            'complete_prefix_bytes':prefix,'separately_charged_staging_bytes':staging,
            'temporary_instance_bytes':3*28,'last_fit_LDNs':maximum,'first_excess_LDNs':maximum+1,
            'existing_scratch_exclusion':[0x20000,0x40000] if port=='pb430' else None,'cases':results}


def runtime_provider_set(port):
    results={}
    for name,actions in (('empty',()),('one',('boot',)),('A1_A2',('cf','cf')),('A1_A2_B',('cf','cf','boot'))):
        m=runtime_external_machine(port,actions)
        relative=int.from_bytes(m.cpu.mem_read(m.base+0x334,4),'little')
        assert int.from_bytes(m.cpu.mem_read(m.base+relative+4,4),'little')==len(actions)
        result=runtime_execute_boot(m)
        expected='loader' if actions and actions[-1]=='boot' else 'retry'
        assert result['terminal']==expected
        rows=[struct.unpack('<16H',m.cpu.mem_read(0x900+n*32,32)) for n in range(len(actions))]
        assert all(row[:3]==(1,1,int(action!='boot')) for row,action in zip(rows,actions)),rows
        if expected=='loader':assert int.from_bytes(m.cpu.mem_read(0x6F0,2),'little')==len(actions)
        result.update(equal_product_IDs_distinct_instances=True,complete_count=len(actions),witnesses=rows)
        results[name]=result
    return results



def runtime_legacy(port):
    results={}
    for action in ('return','int18','boot'):
        source="""bits 16
org 0
db 55h,0AAh,4
jmp init
times 1Ah-($-$$) db 0
dw 0
init:
push ds
xor ax,ax
mov ds,ax
inc word [700h]
mov word [64h],chain
mov [66h],cs
pop ds
retf
chain:
push ds
xor ax,ax
mov ds,ax
inc word [702h]
pop ds
"""
        source+=('retf\n' if action=='return' else 'int 18h\n' if action=='int18' else
                 'xor ax,ax\nmov ds,ax\nmov word [6F0h],3\nhlt\n')
        source+='times 2048-($-$$) db 0\n'
        raw=bytearray(runtime_assemble(port,'legacy-chain-'+action,source));raw[-1]=(-sum(raw))&255
        m=runtime_external_machine(port,('cf','cf'),images=(runtime_provider(port,0,'cf'),bytes(raw)))
        if action=='boot':m.runtime_loader_halts=(0xC9000+raw.index(0xF4,0x1C),)
        result=runtime_execute_boot(m)
        assert struct.unpack('<2H',m.cpu.mem_read(0x700,4))==(1,1)
        assert struct.unpack('<3H',m.cpu.mem_read(0x900,6))==(1,1,1)
        assert result['terminal']==('loader' if action=='boot' else 'retry'),result
        if action=='boot':assert m.cpu.mem_read(0x6F0,2)==b'\x03\0'
        result['captured_legacy_chain_only_after_Other_providers']=True
        result['return_or_active_INT18_advances_without_cycle']=action!='boot'
        results[action]=result
    return results

def runtime_bev(port):
    results={}
    for name,indicators,status,bcv,bev in (('eligible',4,0x20,False,True),('not_IPL',0,0x20,False,True),
        ('block_no_BCV',4,0x120,False,True),('null_BEV',4,0x20,False,False),('both_vectors',4,0x20,True,True),
        ('no_attached_IPL',4,0,False,True),('unknown_IPL',4,0x10,False,True),
        ('eligible_INT18',4,0x20,False,True),('eligible_INT19',4,0x20,False,True),('block_both_vectors',4,0x120,True,True)):
        cause='int18' if name.endswith('INT18') else 'int19' if name.endswith('INT19') else 'return'
        image=runtime_provider(port,0,action='cf',bcv=bcv,bev=bev,status=status,indicators=indicators,bev_action=cause)
        m=runtime_external_machine(port,('cf','boot'),images=(image,runtime_provider(port,1)))
        result=runtime_execute_boot(m)
        row=struct.unpack('<16H',m.cpu.mem_read(0x900,32))
        eligible=name in ('eligible','unknown_IPL','eligible_INT18','eligible_INT19')
        block=name=='block_both_vectors'
        assert row[:4]==(1,int(block),int(block),int(eligible)),(name,row)
        if eligible:assert row[4:9]==(0,0xFFFF,0xFFFF,0xF000,m.listing.symbol('pnp_installation')),(name,row)
        if block:assert row[4:9]==(4,0xFFFF,0xFFFF,0xF000,m.listing.symbol('pnp_installation')) and row[10]>0
        assert m.cpu.mem_read(0x6F0,2)==b'\x02\0'
        result['first_BEV_called']=eligible;result['first_connection_or_disconnect']=block
        result['BEV_context']=row[4:9] if eligible else None;result['BEV_cause']=cause
        result['block_BCV_precedes_BEV']=block
        results[name]=result
    return results


def runtime_isa_association_case(port,first_present):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    cards=[];images=[];bases=(0xC8000,0xC9000)
    for n,base in enumerate(bases):
        memory=b'\x86\x09\0\x44'+struct.pack('<II',base,2048)
        stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01'+memory+b'\x79\0'
        cards.append(Card(serial(b'\x41\xD0\x05\0',n+1),stream,powerup_active=True,memory_upper=True))
        images.append(runtime_provider(port,n,status=0x120 if n or first_present else 0,init_witness=True))
    bus=Bus(cards,{0x203:'no-pair'});bus.pause=False;m=isa_machine(port,bus,OUTPUT)
    visibility=[]
    def mapped(cpu,access,address,length,value,unused):
        for n,base in enumerate(bases):
            if base<=address<base+2048:
                regs=cards[n].registers[0]
                actual=int.from_bytes(bytes(regs.get(at,0) for at in range(0x76,0x7A)),'big') if 0x76 in regs else base
                responds=bool(regs[0x30] and actual==base)
                visibility.append((n,responds))
                cpu.mem_write(address,images[n][address-base:address-base+length] if responds else b'\xFF'*length)
                return
    h=m.cpu.hook_add(UC_HOOK_MEM_READ,mapped,None,bases[0],bases[-1]+2047)
    try:
        m.cpu.mem_write(0xD0000,runtime_provider(port,2,init_witness=True))
        m.call('settings_load');m.call('setup_defaults');m.draft()
        for field,value in (('U_BOOT',4),('U_BOOT_SECOND',0),('U_BOOT_THIRD',0),('U_BOOT_FOURTH',0)):m.put(field,bytes((value,)))
        assert m.call('settings_save')
        if port!='m919':m.call('pnp_journal_release')
        m.call('pnp_early');m.call('option_rom_discovery');m.call('pnp_finish_entry')
        m.base=int.from_bytes(m.cpu.mem_read(0x40E,2),'little')<<4
        # Install the actual resident disk handler for the boot reset service;
        # this allocator-entry fixture has not run the POST IVT initializer.
        m.cpu.mem_write(0x4C,struct.pack('<HH',m.listing.symbol('int13'),0xF000))
        runtime_attach_interrupts(m)
        boot=runtime_execute_boot(m)
        expected=1 if first_present else 2
        assert boot['terminal']=='loader' and m.cpu.mem_read(0x6F0,2)==expected.to_bytes(2,'little')
        rows=[struct.unpack('<16H',m.cpu.mem_read(0x900+n*32,32)) for n in range(2)]
        assert [row[1] for row in rows]==([1,0] if first_present else [0,1])
        selected=0 if first_present else 1
        assert rows[selected][4:9]==(4,cards[selected].csn,bus.read_port,0xF000,m.listing.symbol('pnp_installation'))
    finally:m.cpu.hook_del(h)
    assert bus.read_port!=0x203
    observed=[]
    for n,card in enumerate(cards):
        assert card.registers[0][0x30]==1
        ax,bx,dx,es,di=struct.unpack('<5H',m.cpu.mem_read(0x600+n*16,10))
        assert (ax,bx,dx,es,di)==(0xFFFF,card.csn,bus.read_port,0xF000,m.listing.symbol('pnp_installation'))
        observed.append({'serial':card.identity.hex(),'external_actual_CSN':card.csn,'init_BX':bx,'init_DX':dx})
    assert struct.unpack('<3H',m.cpu.mem_read(0x620,6))==(0xFFFF,0xFFFF,bus.read_port)
    base=int.from_bytes(m.cpu.mem_read(0x40E,2),'little')<<4
    offset=int.from_bytes(m.cpu.mem_read(base+0x334,4),'little')
    records=bytes(m.cpu.mem_read(base+offset+60,72))
    assert [struct.unpack_from('<H',records,n*24+10)[0] for n in range(3)]==[0x120 if first_present else 0,0x120,0x120]
    assert [struct.unpack_from('<H',records,n*24+16)[0] for n in range(3)]==[cards[0].csn,cards[1].csn,0xFFFF]
    assert all(struct.unpack_from('<H',records,n*24+22)[0]==0 for n in range(2))
    assert any(not v for n,v in visibility),'Census must actually remove old ROM decode'
    return {'actual_census_solve_ROM_registers_and_init_association':observed,
            'non_ISA_distinct_instance':True,'captured_first_status':0x120 if first_present else 0,'actual_status_selected_terminal':boot,'selected_ROM':expected,
            'complete_runtime_records':records.hex(),'relocated_read_port':bus.read_port}


def runtime_isa_association(port):
    return {str(present):runtime_isa_association_case(port,present) for present in (True,False)}


def allocation_startup_causal(port,groups=None,pci_cases=(False,True),video_cases=(False,True)):
    """Only the three trace contrasts that require an actual CPU startup."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    selected=set(groups or ('video','pci','clear'))
    prefix=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01'
    def saved(policy):
        m=settings.Settings(port,OUTPUT);m.call('settings_load');m.call('setup_defaults');m.draft()
        m.put('U_PNP',policy);m.put('U_POST_DELAY',[0]);assert m.call('settings_save')
        return m
    results={}
    if 'video' in selected and port in ('pb430','m919'):
        tested=[]
        for configurable in video_cases:
            class Display(Bus):
                def __init__(self,cards):super().__init__(cards);self.witness=[]
                def input(self,p,size):
                    if p in (0x310,0x3DA):
                        row=self.cards[0].registers[0] if self.cards else {}
                        responds=(row.get(0x30)==1 and (row.get(0x60,0)<<8|row.get(0x61,0))==p) if p==0x310 else True
                        self.witness.append({'port':p,'responds':responds,'registers':dict(row),
                                             'CS':self.cpu.reg_read(x.UC_X86_REG_CS),'IP':self.cpu.reg_read(x.UC_X86_REG_IP)})
                        return 0x5A if responds else 0xFF
                    return super().input(p,size)
                def observe_startup(self,m,cpu,address,listing):self.cpu=cpu
            stream=prefix[:-3]+b'\x09\0\x01'+b'\x47\x01'+struct.pack('<HHBB',0x300,0x310,16,8)+b'\x79\0'
            bus=Display([Card(serial(b'\x41\xD0\xFF\xFF',1),stream)] if configurable else [])
            raw=bytearray(32768);raw[:3]=b'\x55\xAA\x40'
            # Actual expansion instructions read the assigned device before
            # installing an IRET INT10 provider. No BCV/IPL semantics involved.
            code=bytes.fromhex('50521EBA')+struct.pack('<H',0x310 if configurable else 0x3DA)
            code+=bytes.fromhex('EC3C5A751031C08ED8C70640000001C706420000C01F5A58CB')
            raw[3:3+len(code)]=code;raw[0x100]=0xCF;raw[-1]=(-sum(raw))&255;bus.video_rom=bytes(raw)
            policy=bytearray(15);struct.pack_into('<HH',policy,3,0x300,8)
            m=saved(policy)
            result=startup(port,bytes(m.cmos).hex(),'',pnp_bus=bus,phases=(False,),external_video=True)
            assert any(row['port']==(0x310 if configurable else 0x3DA) and row['responds'] and row['CS']==0xC000
                       for row in bus.witness)
            assert len(result['finish_observations'])==1 and result['private_code_fetches']>0
            tested.append({'configurable_display':configurable,'actual_ROM_IO_witness':bus.witness,
                           'actual_startup_lifetime':result})
        results['M3']=tested
    elif 'video' in selected and port=='presario-800':
        results['M3']={'configurable_external_display':'not-applicable',
            'source':'presario-800/src/bios.asm505-543 validates/shadows the selected retained Cirrus image;605 calls its fixed entry;609 validates its INT10',
            'retained_fixed_output':'Covered by the actual cold/warm startup and full live-journal/finish oracles in M14 and placement; no alternative-display selector exists.'}
    if 'pci' in selected and port=='m919':
        from shared.tools.pci_proof import PCI,Endpoint
        tested=[]
        for reserved in pci_cases:
            stream=prefix+b'\x47\x01'+struct.pack('<HHBB',0xC010,0xC010,1,16)+b'\x79\0'
            bus=Bus([Card(serial(b'\x41\xD0\xFF\xFF',1),stream)])
            endpoint=Endpoint(bars={0x10:0xFFFFFFF1});bus.pci=PCI({0x58:endpoint})
            policy=bytearray(15)
            # C010 is required ISA; C03F is the next PCI candidate's last byte.
            if reserved:struct.pack_into('<HHHH',policy,3,0xC03F,1,0xC050,16)
            m=saved(policy)
            result=startup(port,bytes(m.cmos).hex(),'',pnp_bus=bus,phases=(False,))
            bar=endpoint.read(0x10,4)&~3
            expected,candidates=pci_manual_oracle(reserved)
            assert bar==expected,(reserved,hex(bar),candidates)
            assert endpoint.read(4,2)&7==1 and bus.cards[0].registers[0][0x30]==1
            assert bytes(bus.cards[0].registers[0][a] for a in (0x60,0x61))==b'\xC0\x10'
            tested.append({'manual_windows':reserved,'actual_BAR':bar,'actual_command':endpoint.read(4,2),
                           'independent_candidate_exclusions':candidates,
                           'endpoint_writes':endpoint.writes,'actual_reset_to_finish':result})
        results['M11']=tested
    if 'clear' in selected:
        stream=prefix+b'\x4B\xE0\x03\x08'
        checksum=(-sum(stream)-0x79)&255
        assert checksum
        good=stream+bytes((0x79,checksum));bad=stream+bytes((0x79,(checksum+1)&255 or 1))
        class Lifecycle(Bus):
            def __init__(self,cards):
                super().__init__(cards);self.finishing=False;self.index=0;self.retirement=[];self.boot=0
            def output(self,p,size,value):
                if p==0x70:self.index=value&127
                if p==0x71 and self.finishing:self.retirement[-1].append((self.index,value))
                return super().output(p,size,value)
            def observe_startup(self,m,cpu,address,listing):
                if address==finish:
                    self.finishing=True;self.retirement.append([])
                if address==end:
                    self.finishing=False;self.boot+=1
                    self.cards[0].resources=good
        bus=Lifecycle([Card(serial(b'\x41\xD0\xFF\xFF',1),bad,powerup_active=True)])
        policy=bytearray(15);policy[2]=1<<3;struct.pack_into('<HHHHH',policy,3,0x350,8,0x370,8,1<<8);policy[14]=1
        m=saved(policy);before=decode_saved(m)
        finish=0xF0000+m.listing.symbol('pnp_finish_entry');end=0xF0000+m.listing.symbol('pnp_post_summary_complete')
        result=startup(port,bytes(m.cmos).hex(),'',pnp_bus=bus,phases=(False,True,True),
                       expect_first_active=lambda index:index>0)
        assert len(bus.retirement)==3 and not bus.retirement[0] and bus.retirement[1] and not bus.retirement[2]
        decoded=[]
        for index,cmos in enumerate(result['persistent_snapshots']):
            check=settings.Settings(port,OUTPUT);check.cmos[:]=bytes.fromhex(cmos)
            value=decode_saved(check);expected=bytearray(policy);expected[14]=int(index==0)
            assert value[0]['C_PNP']==expected and value[1]==before[1]
            for name in ('C_IDE','C_PORTS','C_CHIP'):assert value[0][name]==before[0][name]
            decoded.append({'boot':index,'pending':expected[14],'retirement_writes':bus.retirement[index]})
        # Verification failures must be reached from the real finish facade,
        # rather than calling its storage helper as a proxy.
        failures=[]
        ordinal=65 if port=='m919' else 58;logical=settings.PAYLOAD_INDICES[ordinal]
        for failed in (logical,0x35):
            c=Card(serial(b'\x41\xD0\xFF\xFF',1),good)
            machine,device=allocation_fixture(port,[c],policy)
            machine.cmos[0x69]=0xD2;machine.cmos[0x36]=0x71;machine.cmos[0x37]=0xB5
            machine.put('U_PNP',bytes(range(15)))
            original=machine.snapshot();draft=machine.get('U_PNP',15);machine.fail=('cmos',failed)
            machine.writes.clear();machine.call('pnp_finish_entry')
            assert machine.snapshot()==original and machine.get('C_PNP',15)[14]==1
            assert machine.get('U_PNP',15)==draft and machine.writes
            assert decode_saved(machine)[0]['C_PNP']==policy
            assert not any(machine.cpu.mem_read(machine.base+0x338,4))
            failures.append({'failed_byte':failed,'actual_finish_writes':machine.writes,'complete_record_restored':True})
        results['M14']={'no_resave_three_actual_boots':decoded,'actual_reset_to_finish':result,'finish_verification_failures':failures}
    return results


def finish_retirement_unverifiable(port):
    """The real finish owner must retain the storage-error result too."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    ordinal=65 if port=='m919' else 58
    logical=settings.PAYLOAD_INDICES[ordinal]
    class Unverifiable(Bus):
        enabled=False;armed=False
        def output(self,p,size,value):
            if self.enabled and p==0x71 and machine.index==logical:self.armed=True
            return super().output(p,size,value)
        def input(self,p,size):
            if self.armed and p==0x71 and machine.index==logical:return machine.cmos[logical]^1
            return super().input(p,size)
    stream=b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B\xE0\x03\x08\x79\0'
    card=Card(serial(b'\x41\xD0\xFF\xFF',1),stream)
    bus=Unverifiable([card]);policy=bytearray(15);policy[14]=1
    machine,bus=allocation_fixture(port,[card],policy,bus=bus)
    machine.cmos[0x69]=0xD2;machine.cmos[0x36]=0x71;machine.cmos[0x37]=0xB5
    machine.put('U_PNP',bytes(range(15)))
    original=machine.snapshot();draft=machine.get('U_PNP',15)
    bus.enabled=True;machine.writes.clear();machine.call('pnp_finish_entry')
    assert bus.armed and machine.get('C_ERROR')[0]&4 and machine.get('C_PNP',15)[14]==1
    observed=machine.snapshot();allowed={logical,0x35}|({0x2E,0x2F} if port=='m919' else set())
    assert all(before==after for at,(before,after) in enumerate(zip(original[0],observed[0])) if at not in allowed)
    assert observed[1]==original[1] and machine.get('U_PNP',15)==draft
    assert not any(machine.cpu.mem_read(machine.base+0x338,4))
    assert bytes(machine.cpu.mem_read(0x4FB,3))==b'\x01\x0B\x02'
    return {'actual_finish_storage_error':True,'pending_and_unrelated_state_preserved':True,
            'distinct_draft_and_recovery_preserved':True,'ISA_publication_and_release_completed':True,
            'actual_finish_writes':machine.writes}


def placement(port):
    gate=setup_journal_lifetime(port,OUTPUT)
    result={'packet_owner':packet_journal_lifetime(port,OUTPUT),
            'capacity':journal_boundaries(port,OUTPUT),
            'actual_Setup_lifetime':{k:v for k,v in gate.items() if not k.startswith('saved_')},
            'Save_reset_fresh_cold_warm':allocation_startup(port,saved_setup=gate)}
    if port=='pb430':
        result['existing_scratch_lifetime']=pb_scratch_lifetime(OUTPUT)
        result['external_C000_branch']=allocation_startup(port,external_video=True,phases=(False,))
    return result


def composed_capacity(port,baseline):
    """Normal POST's own memory count, largest fitting population and one LDN more."""
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    initial=baseline['placement_observations'][0]
    assert initial['actual_LDN_count']==initial['stored_LDN_count']==1
    kib=initial['original_KiB']
    overhead=kib*1024-initial['journal_cursor']-564-32
    available=(kib-64)*1024
    maximum=0
    while overhead+(maximum+1)*564+((maximum+256)//256)*32<=available:maximum+=1
    if port=='pb430':
        # Actual normal snapshot includes the final live C000 extent claim.
        # Reproduce only allocator arithmetic and standard serial priority.
        before_census=initial['journal_cursor']+564+32+32
        def fits(amount):
            cursor=before_census
            def take(size):
                nonlocal cursor
                candidate=cursor-size
                if candidate<0x40000 and cursor>0x20000:candidate=0x20000-size
                cursor=candidate
                return cursor>=0x10000
            shapes=[];remaining=amount
            while remaining:
                count=min(remaining,256);identity=serial(b'\x41\xD0\xFF\xFF',len(shapes)+1)
                priority=tuple((byte>>bit)&1 for byte in identity for bit in range(8))
                shapes.append((priority,count));remaining-=count
            for priority,count in sorted(shapes,reverse=True):
                if not take(32):return False
                for _ in range(count):
                    if not take(564):return False
            return take(32)
        maximum=0
        while fits(maximum+1):maximum+=1
    assert maximum>1
    results=[]
    for amount in (maximum,maximum+1):
        remaining=amount;cards=[]
        while remaining:
            count=min(remaining,256)
            stream=b'\x0A\x10\0\x82\x03\0ISA'+b'\x15\x41\xD0\x05\0\0'*count+b'\x79\0'
            cards.append(Card(serial(b'\x41\xD0\xFF\xFF',len(cards)+1),stream,ldns=count,powerup_active=True))
            remaining-=count
        bus=Bus(cards);bus.pause=False
        m=settings.Settings(port,OUTPUT);m.call('settings_load');m.call('setup_defaults');m.draft()
        m.put('U_POST_DELAY',b'\0')
        m.put('U_HALT',b'\x01')  # Expected census exhaustion must not halt early POST.
        policy=bytearray(15);struct.pack_into('<H',policy,0,1<<15)
        struct.pack_into('<HH',policy,3,0x350,8);policy[13:]=b'\x01\x01'
        m.put('U_PNP',policy)
        if port!='presario-800':
            chip=bytearray(m.get('U_CHIP',24));chip[12 if port=='m919' else 6]=1;m.put('U_CHIP',chip)
        assert m.call('settings_save')
        before=decode_saved(m)
        print(port,'census capacity',amount,'LDNs',file=sys.stderr,flush=True)
        result=startup(port,bytes(m.cmos).hex(),bytes(m.nvram[0x200:0x240]).hex(),
            pnp_bus=bus,phases=(False,),expect_first_active=False)
        observed=result['placement_observations'][0]
        assert observed['original_KiB']==kib
        assert observed['actual_LDN_count']==amount
        assert bool(observed['reconstruction_status'])==(amount>maximum)
        assert observed['stored_LDN_count']==min(amount,maximum)
        assert all(not row[0x30] for card in cards for row in card.registers.values())
        m.cmos[:]=bytes.fromhex(result['cmos']);after=decode_saved(m)
        expected=bytearray(policy);expected[14]=int(not result['finish_observations'][0]['runtime_published'])
        assert after[0]['C_PNP']==expected and after[1]==before[1]
        for field in ('C_IDE','C_PORTS','C_CHIP'):assert after[0][field]==before[0][field]
        assert len(result['finish_observations'])==1
        results.append({'LDNs':amount,'cards':len(cards),'actual_before_video':observed,
            'actual_finish':result['finish_observations'][0],'pending_Clear':expected[14],
            'all_LDNs_actually_deactivated':True,'unrelated_saved_state_preserved':True})
    return {'actual_normal_POST_memory_KiB':kib,'derived_fixed_code_and_journal_overhead':overhead,
            'LDN_record_bytes':564,'CARD_record_bytes':32,'largest_fit':maximum,
            'existing_scratch_exclusion':[0x20000,0x40000] if port=='pb430' else None,'cases':results}


def isolation(port):return {'transport':isa_transport(port,OUTPUT),'census':card_census(port,OUTPUT),
                            'mode3_delays':mode3_delays(port,OUTPUT),
                            'census_to_commit':allocation_causal(port,('identity',))}
def resource_reopen(port):return {'transport':isa_transport(port,OUTPUT),'replay_to_commit':allocation_causal(port,('reopen',))}
def logical_devices(port):return {'census':card_census(port,OUTPUT),'ordinals':resource_programming(port,OUTPUT),
                                  'hardware_limits':logical_limits(port,OUTPUT),
                                  'metadata_and_shifted_ordinals':allocation_causal(port,('metadata','ordinals'))}
def memory_and_streams(port):
    return {'framing':resource_framing(port,OUTPUT),'domains':resource_domains(port,OUTPUT),
            'programming':resource_programming(port,OUTPUT),'malformed':card_census(port,OUTPUT,cases=('malformed',)),
            'register_boundaries':memory_register_boundaries(port),
            'seeded_memory_and_rejection_to_commit':allocation_causal(port,('memory','family','malformed'))}
def resource_semantics(port):
    return {'ledger':resource_ledger(port,OUTPUT),'capabilities':resource_capabilities(port,OUTPUT),
            'manual_IRQ':manual_irq_alias(port,OUTPUT),'programming':resource_programming(port,OUTPUT),
            'decoded_candidates_to_commit':allocation_causal(port,('io',))}
def option_roms(port):return {'static':static_resources(port,OUTPUT),'retained_ISA':retained_isa_rom(port,OUTPUT),
    'static_report_to_commit':allocation_causal(port,('static',)),'full_static_buffer_PCI':runtime_static_buffer(port),
    'complete_generic_chain':runtime_chain(port),'complete_instances':runtime_provider_set(port),
    'actual_ISA_association':runtime_isa_association(port),'selected_Video2':runtime_display(port),
    'early_legacy_display':early_display_entry(port),'early_PnP_display':early_display_entry(port,True),
    'PCI_deployment_instances':runtime_pci_instances(port)}




def runtime_static_buffer(port):
    from shared.tools.isa_pnp_proof import Bus,Card,serial
    from shared.tools.pci_proof import PCI,Endpoint
    io=lambda base:b'\x47\x01'+struct.pack('<HHBB',base,base,1,16)
    allocated=io(0xC010)*124+io(0xC030)+b'\x22\0\0'*2+b'\x79\0'
    node=struct.pack('<HB4s3sH',1024,0,b'\x41\xD0\x05\0',bytes(3),3)+allocated+b'\x79\0\x79\0'
    assert len(node)==1024
    raw=bytearray(4096);raw[:4]=b'\x55\xAA\x08\xCB';struct.pack_into('<H',raw,0x1A,0x40)
    raw[0x40:0x46]=b'$PnP\x01\x02';raw[0x4A:0x4E]=b'\x41\xD0\x05\0'
    struct.pack_into('<H',raw,0x5E,0x200);raw[0x49]=(-sum(raw[0x40:0x60]))&255
    code=bytes.fromhex('1E570E1FBE0004B90004FCF3A45F1FCB')
    raw[0x200:0x200+len(code)]=code;raw[0x400:0x800]=node;raw[-1]=(-sum(raw))&255
    returning=0xC8200+len(code)-1;results=[]
    for present in (False,True):
        card=Card(serial(b'\x41\xD0\xFF\xFF',1),b'\x0A\x10\0\x82\x03\0ISA\x15\x41\xD0\x05\0\x01\x4B\xE0\x03\x08\x79\0')
        bus=Bus([card]);bounds=[];active=[None];written=set();endpoint=Endpoint(bars={0x10:0xFFFFFFF1})
        if port=='m919':bus.pci=PCI({0x60:endpoint});bus.pci_address=0
        def configure(m):
            if not present:return
            m.cpu.mem_write(0xC8000,bytes(raw))
            def entry(cpu,address,length,unused):
                if address==0xC8200:
                    low=(cpu.reg_read(x.UC_X86_REG_ES)<<4)+cpu.reg_read(x.UC_X86_REG_DI)
                    active[0]=(low,bytes(cpu.mem_read(low-16,16)),bytes(cpu.mem_read(low+1024,16)))
                elif address==returning:
                    low,before,after=active[0]
                    assert bytes(cpu.mem_read(low-16,16))==before and bytes(cpu.mem_read(low+1024,16))==after
                    assert bytes(cpu.mem_read(low,1024))==node and written==set(range(low,low+1024))
                    bounds.append({'actual_ES_DI':low,'written_bytes':1024,'before_canary':before.hex(),'after_canary':after.hex()});active[0]=None
            def write(cpu,access,address,length,value,unused):
                if active[0] is not None and active[0][0]-16<=address<active[0][0]+1040:written.update(range(address,address+length))
            m.cpu.hook_add(UC_HOOK_CODE,entry);m.cpu.hook_add(UC_HOOK_MEM_WRITE,write)
        m,bus=allocation_fixture(port,[card],bus=bus,configure=configure)
        assert card.registers[0][0x30]==1 and len(bounds)==int(present)
        query=m.call('pnp_claim_query',AX=0x201,EDX=0xC010,ECX=16)
        assert query==(not present),(port,present,query,bounds,bytes(m.cpu.mem_read(int.from_bytes(m.cpu.mem_read(m.base+0x330,4),'little'),32)).hex())
        assert m.call('pnp_claim_query',AX=0x201,EDX=0xC030,ECX=16)==(not present)
        bar=None
        if port=='m919':
            m.call('pci_initialize');bar=endpoint.read(0x10,4)&~3
            # The first16-byte candidate C000 aliases DMA0..0F. Without
            # the report C010 is free. With it, C010/C030 are static claims,
            # C020 aliases PIC20..21, and C040 aliases PIT40..43, so C050
            # is the first free candidate. These are independent AT decodes.
            assert bar==(0xC050 if present else 0xC010),hex(bar)
            assert endpoint.read(4,2)&1
        results.append({'static_present':present,'actual_vector_boundaries':bounds,'ISA_active':True,'actual_PCI_BAR':bar,
                        'complete_later_resource_after_124_duplicate_descriptors':True})
    return results


def runtime_legacy_coexistence(port,post=None):
    source="""bits 16
org 0
db 55h,0AAh,4
jmp init
times 1Ah-($-$$) db 0
dw 0
init:
push ds
xor ax,ax
mov ds,ax
inc word [700h]
mov word [64h],chain
mov [66h],cs
pop ds
retf
chain:
push ds
xor ax,ax
mov ds,ax
inc word [702h]
cmp byte [6EEh],1
pop ds
je interrupted
retf
interrupted: int 18h
hlt
times 2048-($-$$) db 0
"""
    legacy=bytearray(runtime_assemble(port,'coexisting-legacy',source));legacy[-1]=(-sum(legacy))&255
    chain=int.from_bytes(legacy[0x1E+0:0x1E+2],'little') if False else legacy.index(b'\x1E\x31\xC0\x8E\xD8\xFF\x06\x02\x07')
    if post is None:post=runtime_startup_snapshot(port,rom_images=((0xC800,runtime_provider(port,0,'cf')),(0xC900,bytes(legacy))),
        boot_order=(2,3,4,1),snapshot_name='p3-coexistence-post')
    results=[]
    for interrupted in (False,True):
        m=runtime_clone_post(post);cd,disk=runtime_native_device(m);m.cpu.mem_write(0x6EE,bytes((int(interrupted),)))
        native=runtime_assemble(port,'coexisting-native',"""bits 16
org 7C00h
xor ax,ax
mov ds,ax
mov word [6F2h],80h
int 18h
hlt
times 510-($-$$) db 0
dw 0AA55h
""")
        disk.disk_words.update({(0,n):word for n,word in enumerate(struct.unpack('<256H',native))})
        image=cd.disc(media=0)
        cdloader=runtime_assemble(port,'coexisting-CD',"""bits 16
org 7C00h
xor ax,ax
mov ds,ax
mov word [6F4h],0E0h
int 19h
hlt
times 510-($-$$) db 0
dw 0AA55h
""")
        image[21*2048:21*2048+512]=cdloader;disk.images[1]=image
        floppy=runtime_assemble(port,'coexisting-floppy',"""bits 16
org 7C00h
xor ax,ax
mov ds,ax
mov word [6F6h],0FDh
hlt
times 510-($-$$) db 0
dw 0AA55h
""")
        fdc,fdc_hook=runtime_floppy_device(m,floppy)
        native13=bytes(m.cpu.mem_read(0x4C,4));trace=[]
        bcv=0xC8000+int.from_bytes(m.cpu.mem_read(0xC8076,2),'little')
        def observe(cpu,address,length,unused):
            if address==0x7C00:
                dl=cpu.reg_read(x.UC_X86_REG_DL);trace.append(('load',dl))
                assert (cpu.reg_read(x.UC_X86_REG_ES),cpu.reg_read(x.UC_X86_REG_DI))==(0xF000,m.listing.symbol('pnp_installation'))
            elif address==bcv:trace.append(('PnP',0))
            elif address==0xC9000+chain:
                trace.append(('legacy',int(interrupted)))
                assert bytes(cpu.mem_read(0x4C,4))==native13 and cpu.mem_read(m.base+0x298,1)==b'\0'
                assert cpu.mem_read(0x475,1)==b'\x01'
        hook=m.cpu.hook_add(UC_HOOK_CODE,observe)
        try:boot=runtime_execute_boot(m,fdc_attached=True)
        finally:m.cpu.hook_del(hook);m.cpu.hook_del(fdc_hook)
        assert boot['terminal']=='loader' and trace==[('load',0x80),('load',0xE0),('PnP',0),('legacy',int(interrupted)),('load',0)],trace
        assert struct.unpack('<3H',m.cpu.mem_read(0x6F2,6))==(0x80,0xE0,0xFD)
        assert struct.unpack('<2H',m.cpu.mem_read(0x700,4))==(1,1)
        # Actual CD volume/catalog reads own0800h..0FFFh, so they deliberately
        # overwrite the old init witness900h. Initialization is observed on the
        # external ROM entry during actual POST; BCV/disconnect occur afterwards.
        assert post.startup_evidence['actual_ROM_initializations']==[1,1]
        assert struct.unpack('<2H',m.cpu.mem_read(0x902,4))==(1,1)
        results.append({'legacy_interrupt':interrupted,'same_native_CD_PnP_legacy_floppy_chain':trace,
            'actual_FDC_commands':fdc.fdc_log,'actual_ATA_commands':disk.selected_commands,
            'one_PnP_disconnect_and_one_legacy_call':True,'actual_CD_scratch_reused_old_init_witness':True})
    return {'actual_startup':post.startup_evidence,'cases':results}


def runtime_noncontiguous_pack(port):
    from shared.tools.isa_pnp_proof import Bus
    results=[]
    for fit in (True,False):
        m=isa_machine(port,Bus([]),OUTPUT)
        m.call('settings_load');m.call('setup_defaults');m.draft();m.put('U_POST_DELAY',b'\0')
        for field,value in (('U_HALT',1),('U_BOOT',4),('U_BOOT_SECOND',0),('U_BOOT_THIRD',0),('U_BOOT_FOURTH',0)):m.put(field,bytes((value,)))
        policy=bytearray(15);policy[14]=1;m.put('U_PNP',policy);assert m.call('settings_save')
        if port!='m919':m.call('pnp_journal_release')
        m.call('pnp_early')
        prefix=m.cpu.mem_read(m.base,1)[0]*1024
        stage=(prefix+60+3*24+1023)&~1023
        failure_ceiling=64+stage//1024-1
        reserve=runtime_assemble(port,'reserve-between-records-'+str(fit),f"""bits 16
org 100h
pushad
push ds
push es
xor ax,ax
mov ds,ax
mov bx,[413h]
mov [6D0h],bx
mov dx,bx
{'sub bx,8' if fit else f'mov bx,{failure_ceiling}'}
mov [6D2h],bx
mov [413h],bx
sub dx,bx
mov ax,bx
shl ax,6
mov es,ax
xor di,di
.block:
mov ax,6D6Dh
mov cx,512
rep stosw
mov ax,es
add ax,40h
mov es,ax
xor di,di
dec dx
jnz .block
pop es
pop ds
popad
xor ax,ax
retf
""")
        raw=bytearray(runtime_rom(0,status=0));raw[0x100:0x100+len(reserve)]=reserve;raw[-1]=0;raw[-1]=(-sum(raw))&255
        for segment,image in ((0xC800,raw),(0xC900,runtime_provider(port,1,'cf')),(0xCA00,runtime_provider(port,2))):m.cpu.mem_write(segment<<4,bytes(image))
        m.call('option_rom_discovery')
        high,low=struct.unpack('<HH',m.cpu.mem_read(0x6D0,4));owner=(low*1024,high*1024)
        assert high>low and m.cpu.mem_read(owner[0],owner[1]-owner[0])==b'\x6D'*(owner[1]-owner[0])
        pointer=int.from_bytes(m.cpu.mem_read(m.base+0x334,4),'little');links=[];payload=[];seen=set()
        while pointer:
            assert pointer not in seen;seen.add(pointer)
            row=bytes(m.cpu.mem_read(pointer,28));links.append((pointer,int.from_bytes(row[:4],'little')))
            payload.append(row[4:]);pointer=links[-1][1]
        assert len(links)==3 and any(abs(a-b)>28 for a,b in links if b),links
        old=m.base;before=bytes(m.cpu.mem_read(old,prefix));saved=m.snapshot()
        m.call('pnp_finish_entry')
        base=int.from_bytes(m.cpu.mem_read(0x40E,2),'little')<<4
        after=bytes(m.cpu.mem_read(base,prefix))
        allowed={0,m.state['C_ERROR'],m.state['C_PNP']+14}|set(range(0x320,0x33C))
        differences=[n for n,(a,b) in enumerate(zip(before,after)) if a!=b]
        assert not set(differences)-allowed,(port,fit,differences)
        assert after[m.state['C_ERROR']]==before[m.state['C_ERROR']]|(0 if fit else 0x40)
        assert after[0x328:0x32A]==before[0x328:0x32A]
        assert m.cpu.mem_read(owner[0],owner[1]-owner[0])==b'\x6D'*(owner[1]-owner[0])
        assert not any(m.cpu.mem_read(base+0x320,8)) and not any(m.cpu.mem_read(base+0x338,4))
        relative=int.from_bytes(m.cpu.mem_read(base+0x334,4),'little')
        if fit:
            assert relative==prefix and base+(m.cpu.mem_read(base,1)[0]*1024)==owner[0]
            header=bytes(m.cpu.mem_read(base+relative,60))
            assert m.cpu.mem_read(base,1)[0]*1024==stage
            assert header[19]==prefix//1024
            assert struct.unpack_from('<HHHB',header,40)==(int.from_bytes(before[0x328:0x32A],'little'),low,base>>4,stage//1024)
            assert int.from_bytes(header[50:52],'little')==base>>4
            assert int.from_bytes(header[4:8],'little')==3 and header[8:19]==bytes(11)
            packed=bytes(m.cpu.mem_read(base+relative+60,72));assert packed==b''.join(reversed(payload))
            assert m.cpu.mem_read(base+m.state['C_PNP']+14,1)==b'\0'
            m.base=base
            runtime_attach_interrupts(m)
            # As in runtime_native_device, install the real resident BIOS disk
            # vector in this allocator-entry fixture. No native device/count is
            # fabricated; the actual reset service handles its absent drive.
            m.cpu.mem_write(0x4C,struct.pack('<HH',m.listing.symbol('int13'),0xF000))
            calls=[];interrupt=m.runtime_interrupt
            def observed_interrupt(cpu,vector):
                calls.append((vector,bytes(cpu.mem_read(vector*4,4)).hex(),cpu.reg_read(x.UC_X86_REG_CS),cpu.reg_read(x.UC_X86_REG_IP)))
                return interrupt(cpu,vector)
            m.runtime_interrupt=observed_interrupt
            try:boot=runtime_execute_boot(m)
            except Exception as error:
                pc=(m.cpu.reg_read(x.UC_X86_REG_CS)<<4)+m.cpu.reg_read(x.UC_X86_REG_IP)
                raise AssertionError('noncontiguous boot',port,owner,base,hex(pc),bytes(m.cpu.mem_read(pc,16)).hex(),
                    {r:m.cpu.reg_read(getattr(x,'UC_X86_REG_'+r)) for r in ('CS','IP','SS','SP','FS','GS')},links,calls) from error
            assert boot['terminal']=='loader' and m.cpu.mem_read(0x6F0,2)==b'\x03\0'
            assert m.cpu.mem_read(owner[0],owner[1]-owner[0])==b'\x6D'*(owner[1]-owner[0])
        else:
            assert base==old and relative==0 and m.get('C_ERROR')[0]&0x40
            assert m.get('C_PNP',15)[14]==1 and m.snapshot()==saved
            boot=None
        ceiling=int.from_bytes(m.cpu.mem_read(0x413,2),'little')
        assert ceiling==(base>>10 if fit else low)
        expected=bytearray(policy);expected[14]=int(not fit)
        assert decode_saved(m)[0]['C_PNP']==expected
        results.append({'runtime_fit':fit,'real_returning_ROM_external_interval':owner,'owner_bytes':owner[1]-owner[0],
            'noncontiguous_links':links,'complete_payloads_in_encounter_order':[r.hex() for r in reversed(payload)],
            'whole_prefix_sha256':hashlib.sha256(before).hexdigest(),'whole_prefix_actual_differences':differences,
            'only_explicit_publication_fields_changed':True,'full_external_owner_and_boundary_canaries_preserved':True,
            'actual_available_KiB':ceiling,'final_base':base,'pending_Clear':int(not fit),'boot':boot})
    return results

def runtime_clock_restart(port,rows=None):
    if port!='pb430':return {'private_clock_relocation':'not-applicable'}
    import importlib
    from shared.tools.isa_pnp_proof import Bus
    sys.path.insert(0,str(ROOT/port/'tools'))
    suite=importlib.import_module('test-port');scenario=importlib.import_module('scenarios')
    image=ROOT/port/OUTPUT/'production/baios-pb430.bin'
    if rows is None:rows=scenario.clock(image,suite.nvram,post_only=True)
    n=suite.nvram();n[0x38]=0;n[0x0E]=0x80
    m=scenario.ACC(image,n,isa_bus=Bus([]))
    m.call('pnp_early')
    m.script=[0x20] # Fresh D chooses the existing verified defaults transaction.
    address=0xF0000+m.listing.symbol('controlled_defaults_restart');entered=[]
    h=m.cpu.hook_add(UC_HOOK_CODE,lambda u,a,z,v:entered.append(a),None,address,address)
    try:
        u=m.cpu
        for reg,value in dict(CS=0xF000,IP=m.listing.symbol('post_clock_alert'),DS=0,ES=0,FS=m.base>>4,SS=0,SP=0x7000,EFLAGS=0x202).items():
            u.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
        u.mem_write(0x7000,b'\xFF\xFF')
        u.emu_start(0xF0000+m.listing.symbol('post_clock_alert'),0xFFFFF,count=12000000)
    finally:m.cpu.hook_del(h)
    assert entered==[address] and m.reset_pending,(entered,m.reset_pending,hex(m.cpu.reg_read(x.UC_X86_REG_IP)),m.console)
    assert m.cmos[0x33:0x35]==b'N\x06' and m.cmos[0x0F]==0
    checked=settings.Settings(port,OUTPUT);checked.cmos[:]=m.cmos;checked.call('settings_load')
    assert checked.get('C_VALID')==b'\x01';decode_saved(checked);settings.at_checksum(checked.cmos)
    return {'existing_valid_invalid_clock_Save_reset':rows,'actual_private_invalid_settings_defaults_restart':True,
            'resident_restart_before_actual_reset_pulse':entered,'verified_NV6_defaults':True}

def boot_continuation(port):
    post=runtime_startup_snapshot(port)
    return {'promotion':runtime_promotion(port),'media_and_disk_ownership':runtime_media(port,post),
            'relocated_actual_disk_ownership':runtime_disk_ownership(port,post),
            'native_loader_INT19':runtime_handoff_native(port,runtime_clone_post(post),'int19'),
            'relocated_real_buffer_APIs':runtime_relocated_buffer_apis(port,post),
            'saved_category_priority':runtime_saved_priority(port,post),
            'relocated_clock_owner':runtime_clock_restart(port),
            'external_continuation':{a:runtime_handoff_external(port,a) for a in ('cf','unsigned','int18','int19')},
            'strict_CHS_other':runtime_strict_chs(port),
            'BEV':runtime_bev(port),'legacy_chain':runtime_legacy(port),'legacy_coexistence':runtime_legacy_coexistence(port),'relocation':runtime_relocation(port),
            'stale_and_fresh_retry':runtime_retry(port),'actual_CAD_and_repeated_warm':runtime_reset(port,cad=True,used=True),
            'natural_new_stage_capacity':runtime_capacity(port,post),'noncontiguous_full_prefix':runtime_noncontiguous_pack(port),
            'APM':{name:runtime_apm(port,mode) for name,mode in (('real',1),('pm16',2),('pm32',3))}}
def composed_resources(port):
    result={'joint_and_dependent':dependent_alternatives(port,OUTPUT),'map':onboard_map(port,OUTPUT),
            'policy_and_release':allocation_policy(port,OUTPUT),'retirement':clear_retirement(port,OUTPUT),
            'bad_End_valid_next_and_unassignable_Clear':rebuild_clear(port,OUTPUT),
            'early_actual_decode':early_port_ownership(port,OUTPUT),
            'natural_capacity':natural_capacity(port,OUTPUT),'actual_startup':allocation_startup(port),
            'saved_DMA_memory_release_to_commit':allocation_causal(port,('manual',)),
            'startup_video_PCI_Clear':allocation_startup_causal(port),
            'finish_unverifiable_rollback':finish_retirement_unverifiable(port)}
    if port=='pb430':result['actual_fixed_video']=pb_fixed_video(OUTPUT)
    if port=='m919':result.update(PCI_precedence=pci_precedence(OUTPUT),PCI_fixed_ROM=pci_fixed_rom(OUTPUT),
                                  selected_VGA_legacy=selected_vga_resources(OUTPUT),
                                  PCI_VGA_first_use=pci_vga_first_use(OUTPUT),
                                  final_routing=pci_final_routing(OUTPUT),PCI_manual_windows=pci_manual_windows(OUTPUT))
    result['actual_normal_capacity']=composed_capacity(port,result['actual_startup'])
    return result


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


def image_contract(port,output=None):
    c=Caller(port) if output is None else settings.Settings(port,output)
    image=c.image.parent/'production'/c.image.name if output is None else c.image
    assert len(scan(image.read_bytes()))==int(port!='mp386')
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
        # Qualified B35 owner changes only the frozen prefix-excluded tail.
        assert hashlib.sha256(full[:0xC000]).hexdigest()==json.loads((ROOT/'shared/tests/fixtures/pnp-placement-p1.json').read_text())['ports'][port]['retained_sha256']
        assert sum(full)&255==int(frozen['sum32'],16)&255
    if port=='m919':
        # E0 is generated APM/SMM code, not a retained vendor input. Test-only
        # discovery cannot alter it; its independent region checksum also holds.
        assert sum(raw[:65536])&255==0
        frozen=json.loads((ROOT/'shared/tests/fixtures/pnp-placement-p1.json').read_text())['ports'][port]
        assert hashlib.sha256(raw[:0x1600]).hexdigest()==frozen['retained_sha256']
        if output is None:assert raw[:0x1600]==c.image.read_bytes()[:0x1600]
    placement={}
    if port in ('m919','pb430','presario-800'):
        spec=importlib.util.spec_from_file_location('pnp_ui_layout',ROOT/'shared/tests/test-ui-text.py')
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
        placement=owner.owned_post_layout(full,port)
    if port=='mp386':
        spec=importlib.util.spec_from_file_location('pnp_mp_build',ROOT/port/'tools/build.py')
        fixed=json.loads((ROOT/'shared/tests/fixtures/pnp-placement-p1.json').read_text())['mp386_fixed_compatibility']
        assert hashlib.sha256(rom[fixed['start']:fixed['end']]).hexdigest()==fixed['sha256']
        owner=importlib.util.module_from_spec(spec);spec.loader.exec_module(owner)
        owner.validate(image)
    regions=[]
    for line in listing.lines:
        if re.search(r'\btimes\s+(?:0xF065|0xFFF0|CFG_ROM_CHECKSUM_OFFSET)',line) and 'db 0xFF' in line:
            match=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+FF<rep ([0-9A-F]+)h>',line)
            if match:regions.append((int(match[1],16),int(match[2],16)))
    partial=prepare_partial(port) if port!='mp386' and output is None else None
    return {'normal_complete_installation':port!='mp386','partial_composition':partial,'placement':placement,'sha256':hashlib.sha256(full).hexdigest(),
            'size':len(full),'sum32':f'{sum(full):08X}',
            'system_sha256':hashlib.sha256(rom).hexdigest(),
            'free_system_bytes':sum(n for at,n in regions if at<0xFFF0),'padding_regions':regions}


def settings_regressions(port):
    """Compare current load/fallback/recovery with frozen P0S logical outputs."""
    fixture=json.loads((ROOT/'shared/tests/fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
    captured=json.loads((ROOT/'shared/tests/fixtures/pnp-recovery-load-p0s.json').read_text())['ports'][port]['expectations']
    expected={(row['format'],row['bad_checksum'],row['recovery_D2']):row for row in captured}
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
                new=settings.Settings(port,OUTPUT)
                new.cmos[:],new.nvram[:]=persistent
                if bad:
                    at=0x35 if fmt=='nv6' else 0x72 if port=='m919' else 0x6A
                    new.cmos[at]^=1
                if recovery:
                    at=0x71 if port=='m919' and fmt=='legacy' else 0x69
                    new.cmos[at]=0xD2
                new.call('settings_load')
                assert not new.writes
                row=expected[fmt,bad,recovery]
                assert new.get('C_CHIP',24)==bytes.fromhex(row['C_CHIP']),(port,fmt,bad,recovery,'chip')
                assert new.get('C_VALID')==bytes.fromhex(row['C_VALID']),(port,fmt,bad,recovery,'valid')
                state=bytes(new.cpu.mem_read(new.base,new.allocated));saved=new.snapshot()
                new.call('pnp_publish')
                assert bytes(new.cpu.mem_read(new.base,new.allocated))==state and new.snapshot()==saved
                tested.append((fmt,bad,recovery))
    assert len(tested)==len(captured)
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
    parser.add_argument('--port',choices=('all','mp386')+PORTS,default='all')
    parser.add_argument('--case',choices=('all','abi','information-services','nodes','set-node','image-contract','mp-negative',
        'isolation','resource-reopen','logical-devices','memory-and-streams','resource-semantics',
        'dependent-alternatives','composed-resources','option-roms','boot-continuation','placement'))
    parser.add_argument('--startup-causal',action='store_true')
    parser.add_argument('--startup-cmos')
    parser.add_argument('--startup-nv',default='')
    args=parser.parse_args()
    if args.startup_cmos:
        assert args.port!='all'
        print(json.dumps(startup(args.port,args.startup_cmos,args.startup_nv,args.startup_causal)))
        raise SystemExit
    assert args.case,'--case is required'
    if args.case in ('isolation','resource-reopen','logical-devices','memory-and-streams','resource-semantics',
        'dependent-alternatives','composed-resources','option-roms','boot-continuation','placement'):
        OUTPUT='build/tests/pnp-runtime'
    if args.case=='mp-negative':
        assert args.port in ('all','mp386')
        subprocess.run([sys.executable,'-B',str(ROOT/'mp386/tools/build.py'),'--output','build/tests/pnp-runtime'],check=True,cwd=ROOT)
        print(json.dumps({'mp386':mp_negative()},indent=2))
        raise SystemExit
    assert args.port!='mp386','MP does not adopt PnP; select --case mp-negative'
    if args.port=='all':
        # Existing per-port hardware seams configure module-level RTC/listing
        # aliases. Keep each board's external model in its own Python process.
        results={}
        for port in PORTS:
            command=[sys.executable,'-B',str(Path(__file__).resolve()),'--case',args.case,'--port',port]
            results.update(json.loads(subprocess.check_output(command,cwd=ROOT,text=True)))
        print(json.dumps(results,indent=2))
        raise SystemExit
    ports=(args.port,)
    results={}
    for port in ports:
        prepare(port)
        cases=('abi','information-services','nodes','set-node','image-contract','isolation','resource-reopen',
               'logical-devices','memory-and-streams','resource-semantics','dependent-alternatives',
               'composed-resources','option-roms','boot-continuation','placement') if args.case=='all' else (args.case,)
        results[port]={case:globals()[case.replace('-','_')](port) for case in cases}
        if args.case in ('all','set-node'):results[port]['affected_settings']=settings_regressions(port)
    print(json.dumps(results,indent=2))
