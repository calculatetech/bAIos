"""Execute the ROM-only mapper with an independent two-region UMC DRAM seam."""
import hashlib
import importlib.util
import json
import struct
import sys
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x
from capstone import Cs, CS_ARCH_X86, CS_MODE_16

PORT=Path(__file__).resolve().parents[1]
REPOSITORY=PORT.parent
sys.path.insert(0,str(REPOSITORY))
from shared.tools.rom import build, configuration
from shared.tools.ram_proof import Listing, constants, run as ram_run


class DRAM:
    """HB52 decoded regions, HB53 banks/sides/swap, HB61 asymmetric address mode."""
    def __init__(self, modules, flat=None, alias=None, fault=None, revision=4, outside_wrap=False):
        self.modules=modules
        self.flat=flat
        self.alias=alias
        self.fault=fault
        self.outside_wrap=outside_wrap
        self.data={}
        self.registers={0x08:revision,0x52:1,0x53:0,0x61:2}
        self.writes=[]
        self.touched=set()
        self.pattern_writes=[]
        self.gates={0x61:0,0x92:2}
        self.reset_requests=[]

    def physical(self,address):
        if 0xA0000<=address<0x100000:
            return None
        if self.flat is not None:
            return (4,address) if address<self.flat else None
        r=self.registers
        lower=0x100000<<(r[0x52]&7) if r[0x52]&7 else 0
        upper=0x100000<<((r[0x52]>>4)&7) if r[0x52]&0x70 else 0
        if address>=lower+upper:
            if not self.outside_wrap or not lower+upper:
                return None
            address %= lower+upper
        region=int(address>=lower)
        offset=address-lower if region else address
        pair=region ^ bool(r[0x52]&8)
        both=bool(r[0x53]&(1<<(region*2)))
        side=bool(r[0x53]&(2<<(region*2)))
        swap=bool(r[0x53]&(0x10<<region))
        bank=(offset>>2)&1 if both else 0
        if both:
            offset=((offset>>3)<<2)|(offset&3)
        bank ^= swap
        module=pair*2+bank
        installed=self.modules[module]
        if installed is None:
            return None
        size,sides,asymmetric=installed
        if side!=sides:
            size//=2
        if bool(r[0x61]&(0x10<<region))!=asymmetric:
            size//=2
        offset %= size*0x100000
        if self.alias is not None:
            offset &= ~(1<<self.alias)
        return module,offset

    @staticmethod
    def initial(key):
        module,offset=key
        return ((offset*37)^(offset>>7)^(module*71)^0xA5)&255

    def read(self,address,size):
        out=bytearray()
        for a in range(address,address+size):
            key=self.physical(a)
            out.append(255 if key is None else self.data.get(key,self.initial(key)))
        return bytes(out)

    def write(self,address,size,value):
        if size==4 and value in (0x55AA55AA,0xAA55AA55):
            self.pattern_writes.append((address,value))
        for i,a in enumerate(range(address,address+size)):
            key=self.physical(a)
            if key is not None:
                self.touched.add(key)
                if self.fault is not None and a==self.fault:
                    continue
                self.data[key]=(value>>(i*8))&255


def mapped(modules, *, flat=None, alias=None, fault=None, expected=None, revision=4, outside_wrap=False, memory=None,cpu_signature=0xDEAD04F0,rom_image=None):
    result=build(PORT,'build/hardware-tests/geometry')
    if rom_image is not None:
        from shared.tools.rom import verify
        result=verify(PORT,rom_image)
    rom=Path(result['path']);listing=Listing(rom.with_suffix('.lst'))
    _,cfg=configuration(PORT);layout=cfg['rom'];state=constants(REPOSITORY/'shared/src/pc/state.inc')
    state.update(constants(REPOSITORY/'shared/src/setup/layout.inc'))
    code=layout['code_segment']<<4
    u=Uc(UC_ARCH_X86,UC_MODE_16)
    u.mem_map(0,0x10200000)
    u.mem_write(layout['base'],rom.read_bytes())
    d=memory if memory is not None else DRAM(modules,flat,alias,fault,revision,outside_wrap)
    original_data=dict(d.data)
    if memory is not None:memory.machine=u
    cmos=bytearray(getattr(memory,'initial_cmos',bytes(128)));index=0;config_address=0;terminal=[];remapping=[True]
    cs=Cs(CS_ARCH_X86,CS_MODE_16)
    init=code+listing.symbol('ram_initialize')
    ready=code+listing.symbol('.ram_ready','startup')
    finish=code+listing.symbol('init_pic_pit')
    begin_state=cfg['platform']['state_seg']<<4
    stack_ops=[];excluded_writes=[];instructions={}

    def read(uc,access,address,size,value,user):
        if address<0x10200000 and not 0xA0000<=address<0x100000:
            uc.mem_write(address,d.read(address,size))

    def write(uc,access,address,size,value,user):
        if 0xA0000<=address<0x100000:
            excluded_writes.append(address)
        elif address<0x10200000:
            d.write(address,size,value)

    def inp(uc,port,size,user):
        if 0xCFC<=port<=0xCFF:
            if memory is not None and getattr(memory,'composed',False):
                return memory.pci_read(config_address,port,size)
            offset=(config_address&0xFC)+(port-0xCFC)
            return sum(d.registers.get(offset+i,0)<<(8*i) for i in range(size))
        if port==0x71:return cmos[index&127]
        if port in d.gates:return d.gates[port]
        if memory is not None:return memory.incoming(uc,port,size)
        return 0

    def out(uc,port,size,value,user):
        nonlocal config_address,index
        if port==0xCF8:config_address=value
        elif 0xCFC<=port<=0xCFF:
            offset=(config_address&0xFC)+(port-0xCFC)
            if memory is not None and getattr(memory,'composed',False):
                memory.pci_write(config_address,port,size,value)
            else:
                for i in range(size):d.registers[offset+i]=(value>>(8*i))&255
                d.writes.append((offset,size,value))
        elif port==0x70:index=value
        elif port==0x71:cmos[index&127]=value
        elif port in d.gates:d.gates[port]=value
        elif port==0x64 and value==0xFE:
            d.reset_requests.append(value);uc.emu_stop()
        elif port==cfg['platform']['post_port'] and value in (0xE2,0xE3):
            terminal.append(value);uc.emu_stop()
        if memory is not None:memory.outgoing(uc,port,size,value)

    def step(uc,address,size,user):
        if memory is not None:memory.observe(uc,address,size)
        if address==ready:remapping[0]=False
        if remapping[0] and address>=init:
            if address not in instructions:
                instructions[address]=next(cs.disasm(bytes(uc.mem_read(address,size)),address)).mnemonic
            mnemonic=instructions[address]
            if mnemonic.startswith(('push','pop')) or mnemonic in ('call','ret','enter','leave'):
                stack_ops.append((address,mnemonic))
        if address==finish and not terminal and not getattr(memory,'continuing',False):
            terminal.append('published');uc.emu_stop()

    u.report_output=[]
    def interrupt(uc,number,user):
        if memory is not None:return memory.interrupt(uc,number)
        assert number==0x10,number
        ax=uc.reg_read(x.UC_X86_REG_AX)
        if ax>>8==0x0E:u.report_output.append(ax&255)
    u.hook_add(UC_HOOK_INTR,interrupt)
    u.hook_add(UC_HOOK_MEM_READ,read)
    u.hook_add(UC_HOOK_MEM_WRITE,write)
    u.hook_add(UC_HOOK_INSN,inp,None,1,0,x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN,out,None,1,0,x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_CODE,step)
    for reg,val in ((x.UC_X86_REG_CS,layout['code_segment']),(x.UC_X86_REG_EDX,cpu_signature),(x.UC_X86_REG_CR0,0x10)):
        u.reg_write(reg,val)
    if memory is not None and getattr(memory,'composed',False):memory.prepare(u)
    u.emu_start(code+listing.symbol('startup'),code+0xFFFF,count=5000000+(memory.capacity*24 if memory is not None else 0))
    assert terminal and not stack_ops and not excluded_writes,(terminal,stack_ops,excluded_writes)
    if revision!=4:
        assert not any(offset==0x61 and value&0x30 for offset,size,value in d.writes),d.writes
    if terminal!=['published']:
        assert expected is None, (expected,terminal)
        owned={d.physical(a) for a in range(0x504,0x50A)} if terminal==[0xE3] else set()
        assert all(d.data.get(key,d.initial(key))==original_data.get(key,d.initial(key)) for key in d.touched-owned),(terminal,'failed-path restoration')
        return {'modules':modules,'terminal':terminal,'no_ram_stack':True},None
    total=(int.from_bytes(d.read(begin_state+state['S_EXTENDED_KIB32'],4),'little')+1024)*1024
    legacy=int.from_bytes(d.read(begin_state+state['S_EXTENDED_KIB'],2),'little')
    installed=int.from_bytes(d.read(begin_state+state['S_INSTALLED_KIB32'],4),'little')
    banks=d.read(begin_state+0x1033,1)[0]
    assert installed==total//1024-1024
    assert legacy==min(installed,0xFC00),(legacy,installed)
    assert d.read(begin_state+state['S_CPU_SIGNATURE'],2)==struct.pack('<H',cpu_signature&0xFFFF)
    assert d.read(0x40E,2)==struct.pack('<H',cfg['platform']['state_seg'])
    assert total==expected*0x100000,(modules,total//0x100000,expected,d.registers)
    firmware_keys={d.physical(a) for a in range(0x10000)}
    firmware_keys.update(d.physical(a) for a in range(begin_state,0xA0000))
    for key in d.touched:
        if key not in firmware_keys:
            assert d.data.get(key,d.initial(key))==original_data.get(key,d.initial(key)),(key,d.data[key],original_data.get(key,d.initial(key)))
    record={'modules':modules,'revision':revision,'outside_wrap':outside_wrap,'rom_sha256':result['sha256'],'flat':flat,'total_mib':total//0x100000,'legacy_kib':legacy,
            'banks':banks,'hb52':d.registers[0x52],'hb53':d.registers[0x53],'hb61':d.registers[0x61],
            'terminal':terminal,'no_ram_stack':True,'sentinels_restored':True,'excluded_regions_unchanged':True}
    return record,(u,d,listing,state,cmos,step)


def invoke(fixture,name,iret=False,reset=False,count=100000):
    u,d,listing,_,_,_=fixture
    code=u.reg_read(x.UC_X86_REG_CS)<<4
    u.reg_write(x.UC_X86_REG_SS,0)
    u.reg_write(x.UC_X86_REG_SP,0x6F00)
    frame=struct.pack('<HHH',0xFF00,code>>4,0x247) if iret else struct.pack('<H',0xFF00)
    for i,b in enumerate(frame):d.write(0x6F00+i,1,b)
    u.reg_write(x.UC_X86_REG_EFLAGS,0x247)
    u.emu_start(code+listing.symbol(name),code+0xFF00,count=count)
    if reset:
        assert d.reset_requests==[0xFE],(name,d.reset_requests)
    else:
        assert u.reg_read(x.UC_X86_REG_IP)==0xFF00,name


def render_banks(fixture,expected):
    u=fixture[0]
    u.reg_write(x.UC_X86_REG_DS,u.reg_read(x.UC_X86_REG_CS))
    u.reg_write(x.UC_X86_REG_ES,0xB800)
    for name,row,column in (('post_ui_banks',6,24),('post_debug_summary',4,58)):
        u.mem_write(0xB8000+row*160+column*2,b' \x07'*7)
        invoke(fixture,name)
        cells=bytes(u.mem_read(0xB8000+row*160+column*2,14))
        assert cells[::2].decode()==expected.ljust(7),(name,cells,expected)
        assert cells[1::2]==b'\x07'*7,(name,cells)
    return expected


def geometry():
    results=[]
    results.append(mapped([None]*4)[0])
    for bank in range(4):
        modules=[None]*4;modules[bank]=(16,False,False)
        r,fixture=mapped(modules,expected=16);assert r['banks']==1<<bank,r
        r['rendered_banks']=render_banks(fixture,str(bank))
        results.append(r)
    for sides,asym in ((True,False),(False,True),(True,True)):
        r,_=mapped([(32,sides,asym),None,None,None],expected=32);results.append(r)
    for modules,total,banks in (([(16,False,False)]*2+[None]*2,32,3),
                              ([(16,False,False)]*4,64,15),
                              ([(8,False,False)]*2+[(32,True,True)]*2,80,15),
                              ([(64,True,False)]*4,256,15),
                              ([(8,False,False),(16,False,False),None,None],16,2),
                              ([(16,False,False),(8,False,False),None,None],16,1),
                              ([None,None,(8,False,False),(16,False,False)],16,8),
                              ([None,None,(16,False,False),(8,False,False)],16,4)):
        r,fixture=mapped(modules,expected=total)
        if banks is not None:assert r['banks']==banks,r
        if banks==15:r['rendered_banks']=render_banks(fixture,'0 1 2 3')
        results.append(r)
    for mib in (8,16,48,64,128,256):
        results.append(mapped([None]*4,flat=mib*0x100000,expected=mib)[0])
    results.append(mapped([(16,False,False),None,None,None],alias=23,expected=8)[0])
    failed=mapped([(16,False,False),None,None,None],fault=0x22000)[0]
    assert failed['terminal']==[0xE3],failed
    results.append(failed)
    failed=mapped([(16,False,False),None,None,None],alias=2)[0]
    assert failed['terminal']==[0xE2],failed
    results.append(failed)
    for asym,total in ((False,32),(True,16)):
        results.append(mapped([(32,False,asym),None,None,None],expected=total,revision=3)[0])
    results.append(mapped([(16,False,False),None,None,None],expected=16,outside_wrap=True)[0])
    return results


def services():
    results=[]
    for mib in (16,64,80,128,256):
        modules=([(mib,False,False),None,None,None] if mib<=128 else [(64,True,False)]*4)
        if mib==80:modules=[(8,False,False)]*2+[(32,True,True)]*2
        r,fixture=mapped(modules,expected=mib)
        u,d,listing,state,cmos,step=fixture
        code=u.reg_read(x.UC_X86_REG_CS)<<4
        base=configuration(PORT)[1]['platform']['state_seg']<<4
        u.reg_write(x.UC_X86_REG_CS,code>>4);u.reg_write(x.UC_X86_REG_SS,0)
        invoke(fixture,'publish_memory_cmos')
        expected=min(mib*1024-1024,0xFC00)
        assert cmos[0x17:0x19]==struct.pack('<H',expected)
        assert cmos[0x30:0x32]==struct.pack('<H',expected)
        assert cmos[0x15:0x17]==struct.pack('<H',640)
        assert int.from_bytes(cmos[0x2E:0x30],'big')==sum(cmos[0x10:0x2E])
        u.reg_write(x.UC_X86_REG_EAX,0xCAFE8800)
        invoke(fixture,'int15',True)
        assert u.reg_read(x.UC_X86_REG_EAX)==0xCAFE0000+expected
        assert not u.reg_read(x.UC_X86_REG_EFLAGS)&1
        # Render the common count owner with the actual published wide count.
        u.reg_write(x.UC_X86_REG_ES,0xB800);u.reg_write(x.UC_X86_REG_DI,24*2)
        u.reg_write(x.UC_X86_REG_FS,base>>4)
        u.reg_write(x.UC_X86_REG_EAX,mib*1024)
        invoke(fixture,'post_count')
        text=bytes(u.mem_read(0xB8000+48,12))[::2].decode()
        assert text==str(mib*1024).ljust(6),text
        u.reg_write(x.UC_X86_REG_DS,code>>4)
        u.reg_write(x.UC_X86_REG_ES,0xB800)
        d.write(base+state['U_FOCUS'],1,1)
        invoke(fixture,'setup_draw')
        value_col=state['UI_LABEL_COL']+state['UI_LABEL_WIDTH']+1
        setup_total=bytes(u.mem_read(0xB8000+9*160+value_col*2,12))[::2].decode()
        setup_extended=bytes(u.mem_read(0xB8000+11*160+value_col*2,12))[::2].decode()
        assert setup_total==str(mib*1024).ljust(6),setup_total
        assert setup_extended==str(mib*1024-1024).ljust(6),setup_extended
        invoke(fixture,'post_debug_summary')
        summary_extended=bytes(u.mem_read(0xB8000+3*160+58*2,12))[::2].decode()
        assert summary_extended==str(mib*1024-1024).ljust(6),summary_extended
        r.update(cmos_kib=expected,int15_kib=expected,rendered_total=text,
                 setup_total=setup_total,setup_extended=setup_extended,summary_extended=summary_extended)
        results.append(r)
    # Execute the optional serial/VGA diagnostic owner with the same published state.
    report=build(PORT,'build/hardware-tests/geometry-report',defines=('EMULATOR_TEST',))
    report_rom=Path(report['path'])
    u.mem_write(configuration(PORT)[1]['rom']['base'],report_rom.read_bytes())
    listing=Listing(report_rom.with_suffix('.lst'))
    u.reg_write(x.UC_X86_REG_DS,code>>4)
    u.report_output=[]
    invoke((u,d,listing,state,cmos,step),'report_memory')
    text=bytes(u.report_output).decode()
    assert text.endswith(' RAM=262144 KiB\r\n'),text
    results.append({'standalone_report':text,'rom_sha256':report['sha256']})
    # The actual RAM owner must traverse above the word boundary.
    _,cfg=configuration(PORT);rom=PORT/'build/hardware-tests/geometry/baios-m919.bin'
    for kib in (65536,131072):
        proof=ram_run(rom,cfg['rom'],constants(REPOSITORY/'shared/src/pc/state.inc'),kib=kib,
                      coverage=False,legacy=kib==65536)
        if kib==131072:
            cells=bytes.fromhex(proof['progress_cells'])
            assert cells[::2]==b'131072KB' and cells[1::2]==b'\x07'*8,cells
        assert proof['ranges'][-1][1]==kib*1024
        results.append({'ram_kib':kib,'ram_owner':proof})
    # Supply timer events through the installed IRQ0/INT1C owners for error tones.
    from cache_proof import SRAM
    class TimerDRAM(DRAM):
        capacity=0
        def incoming(self,u,port,size):return 0
        def outgoing(self,u,port,size,value):pass
        def interrupt(self,u,number):
            if number==0x10:
                if u.reg_read(x.UC_X86_REG_AX)>>8==0x0E:u.report_output.append(u.reg_read(x.UC_X86_REG_AL))
            else:SRAM.cpu_interrupt(self,u,number)
        def observe(self,u,address,size):
            if bytes(u.mem_read(address,size))==b'\xF4' and u.reg_read(x.UC_X86_REG_EFLAGS)&0x200:
                SRAM.cpu_interrupt(self,u,8,(u.reg_read(x.UC_X86_REG_IP)+size)&0xFFFF)

    # A fault beyond the legacy ceiling must reach the post-RAM owner.
    for fault in (None,0x4100000):
        r,fixture=mapped([(128,False,False),None,None,None],expected=128,
                         memory=TimerDRAM([(128,False,False),None,None,None]))
        u,d,listing,state,cmos,_=fixture
        code=u.reg_read(x.UC_X86_REG_CS)<<4
        points=[0x10000]+[mib*0x100000 for mib in range(1,127)]
        before={address:d.read(address,4) for address in points}
        d.fault=fault;d.pattern_writes.clear();d.gates.update({0x61:0x40,0x92:0x22})
        u.reg_write(x.UC_X86_REG_DS,0x1234);u.reg_write(x.UC_X86_REG_ES,0x2345)
        row=next(i for i in range(listing.row('chipset_post_ram_cache'),len(listing.lines))
                 if 'call chipset_runtime_ram_check' in listing.lines[i])
        branch=code+listing.offset(row)
        entry=code+listing.symbol('chipset_runtime_ram_check')
        registers=(x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX,
                   x.UC_X86_REG_ESI,x.UC_X86_REG_EDI,x.UC_X86_REG_EBP,x.UC_X86_REG_DS,
                   x.UC_X86_REG_ES,x.UC_X86_REG_FS,x.UC_X86_REG_GS,x.UC_X86_REG_CR0,
                   x.UC_X86_REG_GDTR,x.UC_X86_REG_SS,x.UC_X86_REG_SP)
        snapshots=[];carry=[]
        def observe(uc,address,size,user):
            if address in (entry,branch):
                values=[uc.reg_read(reg) for reg in registers]
                if address==entry:values[-1]+=2
                snapshots.append((tuple(values),dict(d.gates)))
                if address==branch:carry.append(uc.reg_read(x.UC_X86_REG_EFLAGS)&1)
        hook=u.hook_add(UC_HOOK_CODE,observe)
        invoke(fixture,'chipset_post_ram_cache',reset=fault is not None)
        u.hook_del(hook)
        assert len(snapshots)==2 and snapshots[0]==snapshots[1],snapshots
        assert carry==[int(fault is not None)],carry
        checked=points if fault is None else points[:points.index(fault)+1]
        expected=[(address,pattern) for address in checked for pattern in (0x55AA55AA,0xAA55AA55)]
        if fault is not None:expected.pop()
        assert d.pattern_writes==expected,(fault,d.pattern_writes)
        assert all(d.read(address,4)==value for address,value in before.items()),'late probe restoration'
        assert cmos[0x69]==(0 if fault is None else 0xD2)
        assert cmos[0x36]==(0 if fault is None else 0x1A)
        assert d.reset_requests==([] if fault is None else [0xFE])
        r.update(late_runtime_fault=fault,probe_points=checked,runtime_cf=carry[0],
                 probe_bytes_restored=True,machine_state_restored=True,
                 cmos_recovery=[cmos[0x69],cmos[0x36]],reset_requests=d.reset_requests,
                 late_terminal='returned' if fault is None else '8042 FE request; reset/reload not emulated')
        results.append(r)
    return results


def native_checks():
    spec=importlib.util.spec_from_file_location('m919_post',PORT/'tools/test-post.py')
    post=importlib.util.module_from_spec(spec);spec.loader.exec_module(post)
    results=[]
    for mib in (8,16,128):
        name='geometry-native-'+str(mib)+'m'
        results.append(post.execute(name,{0:65},ram=mib*1024))
        vm=(PORT/'build/tests/post'/name/'vm').resolve()
        assert vm.is_relative_to((PORT/'build/tests/post').resolve())
        import shutil
        shutil.rmtree(vm)
    return results


def check(case):
    results=geometry() if case=='geometry' else services()
    path=PORT/'build/research/hardware/geometry-proof.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    record=json.loads(path.read_text()) if path.exists() else {}
    record[case]=results
    if case=='memory-services':record['native']=native_checks()
    names=('m919/src/hardware/memory.inc','m919/src/hardware/startup-core.inc','m919/src/hardware/post-core.inc',
           'm919/src/hardware/board-definition.inc','m919/src/hardware/board-core.inc','shared/src/pc/state.inc',
           'shared/src/firmware/ram-test.inc','shared/src/firmware/post.inc','shared/src/firmware/setup.inc',
           'shared/tools/ram_proof.py','m919/tools/geometry_proof.py','m919/tests/core-boot.asm')
    record['sources']={name:hashlib.sha256((REPOSITORY/name).read_bytes()).hexdigest() for name in names}
    path.write_text(json.dumps(record,indent=2)+'\n')
    print(f'{case}: {len(results)} actual-firmware scenarios PASS',flush=True)
    return results

if __name__=='__main__':check(sys.argv[1] if len(sys.argv)>1 else 'geometry')
