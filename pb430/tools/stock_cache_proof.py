"""Compare assembled cache hardware operations with the unmodified PB430 ROM."""
import json
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.ram_proof import Listing


def verify(image, cold_record=None):
    image = Path(image)
    original = (PORT/'reference/pb430-m27c1001.bin').read_bytes()[65536:]
    candidate = image.read_bytes()[65536:]
    listing = Listing(image.with_suffix('.lst'))
    def instructions(raw, start, stop, targets=None):
        decoded=list(Cs(CS_ARCH_X86, CS_MODE_16).disasm(raw[start:stop],start))
        assert decoded and decoded[-1].address+decoded[-1].size==stop
        positions={ins.address:i for i,ins in enumerate(decoded)}
        result=[]
        for ins in decoded:
            operand=ins.op_str
            if ins.mnemonic=='call':operand=targets[int(operand,16)]
            elif ins.mnemonic.startswith('j'):operand=positions[int(operand,16)]
            elif ins.mnemonic=='xchg':operand=','.join(sorted(operand.split(', ')))
            result.append((ins.mnemonic,operand))
        return result
    exact = {}
    reset_prefix_start=listing.symbol('.cache_off','startup')
    reset_prefix_end=listing.symbol('.refresh_dma','startup')
    assert original[0x963D:0x964B]==original[0x8F3A:0x8F48]
    assert candidate[reset_prefix_start:reset_prefix_end]==original[0x963D:0x964B], 'Reset cache disable differs from stock'
    exact['startup_cache_off']={'source':'963D-964A / 8F3A-8F47','byte_identical':True,'placement':'before modular RAM work'}
    for name,end,start,stop in (
        ('cache_stock_cold_resume','cache_stock_cold_resume_controls',0xE081,0xE0B2),
        ('cache_stock_cold_resume_controls','cache_stock_cold_resume_end',0xE0E6,0xE10C),
    ):
        assert candidate[listing.symbol(name):listing.symbol(end)]==original[start:stop], 'Cold shutdown-test resume differs from stock'
        exact[name]={'source':f'{start:04X}-{stop-1:04X}','byte_identical':True}
    timer=listing.symbol('cache_stock_timer')
    timer_end=listing.symbol('cache_stock_timer_end')
    zero=listing.symbol('cache_stock_timer_zero')
    expected_timer=bytearray(original[0xCFDF:0xD028])
    assert original[0xD56F:0xD571]==b'\0\0'
    assert expected_timer[3:6]==bytes.fromhex('2e8e1e')
    expected_timer[6:8]=struct.pack('<H',zero)
    assert candidate[zero:zero+2]==b'\0\0'
    assert candidate[timer:timer_end]==expected_timer,'Stock timer changed beyond its relocated zero constant'
    exact['cache_stock_timer']={'source':'CFDF-D027','only_zero_constant_address_relocated':True}
    for name, end, start, stop in (
        ('acc_read', 'acc_write', 0xA168, 0xA171),
        ('cache_stock_write', 'cache_stock_write_end', 0xA171, 0xA17C),
        ('cache_stock_cmos_read', 'cache_stock_cmos_read_end', 0xDC2C, 0xDC38),
        ('cache_stock_cpu_enable', 'cache_stock_cpu_enable_end', 0x971F, 0x972D),
        ('cache_stock_fill', 'cache_stock_fill_end', 0x9795, 0x97C7),
        ('shadow_memory_finish', 'shadow_memory_finish_end', 0x94B1, 0x94E9),
    ):
        first,last=listing.symbol(name),listing.symbol(end)
        actual = candidate[first:last]
        if name=='cache_stock_fill':
            assert actual==original[start:stop], 'cache_stock_fill bytes differ from stock'
            assert listing.symbol('.fill',name)==first+0x12
            assert listing.symbol('.reads',name)==first+0x1B
        assert instructions(candidate,first,last)==instructions(original,start,stop), name
        exact[name] = {'source':f'{start:04X}-{stop-1:04X}','instructions_match':True,'byte_identical':actual==original[start:stop]}
    restore=listing.symbol('cache_late_restore')
    restore_end=listing.symbol('cache_late_restore_end')
    assert candidate[restore:restore_end]==original[0x978E:0x9795]
    assert candidate[listing.symbol('.reset_pulse_prepare','warm_reset'):listing.symbol('.reset_pulse_ready','warm_reset')]==original[0x7EE2:0x7EF5]
    assert instructions(candidate,listing.symbol('.warm_cache','startup'),listing.symbol('.warm_cache_ready','startup'))==instructions(original,0x8E88,0x8E9E)
    names = {0xA168:'read', 0xA171:'write', 0xDC2C:'cmos', 0x9795:'fill'}
    relocated = {listing.symbol(a):b for a,b in (
        ('acc_read','read'), ('cache_stock_write','write'),
        ('cache_stock_cmos_read','cmos'), ('cache_stock_fill','fill'))}
    assert instructions(candidate, listing.symbol('cache_stock_enable'), listing.symbol('cache_stock_enable_end'), relocated) == instructions(original, 0x9748, 0x978E, names), 'Uninterrupted cache transition differs from stock'
    assert instructions(candidate,listing.symbol('cache_stock_warm_entry'),listing.symbol('cache_stock_warm_entry_end'),relocated)==instructions(original,0x963D,0x9688,names)
    for name, offset in (('acc_cache_safe_table',0x91EA), ('acc_cache_live_table',0x9232)):
        start=listing.symbol(name)
        for row in range(6):
            index, mask, *values = candidate[start+row*6:start+(row+1)*6]
            assert b''.join(bytes((index,mask,value)) for value in values)==original[offset+row*12:offset+(row+1)*12]
    for code in (1,2,3):
        for name, offset in (('acc_cache_size_1d',0x927A), ('acc_cache_size_1e',0x9284)):
            table=struct.unpack_from('<H',original,offset+code*2)[0]
            value=candidate[listing.symbol(name)+code-1]
            assert all(original[table+i*3+2]==value for i in range(4))
    for code,name in ((0,'acc_range_absent'),(1,'acc_range128'),(2,'acc_range256_512'),(3,'acc_range256_512')):
        table=0x9E4D if code==0 else struct.unpack_from('<H',original,0x9E43+code*2)[0]
        values=candidate[listing.symbol(name):listing.symbol(name)+6]
        for row in range(9):
            assert original[table+row*12:table+(row+1)*12]==b''.join(bytes((0x0C+i,v)) for i,v in enumerate(values))

    def io_block(raw,start,stop,jumper=4):
        u=Uc(UC_ARCH_X86,UC_MODE_16);u.mem_map(0,0x100000);u.mem_write(0xF0000,raw)
        registers=bytearray([0xA5])*256;registers[5]=0x18
        index=0;port92=0x40;events=[]
        def write(cpu,port,size,value,unused):
            nonlocal index,port92
            if port!=0x80:events.append((port,value))
            if port==0xF2:index=value
            elif port==0xF3:registers[index]=value
            elif port==0x92:port92=value
        def read(cpu,port,size,unused):
            if port==0xF3:return registers[index]
            if port==0x78:return jumper
            if port==0x92:return port92
            return 0
        u.hook_add(UC_HOOK_INSN,write,None,1,0,x.UC_X86_INS_OUT)
        u.hook_add(UC_HOOK_INSN,read,None,1,0,x.UC_X86_INS_IN)
        u.reg_write(x.UC_X86_REG_CS,0xF000);u.reg_write(x.UC_X86_REG_IP,start);u.reg_write(x.UC_X86_REG_EFLAGS,2)
        u.emu_start(0xF0000+start,0xF0000+stop,count=100000)
        assert u.reg_read(x.UC_X86_REG_IP)==stop
        return events,bytes(registers),port92
    reset_prefix=[]
    for jumper in range(8):
        assert io_block(original,0xE067,0xE0A9,jumper)==io_block(candidate,listing.symbol('.clock','startup'),listing.symbol('.initial_setup','startup'),jumper)
        reset_prefix.append({'jumper':jumper,'initial_clock_and_board_io_match':True})
    expected_reset=io_block(original,0xF163,0xF1A0)
    actual_reset=io_block(candidate,listing.symbol('.initial_setup','startup'),listing.symbol('.initial_done','startup'))
    assert actual_reset==expected_reset,('initial reset I/O',next(((i,a,b) for i,(a,b) in enumerate(zip(actual_reset[0],expected_reset[0])) if a!=b),None),len(actual_reset[0]),len(expected_reset[0]))
    refresh=io_block(original,0xE115,0xE133)
    assert io_block(candidate,listing.symbol('.refresh_dma','startup'),listing.symbol('.refresh_dma_ready','startup'))==refresh, 'refresh/cascade prerequisite differs'
    assert io_block(original,0x9909,0x99C8)==io_block(candidate,listing.symbol('memory_initialize'),listing.symbol('.mode1_ready','memory_initialize'))

    def execute(raw, entry, fill, code, cpu_enabled, early=False, jumper=4, interrupts=True, memory_state=None, initial_registers=None,l2_enabled=True):
        u=Uc(UC_ARCH_X86,UC_MODE_16);u.mem_map(0,0x100000)
        u.mem_write(0xF0000,raw);u.mem_write(0x40E,struct.pack('<H',0x9E00))
        u.mem_write(0x9E061,bytes((int(cpu_enabled),int(l2_enabled))))
        u.mem_write(0x9F003,bytes((int(bool(code)),code,int(bool(code)))))
        u.mem_write(0x6FFE,b'\xff\xff')
        registers=bytearray(256);registers[1]=0x93;registers[2]=0xB9
        registers[4]=0x14;registers[0x1A]=0x64
        reset_entries=(0x968E,listing.symbol('cache_stock_reset'),0x963D,listing.symbol('cache_stock_warm_entry'))
        if entry in reset_entries:
            registers[4]|=int(bool(code) and cpu_enabled and l2_enabled)
        registers[0x1D]=0xF0;registers[0x1E]=0xFB
        if initial_registers is not None:registers[:]=initial_registers
        if memory_state is not None:registers[0],registers[0x12]=memory_state
        cmos=bytearray(128);cmos[0x34]=0x40 if cpu_enabled else 0
        cmos[0x3D]=0x10 if code and l2_enabled else 0;cmos[0x3F]=code
        stock_early=early and entry==0x8F07
        if early and not stock_early:
            chip=bytes((0,int(cpu_enabled),1,1,1,1))+bytes(18)
            cmos[0x69]=0xC2;cmos[0x6A]=(-0xC2-sum(chip))&255
            cmos[0x6B:0x80]=chip[:21];cmos[0x33:0x36]=chip[21:]
        sram=bytearray({0:0,1:128,2:512,3:256}[code]*1024)
        index=0;cmos_index=0;events=[];reads=[];stack_accesses=[];chipset_io=[]
        last_chipset=False;nmi_masked=False
        probe_io=[];probe_active=False;probe_tail=False
        activation=False
        activation_start=0xF9748 if raw is original else 0xF0000+listing.symbol('cache_stock_enable')
        activation_end=0xF978E if raw is original else 0xF0000+listing.symbol('cache_stock_enable_end')
        def write(cpu,port,size,value,unused):
            nonlocal index,cmos_index,last_chipset,nmi_masked,probe_active,probe_tail
            if early and port==0xF3 and index==0x1A and value&0x18==0x10:probe_active=True
            if probe_active or probe_tail:
                probe_io.append((cpu.reg_read(x.UC_X86_REG_IP),'out',port,size,value))
                if probe_tail:
                    assert port==0xED,'Missing stock probe exit delay'
                    probe_tail=False
                elif port==0xF3 and index==0x1A and value&0x18!=0x10:
                    probe_active=False;probe_tail=True
            if activation:chipset_io.append(('activation_out',port,size,value))
            if port in (0xF2,0xF3):
                chipset_io.append(('out',port,value));last_chipset=True
            elif port==0xED:
                if last_chipset:chipset_io.append(('delay',value))
            else:
                last_chipset=False
            if port==0x70 and bool(value&0x80)!=nmi_masked:
                nmi_masked=bool(value&0x80);chipset_io.append(('nmi_masked',nmi_masked))
            if port==0xF2:index=value
            elif port==0xF3:
                registers[index]=value
                events.append(('register',index,value,cpu.reg_read(x.UC_X86_REG_CR0),bool(cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200)))
            elif port==0x70:cmos_index=value&0x7F
            elif port in (0x64,0x60):events.append(('kbc_write',port,value,bool(cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200)))
        def read(cpu,port,size,unused):
            nonlocal last_chipset
            assert not probe_tail,'Missing stock probe exit delay'
            if probe_active:
                value=registers[index] if port==0xF3 else cmos[cmos_index] if port==0x71 else jumper if port==0x78 else 0
                probe_io.append((cpu.reg_read(x.UC_X86_REG_IP),'in',port,size,value))
            if activation:
                value=registers[index] if port==0xF3 else cmos[cmos_index] if port==0x71 else jumper if port==0x78 else 0
                chipset_io.append(('activation_in',port,size,value))
            if port==0xF3:
                chipset_io.append(('in',port,registers[index]));last_chipset=True
                return registers[index]
            last_chipset=False
            if port==0x71:return cmos[cmos_index]
            if port==0x78:return jumper
            if port==0x64:events.append(('kbc_status',bool(cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200)))
            return 0
        def instruction(cpu,address,size,unused):
            nonlocal activation
            if address==activation_start:activation=True
            elif address==activation_end:activation=False
            op=bytes(cpu.mem_read(address,size))
            if op==b'\x0f\x22\xc0':events.append(('cr0',cpu.reg_read(x.UC_X86_REG_EAX)))
            elif op in (b'\x0f\x08',b'\x0f\x09'):events.append(('invd' if op[-1]==8 else 'wbinvd',))
        def memory(cpu,access,address,size,value,unused):
            if registers[0x1A]&0x18==8 and address<0x10000 and cpu.reg_read(x.UC_X86_REG_CS)*16+cpu.reg_read(x.UC_X86_REG_IP)!=0xF0000+fill:
                if early:
                    assert not registers[4]&1 and cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000,'Cold resume frame accessed with cache active'
                stack_accesses.append(('read',address,size))
            if early and registers[0x1A]&0x18==0x10 and 0x20000<=address<0x80000:
                cpu.mem_write(address,bytes(sram[(address-0x20000+i)%len(sram)] for i in range(size)) if sram else b'\xff'*size)
            if cpu.reg_read(x.UC_X86_REG_CS)*16+cpu.reg_read(x.UC_X86_REG_IP)==0xF0000+fill:reads.append((address,size))
        def memory_write(cpu,access,address,size,value,unused):
            if registers[0x1A]&0x18==8 and address<0x10000:stack_accesses.append(('write',address,size))
            if early and sram and registers[0x1A]&0x18==0x10 and 0x20000<=address<0x80000:
                for i,b in enumerate(value.to_bytes(size,'little')):sram[(address-0x20000+i)%len(sram)]=b
        u.hook_add(UC_HOOK_INSN,write,None,1,0,x.UC_X86_INS_OUT)
        u.hook_add(UC_HOOK_INSN,read,None,1,0,x.UC_X86_INS_IN)
        u.hook_add(UC_HOOK_CODE,instruction)
        u.hook_add(UC_HOOK_MEM_READ,memory)
        u.hook_add(UC_HOOK_MEM_WRITE,memory_write)
        for reg,value in ((x.UC_X86_REG_EAX,0x11223344),(x.UC_X86_REG_EBX,0x55667788),
                          (x.UC_X86_REG_ECX,0x99AABBCC),(x.UC_X86_REG_EDX,0xDDEEFF00),
                          (x.UC_X86_REG_ESI,0x12345678),(x.UC_X86_REG_EDI,0x23456789),
                          (x.UC_X86_REG_EBP,0x3456789A),
                          (x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_IP,entry),
                          (x.UC_X86_REG_FS,0x9E00),
                          (x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x6FFE),
                          (x.UC_X86_REG_CR0,0x10 if entry in reset_entries and cpu_enabled else 0x60000010),(x.UC_X86_REG_EFLAGS,2 if early or not interrupts else 0x202)):
            u.reg_write(reg,value)
        finish=0xF9688 if entry==0x963D else 0xF0000+listing.symbol('cache_stock_warm_entry_end') if entry==listing.symbol('cache_stock_warm_entry') else 0xF3A5A if stock_early else 0xF4C56 if entry==0x4C45 else 0xFFFFF
        u.emu_start(0xF0000+entry,finish,count=2000000)
        assert u.reg_read(x.UC_X86_REG_IP)==finish-0xF0000
        if stock_early:
            # 437F/4381 pulses reset with shutdown0A. The boot block resumes43C7
            # through these hardware owners, without repeating the cold probe.
            for start,stop in ((0xE081,0xE0B2),(0xE0E6,0xE10C)):
                u.reg_write(x.UC_X86_REG_IP,start)
                u.emu_start(0xF0000+start,0xF0000+stop,count=1000)
                assert u.reg_read(x.UC_X86_REG_IP)==stop
        if early and not stock_early:
            u.reg_write(x.UC_X86_REG_SP,0x6FFE);u.mem_write(0x6FFE,b'\xff\xff')
            u.reg_write(x.UC_X86_REG_IP,listing.symbol('cache_initial_policy'))
            u.emu_start(0xF0000+listing.symbol('cache_initial_policy'),0xFFFFF,count=2000000)
            assert u.reg_read(x.UC_X86_REG_IP)==0xFFFF
        abi=tuple(u.reg_read(reg) for reg in (x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX,x.UC_X86_REG_ESI,x.UC_X86_REG_EDI,x.UC_X86_REG_EBP,x.UC_X86_REG_ESP,x.UC_X86_REG_DS,x.UC_X86_REG_ES,x.UC_X86_REG_FS,x.UC_X86_REG_GS)) if not early else ()
        assert not probe_active and not probe_tail,'SRAM probe did not restore normal mode'
        return events, reads, bytes(registers), u.reg_read(x.UC_X86_REG_CR0), bool(u.reg_read(x.UC_X86_REG_EFLAGS)&0x200), abi, stack_accesses, chipset_io, probe_io

    start,stop=listing.symbol('cache_stock_fill'),listing.symbol('cache_stock_fill_end')
    fill=next(ins.address for ins in Cs(CS_ARCH_X86,CS_MODE_16).disasm(candidate[start:stop],start) if ins.mnemonic=='rep lodsd')
    cases=[]
    for code in (0,1,2,3):
        for enabled in (False,True):
            for interrupts in (False,True):
                stock=execute(original,0x9706,0x97B0,code,enabled,interrupts=interrupts)
                port=execute(candidate,listing.symbol('cache_late_stock_frame'),fill,code,enabled,interrupts=interrupts)
                assert port==stock, (code,enabled,interrupts,'stock hardware/return sequence differs',port[0],stock[0],port[4:],stock[4:])
                assert len(port[1])==(8*0x3FFF if code and enabled else 0)
                cases.append({'cache_code':code,'cpu_enabled':enabled,'entry_interrupts':interrupts,'register_cpu_if_order_and_return_match':True,'fill_reads':len(port[1])})
    physical_stack=[]
    for code in (0,1,2,3):
        for enabled in (False,True):
            stock=execute(original,0x4C45,0x97B0,code,enabled,interrupts=False)
            port=execute(candidate,listing.symbol('chipset_late_cache'),fill,code,enabled,interrupts=False)
            assert port[:5]==stock[:5] and port[6:]==stock[6:],(code,enabled,'stock caller/cache physical accesses or I/O differ',port[6][:20],stock[6][:20])
            if code and enabled:
                assert min(address for direction,address,size in port[6])==0x3D8
                assert max(address+size for direction,address,size in port[6])<=0x3EE
            physical_stack.append({'cache_code':code,'cpu_enabled':enabled,'stock_parent_physical_accesses_match':True,'minimum_physical_stack':0x3D8 if code and enabled else None})
    reset_cases=[]
    warm_entry_cases=[]
    for enabled in (False,True):
        for interrupts in (False,True):
            stock=execute(original,0x963D,0x97B0,2,enabled,interrupts=interrupts)
            port=execute(candidate,listing.symbol('cache_stock_warm_entry'),fill,2,enabled,interrupts=interrupts)
            assert port[:5]==stock[:5] and port[7]==stock[7], 'earlier warm teardown differs'
            assert len(port[1])==8*0x3FFF and not port[2][4]&1 and not port[2][0x1E]&0x20
            warm_entry_cases.append({'l1_before':enabled,'if_before':interrupts,'stock_io_cpu_fill_nmi_if_match':True})
    for code in (0,1,2,3):
        for enabled in (False,True):
            for interrupts in (False,True):
                for requested in ((False,True) if code else (True,)):
                    stock=execute(original,0x968E,0x97B0,code,enabled,interrupts=interrupts,l2_enabled=requested)
                    port=execute(candidate,listing.symbol('cache_stock_reset'),fill,code,enabled,interrupts=interrupts,l2_enabled=requested)
                    assert port[:6]==stock[:6] and port[7]==stock[7],(code,enabled,interrupts,requested,'stock reset cache hardware/ABI differs',port[:1],stock[:1])
                    reset_cases.append({'cache_code':code,'cpu_enabled':enabled,'entry_interrupts':interrupts,'l2_requested':requested,'entry_l1_enabled':enabled,'hardware_cpu_nmi_if_fill_and_return_match':True,'register1E_untouched':True})
    cold=[]
    # Stock private CMOS storage is replaced by registers, then published after
    # restoration. Keep the first BD NMI mask, final70 unmask and all other I/O.
    private_cmos_io=set()
    for first,last in ((0x8FB1,0x8FC5),(0x8FCC,0x8FE0),(0x9008,0x9022),
                       (0x9044,0x905E),(0x9080,0x909A),(0x90B6,0x90D0),(0x90D0,0x90E8)):
        for ins in Cs(CS_ARCH_X86,CS_MODE_16).disasm(original[first:last],first):
            if ins.mnemonic in ('in','out'):
                assert any(p in ins.op_str for p in ('0x70','0x71','0xed'))
                private_cmos_io.add(ins.address)
    for code in (0,1,2,3):
        for enabled in (False,True):
            for jumper in range(8):
                stock=execute(original,0x8F07,-1,code,enabled,True,jumper)
                port=execute(candidate,listing.symbol('cache_initialize'),-1,code,enabled,True,jumper)
                expected_probe=[row[1:] for row in stock[8] if row[0] not in private_cmos_io]
                actual_probe=[row[1:] for row in port[8]]
                assert actual_probe==expected_probe,('complete SRAM probe I/O differs',code,actual_probe,expected_probe)
                # The reference prefix ends in JMP DI. Our cold policy returns
                # through its existing PUSHAD frame with both caches held off.
                expected_frame=[('read',0x6FDC,2)]+[('read',at,4) for at in (0x6FDE,0x6FE2,0x6FE6,0x6FEE,0x6FF2,0x6FF6,0x6FFA)]+[('read',0x6FFE,2)]
                assert stock[6]==[] and port[6]==expected_frame,'Cold resume frame changed'
                assert port[:6]==stock[:6] and port[7]==stock[7],(code,enabled,jumper,'cold stock sequence differs',[(i,str(a)[:700],str(b)[:700]) for i,(a,b) in enumerate(zip(port,stock)) if i!=6 and a!=b])
                cold.append({'cache_code':code,'cpu_enabled':enabled,'jumper':jumper,'probe_ranges_timing_cpu_order_matches':True,'shutdown_reset_resume_included':True,'inactive_resume_frame_checked':True,'complete_probe_io_match':True,'stock_probe_io':stock[8],'candidate_probe_io':port[8],'private_cmos_storage_offsets':sorted(private_cmos_io)})
    post_shadow=[]
    for mode in range(4):
        for code in range(16):
            for high in (0x20,0xA0):
                state=(high|code,0xAC|mode)
                stock=execute(original,0x94B1,-1,0,False,memory_state=state)
                port=execute(candidate,listing.symbol('shadow_memory_finish'),-1,0,False,memory_state=state)
                assert port==stock,(state,'post-shadow state/return differs')
                post_shadow.append({'register00_before':state[0],'mode':mode,'register00_after':port[2][0],'stock_operations_and_return_match':True})
    composed=None
    if cold_record is not None:
        assert cold_record['cache_kib']==512 and not cold_record['warm_marker']
        incoming=bytearray.fromhex(cold_record['cache_entry_registers_hex'])
        expected=execute(original,0x8F07,-1,2,True,True,initial_registers=incoming)
        after=expected[2]
        completed=execute(original,0x94B1,-1,0,False,memory_state=(after[0],after[0x12]))
        actual=cold_record['late_entry_state'][0]
        assert actual['registers']['02']&0xC0==after[2]&0xC0
        for index in range(0x27):
            if index==2:continue # The port owns its64-KiB system/onboard-video mapping.
            value=completed[2][0] if index==0 else after[index]
            assert actual['registers'][f'{index:02X}']==value,('actual cold POST entry differs from stock',index,actual,value)
        assert actual['cr0']==expected[3]
        composed={'actual_reset_dram_probe_and_post':True,'stock_cache_input_registers_match':True,'register00':actual['registers']['00'],'register1A':actual['registers']['1A'],'register1E':actual['registers']['1E'],'cold_shutdown_reset_resume_included':True,'shadow_register02':actual['registers']['02'],'shadow_mapping_is_explicit_port_adaptation':True,'cr0':actual['cr0']}
    return {'exact_reference_routines':exact,'return_epilogue_byte_identical':True,'warm_entry_instructions_match':True,'activation_instructions_match':True,'uninterrupted_transition_all_io_compared':True,'all_timing_and_range_rows_match':True,'complete_chipset_reads_writes_and_delay_cycles_match':True,'nmi_mask_transitions_match':True,'reset_clock_comparisons':reset_prefix,'preliminary_reset_table_order_matches':True,'dram_mode1_entry_order_matches':True,'physical_stock_stack_comparisons':physical_stack,'complete_parent_through_4C56':True,'refresh_dma_precedes_ram':True,'early_warm_teardown_comparisons':warm_entry_cases,'reset_teardown_comparisons':reset_cases,'executed_stock_comparisons':cases,'executed_cold_stock_comparisons':cold,'post_shadow_comparisons':post_shadow,'composed_cold_entry':composed}


if __name__=='__main__':
    print(json.dumps(verify(PORT/'build/baios-pb430.bin'),indent=2))
