"""Focused execution of the production timing menu, policy and reset restoration."""
import importlib
import json
import re
import struct
import sys
from pathlib import Path
from unicorn import x86_const as x, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from capstone import Cs, CS_ARCH_X86, CS_MODE_16

PORT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PORT.parent))
from core_proof import ACC
suite=importlib.import_module('test-port')
DEFAULT=bytes((0,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0x15,0,0,0,0,0,0x10,0,0xA3))
BASE={1:0xBF,2:0xF9,4:0x15,5:0x9C,0x0B:0x15,0x12:9,0x14:6,0x16:0,0x18:0,0x19:8}

def record(chip):
    n=suite.nvram();n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255
    n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
    return n

def model(image,chip=DEFAULT,cls=ACC):
    m=cls(image,record(chip));m.jumper=5
    for i,v in BASE.items():m.registers[i]=v
    m.cpu.mem_write(m.base+0x1005,b'\1\1')
    return m

def profile(m,value):
    m.cpu.mem_write(m.base+0x26E,bytes((value,)))
    m.cpu.reg_write(x.UC_X86_REG_SI,0x260);m.call('chipset_profile_apply')

def restore(m):
    start=m.listing.symbol('.refresh_dma_ready','startup')
    end=m.listing.symbol('.write_timing_reset_ready','startup')
    for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_EFLAGS,2),(x.UC_X86_REG_EDX,0x12345678),(x.UC_X86_REG_EBP,1),(x.UC_X86_REG_ESP,0x23456789)):
        m.cpu.reg_write(reg,value)
    m.cpu.emu_start(0xF0000+start,0xF0000+end,count=10000)
    assert m.cpu.reg_read(x.UC_X86_REG_IP)==end
    assert [m.cpu.reg_read(r) for r in (x.UC_X86_REG_EDX,x.UC_X86_REG_EBP,x.UC_X86_REG_ESP)]==[0x12345678,1,0x23456789]

def reset_edges(image):
    rows=[]
    # Require a new RTC address after each data access, as the shared helpers do.
    class ReselectRTC(ACC):
        def port_in(self,cpu,port,size,unused):
            value=super().port_in(cpu,port,size,unused)
            if port==0x71:self.index=0x0D
            return value
        def port_out(self,cpu,port,size,value,unused):
            result=super().port_out(cpu,port,size,value,unused)
            if port==0x71:self.index=0x0D
            return result
    chip=bytearray(DEFAULT);chip[14]=1
    m=model(image,chip,ReselectRTC)
    def stop_halt(mm,address):
        if address==0xF0000+mm.listing.symbol('hard_halt'):mm.cpu.emu_stop()
    m.code_observer=stop_halt
    m.call('chipset_memory_policy')
    assert m.posts[-1]==0x77 and m.cmos[0x37]==0xA7
    restore(m)
    assert m.cmos[0x37]==0 and m.registers[0xB]==0x15 and m.registers[0x16]==0
    rows.append({'rtc_reselection_late_apply_and_early_restore':True})
    for shutdown in (5,0x0A):
        m=model(image);m.cmos[0x37]=0xA7;m.cmos[0x36]=0xAB;m.cmos[0x0F]=shutdown
        m.registers[0xB]=0;m.registers[0x16]=3;m.registers[0x19]=0x28
        before=bytes(m.registers);m.continue_reset=True;m.sys_flag=4
        m.cpu.mem_write(0x467,struct.pack('<HH',0,0x9000));m.stop_address=0x90000
        m.reset_pending=True;m.complete_reset(count=100000)
        assert bytes(m.registers)==before and m.cmos[0x37]==0xA7 and m.posts==[shutdown]
        assert m.cmos[0x36]==0xAB
        rows.append({'service_resume_preserves_timing_and_cookie':shutdown})
    class RejectRestore(ACC):
        def port_out(self,cpu,port,size,value,unused):
            if port==0xF3 and self.acc_index==0xB and value==0x15:return
            return super().port_out(cpu,port,size,value,unused)
    m=model(image,cls=RejectRestore);m.cmos[0x37]=0xA7;m.registers[0xB]=0;m.registers[0x16]=3
    halted=[]
    def halt(mm,address):
        if address==0xF0000+mm.listing.symbol('hard_halt'):halted.append(True);mm.cpu.emu_stop()
    m.code_observer=halt
    try:restore(m)
    except AssertionError:assert halted and m.posts[-1]==0xF1 and m.cmos[0x37]==0xA7 and m.registers[0x16]==3
    else:raise AssertionError('Failed restoration cleared marker or continued')
    rows.append({'failed_restore_retains_advance_and_cookie':True})
    class RejectDiagnostic(ACC):
        reject_acc=None
        reject_cmos=None
        def port_out(self,cpu,port,size,value,unused):
            if port==0xF3 and self.acc_index==self.reject_acc:return
            if port==0x71 and self.index==0x37 and value==self.reject_cmos:return
            return super().port_out(cpu,port,size,value,unused)
    for index,changed,code in ((0xB,0,0xF1),(0x16,3,0xF2),(0x18,1,0xF3),(0x19,0x28,0xF4),(0x12,0x49,0xF5),(0x14,0x16,0xF6),(4,0x1D,0xF7),(5,0x9F,0xF8),(1,0x83,0xF9)):
        m=model(image,cls=RejectDiagnostic);m.cmos[0x37]=0xA7
        m.registers[index]=changed;m.reject_acc=index;m.code_observer=stop_halt
        try:restore(m)
        except AssertionError:assert m.posts[-1]==code,(index,m.posts)
        else:raise AssertionError(('Rejected restore returned success',index))
    for value,code in ((0xA7,0xF0),(0,0xFA)):
        m=model(image,cls=RejectDiagnostic);m.reject_cmos=value;m.code_observer=stop_halt
        m.cmos[0x37]=0 if value else 0xA7
        try:
            if value:m.call('chipset_memory_policy')
            else:restore(m)
        except AssertionError:assert m.posts[-1]==code,m.posts
        else:raise AssertionError(('Rejected marker write returned success',value))
    rows.append({'distinct_timing_failure_codes':11})
    # Follow the actual Setup save -> reset -> cache -> late timing -> bootstrap path.
    chip=bytearray(DEFAULT);chip[6]=1;chip[14]=1
    m=model(image,chip);m.continue_reset=True;m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
    m.open([0x44,28]);assert m.posts[-1]==0xE4
    assert [m.registers[i] for i in (1,5,0xB,0x16,0x19)]==[0x83,0x9F,0,3,0x28],(list(m.registers[:0x1A]),m.posts,bytes(m.cpu.mem_read(m.base+0x60,24)).hex())
    assert m.cmos[0x37]==0xA7
    m.acc_writes.clear();m.irq_scans([0x1D,0x38,0xE0,0x53]);assert m.reset_pending
    m.complete_reset()
    assert m.posts[-1]==0xE4 and m.reset_count==2 and m.cmos[0x37]==0xA7
    assert [m.registers[i] for i in (1,5,0xB,0x16,0x19)]==[0x83,0x9F,0,3,0x28],(list(m.registers[:0x1A]),m.posts,bytes(m.cpu.mem_read(m.base+0x60,24)).hex())
    assert (0xB,0x15) in m.acc_writes and m.acc_writes.index((0xB,0x15))<m.acc_writes.index((0x16,0))
    rows.append({'fast_profile_after_save_and_second_warm_reset':True})
    return rows

def run(image):
    image=Path(image);rows=[]
    # Existing installed settings survive the expanded schema unchanged.
    for writes in (0,1):
        for slow in (0,1):
            old=bytes((1,1,1,1,1,1,1,slow,writes))+bytes(15)
            m=ACC(image,record(old));got=bytes(m.cpu.mem_read(m.base+0x60,24))
            assert got[:9]==old[:9] and got[15]==(4 if writes else 0x15) and got[23]==0xA3
            assert bytes(m.cmos)==bytes(record(old)[:128])
            rows.append({'migration':[writes,slow]})
    for offset,value in ((14,3),(16,1),(17,1),(18,12),(19,4),(20,8),(21,1),(22,128),(23,1)):
        chip=bytearray(DEFAULT);chip[offset]=value
        m=ACC(image,record(chip));assert bytes(m.cpu.mem_read(m.base+0x60,24))==DEFAULT,(offset,value)
    rows.append({'invalid_records_rejected':9})
    print('PASS migration and invalid records',flush=True)
    for selected,expected in ((0,{0xB:0x15,0x16:0,0x19:8,5:0x9C}),(1,{0xB:0,0x16:3,0x19:0x28,5:0x9F})):
        chip=bytearray(DEFAULT);chip[14]=selected
        m=model(image,chip);m.acc_writes.clear();m.call('chipset_memory_policy')
        assert all(m.registers[i]==v for i,v in expected.items()),dict((i,m.registers[i]) for i in expected)
        assert m.registers[1]==0x83 and m.cmos[0x37]==0xA7 and m.posts[-1]==0x77
        indices=[i for i,v in m.acc_writes];assert indices.index(0x16)<indices.index(0x19)<indices.index(0xB)
        m.acc_writes.clear();restore(m)
        assert m.cmos[0x37]==0 and all(m.registers[i]==(0x93 if i==1 else v) for i,v in BASE.items())
        indices=[i for i,v in m.acc_writes];assert indices.index(0xB)<indices.index(0x16)
        rows.append({'profile':selected,'ordered_apply_and_stackless_restore':True})
    # Exercise every owned bit, while keeping all reserved/bank/cache-enable bits.
    chip=bytearray(DEFAULT);chip[14]=2;chip[15]=0xFF;chip[16]=0xC0;chip[17]=0x58
    chip[18]=0x1B;chip[19]=0xF3;chip[20]=0xF7;chip[21]=0xF8;chip[22]=1;chip[13]=1;chip[9]=1;chip[7]=3
    m=model(image,chip);m.registers[0x16]=0x80;m.registers[0x18]=0x0C
    m.call('chipset_memory_policy')
    expected={1:0x93,2:0x99,4:0x7D,5:0x9E,0xB:0xFF,0x12:0xC9,0x14:0x5E,0x16:0xCF,0x18:0xFE,0x19:0xFF}
    assert all(m.registers[i]==v for i,v in expected.items()),dict((i,m.registers[i]) for i in expected)
    restore(m);assert m.registers[0x16]==0x80 and m.registers[0x18]==0x0C
    rows.append({'manual_masks_and_preserved_bits':True})
    print('PASS profile writes, masks and reset order',flush=True)
    for kind in ('safe','l1-off','unqualified','wrong-jumper'):
        m=model(image)
        if kind=='safe':m.registers[4]=0x54;m.registers[0xB]=5
        if kind=='l1-off':m.cpu.mem_write(m.base+0x61,b'\0')
        if kind=='unqualified':m.cpu.mem_write(m.base+0x1005,b'\0')
        if kind=='wrong-jumper':m.jumper=4
        before=(m.registers[4],m.registers[0xB]);m.call('chipset_memory_policy')
        assert (m.registers[4],m.registers[0xB])==before and m.cmos[0x37]==0 and m.posts[-1]==0x78
        restore(m);assert (m.registers[4],m.registers[0xB])==before
        rows.append({'untuned_path_preserved':kind})
    # Failed writes restore prior to reporting; failed restores retain the cookie.
    class Reject(ACC):
        reject_index=None
        reject_value=None
        def port_out(self,cpu,port,size,value,unused):
            if port==0xF3 and self.acc_index==self.reject_index and value==self.reject_value:return
            return super().port_out(cpu,port,size,value,unused)
    for fail_at,value in ((0x16,3),(0x19,0x28),(0xB,0)):
        chip=bytearray(DEFAULT);chip[14]=1;m=model(image,chip,Reject)
        m.reject_index=fail_at;m.reject_value=value
        halted=[]
        def halt(mm,address):
            if address==0xF0000+mm.listing.symbol('hard_halt'):halted.append(True);mm.cpu.emu_stop()
        m.code_observer=halt
        try:m.call('chipset_memory_policy')
        except AssertionError:assert halted and m.posts[-1]==0xEB and m.cmos[0x37]==0
        else:raise AssertionError('Ignored write returned success')
        assert m.registers[0xB]==0x15 and m.registers[0x16]==0
        rows.append({'rejected_write':fail_at})
    # Render each real group; use actual key dispatch for profile and Manual edits.
    print('PASS skipped paths and rejected writes',flush=True)
    m=model(image);raw=image.read_bytes()[65536:]
    # NASM brackets relocated data addresses; the instruction helper skips those.
    def data_symbol(name):
        return next(int(match[1],16) for line in m.listing.lines[m.listing.row(name)+1:]
                    if (match:=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[\[0-9A-F]',line)))
    groups=struct.unpack_from('<6H',raw,data_symbol('chipset_groups'))
    counts=raw[m.listing.symbol('chipset_group_counts'):m.listing.symbol('chipset_group_counts')+6]
    choices=0
    for group,(table,count) in enumerate(zip(groups,counts),1):
        for field in range(count):
            label,offset,shift,mask,count_values,values,h1,h2,_=struct.unpack_from('<HBBBHHHHB',raw,table+field*14)
            for choice in range(count_values):
                draft=bytearray(DEFAULT);draft[0]=1;draft[14]=2;draft[19]=2;draft[22]=2;draft[21]|=8
                m.cpu.mem_write(m.base+0x260,bytes(draft));m.cpu.mem_write(m.base+0x1007,b'\0')
                m.cpu.mem_write(m.base+0x278,bytes((group,choice)));m.cpu.mem_write(m.base+0xF7,bytes((field,)))
                m.call('chipset_ui_commit')
                got=bytes(m.cpu.mem_read(m.base+0x260,24))
                assert (got[offset]>>shift)&mask==choice,(group,field,choice,got)
                m.cpu.reg_write(x.UC_X86_REG_SI,0x260);m.call('chipset_valid')
                assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1,(group,field,choice)
                choices+=1
    rows.append({'every_menu_choice_commits_valid_record':choices})
    # Required onboard windows cannot be edited from either menu location.
    for group,field,offset in ((1,4,4),(6,1,4),(6,4,12)):
        m=model(image);m.cpu.mem_write(m.base+0x260,DEFAULT)
        m.cpu.mem_write(m.base+0x278,bytes((group,0)));m.cpu.mem_write(m.base+0xF7,bytes((field,)))
        m.call('chipset_ui_commit');assert bytes(m.cpu.mem_read(m.base+0x260,24))==DEFAULT
    rows.append({'onboard_shadow_fields_locked':True})
    class ShadowACC(ACC):
        def overlay(self):
            self.windows={}
            for start,length,bit in ((0xC8000,0x8000,2),(0xD0000,0x10000,4),(0xE0000,0x10000,8)):
                rom=bytes((i*17+(start>>12))&255 for i in range(length))
                self.windows[start]=(rom,bytearray(length),bit)
            def memory(cpu,access,address,size,value,unused):
                for start,(rom,ram,bit) in self.windows.items():
                    if start<=address<start+len(rom):
                        at=address-start
                        if access==16: # UC_MEM_READ: hardware-selected ROM or RAM.
                            cpu.mem_write(address,bytes((ram if self.registers[2]&bit else rom)[at:at+size]))
                        elif self.registers[2]&bit and not self.registers[2]&0x20:
                            ram[at:at+size]=value.to_bytes(size,'little')
            self.cpu.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,memory,begin=0xC8000,end=0xEFFFF)
    chip=bytearray(DEFAULT);chip[10:13]=b'\1\1\1'
    m=model(image,chip,ShadowACC);m.cpu.mem_write(m.base+0x1007,b'\0');m.registers[2]=0xF1;m.overlay()
    m.call('shadow_additional_policy',flags=2)
    assert m.registers[2]==0xFF and all(rom==bytes(ram) for rom,ram,bit in m.windows.values())
    assert m.posts[-1]==0xDB
    rows.append({'shadow_whole_window_copy_and_protection':True})
    print('PASS all menu choices and independent shadow mapping',flush=True)
    for g in range(6):
        m=model(image);before=bytes(m.cmos);captured=[]
        keys=[0x50]*4+[28]+[0x50]*g+[28]
        tail=[1,1,1,28]
        def screen(mm):
            if mm.script==tail and not mm.pending and not captured:
                title=mm.text(3,23,30).strip();assert title
                captured.append(title)
        m.observer=screen;m.open(keys+tail)
        assert captured and bytes(m.cmos)==before,(g,captured)
        rows.append({'menu':g,'title':captured[0]})
        print('PASS menu '+str(g),flush=True)
    for action in ('discard','save','defaults'):
        m=model(image);before=bytes(m.cmos);m.continue_reset=action!='discard'
        m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        # RAM: Normal -> Fast -> Manual, then decrease refresh precharge later.
        keys=[0x50]*4+[28,0x50,28,0x4D,0x4D]
        tail=[1,1,1,28] if action=='discard' else [0x44,28]
        seen=[]
        if action=='defaults':keys += [0x43,28]
        def draft(mm):
            if mm.script==tail and not mm.pending and not seen:
                data=bytes(mm.cpu.mem_read(mm.base+0x260,24))
                if action=='defaults':assert data==DEFAULT
                else:assert data[14]==2 and data[15]==0 and data[18]==1 and data[20]==0x20
                seen.append(True)
        m.observer=draft;m.open(keys+tail);assert seen
        if action=='discard':assert bytes(m.cmos)==before and not m.reset_count
        else:
            assert m.reset_count==1 and m.posts[-1]==0xE4
            loaded=ACC(image,m.cmos);expected=DEFAULT if action=='defaults' else bytes(m.cpu.mem_read(m.base+0x60,24))
            assert bytes(loaded.cpu.mem_read(loaded.base+0x60,24))==expected
            # Check the boot's hardware result independently of the saved record.
            selected={1:0x83,5:0x9C,0xB:0x15,0x16:0,0x19:8} if action=='defaults' else {1:0x83,5:0x9F,0xB:0,0x16:3,0x19:0x28}
            assert all(m.registers[i]==v for i,v in selected.items()),{i:m.registers[i] for i in selected}
            assert m.registers[0x12]==9 and m.registers[0x14]==6
        rows.append({'ui':action})
        print('PASS UI '+action,flush=True)
    # No stack use or extra hardware operations can enter the stock cache window.
    raw=image.read_bytes()[65536:];m=model(image)
    start=m.listing.symbol('.refresh_dma_ready','startup');end=m.listing.symbol('.write_timing_reset_ready','startup')
    assert not any(i.mnemonic.startswith(('call','push','pop','ret')) for i in Cs(CS_ARCH_X86,CS_MODE_16).disasm(raw[start:end],start))
    return rows

if __name__=='__main__':
    edges='--reset-edges' in sys.argv
    rows=reset_edges(PORT/'build/baios-pb430.bin') if edges else run(PORT/'build/baios-pb430.bin')
    output=PORT/'build/diagnostics'/('timing-reset-checks.json' if edges else 'timing-setup-checks.json');output.parent.mkdir(exist_ok=True,parents=True)
    output.write_text(json.dumps(rows,indent=2)+'\n')
    print(f'{len(rows)} focused timing Setup checks passed')
