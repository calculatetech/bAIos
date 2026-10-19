"""Execute the actual stackless mapper against bank RAM and an independent floating bus."""
from pathlib import Path
import struct
import sys

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PORT.parent))
from unicorn import Uc,UC_ARCH_X86,UC_MODE_16,UC_HOOK_CODE,UC_HOOK_INSN,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
from unicorn import x86_const as x
from shared.tools.ram_proof import Listing,constants
from core_proof import ACC
import importlib


def run(image,banks=(16,0,0,0),expected_pattern=0x0004,expected_map=0x20,expected_route=0,jumper=4,reset=True,warm_marker=False,sys_flag=4,cache_kib=0,complete_post=False,ram_skip_at=None,cmos_seed=None):
    raw=Path(image).read_bytes()
    listing=Listing(Path(image).with_suffix('.lst'))
    start=0xFFF0 if reset else listing.symbol('memory_initialize')
    ready=listing.symbol('.ram_ready','startup')
    finish=listing.symbol('.wait','boot_retry') if complete_post else listing.symbol('chipset_post_recovery_notice')
    m=ACC(image,importlib.import_module('test-port').nvram() if cmos_seed is None else cmos_seed);u=m.cpu
    m.starting=True;m.stop_address=0xF0000+finish;m.sys_flag=sys_flag;m.jumper=jumper
    sizes=[n*1024*1024 for n in banks]
    storage=[bytearray(n) for n in sizes]
    sram=bytearray(cache_kib*1024)
    regs=m.registers;regs[0]=0x20;regs[5]=0x18
    index=0;rtc_index=0;writes=[];terminal=[];last=[];stack=[];prepared=False
    platform_writes=[];warm_stack=[]
    initialized=bytearray(0xA0000);initialization=[];skip_sent=False
    ram_flags=constants(PORT.parent/'shared/src/pc/state.inc')['P_RAM_FLAGS']
    cmos=m.cmos;early_trace=[];early_writes=[];owners=[];late_state=[];cache_inputs=[]
    required=('cache_initialize','cache_initial_policy','shadow_system_bios','init_pic_pit','init_rtc','init_superio','init_at_prerequisites','initialize_video','init_keyboard','arm_keyboard_runtime','settings_load','chipset_apply','publish_memory_cmos')
    if complete_post:required+=('chipset_late_cache','boot_retry')
    addresses={0xF0000+listing.symbol(name):name for name in required}
    def mapping(address):
        if 0xA0000 <= address < 0x100000:
            return None
        probing=regs[0]&15==9 and regs[0x12]&15==10
        if probing:
            bank=address//0x1000000
            if bank>=4 or not sizes[bank]:return False
            return bank,(address%0x1000000)%sizes[bank]
        offset=address
        order=sorted(range(4),key=lambda bank:(bank+((regs[0x13]>>(bank*2))&3))&3)
        for bank in order:
            size=sizes[bank]
            if offset<size:return bank,offset
            offset-=size
        return False
    def low_storage():
        bank=min((i for i in range(4) if sizes[i]),key=lambda i:(i+((regs[0x13]>>(i*2))&3))&3)
        return storage[bank]
    if warm_marker:
        regs[0]=0x20|(expected_map&15);regs[0x12]=expected_map>>4;regs[0x13]=expected_route
        low=low_storage()
        for address,payload in ((0x472,b'\x34\x12'),(0x40E,b'\x00\x9e'),(0x413,struct.pack('<H',632)),(0x9E0D0,struct.pack('<H',sum(banks)*1024-1024)),(0x9F000,struct.pack('<H',expected_pattern)),(0x9F002,bytes((expected_route,))),(0x9F007,b'\x01'),(0x180000,b'WARM-RAM')):
            low[address:address+len(payload)]=payload
    def read(cpu,access,address,size,value,context):
        nonlocal refreshing
        if 0xC0000<=address<0xC8000 and not regs[2]&1:
            original_write(address,bytes([255])*size);return
        if regs[0x1A]&0x18==0x10 and 0x20000<=address<0x80000:
            original_write(address,bytes(sram[(address-0x20000+i)%len(sram)] for i in range(size)) if sram else bytes([255])*size);return
        target=mapping(address)
        if target is None:return
        payload=bytes([255])*size if target is False else bytes(storage[target[0]][target[1]:target[1]+size])
        refreshing=True
        try:original_write(address,payload)
        finally:refreshing=False
    def write(cpu,access,address,size,value,context):
        if regs[0x1A]&0x18==0x10 and 0x20000<=address<0x80000:
            if sram:
                for i,b in enumerate(value.to_bytes(size,'little')):sram[(address-0x20000+i)%len(sram)]=b
            return
        target=mapping(address)
        if target is False or target is None:return
        storage[target[0]][target[1]:target[1]+size]=value.to_bytes(size,'little')
        if address<0xA0000:initialized[address:address+size]=bytes([1])*size
    original_write=u.mem_write;refreshing=False
    def external_write(address,data):
        original_write(address,data)
        if refreshing:return
        for offset,byte in enumerate(data):
            target=mapping(address+offset)
            if target is not False and target is not None:storage[target[0]][target[1]]=byte
    u.mem_write=external_write
    cache_entry=0xF0000+listing.symbol('cache_initialize')
    late_entry=0xF0000+listing.symbol('chipset_late_cache') if complete_post else None
    ram_keyboard=0xF0000+listing.symbol('.keyboard','chipset_visible_ram_test')
    ram_visible=0xF0000+listing.symbol('chipset_visible_ram_test')
    ram_point=0xF0000+listing.symbol('.point','chipset_visible_ram_test')
    ram_blocks=[]
    l1_displays=[]
    early_display=0xF0000+listing.symbol('post_early_setup')
    final_display=0xF0000+listing.symbol('post_ui_roms')
    fatal_entry=0xF0000+listing.symbol('hard_halt')
    ram_entries={0xF0000+listing.symbol('memory_initialize'),0xF0000+listing.symbol('.warm_memory','startup')}
    def code(cpu,address,size,context):
        nonlocal prepared,skip_sent
        if address==ram_point:ram_blocks.append(cpu.reg_read(x.UC_X86_REG_EDI))
        if complete_post and address in (early_display,final_display):
            phase=cpu.mem_read(m.base+0x51,1)[0]
            if (address==early_display and phase==1) or (address==final_display and phase==5):
                selected=cpu.mem_read(m.base+0x61,1)[0]
                visible=m.text(3,24,8).strip()
                assert visible==('Enabled' if selected else 'Disabled')
                off=bool(cpu.reg_read(x.UC_X86_REG_CR0)&0x40000000)
                assert off==(phase==1 or not selected)
                l1_displays.append((phase,visible,off))
        if address==0xF0000+ready:
            prepared=True
            if reset and not (warm_marker and sys_flag&4):
                assert all(initialized),'Cold conventional RAM was not fully initialized before the stack and skippable test'
        if address in (0xF0000+ready,ram_visible,late_entry):
            missing=[i for i in range(0x80000) if i%0x10000<0xFFFC and not initialized[i]]
            initialization.append({'owner':'ram_ready' if address==0xF0000+ready else 'visible_test' if address==ram_visible else 'late_cache','unwritten_fill_bytes_this_reset':len(missing),'first_unwritten':missing[:8],'cr0':cpu.reg_read(x.UC_X86_REG_CR0),'acc':bytes(regs[:0x27]).hex(),'port92':m.port92})
        if ram_skip_at is not None and address==ram_keyboard and not skip_sent:
            sp=cpu.reg_read(x.UC_X86_REG_SS)*16+cpu.reg_read(x.UC_X86_REG_SP)
            if int.from_bytes(cpu.mem_read(sp,4),'little')>=ram_skip_at:
                m.pending.append(1) # Esc passes through the production keyboard owner.
                skip_sent=True
        if address==cache_entry and not early_trace:
            early_trace[:]=m.posts;early_writes[:]=m.acc_writes
            cache_inputs.append(bytes(regs).hex())
        if reset and address in ram_entries:
            assert platform_writes[:7]==[(0x8F,0),(0x43,0x54),(0x41,0x12),(0x0D,0x12),(0xDA,0x12),(0xD6,0xC0),(0xD4,0)], 'RAM used before stock refresh/cascade setup'
        if address in addresses:owners.append(addresses[address])
        if complete_post and address==late_entry:
            assert regs[0]&0x80,('missing OEM post-shadow register00 transition',regs[0])
            assert not regs[4]&1 and cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
            late_state.append({'registers':{f'{i:02X}':regs[i] for i in range(0x27)},'cr0':cpu.reg_read(x.UC_X86_REG_CR0)})
        last.append(address);last[:]=last[-8:]
        opcode=bytes(cpu.mem_read(address,min(size,6)))
        if not prepared and opcode[:1] in (b'\x50',b'\x51',b'\x52',b'\x53',b'\x54',b'\x55',b'\x56',b'\x57',b'\xE8'):
            if warm_marker and sys_flag&4:
                assert cpu.reg_read(x.UC_X86_REG_SS)==0 and 0x7BE0<=cpu.reg_read(x.UC_X86_REG_SP)<=0x7C00
                warm_stack.append(address)
            else:
                stack.append(address)
        if address==0xF0000+finish or (opcode[:1]==b'\xF4' and (not complete_post or fatal_entry<=address<fatal_entry+8)):cpu.emu_stop()
    def halt_observer(model,address):
        if bytes(u.mem_read(address,1))==b'\xF4' and (not complete_post or fatal_entry<=address<fatal_entry+8):model.stop_address=address
    m.code_observer=halt_observer
    u.hook_add(UC_HOOK_MEM_READ,read)
    u.hook_add(UC_HOOK_MEM_WRITE,write)
    u.hook_add(UC_HOOK_CODE,code)
    def platform_out(cpu,port,size,value,unused):
        if port in (0x8F,0x43,0x41,0x0D,0xDA,0xD6,0xD4):platform_writes.append((port,value))
    u.hook_add(UC_HOOK_INSN,platform_out,None,1,0,x.UC_X86_INS_OUT)
    for register,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_IP,start),
                           (x.UC_X86_REG_SS,0),(x.UC_X86_REG_ESP,0x430),(x.UC_X86_REG_EDX,0x403),(x.UC_X86_REG_EFLAGS,2),
                           (x.UC_X86_REG_CR0,0x60000010)):
        u.reg_write(register,value)
    u.emu_start(0xF0000+start,0x100000,count=300000000 if complete_post else 100000000)
    terminal=m.posts;writes=m.acc_writes
    if expected_map is None:
        assert terminal[-1]==0xEA and not stack,(banks,terminal,stack)
        assert terminal[2:10]==[0x27,0x2B,0x28,0x2C,0x29,0x2D,0x2A,0x2E]
        return {'banks_mib':banks,'terminal':terminal,'unsupported_map':True}
    assert u.reg_read(x.UC_X86_REG_CS)*16+u.reg_read(x.UC_X86_REG_IP)==0xF0000+finish,(banks,terminal,[hex(n) for n in last])
    if reset:
        restored_clock=0xB7 if jumper==5 else 0xB3 # Initial A5 keeps its upper bits.
        stock_clocks=[] if warm_marker and sys_flag&4 else [0x13,0x33 if jumper==4 else 0xB7 if jumper==5 else 0x13]
        assert [value for index,value in early_writes if index==6]==[restored_clock]+stock_clocks
    assert not stack,('stack access before RAM ready',stack)
    assert regs[0]&15==expected_map&15 and regs[0x12]&3==expected_map>>4,(banks,hex(regs[0]),hex(regs[0x12]),hex(expected_map))
    assert regs[0x13]==expected_route,(banks,hex(regs[0x13]),expected_route)
    total=(struct.unpack('<H',bytes(low_storage()[0x9E0D0:0x9E0D2]))[0]+1024)*1024
    assert total==sum(sizes),(banks,total,sum(sizes))
    assert struct.unpack('<H',low_storage()[0x9F000:0x9F002])[0]==expected_pattern,(banks,hex(struct.unpack('<H',low_storage()[0x9F000:0x9F002])[0]),hex(expected_pattern))
    assert struct.unpack('<H',low_storage()[0x40E:0x410])[0]==0x9E00
    assert struct.unpack('<H',low_storage()[0x413:0x415])[0]==632
    if warm_marker:
        assert bytes(low_storage()[0x180000:0x180008])==(b'WARM-RAM' if warm_marker and sys_flag&4 else bytes(8))
    if warm_marker and sys_flag&4:
        assert 0x11 in early_trace and 0x20 not in early_trace and 0x22 not in early_trace
        assert low_storage()[0x9F007]==1
    elif reset:
        expected_trace=[0x10,0x20,0x27,0x2B,0x28,0x2C,0x29,0x2D,0x2A,0x2E,0x21,0x22,0x23]
        if sum(banks)>1:expected_trace.append(0x26)
        assert early_trace==expected_trace+[0x24,0x25,0x30]
    assert owners==list(required),('Intervening startup owner/order',owners)
    if complete_post:
        assert late_state and terminal[-1]==0xE4
        if ram_skip_at is not None:
            assert skip_sent and low_storage()[m.base+ram_flags]==2,'Esc did not skip the visible RAM test'
        enabled=cache_kib>=128 and all(low_storage()[m.base+i] for i in (0x61,0x62))
        assert bool(regs[4]&1)==enabled
        if enabled:assert all(code in terminal for code in (0x64,0x69,0x54,0x56))
        assert [row[0] for row in l1_displays]==[1,5]
    # The running reset path reached this return after actual publication.
    for vector,ax,expected in ((0x12,0,632),(0x15,0x8800,sum(banks)*1024-1024)):
        actual,flags=m.public(vector,ax)
        assert actual==expected and not flags&1
    assert struct.unpack('<H',cmos[0x17:0x19])[0]==sum(banks)*1024-1024
    return {'l1_post_displays':l1_displays,'visible_ram_blocks':ram_blocks,'ram_flags':int(low_storage()[m.base+ram_flags]),'public_int12_kib':632,'public_int15_kib':sum(banks)*1024-1024,'cmos_extended_kib':struct.unpack('<H',cmos[0x17:0x19])[0],'banks_mib':banks,'physical_bytes':total,'routing':regs[0x13],'register_writes':writes,'terminal':terminal,'warm_marker':warm_marker,'kbc_system_flag':bool(sys_flag&4),'ram_sentinel_preserved':bool(warm_marker and sys_flag&4),'intervening_production_owners':owners,'cache_entry_registers_hex':cache_inputs[0],'late_entry_state':late_state,'cache_kib':cache_kib,'initialization':initialization,'ram_skip_injected':skip_sent,'terminal_owner':'actual boot_retry wait then installed INT12/15' if complete_post else 'actual publication return then installed INT12/15'}


def interleave(image, fault=None, mapper=False):
    """Exercise the candidate transition with flat RAM and explicit rejection faults.

    This checks firmware ordering and destructive validation, not ACC2168 wiring.
    """
    from capstone import Cs, CS_ARCH_X86, CS_MODE_16
    image=Path(image); listing=Listing(image.with_suffix('.lst'))
    start=listing.symbol('memory_initialize' if mapper else 'memory_interleave')
    finish=listing.symbol('.ram_ready','startup') if mapper else listing.symbol('.interleave_done','memory_initialize')
    raw=image.read_bytes();u=Uc(UC_ARCH_X86,UC_MODE_16)
    u.mem_map(0,0x4000000);u.mem_write(0xE0000,raw)
    regs={0:0x29,5:0x9C,0x12:9,0x13:0};index=0;posts=[];writes=[];bank_hooks=[]
    if mapper:
        # Four separate4MiB banks appear in16MiB probe windows, then a16MiB map.
        cells={}
        def bank_read(cpu,access,address,size,value,unused):
            if 0xA0000<=address<0x100000:return
            key=(address//0x1000000,address%0x400000)
            cpu.mem_write(address,cells.get(key,bytes(size)))
        def bank_write(cpu,access,address,size,value,unused):
            if not 0xA0000<=address<0x100000:
                cells[(address//0x1000000,address%0x400000)]=value.to_bytes(size,'little')
        bank_hooks=[u.hook_add(UC_HOOK_MEM_READ,bank_read),u.hook_add(UC_HOOK_MEM_WRITE,bank_write)]
    def inp(cpu,port,size,unused):
        if mapper and port==0x92:return 0xFC
        assert port==0xF3 and size==1
        return regs[index]
    def out(cpu,port,size,value,unused):
        nonlocal index
        assert size==1
        if port==0xF2:index=value
        elif port==0xF3:
            assert index in (0,5,0x12,0x13)
            assert cpu.reg_read(x.UC_X86_REG_ESP)==0x430
            if fault=='mode' and index==5:value|=0x10
            if fault=='map' and index==0 and value&15==5:value^=1
            if fault=='geometry' and index==0x12:value|=8
            regs[index]=value;writes.append((index,value))
        elif port==0x80:
            posts.append(value)
            if mapper and value==0x2F:
                for hook in bank_hooks:cpu.hook_del(hook)
                def absent(machine,access,address,size,value,unused):machine.mem_write(address,bytes([255])*size)
                cpu.hook_add(UC_HOOK_MEM_READ,absent,begin=0x1000000,end=0x3FFFFFF)
            if value in (0xE1,0xE2,0xE3,0xE4,0xE5,0xE6,0xEA):cpu.emu_stop()
        else:assert port==0xED or (mapper and port==0x92),hex(port)
    u.hook_add(UC_HOOK_INSN,inp,None,1,0,x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN,out,None,1,0,x.UC_X86_INS_OUT)
    injected=[]
    if fault=='ram':
        def corrupt(cpu,access,address,size,value,unused):
            if not injected:
                cpu.mem_write(address,bytes([cpu.mem_read(address,1)[0]^1]));injected.append(address)
        u.hook_add(UC_HOOK_MEM_READ,corrupt,begin=0x800000,end=0x800003)
    for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_DS,0),(x.UC_X86_REG_ES,0),
                      (x.UC_X86_REG_SS,0),(x.UC_X86_REG_ESP,0x430),(x.UC_X86_REG_EFLAGS,2),
                      (x.UC_X86_REG_CR0,0x60000010),(x.UC_X86_REG_ESI,0x33330000 if fault!='banks' else 0x22220000),
                      (x.UC_X86_REG_ECX,0)):
        u.reg_write(reg,value)
    # No stack instruction exists anywhere in this early owner, including failures.
    decoder=Cs(CS_ARCH_X86,CS_MODE_16)
    end=listing.symbol('memory_interleave_end')
    assert not any(i.mnemonic.startswith(('push','pop','call','ret')) for i in decoder.disasm(raw[65536+listing.symbol('memory_interleave'):65536+end],listing.symbol('memory_interleave')))
    u.emu_start(0xF0000+start,0xF0000+finish,count=160000000)
    assert u.reg_read(x.UC_X86_REG_ESP)==0x430
    if not mapper:assert u.reg_read(x.UC_X86_REG_ESI)==(0x22220000 if fault=='banks' else 0x33330000)
    assert bytes(u.mem_read(0xE0000,131072))==raw,'RAM test overwrote ROM/UMA'
    if mapper:
        assert posts==[0x27,0x2B,0x28,0x2C,0x29,0x2D,0x2A,0x2E,0x2F,0x31,0x32,0x21,0x22,0x23,0x26,0x24,0x25],posts
        assert u.reg_read(x.UC_X86_REG_CS)==0xF000 and u.reg_read(x.UC_X86_REG_IP)==finish
        assert int.from_bytes(u.mem_read(0x500,2),'little')==0x3333
        assert int.from_bytes(u.mem_read(0x504,4),'little')==0x1000000
        assert regs=={0:0x25,5:0x8C,0x12:0,0x13:0}
        return {'mapper':True,'posts':posts,'writes':writes,'scope':'complete cold bank probe, transition, RAM check/count and first-stack validation; synthetic wiring'}
    if fault=='banks':assert posts==[0xE3] and not writes
    elif fault in ('mode','map','geometry'):assert posts==[0x2F,{'mode':0xE2,'map':0xE4,'geometry':0xE5}[fault]]
    elif fault=='ram':assert posts==[0x2F,0x31,0xE6] and injected==[0x800000]
    else:
        assert posts==[0x2F,0x31,0x32]
        assert u.reg_read(x.UC_X86_REG_CS)==0xF000 and u.reg_read(x.UC_X86_REG_IP)==finish
        assert u.reg_read(x.UC_X86_REG_CR0)==0x60000010
        for at in (0,0x9FFFC,0x100000,0x3FFFFC,0x400000,0x800000,0xFFFFFC):
            assert int.from_bytes(u.mem_read(at,4),'little')==at^0x5AA55AA5
    if fault!='banks':assert writes[:3]==[(0x12,8 if fault=='geometry' else 0),(0,0x28),(5,0x9C if fault=='mode' else 0x8C)]
    if fault not in ('banks','mode'):assert writes[-1]==(0,0x24 if fault=='map' else 0x25)
    return {'fault':fault,'posts':posts,'writes':writes,'scope':'synthetic RAM and register readback; physical interleave unproved'}
