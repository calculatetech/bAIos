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
        if port==0x23:return self.cpu.get(self.cpu_index,0)
        return super().incoming(u,port,size)
    def outgoing(self,u,port,size,value):
        if port==0x22:self.cpu_index=value
        elif port==0x23:
            self.cpu_writes.append((self.cpu_index,value))
            if self.cpu_index==0xC3 and not self.probe_writable:value=(value&~2)|(self.cpu[0xC3]&2)
            self.cpu[self.cpu_index]=value
        super().outgoing(u,port,size,value)


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


def parity_fast_boot_cases(image):
    rows=[]
    for fast in (False,True):
        d,f,base,state=fixture(image)
        u=f[0]
        d.write(base+state['C_CHIP']+6,1,1)
        d.write(base+state['C_CHIP']+2,1,1)
        d.write(base+state['C_CHIP']+12,1,int(fast))
        d.write(base+state['S_INSTALLED_KIB32'],4,4)
        d.write(base+state['S_EXTENDED_KIB32'],4,4)
        d.write(base+state['P_RAM_FLAGS'],1,4)
        if fast:
            d.write(base+state['P_PHASE'],1,1)
            d.write(base+state['P_RAM_FLAGS'],1,0)
            d.write(base+state['S_SETUP_REQUEST'],1,0)
            for address in (0x41A,0x41C):d.write(address,2,0x1E)
            invoke(f,'chipset_visible_ram_test',count=30000000)
            assert d.read(base+state['P_RAM_FLAGS'],1)[0]&4
        original=d.read(0x100000,0x1000)
        writes=set()
        def seed(cpu,access,address,size,value,user):
            assert d.ports.get(0x61,0)&4,'parity armed before initialization'
            assert value==int.from_bytes(original[address-0x100000:address-0x100000+size],'little')
            writes.update(range(address,address+size))
        h=u.hook_add(UC_HOOK_MEM_WRITE,seed,None,0x100000,0x100FFF)
        invoke(f,'chipset_post_ram_cache',count=3000000)
        u.hook_del(h)
        assert writes==(set(range(0x100000,0x101000)) if fast else set())
        assert d.read(0x100000,0x1000)==original and not d.ports[0x61]&4
        rows.append(dict(fast_boot=fast,extended_bytes_seeded=len(writes),values_preserved=True,seeded_before_arm=True))
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
        d,f,base,state=fixture(image)
        # Aggressive explicit bus choices must remain after the entire cache path.
        for offset,value in ((3,0x40 if wb else 0),(7,0x13),(8,0x95),(9,7),(10,0x0D),(14,1)):
            d.write(base+state['C_CHIP']+offset,1,value)
        if vga_bus:
            d.devices[0x60]={0:0x33,1:0x53,2:0x11,3:0x88,4:3,0xB:3,0x3D:1}
            d.write(base+0x1000,2,0x60)
            invoke(f,'board_vga_bus_policy')
        invoke(f,'chipset_apply')
        before={r:d.registers.get(r,0) for r in (0x51,0x52,0x53,0x5A,0x60,0x61,0x62)}
        ibc={r:d.devices[0x90].get(r,0) for r in (0x40,0x41,0x46,0x56,0x57,0xA4)}
        invoke(f,'cache_qualify',count=12000000)
        assert d.read(base+0x1038,1)==b'\x01'
        invoke(f,'chipset_late_cache',count=2000000)
        assert d.read(base+0x1038,1)==b'\x05'
        after={r:d.registers.get(r,0) for r in before}
        assert after[0x51]&0xFE==before[0x51]&0xFE
        assert all(after[r]==before[r] for r in before if r!=0x51),(before,after)
        assert d.registers[0x52]&0x80 and d.registers[0x53]&0xC0==0xC0
        assert d.registers[0x55]&0xC1==0xC1
        assert all(d.devices[0x90].get(r,0)==v for r,v in ibc.items() if r!=0x46)
        assert d.devices[0x90][0xA4]&3==1
        if vga_bus:
            assert d.registers[0x51]&4 and d.devices[0x90][0x50]&0x80
            assert d.devices[0x90][0x56]&0x60==0x60
        rows.append(dict(policy='WB' if wb else 'WT',l2='qualified and enabled',bus_controls_retained=True))
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
        invoke(f,'chipset_apply')
        invoke(f,'chipset_late_cache',count=2000000)
        assert d.read(base+0x1038,1)==bytes((5,))
        assert (d.registers[4],d.registers[5],d.registers[0xC],d.registers[0xD])==(0x1F,0,4,0x40)
        assert d.registers[0x51]&0xF4==0xF4 and d.registers[0x50]&0xF0==(0xF0 if wb else 0xB0)
        assert d.registers[0x52]&0x80 and d.registers[0x53]&0x80
        assert d.devices[0x90][0x40]&4 and d.devices[0x90][0x56]&0x60==0x60
        assert d.devices[0x90][0xA4]&3==1
        rows.append(dict(policy='WB' if wb else 'WT',fast_waits=True,burst='2-1-1-1',divider='1:1',host_header_retained=True))
    return rows


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,default=PORT/'build/baios-m919.bin')
    parser.add_argument('--case',choices=('choices','irq','cyrix','shadow','parity-fast-boot','final-state','vga-bus','vga-cache','host-header','host-cache'),action='append')
    args=parser.parse_args()
    args.image=args.image.resolve()
    checks={'choices':lambda p:m.tuning_cases(p,shared=False),'irq':irq_cases,'cyrix':cyrix_cases,'shadow':shadow_cases,'parity-fast-boot':parity_fast_boot_cases,'final-state':final_state_cases,'vga-bus':vga_bus_cases,'vga-cache':lambda p:final_state_cases(p,vga_bus=True),'host-header':host_header_cases,'host-cache':host_cache_cases}
    result_dir=args.image.parent.parent if args.image.parent.name=='image' else PORT/'build/tests/manual-rebuild'
    target=result_dir/'oem-tuning.json'
    identity=m.verify(PORT,args.image)['sha256']
    output=json.loads(target.read_text()) if target.exists() else {}
    if output.get('rom_sha256')!=identity:output={'rom_sha256':identity}
    for name in args.case or checks:
        output[name]=checks[name](args.image)
        print(name,'PASS',flush=True)
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(output,indent=2)+'\n')
    m.verify(PORT,args.image)
