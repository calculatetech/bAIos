"""Bounded execution of final PCI/ROM/Cyrix policy and its saved choices."""
import argparse
import json
from pathlib import Path
from unicorn import UC_HOOK_INSN, UC_HOOK_MEM_WRITE, UC_HOOK_CODE
import manual_proof as m
from geometry_proof import mapped, invoke, PORT
from unicorn import x86_const as x


class Bus(m.Memory):
    def __init__(self):
        super().__init__(kib=512)
        self.devices={0x90:{0:0x60,1:0x10,2:0x86,3:0x88,0xB:6}}
        self.registers.update({0:0x60,1:0x10,2:0x81,3:0x88,0xB:6})
        self.compat_writable=True
        self.cpu_index=0
        self.cpu={0xC0:0x84,0xC3:0xA0,0x20:0xD5,0xFE:0x28}
        self.cpu_writes=[]
        self.config_writes=[]
        self.sio={0xC0:0xF0,0xC1:0x30,0xC2:0x7E,0xC3:0x5A,0xC4:0xA5}
        self.sio_index=0;self.sio_open=False;self.sio_writes=[]
        self.probe_writable=True
    def pci_read(self,address,port,size):
        bdf=address>>8&0xFFFF
        if bdf==0x80:registers=self.registers
        elif bdf in self.devices:registers=self.devices[bdf]
        else:return (1<<(size*8))-1
        offset=(address&0xFC)+port-0xCFC
        return sum(registers.get(offset+i,0)<<(8*i) for i in range(size))
    def pci_write(self,address,port,size,value):
        bdf=address>>8&0xFFFF
        self.config_writes.append((bdf,(address&0xFC)+port-0xCFC,size,value))
        if bdf==0x80:
            offset=(address&0xFC)+port-0xCFC
            for i in range(size):self.registers[offset+i]=value>>(8*i)&255
        else:super().pci_write(address,port,size,value)
    def incoming(self,u,port,size):
        if port==0x20:return 0 # No pending or in-service PIC request in this fixture.
        if port==0x109 and self.sio_open:return self.sio.get(self.sio_index,255)
        if port==0x23:return self.cpu.get(self.cpu_index,0)
        return super().incoming(u,port,size)
    def outgoing(self,u,port,size,value):
        if port==0x108:
            if value==0xAA:self.sio_open=True
            elif value==0x55:self.sio_open=False
            else:self.sio_index=value
        if port==0x109 and self.sio_open:
            self.sio[self.sio_index]=value;self.sio_writes.append((self.sio_index,value))
        if port==0x22:self.cpu_index=value
        elif port==0x23:
            self.cpu_writes.append((self.cpu_index,value))
            if self.cpu_index==0xC3 and not self.probe_writable:value=(value&~2)|(self.cpu[0xC3]&2)
            self.cpu[self.cpu_index]=value
        super().outgoing(u,port,size,value)

    def interrupt(self,u,number):
        if number not in (9,0x15):return super().interrupt(u,number)
        sp=u.reg_read(x.UC_X86_REG_SP)-6
        frame=(u.reg_read(x.UC_X86_REG_IP).to_bytes(2,'little')+
               u.reg_read(x.UC_X86_REG_CS).to_bytes(2,'little')+
               (u.reg_read(x.UC_X86_REG_EFLAGS)&65535).to_bytes(2,'little'))
        for i,b in enumerate(frame):self.write((u.reg_read(x.UC_X86_REG_SS)<<4)+sp+i,1,b)
        u.reg_write(x.UC_X86_REG_SP,sp)
        u.reg_write(x.UC_X86_REG_EFLAGS,u.reg_read(x.UC_X86_REG_EFLAGS)&~0x300)
        vector=self.read(number*4,4)
        u.reg_write(x.UC_X86_REG_IP,int.from_bytes(vector[:2],'little'))
        u.reg_write(x.UC_X86_REG_CS,int.from_bytes(vector[2:],'little'))


def fixture(image):
    d=Bus()
    _,f=mapped(d.modules,expected=16,memory=d,rom_image=image)
    d.composed=True
    u,_,_,state,_,_=f
    base=u.reg_read(x.UC_X86_REG_FS)<<4
    u.reg_write(x.UC_X86_REG_DI,state['C_CHIP']);invoke(f,'chipset_defaults')
    return d,f,base,state


def irq_cases(image):
    rows=[]
    for mode in ('auto','edge','level','disabled','conflict'):
        d,f,base,state=fixture(image)
        isa=d.devices[0x90]
        isa.update({0x43:0,0x44:0,0x46:0xB0,0x47:0xF0})
        endpoints=[]
        # Distinct functions exercise every pin without pretending a slot exists.
        for slot in (0x60,0x68,0x70):
            for pin in range(1,5):
                bdf=slot+pin-1
                d.devices[bdf]={0:0x34,1:0x12,2:0x78,3:0x56,4:3,6:0xA5,7:0x5A,0xE:0x80,0x3C:0xFF,0x3D:pin}
                endpoints.append((bdf,pin))
        d.devices[0x60][0xB]=3
        # Real onboard ISA owners, and unrelated ELCR bits, must survive.
        for address,value in ((0x400,0x3F8),(0x402,0x2F8),(0x408,0x378)):
            d.write(address,2,value)
        d.write(base+state['C_PORTS']+state['P_FLOPPY'],1,1)
        d.ports[0x4D0]=0x20;d.ports[0x4D1]=0x20
        if mode!='auto':
            # IRQ14, IRQ15, IRQ9, IRQ10; duplicated links share correctly.
            d.write(base+state['C_CHIP']+16,1,0x98)
            d.write(base+state['C_CHIP']+17,1,0x54)
            d.write(base+state['C_CHIP']+19,1,int(mode=='level'))
        if mode=='disabled':d.write(base+state['C_CHIP']+16,2,0xBBBB)
        if mode=='conflict':
            d.write(base+0x1039,1,1)
            d.write(base+state['C_IDE'],1,1)
        d.write(base+state['C_CHIP']+18,1,8)
        invoke(f,'board_pci_runtime_policy',count=300000)
        links=list(d.read(base+0x10A4,4))
        expected={'auto':[11,12,9,10],'edge':[14,15,9,10],'level':[14,15,9,10],
                  'disabled':[255]*4,'conflict':[255,255,9,10]}[mode]
        assert links==expected,(mode,links)
        routes=((0,1,2,3),(3,0,1,2),(2,0,1,3))
        for bdf,pin in endpoints:
            row=((bdf&0xF8)-0x60)//8
            assert d.devices[bdf][0x3C]==expected[routes[row][pin-1]],(mode,bdf,pin)
        assert d.devices[0x60][4]==0x23
        assert (d.devices[0x60][6],d.devices[0x60][7])==(0xA5,0x5A),'W1C status touched'
        assert isa[0x46]&0xF0==0xB0 and isa[0x47]&0xF0==0xF0
        assert isa[0x46]&15==sum(1<<i for i,q in enumerate(expected) if q!=255)
        level=sum(1<<i for i,q in enumerate(expected) if q!=255 and (q<14 or mode=='level'))
        assert isa[0x47]&15==level,(mode,isa)
        elcr=d.ports[0x4D0]|d.ports[0x4D1]<<8
        for q in set(expected)-{255}:
            assert bool(elcr&(1<<q))==(q<14 or mode=='level'),(mode,q,hex(elcr))
        assert elcr&0x2020==0x2020,'Unrelated ISA sources changed'
        assert not set(d.commands)&{0xA7,0xA8,0xA9,0xD3,0xD4}
        rows.append(dict(mode=mode,links=links,elcr=f'{elcr:04X}',all_slot_pins=True))
    for requested in (False,True):
        d,f,base,state=fixture(image)
        d.devices[0x60]={0:0x34,1:0x12,4:0x23,5:1,6:0xA5,7:0x5A,0xB:3}
        d.devices[0x68]={0:0x34,1:0x12,4:0x23,5:1,6:0xA5,7:0x5A,0xB:2}
        d.write(base+state['C_CHIP']+18,1,8 if requested else 0)
        invoke(f,'board_pci_runtime_policy',count=300000)
        assert d.devices[0x60][4]==(0x23 if requested else 3)
        assert d.devices[0x60][5]==1
        assert d.devices[0x68][4]==0x23 and d.devices[0x68][5]==1
        assert all((d.devices[bdf][6],d.devices[bdf][7])==(0xA5,0x5A) for bdf in (0x60,0x68))
        rows.append(dict(palette=requested,display_command=d.devices[0x60][4],non_display_unchanged=True))
    d,f,base,state=fixture(image)
    d.devices[0x60]={0:0x34,1:0x12,0x3D:1,0x3C:0xFF}
    d.write(base+state['C_CHIP']+16,1,10) # Explicit IRQ3, before UART activation.
    d.ports[0x4D1]=0x20
    invoke(f,'board_pci_runtime_policy',count=300000)
    assert d.devices[0x60][0x3C]==3 and d.ports[0x4D0]&8
    d.write(0x400,2,0x2F8)
    invoke(f,'board_pci_runtime_policy',count=300000)
    assert d.devices[0x60][0x3C]==255 and not d.ports[0x4D0]&8
    assert d.ports[0x4D1]&0x20
    rows.append(dict(transition='PCI IRQ3 to active UART',edge_restored=True,unrelated_preserved=True))
    for enabled in (False,True):
        d,f,base,state=fixture(image)
        d.devices[0x60]={0:0x34,1:0x12,0x3D:1,0x3C:0xFF}
        d.write(base+0x1039,1,1)
        d.write(base+state['C_IDE'],1,int(enabled))
        d.write(base+state['C_CHIP']+16,1,8) # Explicit IRQ14.
        invoke(f,'board_pci_runtime_policy',count=300000)
        assert d.devices[0x60][0x3C]==(255 if enabled else 14)
        rows.append(dict(ide_enabled=enabled,irq14=d.devices[0x60][0x3C]))
    return rows


def game_port_cases(image):
    rows=[]
    for owner in ('ide_apply_controller','init_peripherals'):
        for requested in (0,1):
            for incoming in (0x00,0xFF):
                d,f,base,state=fixture(image)
                d.sio[0xC0]=incoming
                d.write(base+state['C_CHIP']+22,1,requested)
                invoke(f,owner,count=300000)
                assert not d.sio[0xC0]&0x20
                assert d.read(base+state['C_CHIP']+22,1)==bytes((requested,))
                assert d.sio[0xC0]&0xD0==incoming&0xD0
                assert not d.sio_open and d.sio_index==0xC1
                rows.append(dict(caller=owner,enabled=bool(requested),incoming=incoming,result=d.sio[0xC0],unrelated_preserved=True,locked=True))
    return rows


def ecp_dma_cases(image):
    rows=[]
    for requested in (0,1):
        for incoming in (0x00,0xFF):
            d,f,base,state=fixture(image)
            # The saved choice remains unchanged through every inactive route.
            d.write(base+state['C_CHIP']+22,1,requested*2)
            for lpt,mode in ((0,2),(2,0),(2,1),(2,2)):
                d.sio[0xC3]=incoming;d.sio[0xC4]=0xA5
                d.write(base+state['C_PORTS']+3,1,lpt)
                d.write(base+state['C_PORTS']+4,1,mode)
                d.sio_writes.clear();invoke(f,'ide_apply_controller')
                active=lpt!=0 and mode==2
                expected=(incoming&0xBF)|(requested*0x40) if active else incoming
                assert d.sio[0xC3]==expected and d.sio[0xC4]==0xA5
                assert sum(reg==0xC3 for reg,v in d.sio_writes)==int(active)
                assert d.read(base+state['C_CHIP']+22,1)==bytes((requested*2,))
                assert not d.sio_open
                rows.append(dict(channel=1 if requested else 3,incoming=incoming,lpt=lpt,mode=mode,active=active,C3=expected,C4_preserved=True))
    return rows


def parity_controls_cases(image):
    rows=[]
    for requested in (0,1):
        for seed in (0,255):
            for io_check in (0,8):
                d,f,base,state=fixture(image)
                d.registers.update({0x5A:0x2D|(seed&0x10),5:seed,6:0xA5,7:0x5A})
                d.devices[0x90].update({0x41:seed,6:0x96,7:0x69})
                d.ports[0x61]=d.gates[0x61]=0xA3|io_check
                d.write(base+state['C_CHIP']+6,1,requested)
                d.write(base+state['C_CHIP']+2,1,1) # Disable unrelated L2 qualification in this bounded parity check.
                d.write(base+state['S_INSTALLED_KIB32'],4,4)
                d.write(base+state['P_RAM_FLAGS'],1,4)
                d.config_writes.clear()
                invoke(f,'chipset_apply')
                control=next(i for i,(b,r,n,v) in enumerate(d.config_writes) if (b,r,n)==(0x80,5,1))
                early=d.config_writes[control-1:control+2]
                assert [(b,r,n) for b,r,n,v in early]==[(0x80,0x5A,1),(0x80,5,1),(0x90,0x41,1)]
                assert tuple(v for b,r,n,v in early)==(0x2D,seed&0xFE,seed|0x40)
                assert not d.registers[0x5A]&0x10 and not d.registers[5]&1 and d.devices[0x90][0x41]&0x40
                assert d.ports[0x61]==0xA7|io_check
                before=(d.registers[0x5A],d.registers[5],d.devices[0x90][0x41])
                d.config_writes.clear()
                invoke(f,'chipset_post_ram_cache',count=3000000)
                expected=((before[0]&0xEF)|(requested<<4),(before[1]&0xFE)|requested,
                          (before[2]&0xBF)|((1-requested)<<6))
                assert (d.registers[0x5A],d.registers[5],d.devices[0x90][0x41])==expected
                assert [(b,r,n) for b,r,n,v in d.config_writes]==[(0x80,0x5A,1),(0x80,5,1),(0x90,0x41,1)]
                assert tuple(v for b,r,n,v in d.config_writes)==expected
                assert d.ports[0x61]==(0xA3|io_check|(0 if requested else 4))
                assert (d.registers[6],d.registers[7],d.devices[0x90][6],d.devices[0x90][7])==(0xA5,0x5A,0x96,0x69)
                rows.append(dict(parity=bool(requested),seed=seed,IOCHK=bool(io_check),callers=['chipset_apply','chipset_post_ram_cache'],early_ordered_byte_writes=True,ordered_byte_writes=True,PCI_status_preserved=True))
    return rows


def parity_fast_boot_cases(image,modes=('full','fast','esc')):
    rows=[]
    for mode in modes:
        d,f,base,state=fixture(image)
        u=f[0]
        d.write(base+state['C_CHIP']+6,1,1)
        d.write(base+state['C_CHIP']+2,1,1)
        d.write(base+state['C_CHIP']+12,1,int(mode=='fast'))
        d.write(base+state['S_INSTALLED_KIB32'],4,4)
        d.write(base+state['S_EXTENDED_KIB32'],4,4)
        d.write(base+state['P_PHASE'],1,1)
        d.write(base+state['P_RAM_FLAGS'],1,0)
        d.write(base+state['S_SETUP_REQUEST'],1,0)
        for address in range(0x417,0x41E):d.write(address,1,0)
        for address in range(0x490,0x4A0):d.write(address,1,0)
        d.write(0x41A,2,0x1E);d.write(0x41C,2,0x1E)
        d.write(0x400+state['KB_POST_STATE'],1,1)
        d.write(9*4,2,f[2].symbol('int09'));d.write(9*4+2,2,0xF000)
        d.write(0x15*4,2,f[2].symbol('int15'));d.write(0x15*4+2,2,0xF000)
        if mode=='esc':d.queue=[0x01] # Real make code is consumed by keyboard_poll during the RAM yield.
        invoke(f,'chipset_apply_timing')
        invoke(f,'chipset_visible_ram_test',count=30000000)
        flags=d.read(base+state['P_RAM_FLAGS'],1)[0]
        assert flags==(2 if mode=='esc' else 4),(mode,flags)
        original=d.read(0x100000,0x1000);writes=set();low_next=[0]
        seed_start=f[2].symbol('.seed','chipset_parity_apply')
        seed_end=f[2].symbol('.seeded','chipset_parity_apply')
        def low_seed(cpu,access,address,size,value,user):
            if not seed_start<=cpu.reg_read(x.UC_X86_REG_IP)<seed_end:return
            assert address==low_next[0],(mode,address,low_next[0])
            low_next[0]+=size
            assert d.ports[0x61]&4 and not d.registers[0x5A]&0x10
            assert not d.registers[5]&1 and d.devices[0x90][0x41]&0x40
        original_write=d.write
        def preserving_write(address,size,value):
            if address<0xA0000 and seed_start<=u.reg_read(x.UC_X86_REG_IP)<seed_end:
                expected=int.from_bytes(d.read(address,size),'little')
                assert value==expected,(mode,hex(address),hex(expected),hex(value))
            original_write(address,size,value)
        d.write=preserving_write
        low_hook=u.hook_add(UC_HOOK_MEM_WRITE,low_seed,None,0,0x9FFFF)
        def seed(cpu,access,address,size,value,user):
            assert d.ports.get(0x61,0)&4,'port61 armed before initialization'
            assert not d.registers[0x5A]&0x10 and not d.registers[5]&1 and d.devices[0x90][0x41]&0x40
            assert value==int.from_bytes(original[address-0x100000:address-0x100000+size],'little')
            writes.update(range(address,address+size))
        h=u.hook_add(UC_HOOK_MEM_WRITE,seed,None,0x100000,0x100FFF)
        invoke(f,'chipset_post_ram_cache',count=3000000)
        u.hook_del(h);u.hook_del(low_hook);d.write=original_write
        assert low_next[0]==0xA0000,(mode,low_next)
        assert writes==(set() if mode=='full' else set(range(0x100000,0x101000)))
        assert d.read(0x100000,0x1000)==original and not d.ports[0x61]&4
        assert d.registers[0x5A]&0x10 and d.registers[5]&1 and not d.devices[0x90][0x41]&0x40
        rows.append(dict(mode=mode,visible_flags=flags,low_bytes_seeded=low_next[0],extended_bytes_seeded=len(writes),values_preserved=True,all_low_prewrite_values_checked=True,all_gates_safe_until_seeded=True))
    return rows


def cyrix_cases(image):
    rows=[]
    configurations=[(vendor,dir0,writable,4,0xD5,'cpuid') for vendor,dir0,writable in
           [('AuthenticAMD',0x28,True),('GenuineIntel',0x28,True),
            ('CyrixInstead',0x28,True),('CyrixInstead',0x2F,True),
            ('CyrixInstead',0x27,True),('CyrixInstead',0x30,True),('CyrixInstead',0x28,False)]]
    configurations.extend([('CyrixInstead',0x28,True,3,0xD5,'cpuid'),('CyrixInstead',0x28,True,4,0x55,'cpuid')])
    configurations.extend((vendor,0x28,True,4,0xD5,route) for vendor,route in
                          [('CyrixInstead','legacy'),('GenuineIntel','legacy'),('CyrixInstead','no-ac')])
    for vendor,dir0,writable,revision,pcr,route in configurations:
        d,f,base,state=fixture(image)
        u=f[0]
        cpuid_calls=[]
        def cpuid(cpu,user):
            cpuid_calls.append(True)
            raw=vendor.encode()
            for reg,part in ((x.UC_X86_REG_EBX,raw[:4]),(x.UC_X86_REG_EDX,raw[4:8]),(x.UC_X86_REG_ECX,raw[8:])):
                cpu.reg_write(reg,int.from_bytes(part,'little'))
            cpu.reg_write(x.UC_X86_REG_EAX,1)
            return True
        u.hook_add(UC_HOOK_INSN,cpuid,None,1,0,x.UC_X86_INS_CPUID)
        if route!='cpuid':
            def capabilities(cpu,address,size,user):
                opcode=bytes(cpu.mem_read(address,size))
                if opcode==b'\x66\x9d':
                    stack=(cpu.reg_read(x.UC_X86_REG_SS)<<4)+cpu.reg_read(x.UC_X86_REG_SP)
                    flags=int.from_bytes(cpu.mem_read(stack,4),'little')
                    flags&=~(0x200000|(0x40000 if route=='no-ac' else 0))
                    d.write(stack,4,flags)
                elif opcode==b'\x9f':
                    # DIV preserves arithmetic flags on Cyrix; Intel leaves a different signature.
                    flags=cpu.reg_read(x.UC_X86_REG_EFLAGS)&~0xD5
                    cpu.reg_write(x.UC_X86_REG_EFLAGS,flags|(0 if vendor=='CyrixInstead' else 4))
            u.hook_add(UC_HOOK_CODE,capabilities)
        d.cpu[0xFE]=dir0;d.cpu[0x20]=pcr;d.probe_writable=writable
        d.registers[0x08]=revision
        d.registers[0x62]=0xA0
        d.write(base+state['C_CHIP']+18,1,7)
        invoke(f,'chipset_cyrix_apply')
        qualified=vendor=='CyrixInstead' and 0x28<=dir0<=0x2F and writable and route!='no-ac'
        assert d.registers[0x62]==(0xA0 if revision!=4 else 0xA3 if qualified else 0xA1)
        if qualified:
            assert d.cpu[0xC3]==(0xA4 if revision==4 else 0xA0) and d.cpu[0x20]==0x55
            d.write(base+state['C_CHIP']+18,1,0)
            invoke(f,'chipset_cyrix_apply')
            assert d.cpu[0xC3]==0xA0 and d.cpu[0x20]==pcr
            assert d.registers[0x62]==0xA0
        else:
            assert d.cpu[0xC3]==0xA0 and d.cpu[0x20]==0xD5
            assert all(index==0xC3 for index,_ in d.cpu_writes)
        if vendor!='CyrixInstead' or route=='no-ac':assert not d.cpu_writes and 0x22 not in d.ports
        assert bool(cpuid_calls)==(route=='cpuid'), (vendor,route,cpuid_calls)
        rows.append(dict(vendor=vendor,dir0=dir0,writable=writable,revision=revision,initial_pcr=pcr,route=route,qualified=qualified,warm_restore=True))
    return rows


def shadow_cases(image):
    rows=[]
    for cache,request in ((False,0),(False,1),(True,0),(True,1)):
        d,f,base,state=fixture(image)
        u=f[0]
        d.registers[0x54]=2;d.registers[0x55]=0xC0;d.registers[0x50]=0x80 if cache else 0
        d.write(base+state['C_CHIP']+14,1,request)
        d.write(base+state['C_CHIP']+15,1,0xFC)
        payload=bytes((i*37+(i>>14)*53+0x69)&255 for i in range(0x18000))
        u.mem_write(0xC8000,payload)
        mandatory=bytes((i*19+0xA7)&255 for i in range(0x8000))
        u.mem_write(0xC0000,mandatory)
        copied=[]
        def observe(cpu,access,address,size,value,user):
            assert value==int.from_bytes(payload[address-0xC8000:address-0xC8000+size],'little')
            copied.append((address,size))
        h=u.hook_add(UC_HOOK_MEM_WRITE,observe,None,0xC8000,0xDFFFF)
        invoke(f,'board_rom_tuning',count=350000)
        u.hook_del(h)
        assert d.registers[0x54]==0xFE and d.registers[0x55]==0xC0|int(cache and request)
        assert sum(s for _,s in copied)==0x18000
        assert {a//0x4000 for a,_ in copied}==set(range(0xC8000//0x4000,0xE0000//0x4000))
        assert bytes(u.mem_read(0xC8000,len(payload)))==payload
        assert bytes(u.mem_read(0xC0000,len(mandatory)))==mandatory
        rows.append(dict(l2=cache,video_request=request,effective=bool(cache and request),copied_kib=96,exact_payload=True,mandatory_preserved=True))
    return rows


def final_state_cases(image,vga_bus=False):
    rows=[]
    for wb in (False,True):
        for parity in (0,1):
            d,f,base,state=fixture(image)
            # Aggressive explicit bus choices must remain after the entire cache path.
            for offset,value in ((3,0x40 if wb else 0),(7,0x13),(8,0x95),(9,7),(10,0x0D),(14,1)):
                d.write(base+state['C_CHIP']+offset,1,value)
            if vga_bus:
                d.devices[0x60]={0:0x33,1:0x53,2:0x11,3:0x88,4:3,0xB:3,0x3D:1}
                d.write(base+0x1000,2,0x60)
                invoke(f,'board_vga_bus_policy')
            d.write(base+state['C_CHIP']+6,1,parity)
            d.write(base+state['P_RAM_FLAGS'],1,4)
            invoke(f,'chipset_apply')
            invoke(f,'chipset_parity_apply',count=3000000)
            parity_port=d.ports[0x61]
            before={r:d.registers.get(r,0) for r in (5,0x51,0x52,0x53,0x5A,0x60,0x61,0x62)}
            ibc={r:d.devices[0x90].get(r,0) for r in (0x40,0x41,0x46,0x56,0x57,0xA4)}
            invoke(f,'cache_qualify',count=12000000)
            assert d.read(base+0x1038,1)==b'\x01'
            invoke(f,'chipset_late_cache',count=2000000)
            assert d.read(base+0x1038,1)==b'\x05'
            after={r:d.registers.get(r,0) for r in before}
            assert after[0x51]&0xFE==before[0x51]&0xFE
            assert all(after[r]==before[r] for r in before if r!=0x51),(before,after)
            assert d.ports[0x61]==parity_port and bool(parity_port&4)==(not parity)
            assert d.registers[5]&1==parity and bool(d.registers[0x5A]&0x10)==bool(parity)
            assert bool(d.devices[0x90][0x41]&0x40)==(not parity)
            assert d.registers[0x52]&0x80 and d.registers[0x53]&0xC0==0xC0
            assert d.registers[0x55]&0xC1==0xC1
            assert all(d.devices[0x90].get(r,0)==v for r,v in ibc.items() if r!=0x46)
            assert d.devices[0x90][0xA4]&3==1
            if vga_bus:
                assert d.registers[0x51]&4 and d.devices[0x90][0x50]&0x80
                assert d.devices[0x90][0x56]&0x60==0x60
            rows.append(dict(policy='WB' if wb else 'WT',parity=parity,l2='qualified and enabled',bus_controls_retained=True,parity_controls_retained=True))
    return rows

def vga_bus_cases(image):
    d,f,base,state=fixture(image)
    rows=[]
    for provider in (0xFFFF,0x60):
        for seed in (0,0xFF,0xA9):
            d.write(base+0x1000,2,provider)
            d.registers[0x51]=seed
            d.devices[0x90][0x50]=seed^0x35
            d.devices[0x90][0x56]=seed^0x5A
            d.config_writes.clear()
            before=(d.registers[0x51],d.devices[0x90][0x50],d.devices[0x90][0x56])
            invoke(f,'board_vga_bus_policy')
            active=provider!=0xFFFF
            masks=(4,0x80,0x60)
            expected=tuple((v&~mask)|(mask if active else 0) for v,mask in zip(before,masks))
            after=(d.registers[0x51],d.devices[0x90][0x50],d.devices[0x90][0x56])
            assert after==expected,(provider,seed,before,after)
            assert d.config_writes==[(0x80,0x51,1,expected[0]),(0x90,0x50,1,expected[1]),(0x90,0x56,1,expected[2])]
            assert f[0].reg_read(x.UC_X86_REG_EFLAGS)&0xFFFF==0x247
            rows.append(dict(provider=provider,before=before,after=after,ordered=True))
    # Enter the real initialization owner once for each provider path.
    startup=m.vga_aperture_cases(image,(0x8000,None))
    return dict(mask_cases=rows,startup=startup)


def host_header_cases(image):
    rows=[]
    for identity,bdf,command in ((0x88811060,0x80,0),(0x88811060,0x80,0x0140),
                                 (0x88811060,0x80,0xF7E0),(0x88821060,0x80,0),
                                 (0x88811060,0x60,0)):
        d,f,base,state=fixture(image)
        for i,b in enumerate(identity.to_bytes(4,'little')):d.registers[i]=b
        d.registers.update({4:command&255,5:command>>8,6:0xA5,7:0x5A,0xC:0x11,0xD:0x22,0xE:0x80,0xF:0x55})
        before=dict(d.registers)
        f[0].reg_write(x.UC_X86_REG_BX,bdf)
        d.config_writes.clear()
        invoke(f,'board_pci_host_setup')
        accepted=identity==0x88811060 and bdf==0x80
        if accepted:
            assert d.registers[0xD]==0x40 and d.registers[0xC]==4
            assert d.registers[4]|d.registers[5]<<8==command|0x1F
            assert d.config_writes==[(0x80,0xD,1,0x40),(0x80,0xC,1,4),(0x80,4,2,command|0x1F)]
            assert all(d.registers[r]==v for r,v in before.items() if r not in (4,5,0xC,0xD))
        else:
            assert d.registers==before and not d.config_writes
        assert f[0].reg_read(x.UC_X86_REG_EFLAGS)&0xFFFF==0x247
        rows.append(dict(identity=f'{identity:08X}',bdf=bdf,command=command,accepted=accepted,status_and_SERR_preserved=True))
    # The actual enumerator reaches the fixed host and leaves ISA header alone.
    d,f,base,state=fixture(image)
    d.registers.update({4:0,5:1,6:0xA5,7:0x5A})
    isa=d.devices[0x90];isa.update({4:0x45,5:0,0xC:0x11,0xD:0x22})
    invoke(f,'pci_initialize',count=300000)
    assert (d.registers[4],d.registers[5],d.registers[6],d.registers[7],d.registers[0xC],d.registers[0xD])==(0x1F,1,0xA5,0x5A,4,0x40)
    assert (isa[4],isa[5],isa[0xC],isa[0xD])==(0x45,0,0x11,0x22)
    rows.append(dict(actual_enumerator=True,fixed_host_programmed=True,ISA_header_unchanged=True))
    return rows


def host_cache_cases(image):
    rows=[]
    for wb in (False,True):
        for parity in (0,1):
            d,f,base,state=fixture(image)
            d.write(base+0x1000,2,0x60)
            f[0].reg_write(x.UC_X86_REG_BX,0x80)
            invoke(f,'board_pci_device')
            invoke(f,'board_vga_bus_policy')
            # Reuse already-qualified 512KB geometry; only activation/preservation changed.
            for offset,size,value in ((0x1036,1,4),(0x1037,1,4),(0x1038,1,1),(0x103C,4,512*1024)):
                d.write(base+offset,size,value)
            d.write(base+state['C_CHIP'],1,0xF0)
            d.write(base+state['C_CHIP']+3,1,0x30|(0x40 if wb else 0))
            d.write(base+state['C_CHIP']+9,1,7)
            d.write(base+state['C_CHIP']+10,1,12)
            d.write(base+state['C_CHIP']+6,1,parity)
            d.write(base+state['P_RAM_FLAGS'],1,4)
            invoke(f,'chipset_apply')
            invoke(f,'chipset_parity_apply',count=3000000)
            parity_port=d.ports[0x61]
            invoke(f,'chipset_late_cache',count=2000000)
            assert d.read(base+0x1038,1)==bytes((5,))
            assert (d.registers[4],d.registers[5],d.registers[0xC],d.registers[0xD])==(0x1F,parity,4,0x40)
            assert d.ports[0x61]==parity_port and bool(parity_port&4)==(not parity)
            assert bool(d.registers[0x5A]&0x10)==bool(parity) and bool(d.devices[0x90][0x41]&0x40)==(not parity)
            assert d.registers[0x51]&0xF4==0xF4 and d.registers[0x50]&0xF0==(0xF0 if wb else 0xB0)
            assert d.registers[0x52]&0x80 and d.registers[0x53]&0x80
            assert d.devices[0x90][0x40]&4 and d.devices[0x90][0x56]&0x60==0x60
            assert d.devices[0x90][0xA4]&3==1
            rows.append(dict(policy='WB' if wb else 'WT',parity=parity,parity_controls_retained=True,fast_waits=True,burst='2-1-1-1',divider='1:1',host_header_retained=True))
    return rows

def setup_owner_cases(image,baseline=False):
    """Audit assembled views and rendered controls against their real owners."""
    from ide_completeness_proof import Machine
    import struct
    machine=Machine(image);cpu=machine.cpu;listing=machine.listing
    def data(name):
        row=next(i for i,line in enumerate(listing.lines) if name+' db' in line or name+' dw' in line)
        return listing.offset(row-1)
    def read(address,size):return bytes(cpu.mem_read(0xF0000+address,size))
    def word(address):return int.from_bytes(read(address,2),'little')
    def text(address):return read(address,100).split(b'\0')[0].decode()
    def draw(page,screen=0,field=0):
        machine.put('U_PAGE',page);machine.put('U_FOCUS',1);machine.put('U_FIELD',field)
        machine.put('U_CHIP_SCREEN',screen);machine.put('U_IDE_DEVICE',255)
        machine.call('setup_draw',DS=0xF000,ES=0xB800)
        return bytes(cpu.mem_read(0xB8000,4000))[::2]
    rows=[];issues=[];seen={};drawn_owners=[]
    groups=listing.symbol('chipset_groups');counts=listing.symbol('chipset_group_counts')
    first=data('chipset_first_view');viewcounts=data('chipset_view_counts');views=listing.symbol('chipset_views')
    rowtables=[data('chip_rows_'+str(i)) for i in range(7)]+[data('chip_headers')]
    for group in range(7):
        group_ptr=word(groups+group*2);group_count=read(counts+group,1)[0]
        start=read(first+group,1)[0];number=read(viewcounts+group,1)[0]
        for view in range(start,start+number):
            title,begin,count,rowptr,headers=struct.unpack('<HBBHH',read(views+view*8,8))
            if begin+count>group_count:issues.append(dict(kind='descriptor_spill',group=group,first=begin,count=count,owned=group_count))
            nextrow=min(p for p in rowtables if p>rowptr)
            if nextrow-rowptr!=count:issues.append(dict(kind='row_count',group=group,count=count,bytes=nextrow-rowptr))
            screen=draw(5,group+1,begin);labels=[]
            for field in range(begin,begin+count):
                descriptor=group_ptr+field*14;label=text(word(descriptor));row=read(rowptr+field-begin,1)[0]
                rendered=screen[row*80+24:row*80+24+len(label)].decode()
                assert rendered==label,(group,field,label,rendered)
                owner=tuple(read(descriptor+2,3));labels.append(label)
                if owner in seen:issues.append(dict(kind='duplicate_chip_owner',owner=owner,first=seen[owner],second=(group,field)))
                seen[owner]=(group,field);drawn_owners.append((group,field,owner,label))
            rows.append(dict(group=group,title=text(title),owned=group_count,first=begin,count=count,rows=list(read(rowptr,count)),labels=labels))
    devices=draw(3);device_owners=[]
    device_count=data('board_ports_pointers')-data('board_ports_counts')
    for field in range(device_count):
        machine.put('U_FIELD',field);machine.call('ports_ui_parameters')
        device_owners.append(machine.cpu.reg_read(x.UC_X86_REG_BX))
    if machine.state['U_PORTS']+5 in device_owners:
        assert b'Floppy Controller' in devices
        issues.append(dict(kind='duplicate_FDC',pages=['Devices','Drives'],owner=machine.state['U_PORTS']+5))
    assert b'DRAM Read Waits' not in devices
    drives=draw(1)
    assert b'Floppy Controller' in drives
    machine.put('U_FIELD',7)
    before=bytes(cpu.mem_read(machine.base+machine.state['U_PORTS'],8))
    machine.call('setup_change',AX=0x4D00)
    expected=bytearray(before);expected[5]^=1
    assert bytes(cpu.mem_read(machine.base+machine.state['U_PORTS'],8))==expected
    if baseline:
        assert {issue['kind'] for issue in issues}=={'descriptor_spill','duplicate_chip_owner','duplicate_FDC'},issues
        return dict(rejected=True,issues=issues,rendered_views=rows,device_owners=device_owners,Drives_FDC_resolved=True)
    ide_labels=[b'Primary IDE Master',b'Primary IDE Slave',b'Secondary IDE Master',b'Secondary IDE Slave']
    for index,label in enumerate(ide_labels):assert drives[(8+index)*80+24:(8+index)*80+24+len(label)]==label
    assert b'IDE Device ' not in image.read_bytes()
    if issues:raise AssertionError(issues)
    assert machine.state['U_PORTS']+5 not in device_owners
    assert rows[4]['count']==3 and 'DRAM Read Waits' not in rows[4]['labels']
    assert rows[5]['labels'].count('DRAM Read Waits')==1
    rows.append(dict(devices_owners=device_owners,FDC_only_Drives=True,IDE_labels=[v.decode() for v in ide_labels]))
    # Exercise the existing Drives arrow and popup owners, including save/reload.
    for method in ('arrow','popup'):
        m=Machine(image);before=bytes(m.cpu.mem_read(m.base+m.state['C_PORTS'],8))
        chip=bytes(m.cpu.mem_read(m.base+m.state['C_CHIP'],24));ide=bytes(m.cpu.mem_read(m.base+0xA00,51))
        m.keys=[0x5000,9]+[0x5000]*7
        m.keys += [0x4D00] if method=='arrow' else [13,0x5000,13]
        m.keys += [0x4400,ord('y')]
        m.call('setup_main',count=12000000)
        assert not m.keys and m.reset
        expected=bytearray(before);expected[5]^=1
        assert bytes(m.cpu.mem_read(m.base+m.state['U_PORTS'],8))==expected
        fresh=Machine(image);fresh.cmos[:]=m.cmos;fresh.writes.clear();fresh.call('settings_load')
        assert not fresh.writes and bytes(fresh.cpu.mem_read(fresh.base+fresh.state['C_PORTS'],8))==expected
        assert bytes(fresh.cpu.mem_read(fresh.base+fresh.state['C_CHIP'],24))==chip
        assert bytes(fresh.cpu.mem_read(fresh.base+0xA00,51))==ide
        rows.append(dict(Drives_FDC=method,saved_reloaded=True,other_owners_unchanged=True))
    return rows


def ide_label_cases(image):
    from ide_completeness_proof import Machine
    rows=[]
    labels=('Primary IDE Master','Primary IDE Slave','Secondary IDE Master','Secondary IDE Slave')
    for position,label in enumerate(labels):
        machine=Machine(image);machine.put('U_PAGE',1);machine.put('U_FOCUS',1)
        machine.put('U_FIELD',0);machine.put('U_IDE_DEVICE',position)
        machine.call('setup_draw',DS=0xF000,ES=0xB800)
        screen=bytes(machine.cpu.mem_read(0xB8000,4000))[::2]
        assert screen[3*80+23:3*80+23+len(label)]==label.encode()
        machine.put('U_IDE_DEVICE',255);machine.put('U_FIELD',position+2);machine.keys=[27]
        machine.call('setup_help',DS=0xF000,ES=0xB800)
        screen=bytes(machine.cpu.mem_read(0xB8000,4000))[::2]
        assert screen[18*80+25:18*80+25+len(label)]==label.encode()
        assert not machine.keys
        rows.append(dict(position=position,label=label,submenu_title=True,overview_help_title=True))
    return rows


def device_bounds_cases(image):
    from ide_completeness_proof import Machine
    rows=[]
    for owner in ('ports_ui_available','ports_ui_visible'):
        for field in (2,5,6,7):
            m=Machine(image);m.call(owner,CX=field)
            rejected=bool(m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1)
            assert rejected==(field>=5),(owner,field,rejected)
            rows.append(dict(owner=owner,field=field,rejected=rejected))
    return rows


def device_commit_cases(image):
    from ide_completeness_proof import Machine
    rows=[]
    for field,slot,value in ((0,0,1),(1,1,2),(2,3,3),(3,4,0),(4,None,0)):
        for flags in (0x202,0x247):
            m=Machine(image);m.put('U_PAGE',3);m.put('U_FIELD',field)
            m.cpu.mem_write(m.base+m.state['U_CHIP']+22,b'\xA1')
            before_ports=bytes(m.cpu.mem_read(m.base+m.state['U_PORTS'],8))
            before_chip=bytes(m.cpu.mem_read(m.base+m.state['U_CHIP'],24))
            pointer=m.state['U_CHIP_VALUE'] if field in (3,4) else m.state['U_PORTS']+slot
            m.call('ports_ui_parameters')
            assert m.cpu.reg_read(x.UC_X86_REG_BX)==pointer,(field,'owner pointer')
            if field in (3,4):
                values=m.cpu.reg_read(x.UC_X86_REG_SI);labels=[]
                for index in range(m.cpu.reg_read(x.UC_X86_REG_CX)):
                    offset=int.from_bytes(m.cpu.mem_read(0xF0000+values+index*2,2),'little')
                    labels.append(bytes(m.cpu.mem_read(0xF0000+offset,32)).split(b'\0')[0])
                assert labels==([b'ECP',b'EPP',b'Printer'] if field==3 else [b'1',b'3'])
            registers=dict(AX=0xB700|value,BX=pointer,CX=0x1234,DX=0xABCD,SI=0x3388,DI=0x5566,BP=0x7F20,EFLAGS=flags)
            m.call('setup_enum_store',**registers)
            for register,expected in registers.items():
                assert m.cpu.reg_read(getattr(x,'UC_X86_REG_'+register))==expected,(field,register)
            expected_ports=bytearray(before_ports);expected_chip=bytearray(before_chip)
            if field==4:expected_chip[22]|=2
            else:expected_ports[slot]=2-value if field==3 else value
            assert bytes(m.cpu.mem_read(m.base+m.state['U_PORTS'],8))==expected_ports
            assert bytes(m.cpu.mem_read(m.base+m.state['U_CHIP'],24))==expected_chip
            rows.append(dict(field=field,flags=flags,registers_preserved=True,only_existing_owner_changed=True))
    return rows


def t4_policy_cases(image):
    from ide_completeness_proof import Machine
    assert b'Game Port\0' not in image.read_bytes()
    class Screen(Machine):
        def __init__(self,*args,**kwargs):
            self.sio={0xC0:255,0xC1:0x30,0xC2:0x7E,0xC3:0x5A,0xC4:0xA5}
            self.sio_open=False;self.sio_index=0;self.popup=False;self.help_seen=False
            super().__init__(*args,**kwargs)
        def incoming(self,cpu,port,size,data):
            if port==0x109 and self.sio_open:return self.sio.get(self.sio_index,255)
            return super().incoming(cpu,port,size,data)
        def outgoing(self,cpu,port,size,value,data):
            if port==0x108:
                if value==0xAA:self.sio_open=True
                elif value==0x55:self.sio_open=False
                else:self.sio_index=value
            if port==0x109 and self.sio_open:self.sio[self.sio_index]=value
            return super().outgoing(cpu,port,size,value,data)
        def interrupt(self,cpu,number,data):
            if number==0x16 and cpu.reg_read(x.UC_X86_REG_AH)==0 and self.keys and self.get('U_PAGE')==3:
                text=bytes(cpu.mem_read(0xB8000,4000))[::2]
                assert b'Game Port' not in text
                assert b'Floppy Controller' not in text and b'DRAM Read Waits' not in text
                labels=[text[row*80+23:row*80+48].strip() for row in range(5,10)]
                if self.get('U_FOCUS')==1 and not b'SELECT VALUE' in text and b'DMA channel used' not in text:
                    assert labels==[b'Serial Port',b'Serial Port B',b'Parallel Port',b'Parallel Port Mode',b'Parallel ECP DMA Channel'],labels
                if hasattr(self,'checkpoints') and len(self.keys) in self.checkpoints:
                    field,lpt,mode,chip=self.checkpoints.pop(len(self.keys))
                    assert self.get('U_FIELD')==field,(field,self.get('U_FIELD'))
                    assert bytes(cpu.mem_read(self.base+self.state['U_PORTS']+3,2))==bytes((lpt,mode))
                    assert cpu.mem_read(self.base+self.state['U_CHIP']+22,1)[0]==chip
                if self.get('U_FOCUS')==1 and self.get('U_FIELD')==4:
                    raw=cpu.mem_read(self.base+self.state['U_CHIP']+22,1)[0]
                    if self.keys[0]==0x4B00:assert raw==self.initial^2
                    if self.keys[0]==0x3B00:
                        assert raw==self.initial
                        assert b'Parallel ECP DMA Channel' in text[9*80:10*80]
                    if self.keys[0] in (0x4800,0x5000) and b'SELECT VALUE' in text[8*80:9*80]:
                        assert [text[row*80+26:row*80+43].strip() for row in (10,11)]==[b'1',b'3']
                        self.popup=True
                    if self.keys[0]==27 and b'DMA channel used by the parallel port in ECP mode.' in text:
                        assert b'3 is the default. Avoid other devices using it.' in text
                        self.help_seen=True
            return super().interrupt(cpu,number,data)
    masks=bytes.fromhex('F0010170900301FFFF070F7F010F01FCFFFF0F01FF01030F')
    def packed(chip):
        bits=[v>>bit&1 for v,mask in zip(chip,masks) for bit in range(8) if mask>>bit&1]
        assert len(bits)==92
        raw=bytearray(b'W\0'+sum(v<<i for i,v in enumerate(bits)).to_bytes(13,'little'))
        raw[1]=-sum(raw)&255
        return raw
    rows=[]
    for initial in (0,1,2,3):
        for action in ('cancel','save'):
            m=Screen(image);m.initial=initial
            original=bytes.fromhex('A0010070900000A255070F6E010F01FCA9870F01E401')+bytes((initial,0))
            m.cpu.mem_write(m.base+0x60,original)
            m.cpu.mem_write(m.base+m.state['C_PORTS']+3,b'\x02\x02')
            devices=bytes(m.cpu.mem_read(m.base+0xA00,51));ports=bytes(m.cpu.mem_read(m.base+m.state['C_PORTS'],8))
            m.keys=[0x5000]*3+[9]+[0x5000]*4
            m.keys += [0x4D00,0x4B00,0x3B00,27,13,0x5000 if initial&2 else 0x4800,13]
            m.keys += [27,27,ord('y')] if action=='cancel' else [0x4400,ord('y')]
            m.call('setup_main',count=12000000)
            assert not m.keys and m.popup and m.help_seen
            draft=bytes(m.cpu.mem_read(m.base+m.state['U_CHIP'],24))
            assert draft==original[:22]+bytes((initial^2,0))
            assert bytes(m.cpu.mem_read(m.base+0x60,24))==original
            if action=='cancel':assert not m.writes and not m.reset
            else:
                assert m.reset and m.cmos[0x71:0x80]==packed(draft)
                fresh=Screen(image);fresh.cmos[:]=m.cmos;fresh.writes.clear();fresh.call('settings_load')
                assert not fresh.writes and bytes(fresh.cpu.mem_read(fresh.base+0x60,24))==draft
                assert bytes(fresh.cpu.mem_read(fresh.base+0xA00,51))==devices
                assert bytes(fresh.cpu.mem_read(fresh.base+fresh.state['C_PORTS'],8))==ports
                for caller in ('ide_apply_controller','init_peripherals'):
                    fresh.sio[0xC0]=255;fresh.sio[0xC3]=0xA5
                    fresh.call(caller)
                    assert not fresh.sio[0xC0]&0x20
                    assert fresh.sio[0xC3]==((0xA5&0xBF)|((draft[22]&2)<<5))
                    assert fresh.sio[0xC4]==0xA5 and not fresh.sio_open
                assert bytes(fresh.cpu.mem_read(fresh.base+0x60,24))==draft,'Opaque game compatibility bit changed'
            rows.append(dict(initial_compatibility_bits=initial,action=action,Game_absent=True,
                             game_decode_forced_off=True,ECP_choice_retained=True,packed_bits=92))
    # Real keyboard navigation must skip the inactive DMA row and restore its
    # saved selection when the same parallel port returns to ECP mode.
    for inactive in ('disabled','SPP','EPP'):
        m=Screen(image);m.initial=1
        m.cpu.mem_write(m.base+m.state['C_CHIP']+22,b'\x01')
        m.cpu.mem_write(m.base+m.state['C_PORTS']+3,b'\x02\x02')
        keys=[0x5000]*3+[9]+[0x5000]*2
        points=[]
        if inactive=='disabled':
            keys += [0x4B00,0x5000]
            points.append((len(keys),(2,0,2,1)))
            keys += [0x4D00,0x5000,0x5000]
        else:
            keys += [0x5000]+[0x4D00]*(2 if inactive=='SPP' else 1)+[0x5000]
            points.append((len(keys),(3,2,0 if inactive=='SPP' else 1,1)))
            keys += [0x4B00]*(2 if inactive=='SPP' else 1)+[0x5000]
        points.append((len(keys),(4,2,2,1)))
        keys += [27,27,ord('y')]
        m.keys=keys;m.checkpoints={len(keys)-at:expected for at,expected in points}
        m.call('setup_main',count=12000000)
        assert not m.keys and not m.checkpoints and not m.writes
        assert m.cpu.mem_read(m.base+m.state['U_CHIP']+22,1)==b'\x01'
        rows.append(dict(inactive=inactive,real_keyboard_skipped_DMA=True,reenabled_selection_retained=True))
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,default=PORT/'build/baios-m919.bin')
    parser.add_argument('--case',choices=('ide-labels','setup-owners','game-port','ecp-dma','parity-controls','t4-policy','device-commit','device-bounds','choices','irq','cyrix','shadow','parity-fast-boot','final-state','vga-bus','vga-cache','host-header','host-cache'),action='append')
    parser.add_argument('--baseline-image',type=Path,help='Prior candidate expected to fail the Setup owner audit.')
    parser.add_argument('--output',type=Path,help='Distinct evidence export for a focused run.')
    args=parser.parse_args()
    args.image=args.image.resolve()
    checks={'ide-labels':ide_label_cases,'setup-owners':setup_owner_cases,'game-port':game_port_cases,'ecp-dma':ecp_dma_cases,'parity-controls':parity_controls_cases,'t4-policy':t4_policy_cases,'device-commit':device_commit_cases,'device-bounds':device_bounds_cases,'choices':lambda p:m.tuning_cases(p,shared=False),'irq':irq_cases,'cyrix':cyrix_cases,'shadow':shadow_cases,'parity-fast-boot':parity_fast_boot_cases,'final-state':final_state_cases,'vga-bus':vga_bus_cases,'vga-cache':lambda p:final_state_cases(p,vga_bus=True),'host-header':host_header_cases,'host-cache':host_cache_cases}
    result_dir=args.image.parent.parent if args.image.parent.name=='image' else PORT/'build/tests/manual-rebuild'
    target=args.output.resolve() if args.output else result_dir/'oem-tuning.json'
    identity=m.verify(PORT,args.image)['sha256']
    output=json.loads(target.read_text()) if target.exists() else {}
    if output.get('rom_sha256')!=identity:output={'rom_sha256':identity}
    for name in args.case or checks:
        output[name]=checks[name](args.image)
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(output,indent=2)+'\n')
        print(name,'PASS',flush=True)
    if args.baseline_image:
        output['setup-owner-baseline']=setup_owner_cases(args.baseline_image.resolve(),baseline=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(output,indent=2)+'\n')
    m.verify(PORT,args.image)
