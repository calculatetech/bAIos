"""Boundary cases through the actual PB430 composition and independent devices."""
import struct
from pathlib import Path
from unicorn import x86_const as x
from core_proof import ACC,setup,rtc,PORT

def setup_policy(image,seed):
    """Requested settings through the real draft/save/reset and cold POST owners."""
    import importlib
    import re
    from unicorn import UC_HOOK_CODE
    from memory_proof import run as cold
    suite=importlib.import_module('test-port')
    rows=[]
    def boot(m,draft=False):
        offsets=(0x182,0x18E,0x18F,0x1F7) if draft else (0x172,0x189,0x18A,0x1F6)
        return tuple(m.cpu.mem_read(m.base+at,1)[0] for at in offsets)
    for kind in ('absent','bad-base','old-chip','bad-fast','reserved'):
        n=suite.chipset_record(seed(),manual=1,ads=1)
        if kind=='absent':n[0x38]=0;n[0x69]=0
        if kind=='bad-base':n[0x3D]^=1
        if kind in ('bad-fast','reserved'):
            n[0x71 if kind=='bad-fast' else 0x79]=2 if kind=='bad-fast' else 1
            n[0x6A]=(-0xC2-sum(n[i] for i in (*range(0x6B,0x80),0x33,0x34,0x35)))&255
        m=ACC(image,n)
        assert bytes(m.cmos)==bytes(n[:128]),kind
        assert boot(m)==((3,1,2,0) if kind in ('absent','bad-base') else (2,1,0,0))
        assert m.cpu.mem_read(m.base+0x65,2)==bytes((int(kind in ('bad-base','old-chip')),0))
        rows.append({'load':kind,'boot':boot(m),'no_cmos_writes':True,'fast_default':0})
    for enabled in (0,1):
        m=ACC(image,suite.chipset_record(seed(),cpu=enabled))
        m.continue_reset=True;m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        display=[]
        early=0xF0000+m.listing.symbol('post_early_setup')
        final=0xF0000+m.listing.symbol('post_ui_roms')
        def observe(model,address):
            phase=model.cpu.mem_read(model.base+0x51,1)[0]
            if (address==early and phase==1) or (address==final and phase==5):
                value=model.text(3,24,8).strip()
                assert value==('Enabled' if enabled else 'Disabled'),(phase,value)
                off=bool(model.cpu.reg_read(x.UC_X86_REG_CR0)&0x40000000)
                assert off==(phase==1 or not enabled)
                display.append((phase,value,off))
        m.code_observer=observe;m.open([0x44,28])
        assert [r[0] for r in display]==[1,5] and m.posts[-1]==0xE4,display
        rows.append({'l1_selected':enabled,'actual_post_displays':display})
    saved={}
    for action in ('enable-save','disable-save','edit-discard','defaults-discard','defaults-save'):
        initial=int(action!='enable-save')
        n=suite.chipset_record(seed(),manual=1,ads=1,fast=initial)
        m=ACC(image,n);before=bytes(m.cmos);active=bytes(m.cpu.mem_read(m.base+0x60,24))
        saving=action.endswith('save');m.continue_reset=saving
        m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        blocks=[];point=0xF0000+m.listing.symbol('.point','chipset_visible_ram_test')
        m.cpu.hook_add(UC_HOOK_CODE,lambda u,a,s,c:blocks.append(u.reg_read(x.UC_X86_REG_EDI)),begin=point,end=point)
        keys=[0x50]*2+[15]
        if action.startswith('defaults'):
            keys += [0x43,28]
        else:
            keys += [0x50]*7+[0x4D]
        tail=[0x44,28] if saving else [1,1,28]
        drafts=[]
        def draft(model):
            if model.script==tail and not model.pending:
                expected=0 if action.startswith('defaults') else 1-initial
                assert model.cpu.mem_read(model.base+0x266,1)==bytes((expected,))
                if action.startswith('defaults'):
                    assert boot(model,True)==(3,1,2,0)
                    assert model.cpu.mem_read(model.base+0x265,1)==b'\0'
                drafts.append(expected);model.observer=None
        m.observer=draft;m.open(keys+tail);assert drafts
        expected=drafts[0]
        if saving:
            assert m.reset_count==1 and m.posts[-1]==0xE4
            assert m.cmos[0x71]==expected and m.cpu.mem_read(m.base+0x66,1)==bytes((expected,))
            assert min(blocks)==0x10000 and (max(blocks)<0x100000)==bool(expected)
            assert m.cpu.mem_read(m.base+0x50,1)==b'\x04'
            if action=='defaults-save':assert boot(m)==(3,1,2,0) and m.cmos[0x70]==0
            assert bool(m.registers[0x1A]&0x80)==(action!='defaults-save')
            saved[expected]=bytes(m.cmos)
            if action in ('enable-save','disable-save'):
                event=0xF0000+m.listing.symbol('post_ui_begin');injected=[];reopened=[]
                def reopen_input(model,address):
                    if address==event and not injected:
                        model.pending.extend((0xE0,0x53));injected.append(True)
                def reopened_draft(model):
                    if model.script==[1,1,28] and not model.pending:
                        assert model.cpu.mem_read(model.base+0x266,1)==bytes((expected,))
                        assert model.text(12,49,8).strip()==('Enabled' if expected else 'Disabled')
                        reopened.append(expected);model.observer=None
                m.code_observer=reopen_input;m.observer=reopened_draft
                m.after_reset_script=[0x50]*2+[15]+[0x50]*7+[1,1,28]
                m.irq_scans([0x1D,0x38,0xE0,0x53]);assert m.reset_pending
                m.complete_reset()
                assert reopened==[expected] and m.posts[-1]==0xE4 and m.cmos[0x71]==expected
                m.code_observer=None
                rows.append({'saved_fast_reopened_after_cad':expected,'draft_and_rendered_choice':True,'discard_keeps_saved_choice':True})
        else:
            assert bytes(m.cmos)==before and m.reset_count==0
            assert bytes(m.cpu.mem_read(m.base+0x60,24))==active
        rows.append({'action':action,'draft_fast':expected,'saved':saving,'ram_block_count':len(blocks),'last_block':max(blocks) if blocks else None})
    for fast in (0,1):
        result=cold(image,banks=(2,0,0,0),expected_pattern=2,expected_map=0x30,cache_kib=512,complete_post=True,cmos_seed=saved[fast])
        blocks=result['visible_ram_blocks']
        assert min(blocks)==0x10000 and (max(blocks)<0x100000)==bool(fast)
        assert result['ram_flags']==4 and result['public_int15_kib']==1024
        assert all(item['unwritten_fill_bytes_this_reset']==0 for item in result['initialization'])
        rows.append({'cold_fast':fast,'result':result})
    disabled=suite.chipset_record(bytearray(saved[1]),cpu=0,fast=1)
    result=cold(image,banks=(2,0,0,0),expected_pattern=2,expected_map=0x30,cache_kib=512,complete_post=True,cmos_seed=disabled)
    rows.append({'cold_l1_disabled':result})
    # Every help string used by the composition must fit its existing panel.
    help_rows=[]
    for relative in ('shared/src/firmware/setup.inc','pb430/src/hardware/chipset-data.inc'):
        text=(PORT.parent/relative).read_text()
        for name,value in re.findall(r"^(\w*help\w*) db '([^']*)',0$",text,re.M):
            assert len(value)<=51,(name,len(value))
            assert not re.search(r'\b(?:CR0|INT13|AUX|SRAM|PIO|CHS|OEM)\b|register|bit ?[0-9]|F0000|C000',value),(name,value)
            help_rows.append((name,value))
    assert any('recommended' in value and 'Disabled' in value for name,value in help_rows)
    rows.append({'help_text':help_rows})
    captures=[]
    for field in range(6):
        m=ACC(image,suite.chipset_record(seed(),manual=1))
        m.cpu.mem_write(m.base+0x1007,b'\0')
        before=bytes(m.cmos);seen=[]
        prefix=[0x50]*4+[28,28]+[0x50]*field
        def help_screen(model):
            if model.script==[1,1,1,1,28] and not model.pending and not seen:
                title=model.text(18,25,51).strip()
                lines=[model.text(row,25,51).strip() for row in (19,20)]
                assert title and all(lines),(field,title,lines)
                seen.append({'field':field,'title':title,'lines':lines})
        m.observer=help_screen;m.open(prefix+[0x3B,1,1,1,1,28])
        assert len(seen)==1 and bytes(m.cmos)==before,(field,seen)
        if field==5:assert seen[0]['lines'][0]=='Disabled is recommended by the AMI manual.'
        captures.extend(seen)
    rows.append({'actual_f1_panels':captures})
    ordinary=[]
    cases=[]
    for page,count in ((0,3),(1,7),(2,8),(3,8),(5,2)):
        cases.append(([0x50]*page,[1,1,28]))
        cases.extend(([0x50]*page+[15]+[0x50]*field,[1,1,1,28]) for field in range(count))
    cases.append(([15,0x50,0x50,0x4D,0x48],[1,1,1,28]))
    # Select User disk type through the ordinary editor to expose geometry help.
    device=[0x50,15,0x50,0x50,28,0x50,0x4B,0x4B,0x48]
    cases.extend((device+[0x50]*field,[1,1,1,1,28]) for field in range(10))
    for prefix,tail in cases:
        m=ACC(image,seed());seen=[];before=bytes(m.cmos)
        def ordinary_help(model):
            if model.script==tail and not model.pending and not seen:
                title=model.text(18,25,51).strip()
                lines=[model.text(row,25,51).strip() for row in (19,20)]
                assert title and all(lines),(prefix,title,lines)
                seen.append({'title':title,'lines':lines})
        m.observer=ordinary_help;m.open(prefix+[0x3B]+tail)
        assert len(seen)==1 and bytes(m.cmos)==before,(prefix,seen)
        ordinary.extend(seen)
    assert any('extended BIOS support' in item['lines'][0] for item in ordinary)
    rows.append({'ordinary_f1_panels':ordinary})
    return rows

def ports_record(n,payload):
    n[0x5D:0x69]=b'P1\x01'+bytes(payload)+b'\0'
    n[0x68]=(-sum(n[0x5D:0x68]))&255
    return n

def boot_defaults(image,seed):
    import importlib
    suite=importlib.import_module('test-port')
    m=ACC(image,seed());m.continue_reset=True
    m.open([0x43,28,0x44,28])
    assert tuple(m.cpu.mem_read(m.base+i,1)[0] for i in (0x172,0x189,0x18A,0x1F6))==(3,1,2,0)
    rows=[]
    for name,cd,floppy,unit in (('cd',True,True,0xE0),('a',False,True,0),('hdd',False,False,0x80)):
        result=suite.native('boot-default-'+name,cmos=m.cmos,positions=(0,),types=0x40,
                            floppy_media=True,bootable_floppy=floppy,cdroms={1:cd},
                            preserve_boot_order=True,expected_boot_unit=unit,
                            boot_source='native-default-boot.asm',expected=0x6B)
        rows.append({'first_available':name,'payload_unit':unit,'result':result})
    # Every recognized saved schema must prefer HDD even with bootable CD and A.
    for version in range(1,6):
        saved=seed();saved[0x3A]=version;saved[0x3B]=1 if version==1 else 0x13
        saved[0x3C]=1 if version==1 else 2;saved[0x3E:0x40]=bytes((1,0))
        saved[0x3D]=(-sum(saved[0x38:0x3D])-saved[0x10]-(sum(saved[0x3E:0x40]) if version>=2 else 0))&255
        result=suite.native('boot-saved-schema-'+str(version),cmos=saved,positions=(0,),types=0x40,
                            floppy_media=True,bootable_floppy=True,cdroms={1:True},
                            preserve_boot_order=True,expected_boot_unit=0x80,
                            boot_source='native-default-boot.asm',expected=0x6B)
        rows.append({'saved_schema':version,'payload_unit':0x80,'all_media_bootable':True,'result':result})
    return rows


def port_masks(model):
    """Observe the real composed routing owner and its actual return."""
    events=[];waiting={};masks={0xDC:1,0xDD:1,0xDB:0xC4,0xDE:0x0C,0xBE:0xC7,0xFB:0xF4}
    previous=model.code_observer
    entries={0xF0000+model.listing.symbol(owner):owner for owner in ('ports_apply','ide_apply_controller')}
    def observe(m,address):
        if previous:previous(m,address)
        if not m.starting:return
        if address in entries:
                owner=entries[address]
                u=m.cpu;ret=struct.unpack('<H',u.mem_read(u.reg_read(x.UC_X86_REG_SS)*16+u.reg_read(x.UC_X86_REG_SP),2))[0]
                waiting[owner]=(0xF0000+ret,bytes(m.registers))
        for owner,(ret,before) in tuple(waiting.items()):
            if address!=ret:continue
            targets=set(masks)|{0xBF} if owner=='ports_apply' else {0xFE}
            selected=masks if owner=='ports_apply' else {0xFE:0xF8}
            assert all(m.registers[index]&mask==before[index]&mask for index,mask in selected.items()),(owner,'reserved mask')
            assert all(m.registers[i]==before[i] for i in range(256) if i not in targets),(owner,'unrelated field')
            events.append({'owner':owner,'preserved_masks':selected,'unrelated_registers_preserved':True});del waiting[owner]
    model.code_observer=observe
    return events


def serial(image,seed):
    rows=[];addresses=(0,0x3F8,0x2F8,0x3E8,0x2E8)
    for owner in (0,1):
        for choice in range(5):
            payload=[0,0,1,2,0,1,1,1];payload[owner]=1
            m=ACC(image,ports_record(seed(),payload));m.continue_reset=True;mask_events=port_masks(m)
            scans=[0x50]*3+[28]+[0x50]*owner
            scans+=([0x4B] if choice==0 else [0x4D]*(choice-1))+[0x44,28]
            before=bytes(m.cmos);writes=tuple(m.acc_writes);observed=[]
            def observer(model):
                if model.script==[0x44,28] and not model.pending:
                    wanted=payload.copy();wanted[owner]=choice
                    assert bytes(model.cpu.mem_read(model.base+0x1EE,8))==bytes(wanted)
                    assert bytes(model.cmos)==before and tuple(model.acc_writes)==writes
                    observed.append(True);model.observer=None
            m.observer=observer;m.open(scans)
            assert observed and m.reset_count==1 and m.visits==['startup']
            wanted=payload.copy();wanted[owner]=choice
            assert m.cmos[0x60:0x68]==bytes(wanted) and sum(m.cmos[0x5D:0x69])&255==0
            assert bytes(m.cpu.mem_read(m.base+0x1E6,8))==bytes(wanted)
            assert struct.unpack('<4H',m.cpu.mem_read(0x400,8))==(addresses[choice],0,0,0)
            assert ((struct.unpack('<H',m.cpu.mem_read(0x410,2))[0]>>9)&7)==int(bool(choice))
            assert m.registers[0xDE]&0x0C==4
            if choice:
                irq=4 if choice&1 else 3
                assert m.irq_sources()[irq]==(2 if owner==0 else 3)
                assert m.irq_sources()[7-irq]==0
                receive,_=m.public(0x14,0x0200);assert receive&255==0xA6
                result,_=m.public(0x14,0x014D);assert result==0x604D
                assert m.devices_uart[owner].tx==[0x4D]
            else:
                result,_=m.public(0x14,0x014D);assert result==0x804D
                assert not m.devices_uart[owner].tx
            assert len(mask_events)==2
            rows.append({'uart':owner,'selector':choice,'base':addresses[choice],'irq_sources':m.irq_sources(),'int14_ax':result,'reset_vector':True,'masks':mask_events})
    # Simultaneous pair: two sources in one causal Save/reset/public-service case.
    m=ACC(image,ports_record(seed(),(1,2,1,2,0,1,1,1)));m.continue_reset=True;mask_events=port_masks(m)
    m.open([0x50]*3+[28,0x4D,0x50,0x4D,0x44,28])
    assert m.cmos[0x60:0x62]==bytes((3,4))
    assert struct.unpack('<4H',m.cpu.mem_read(0x400,8))==(0x3E8,0x2E8,0,0)
    assert ((struct.unpack('<H',m.cpu.mem_read(0x410,2))[0]>>9)&7)==2
    assert m.irq_sources()=={3:3,4:2}
    for unit,payload in ((0,0x41),(1,0x42)):
        receive,_=m.public(0x14,0x0200,dx=unit);assert receive&255==0xA6
        result,_=m.public(0x14,0x0100|payload,dx=unit);assert result==0x6000|payload
        assert m.devices_uart[unit].tx==[payload]
    rows.append({'simultaneous_bases':[0x3E8,0x2E8],'irq_sources':m.irq_sources(),'int14_payloads':[0x41,0x42],'reset_vector':True,'masks':mask_events})
    assert len(mask_events)==2
    # Repeated preferred prefix must not truncate the later ISA candidate.
    from shared.tools.peripheral_proof import UART
    m=ACC(image,ports_record(seed(),(1,2,1,2,0,1,1,1)));m.extra_uarts[0x3E8]=UART();m.continue_reset=True;mask_events=port_masks(m)
    m.open([0x44,28])
    assert struct.unpack('<4H',m.cpu.mem_read(0x400,8))==(0x3F8,0x2F8,0x3E8,0)
    assert ((struct.unpack('<H',m.cpu.mem_read(0x410,2))[0]>>9)&7)==3
    assert m.irq_sources()=={3:3,4:2}
    received,_=m.public(0x14,0x0200,dx=2);assert received&255==0xA6
    result,_=m.public(0x14,0x0143,dx=2);assert result==0x6043 and m.extra_uarts[0x3E8].tx==[0x43]
    rows.append({'duplicate_preferred_prefix':True,'later_isa_base':0x3E8,'bda_count':3,'int14_dx2_ax':result,'save_reset':True,'masks':mask_events})
    assert len(mask_events)==2
    n=ports_record(seed(),(1,1,2,3,1,1,1,1));m=ACC(image,n)
    assert m.cmos==n[:128] and m.cpu.mem_read(m.base+0x174,1)==b'\0'
    assert m.cpu.mem_read(m.base+0x1E6,8)==bytes((1,2,1,2,0,1,1,1))
    rows.append({'invalid_duplicate_record_no_write_fallback':True})
    # Nearest conflict goes through actual UI candidate filtering.
    m=ACC(image,ports_record(seed(),(1,2,1,2,0,1,1,1)));m.continue_reset=True;mask_events=port_masks(m)
    original=bytes(m.cmos);seen=[]
    def conflict(model):
        if not model.script and not model.pending:
            draft=bytes(model.cpu.mem_read(model.base+0x1EE,8))
            assert draft[:2]==bytes((3,2)),draft  #2F8/IRQ3 was skipped, not committed.
            assert bytes(model.cmos)==original
            seen.append(True);model.observer=None;model.script=[0x44,28]
    m.observer=conflict;m.open([0x50]*3+[28,0x4D]);assert seen and m.reset_count==1
    assert m.cmos[0x60:0x62]==bytes((3,2)) and struct.unpack('<2H',m.cpu.mem_read(0x400,4))==(0x3E8,0x2F8)
    assert m.irq_sources()=={3:3,4:2} and len(mask_events)==2
    for unit,byte in ((0,0x51),(1,0x52)):
        received,_=m.public(0x14,0x0200,dx=unit);assert received&255==0xA6
        result,_=m.public(0x14,0x0100|byte,dx=unit);assert result==0x6000|byte and m.devices_uart[unit].tx==[byte],(unit,hex(result),m.devices_uart[unit].tx)
    rows.append({'nearest_irq_conflict_filtered_then_saved':True,'bases':[0x3E8,0x2F8],'int14_payloads':[0x51,0x52],'masks':mask_events})
    # PB430 retains each valid pair without rewriting the saved record.
    for pair in range(4):
        n=ports_record(seed(),(3,0,pair,2,0,1,1,1));m=ACC(image,n)
        assert m.cpu.mem_read(m.base+0x1E6,8)==bytes((3,0,pair,2,0,1,1,1))
        assert m.cmos[0x5D:0x69]==n[0x5D:0x69]
    return rows


def parallel(image,seed):
    rows=[];addresses=(0,0x3BC,0x378,0x278)
    for choice in range(4):
        for mode in range(2) if choice else (0,):
            m=ACC(image,seed());m.continue_reset=True;mask_events=port_masks(m)
            scans=[0x50]*3+[28,0x50,0x50,0x50]
            scans += [0x4B]*(2-choice) if choice<2 else [0x4D]*(choice-2)
            if mode:scans += [0x50,0x4D]
            m.open(scans+[0x44,28])
            assert m.cmos[0x63:0x65]==bytes((choice,mode))
            assert struct.unpack('<3H',m.cpu.mem_read(0x408,6))==(addresses[choice],0,0)
            equipment=struct.unpack('<H',m.cpu.mem_read(0x410,2))[0]
            assert equipment>>14==int(bool(choice))
            assert m.public(0x11,0)[0]==equipment
            assert m.registers[0xBF]==addresses[choice]>>2
            assert bool(m.registers[0xBE]&0x20)==bool(mode)
            result,_=m.public(0x17,0x005A)
            assert bool(result&0x100)==(not choice),(choice,mode,hex(result))
            assert m.printer.tx==([0x5A] if choice else [])
            assert len(mask_events)==2
            rows.append({'selector':choice,'mode':mode,'base':addresses[choice],'equipment_parallel_count':equipment>>14,'public_int11':equipment,'int17_ax':result,'masks':mask_events})
    return rows


def slow_refresh(image,seed):
    """Saved choice, normal startup refresh, late application and native readback."""
    import importlib
    suite=importlib.import_module('test-port')
    rows=[]
    for enabled in (0,1):
        m=ACC(image,suite.chipset_record(seed(),slow=enabled))
        assert m.cpu.mem_read(m.base+0x67,1)==bytes((enabled,))
        for upper in (0,0x9C,0xFC):
            m.registers[5]=upper|3
            m.call('chipset_refresh_policy');assert m.registers[5]==upper|(3 if enabled else 0)
        rows.append({'saved':enabled,'upper_bits_preserved':True})
    n=suite.chipset_record(seed(),slow=2)
    m=ACC(image,n)
    assert m.cpu.mem_read(m.base+0x67,1)==b'\0'
    rows.append({'invalid_choice_defaults_disabled':True})
    for action in ('enable-save','disable-save','discard','defaults-save'):
        initial=int(action!='enable-save')
        m=ACC(image,suite.chipset_record(seed(),manual=1,slow=initial))
        before=bytes(m.cmos)
        m.cpu.mem_write(m.base+0x1007,b'\0')
        saving=action!='discard';m.continue_reset=saving
        m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        keys=[0x50]*4+[28]+[0x50]*3+[28]
        keys += [0x43,28] if action=='defaults-save' else [0x4D if initial else 0x4B]
        tail=[0x44,28] if saving else [1,1,1,28]
        wanted=0 if action=='defaults-save' else 1-initial
        seen=[];normal=[];late=[]
        def draft(model):
            if model.script==tail and not model.pending and not seen:
                assert model.cpu.mem_read(model.base+0x267,1)==bytes((wanted,))
                assert model.text(5,49,15).strip()==('120 us (Slow)' if wanted else '15 us (Normal)')
                seen.append(wanted);model.observer=None
        cache_points={0xF0000+m.listing.symbol(name) for name in ('cache_initialize','cache_stock_warm_entry')}
        m.registers[5]=0x9F
        policy=0xF0000+m.listing.symbol('chipset_refresh_policy')
        def ordering(model,address):
            if address in cache_points:
                assert model.registers[5]&3==0
                normal.append(True)
            if address==policy:
                if model.registers[4]&1:
                    assert model.registers[0x1A]&0x18==0
                    late.append('after-cache')
                else:
                    assert model.cpu.reg_read(x.UC_X86_REG_CR0)&0x40000000
                    late.append('before-ram')
        m.observer=draft;m.code_observer=ordering
        m.open(keys+tail);assert seen
        if saving:
            assert m.reset_count==1 and m.posts[-1]==0xE4
            assert m.cmos[0x72]==wanted and m.cpu.mem_read(m.base+0x67,1)==bytes((wanted,))
            assert m.registers[5]&3==(3 if wanted else 0)
            assert normal and late==['before-ram','after-cache'],late
        else:
            assert bytes(m.cmos)==before and m.reset_count==0
        rows.append({'action':action,'draft':wanted,'normal_before_cache':normal,'late_policy':late})
    for enabled in (0,1):
        rows.append(suite.native('refresh-native-'+str(enabled),
                    cmos=suite.chipset_record(seed(),slow=enabled),saved_refresh=enabled))
    return rows


def fast_writes(image,seed):
    """Fast Writes is now part of the expanded timing policy and its UI checks."""
    import importlib
    timing=importlib.import_module('test-timing-setup')
    return timing.run(image)+timing.reset_edges(image)


def chipset(image,seed):
    rows=[]
    for auto in (False,True):
        n=seed();chip=bytes((1 if auto else 0,1,1,1,1,1))+bytes(18)
        n[0x69]=0xC2;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:];n[0x6A]=(-0xC2-sum(chip))&255
        m=ACC(image,n);m.registers[0x1A]=0xC0;m.continue_reset=True
        m.open([0x50]*4+[28,28,0x4D,0x44,28])
        assert m.cmos[0x6B]==int(not auto) and m.cmos[0x70]==1
        assert bool(m.registers[0x1A]&0x80)==(not auto)
        assert m.registers[0x1A]&0x40 and m.registers[0x1A]&0x3C==0x2C
        rows.append({'auto':auto,'saved_manual_ads':m.cmos[0x70],'register1a':m.registers[0x1A],'reset':m.reset_count})
    for onboard,manual in ((True,False),(True,True),(False,True)):
        m=ACC(image,seed(),external_video=not onboard);m.cpu.mem_write(m.base+0x1007,bytes((int(onboard),)))
        m.continue_reset=True;m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        keys=[0x50]*4+[28,28]
        if manual:keys += [0x4D]
        # All bounded controls are driven through the existing page.
        for field in range(1,6):
            if field==4 and onboard:continue
            if field==5 and not manual:continue
            keys += [0x50,0x4B,0x4D,0x4D] #0->1->0 tests the existing upper bound.
        if not manual:keys += [0x50] # No selectable row remains below System Shadow.
        expected=bytes((int(manual),0,0,0,int(onboard),int(manual)))
        seen=[]
        def draft(model):
            if model.script==[0x44,28] and not model.pending:
                assert model.cpu.mem_read(model.base+0x260,6)==expected,(onboard,manual,bytes(model.cpu.mem_read(model.base+0x260,6)))
                assert model.cpu.mem_read(model.base+0x266,18)==bytes(9)+bytes((0x15,0,0,0,0,0,0x10,0,0xA3))
                assert model.cpu.mem_read(model.base+0xF7,1)==bytes((5 if manual else 3,)),(manual,onboard,bytes(model.cpu.mem_read(model.base+0xF7,1)))
                assert model.text(9,49,25).strip()==('Enabled (required)' if onboard else 'Disabled')
                assert model.text(10,49,8).strip()==('Enabled' if manual else 'Disabled')
                seen.append(True);model.observer=None
        m.observer=draft;m.open(keys+[0x44,28]);assert seen and m.reset_count==1 and m.posts[-1]==0xE4
        assert bytes(m.cpu.mem_read(m.base+0x60,6))==expected and bytes(m.cmos[0x6B:0x71])==expected
        assert m.cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
        assert not m.registers[4]&1 and not m.registers[2]&0x10 and bool(m.registers[2]&1)==onboard,(onboard,manual,m.registers[4],m.registers[2])
        rows.append({'onboard':onboard,'manual':manual,'all_bounded_fields':list(expected),'auto_ads_unavailable':not manual,'manual_ads_editable':manual,'video_fixed':onboard,'actual_save_reset_retry':True})
    return rows


def clock(image,seed):
    rows=[]
    for invalid in (False,True):
        import importlib
        n=seed();n[0x3B]=(n[0x3B]&~0x18)|8;n[0xE]=0x80 if invalid else 0
        importlib.import_module('test-port').repair_checksum(n)
        m=ACC(image,n);m.continue_reset=True
        m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        m.open([0x44,28])
        assert m.posts[-1]==0xE4
        notice='WARNING: CMOS date/time not set.'
        assert (notice in m.console)==invalid,(invalid,m.console)
        assert m.cmos[0x38:0x40]==n[0x38:0x40]
        assert tuple(m.cpu.mem_read(m.base+i,1)[0] for i in (0x172,0x189,0x18A,0x1F6))==(2,1,0,0)
        assert bool(m.invoke(4)[0])==invalid
        rows.append({'post_clock_invalid':invalid,'visible_notice':notice if invalid else None,'valid_settings_preserved':True,'terminal':0xE4,'public_clock_invalid':invalid})
    n=seed();n[0xE]=0x80;m=ACC(image,n)
    original_date=bytes(m.cmos[7:10])
    m.open([15,0x50,28]+setup.keys('120000p\r')+[1,1,28])
    assert bytes(m.cmos[7:10])==original_date and m.cmos[4]==0x12
    assert m.cmos[0xE]&0x80 and m.invoke(2)[0] and m.invoke(4)[0]
    rows.append({'time_only':True,'date_preserved':True,'diagnostic':m.cmos[0xE],'public_clock_invalid':True})
    for low in (False,True):
        n=seed();n[0xE]=0x80
        m=ACC(image,n);m.power_low=low
        # Actual date/time editor and confirmation, then real Discard.
        m.open([15,28]+setup.keys('10012026\r')+[0x50,28]+setup.keys('120000p\r')+[1,1,28])
        assert m.cmos[7:10]==bytes((1,0x10,0x26))
        assert m.cmos[4]==0x12 and m.cmos[2]==0
        assert bool(m.cmos[0xE]&0x80)==low
        result=m.invoke(4);assert result[0]==low
        if not low:assert result[1:3]==(0x2026,0x1001)
        rows.append({'vrt_low':low,'diagnostic':m.cmos[0xE],'int1a_cf':result[0],'date':list(m.cmos[7:10])})
    return rows


def reset(image,seed):
    rows=[]
    for shutdown in (5,10):
        m=ACC(image,seed());m.cmos[15]=shutdown;m.starting=True
        m.cpu.mem_write(0x467,struct.pack('<HH',0x100,0x9000));m.cpu.mem_write(0x90100,b'\x90')
        for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_IP,0xFFF0),(x.UC_X86_REG_SS,0x1200),(x.UC_X86_REG_ESP,0xCAFE1000),(x.UC_X86_REG_EDX,0x12345678),(x.UC_X86_REG_CR0,0x60000010),(x.UC_X86_REG_EFLAGS,2)):
            m.cpu.reg_write(reg,value)
        m.eois.clear();m.acc_writes.clear()
        m.cpu.emu_start(0xFFFF0,0x90100,count=10000)
        assert m.cpu.reg_read(x.UC_X86_REG_CS)==0x9000 and m.cpu.reg_read(x.UC_X86_REG_IP)==0x100
        assert m.cmos[15]==0 and not m.acc_writes
        assert m.cpu.reg_read(x.UC_X86_REG_ESP)==0xCAFE1000 and m.cpu.reg_read(x.UC_X86_REG_SS)==0x1200
        assert m.cpu.reg_read(x.UC_X86_REG_EDX)==0x12345678
        assert m.cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000==0
        assert m.eois==([(0xA0,0x20),(0x20,0x20)] if shutdown==5 else [])
        rows.append({'shutdown':shutdown,'consumed':True,'eois':m.eois,'caller_stack_and_edx':True})
    # One real Save/warm/cold/startup/RAM/boot path. The external gates are
    # independently decoded; only CPU RAM bus translation is opaque hardware.
    from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    m=ACC(image,seed());u=m.cpu;m.port92=0xA6;m.continue_reset=True
    m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
    hand=0xF0000+m.listing.symbol('board_a20_handoff');ram_entry=0xF0000+m.listing.symbol('chipset_visible_ram_test')
    pending={};chronology=[];ram_restored=[]
    def observe(model,address):
        if not m.starting:return
        if address in (hand,ram_entry):
            kind='handoff' if address==hand else 'ram'
            ret=0xF0000+struct.unpack('<H',u.mem_read(u.reg_read(x.UC_X86_REG_SS)*16+u.reg_read(x.UC_X86_REG_SP),2))[0]
            state=(m.port92,m.kbc_output,u.reg_read(x.UC_X86_REG_AX),u.reg_read(x.UC_X86_REG_CR0),u.reg_read(x.UC_X86_REG_GDTR),m.port_in(u,0x61,1,None))
            assert state[1]&2
            if kind=='ram':
                assert not state[0]&3 and chronology[-1]=='handoff_return'
                data=(bytes(u.mem_read(0x10000,8192)),bytes(u.mem_read(0x100800,512)))
            else:data=None
            pending[kind]=(ret,state,len(m.a20_writes),data);chronology.append(kind+'_entry')
        for kind,(ret,state,start,data) in tuple(pending.items()):
            if address!=ret:continue
            if kind=='handoff':
                assert m.port92==state[0]&0xFC and m.kbc_output==state[1] and u.reg_read(x.UC_X86_REG_AX)==state[2]
                assert m.a20_writes[start:]==[(0x92,state[0]&0xFC)]
            else:
                assert (m.port92,m.kbc_output,u.reg_read(x.UC_X86_REG_CR0),u.reg_read(x.UC_X86_REG_GDTR),m.port_in(u,0x61,1,None))==(state[0],state[1],state[3],state[4],state[5])
                assert m.a20_writes[start:]==[(0x92,(state[0]&0xFE)|2),(0x92,state[0]&0xFE)]
                assert (bytes(u.mem_read(0x10000,8192)),bytes(u.mem_read(0x100800,512)))==data
                ram_restored.append(True)
            chronology.append(kind+'_return');del pending[kind]
    m.code_observer=observe
    u.hook_add(UC_HOOK_CODE,lambda cpu,address,size,context:observe(m,address),begin=ram_entry,end=ram_entry)
    m.open([0x44,28]);assert m.posts[-1]==0xE4 and m.reset_count==1
    m.cold_boot();assert m.posts[-1]==0xE4 and ram_restored==[True,True]
    assert chronology==['handoff_entry','handoff_return','ram_entry','ram_return']*2
    assert m.port92==0xA4 and m.kbc_output&2 and not pending
    assert m.public(0x12,0)[0]==632 and m.public(0x15,0x8800)[0]==64512
    # These four independent RAM windows expose physical bit20 wrapping.
    source=bytes((i*13+5)&255 for i in range(512))
    storage={0x800:bytearray([0xA1])*512,0x1800:bytearray([0xD4])*512,0x100800:bytearray(source),0x101800:bytearray([0x77])*512}
    for at,data in storage.items():u.mem_write(at,bytes(data))
    def physical(address):return address if (m.port92|m.kbc_output)&2 else address&~0x100000
    def bus_read(cpu,access,address,size,value,unused):
        at=physical(address);base=next(base for base in storage if base<=at<base+512)
        cpu.mem_write(address,bytes(storage[base][at-base:at-base+size]))
    def bus_write(cpu,access,address,size,value,unused):
        at=physical(address);base=next(base for base in storage if base<=at<base+512)
        storage[base][at-base:at-base+size]=value.to_bytes(size,'little')
    for at in storage:
        u.hook_add(UC_HOOK_MEM_READ,bus_read,begin=at,end=at+511)
        u.hook_add(UC_HOOK_MEM_WRITE,bus_write,begin=at,end=at+511)
    def guest(code):
        u.mem_write(0x90000,code)
        for reg,value in ((x.UC_X86_REG_CS,0x9000),(x.UC_X86_REG_IP,0),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x7000),(x.UC_X86_REG_EFLAGS,0x202)):u.reg_write(reg,value)
        u.emu_start(0x90000,0x90000+len(code),count=100000)
        assert u.reg_read(x.UC_X86_REG_IP)==len(code)
    wrap_read=bytes.fromhex('B8FFFF8EC0BB1008268B07') # ES:BX=FFFF:0810 ->100800.
    guest(wrap_read);assert u.reg_read(x.UC_X86_REG_AX)==int.from_bytes(source[:2],'little')
    assert not m.pending
    # Legacy application D0/read, D1/write: preserve every unrelated output bit.
    guest(bytes.fromhex('B0D0E664E46024FD88C3B0D1E66488D8E660'))
    assert m.kbc_output==0xCD and m.port92==0xA4
    guest(wrap_read);assert u.reg_read(x.UC_X86_REG_AX)==0xA1A1
    table=bytearray(48)
    for off,base in ((0x10,0x100800),(0x18,0x101800)):table[off:off+8]=struct.pack('<HHBBBB',0xFFFF,base&0xFFFF,(base>>16)&255,0x93,0,(base>>24)&255)
    u.mem_write(0x90100,bytes(table));u.reg_write(x.UC_X86_REG_ES,0x9000);u.reg_write(x.UC_X86_REG_SI,0x100)
    gates=(m.port92,m.kbc_output);cr0=u.reg_read(x.UC_X86_REG_CR0);gdtr=u.reg_read(x.UC_X86_REG_GDTR);start=len(m.a20_writes)
    ax,flags=m.public(0x15,0x8700,cx=256)
    assert not flags&1 and ax>>8==0 and bytes(storage[0x101800])==source
    assert (m.port92,m.kbc_output)==gates and u.reg_read(x.UC_X86_REG_CR0)==cr0 and u.reg_read(x.UC_X86_REG_GDTR)==gdtr
    assert m.a20_writes[start:]==[(0x92,0xA6),(0x92,0xA4)]
    guest(wrap_read);assert u.reg_read(x.UC_X86_REG_AX)==0xA1A1
    guest(bytes.fromhex('B0D0E664E4600C0288C3B0D1E66488D8E660'))
    guest(wrap_read);assert u.reg_read(x.UC_X86_REG_AX)==int.from_bytes(source[:2],'little')
    assert m.kbc_output==0xCF and m.port92==0xA4 and bytes(storage[0x800])==bytes([0xA1])*512 and bytes(storage[0x1800])==bytes([0xD4])*512
    rows.append({'actual_save_warm_cold_boot':True,'handoff_ram_chronology':chronology,'ram_context_gate_data_restored':ram_restored,'legacy8042_disable_wrap_reenable':True,'public_int15_move_and_gate_restore':True,'fast_upper_bits_preserved':m.port92,'terminal':0xE4})
    return rows


def diagnostics(image,seed):
    rows=[]
    for absent in (False,True):
        m=ACC(image,seed());m.continue_reset=True;m.keyboard_silent=absent
        m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        m.open([0x44,28])
        ordered=(0x10,0x11,0x30,0x12,0x34,0x37,0x40,0x41,0x42,0x43,0xB0,0xB1,0xB9,0x50,0x3C,0x3F,0x60,0xB4,0xB5,0xB6,0xC0,0xC1,0xC2,0xB7,0xB8,0xBA,0xC3,0xC4,0xC5,0xD3 if absent else 0xC6,0x48,0x49,0x51,0x52,0x53,0x54,0x56,0x57,0x58,0x59,0x5A,0x5B,0x5C,0xFF,0x5D,0x5E,0x5F,0xE4)
        cursor=0
        for stage in ordered:
            cursor=m.posts.index(stage,cursor)+1
        assert m.cpu.mem_read(0x400+0x9F,1)==bytes((int(absent),))
        assert bool(m.cpu.mem_read(m.base+0x175,1)[0]&8)==absent
        rows.append({'keyboard_absent':absent,'ordered_post_codes':ordered,'actual_terminal':m.posts[-1]})
    m=ACC(image,seed());m.continue_reset=True;m.keyboard_bad_bat=True
    m.stop_address=0xF0000+m.listing.symbol('keyboard_halt');m.open([0x44,28])
    assert m.cpu.reg_read(x.UC_X86_REG_AL)==0xD4 and 0xC6 in m.posts and 0x48 not in m.posts
    rows.append({'bad_keyboard_bat':True,'terminal':'actual keyboard_halt','failure_al':0xD4})
    return rows


def input_irq_policy(image,seed):
    from unicorn import UC_HOOK_CODE
    m=ACC(image,seed());m.continue_reset=True
    ram_entry=0xF0000+m.listing.symbol('chipset_visible_ram_test')
    def stop_ram(u,a,z,c):m.stopped=True;u.emu_stop()
    hook=m.cpu.hook_add(UC_HOOK_CODE,stop_ram,begin=ram_entry,end=ram_entry)
    m.stop_address=ram_entry
    # Actual Save/reset reaches this running RAM-owner entry with gate active.
    m.open([0x44,28]);assert m.cpu.reg_read(x.UC_X86_REG_CS)*16+m.cpu.reg_read(x.UC_X86_REG_IP)==ram_entry
    assert m.cpu.mem_read(0x49E,1)==b'\x01'
    queue=bytes(m.cpu.mem_read(0x41A,4));commands=len(m.device_commands)
    for scan in (0xE0,0xFA,0xFE,0x53):m.irq_current(scan)
    assert m.cpu.mem_read(m.base+0xF4,1)==b'\x01' and m.cpu.mem_read(0x41A,4)==queue
    assert all(value!=0xFE for port,value in m.device_commands[commands:] if port==0x64)
    m.cpu.hook_del(hook);m.starting=True;m.stopped=False;m.script=[1,28]
    m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
    m.cpu.emu_start(ram_entry,0x100000,count=100000000)
    assert m.stopped and m.posts[-1]==0xE4 and m.cpu.mem_read(m.base+0xF4,1)==b'\0'
    assert m.cpu.mem_read(0x49E,1)==b'\x02' # Retry uses the actual closed halt gate.
    queue=bytes(m.cpu.mem_read(0x41A,4));commands=len(m.device_commands)
    m.irq_scans((0xFA,0xFE));assert m.cpu.mem_read(0x41A,4)==queue
    m.irq_scans((0xE0,0xFA,0xFE,0x53));assert m.cpu.mem_read(m.base+0xF4,1)==b'\0'
    result,_=m.public(0x16,0);assert result==0x5300
    m.irq_scans((0x1E,));letter,_=m.public(0x16,0);assert letter==0x1E61
    assert all(value!=0xFE for port,value in m.device_commands[commands:] if port==0x64)
    return {'actual_irq1_active_delete_request_not_queued':True,'actual_irq1_closed_delete_queued':result,'command_replies_not_queued':True,'e0_prefix_survives_command_replies':True,'later_int16':letter,'actual_ram_setup_discard_boot_terminal':0xE4}


def diagnostic_callbacks(image,seed):
    from build import run
    # Combined diagnostic text uses the supported stock-VGA layout's extra space.
    diagnostic=run('build/test-results/diagnostics-composed/image',('KEYBOARD_DIAGNOSTIC','FLOPPY_DIAGNOSTIC','MOUSE_DIAGNOSTIC'),vga60=False)['path']
    rows=[]
    for disabled,aux in ((False,True),(False,False),(True,False)):
        n=seed();ports_record(n,(1,2,1,2,0,int(not disabled),int(not disabled),1))
        m=ACC(diagnostic,n);m.aux_present=aux;m.continue_reset=True
        m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        entries={0xF0000+m.listing.symbol(name):name for name in ('post_keyboard_diagnostic','floppy_diagnostics','mouse_report')}
        waiting={};reports={};values={}
        def observe(model,address):
            if not m.starting:return
            if address in entries:
                owner=entries[address];u=m.cpu
                ret=0xF0000+struct.unpack('<H',u.mem_read(u.reg_read(x.UC_X86_REG_SS)*16+u.reg_read(x.UC_X86_REG_SP),2))[0]
                waiting[owner]=(ret,len(m.console));values[owner]={'ax':u.reg_read(x.UC_X86_REG_AX),'bx':u.reg_read(x.UC_X86_REG_BX),'sio':bytes(m.registers),'pic':m.port_in(u,0x21,1,None),'kbc':m.port_in(u,0x64,1,None)}
            for owner,(ret,start) in tuple(waiting.items()):
                if address==ret:reports[owner]=m.console[start:];del waiting[owner]
        m.code_observer=observe;m.open([0x44,28]);assert m.posts[-1]==0xE4
        keyboard=reports['post_keyboard_diagnostic'];assert f"PIC={values['post_keyboard_diagnostic']['pic']:02X} status={values['post_keyboard_diagnostic']['kbc']:02X}" in keyboard
        assert keyboard.count('Keyboard scans=01 last=FA')==10 and 'Keyboard window complete.' in keyboard
        floppy=reports['floppy_diagnostics'];assert 'Configured A/B types: 00/00' in floppy
        assert 'FDC read-only probe: stage 1=reset 2=recal 3=seek' in floppy and 'FDC probe complete; no sectors written.' in floppy
        assert floppy.count('Drive ')==(3 if disabled else 7) and ' BIOS=' in floppy and ' ST0/PCN=' in floppy and ' IRQ6=' in floppy,floppy
        assert m.cpu.mem_read(m.base+0x80,2)==bytes(2)
        assert 'SuperIO CR0..3: '+' '.join(f"{values['floppy_diagnostics']['sio'][i]:02X}" for i in (0xBE,0xDB,0xFB,0xFE)) in floppy
        if disabled:
            assert floppy.count('stage=00 BIOS=01 ST0/PCN=00/00 IRQ6=00')==3 and 'mouse_report' not in reports,(floppy,reports.get('mouse_report'))
            assert not any(port==0x64 and value==0xD4 for port,value in m.device_commands)
        else:
            mouse=reports['mouse_report'];v=values['mouse_report']
            assert f"PS/2 init AH/BX={v['ax']>>8:02X}/{v['bx']:04X}" in mouse
            assert f"ACC3221 DB={v['sio'][0xDB]:02X}" in mouse
            assert ' CB=' in mouse and ' stage=' in mouse and 'PS/2 RX status:data = ' in mouse and 'Mouse probe complete;' in mouse
            assert bool(m.cpu.mem_read(0x410,1)[0]&4)==aux
            assert m.cpu.mem_read(m.base+0xB4,1)==b'\0' # Initialized presence does not enable streaming.
        rows.append({'disabled_fdc_aux':disabled,'aux_present':aux,'actual_callback_reports':reports,'effective_mouse':aux and not disabled,'terminal':m.posts[-1]})
    return rows


def cache(image,seed):
    from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE,UC_HOOK_INSN
    rows=[]
    for kib in (0,32,64,128,256,512):
        for enabled in ((False,True) if kib in (0,32,128,512) else (True,)):
            m=ACC(image,seed());u=m.cpu
            ram=bytearray((i*13+7)&255 for i in range(0x60000));saved=bytes(ram)
            sram=bytearray(kib*1024);reads=[]
            u.mem_write(0x20000,bytes(ram))
            def probing():return m.registers[0x1A]&0x18==0x10
            fill_pc=0xF0000+m.listing.symbol('.reads','cache_stock_fill')
            def probe_access(address,size):
                if m.registers[4]==0x33 or probing():
                    assert any(start<=address and address+size<=end for start,end in ((0x20000,0x20008),(0x28000,0x28004),(0x30000,0x30004),(0x40000,0x40004),(0x60000,0x60004))),('SRAM probe touched stack/state',hex(address),size)
            def read(cpu,access,address,size,value,unused):
                probe_access(address,size)
                if not 0x20000<=address<0x80000:return
                if probing():
                    data=bytes(sram[(address-0x20000+i)%len(sram)] for i in range(size)) if sram else bytes([255])*size
                    cpu.mem_write(address,data)
                else:
                    cpu.mem_write(address,bytes(ram[address-0x20000:address-0x20000+size]))
                    if m.registers[4]&1 and m.registers[0x1A]&8 and size==4 and cpu.reg_read(x.UC_X86_REG_CS)*16+cpu.reg_read(x.UC_X86_REG_IP)==fill_pc:reads.append((address,size))
            def write(cpu,access,address,size,value,unused):
                probe_access(address,size)
                if not 0x20000<=address<0x80000:return
                data=value.to_bytes(size,'little')
                if probing():
                    if sram:
                        for i,b in enumerate(data):sram[(address-0x20000+i)%len(sram)]=b
                else:ram[address-0x20000:address-0x20000+size]=data
            u.hook_add(UC_HOOK_MEM_READ,read,begin=0,end=0x9FFFF)
            u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0,end=0x9FFFF)
            def probe_output(cpu,port,size,value,unused):
                if port==0x80:assert not probing(),'POST write during SRAM probe'
            u.hook_add(UC_HOOK_INSN,probe_output,None,1,0,x.UC_X86_INS_OUT)
            m.call('cache_initialize');assert bytes(ram)==saved
            expected_probe=[0x12]+([0x16 if kib<128 else 0x1F] if kib else [])
            assert m.posts==expected_probe,(kib,m.posts,expected_probe)
            present,code,qualified=bytes(u.mem_read(m.base+0x1003,3))
            assert present==bool(kib) and qualified==(kib>=128)
            assert code=={0:0,32:0,64:0,128:1,256:3,512:2}[kib]
            assert (0x16 in m.posts)==(0<kib<128)
            assert m.registers[1]==(0x92 if kib else 0xA5)
            m.call('cache_initial_policy')
            assert m.registers[1]==0x93
            if qualified:
                assert m.registers[0x1D]=={128:0xFC,256:0xF8,512:0xF0}[kib]
                assert m.registers[0x1E]=={128:0xD9,256:0xDB,512:0xDB}[kib]
            if 0<kib<128:assert m.cpu.mem_read(m.base+0x100A,1)==bytes((int(kib==64),))
            u.mem_write(m.base+0x62,bytes((int(enabled),)))
            m.call('chipset_apply');assert not m.registers[4]&1
            assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
            saved_late=bytes(ram)
            def low_read(cpu,access,address,size,value,unused):
                if m.registers[4]&1 and m.registers[0x1A]&8 and size==4 and cpu.reg_read(x.UC_X86_REG_CS)*16+cpu.reg_read(x.UC_X86_REG_IP)==fill_pc:reads.append((address,size))
            u.hook_add(UC_HOOK_MEM_READ,low_read,begin=0,end=0x1FFFF)
            # Execute the actual final gate (including the closed key predicate).
            m.call('setup_post_gate');m.call('chipset_late_cache')
            assert u.reg_read(x.UC_X86_REG_SS)==0 and u.reg_read(x.UC_X86_REG_SP)==0x7000
            effective=enabled and qualified
            assert bool(m.registers[4]&1)==bool(effective)
            assert u.mem_read(m.base+0x1006,1)==bytes((int(effective),))
            assert m.registers[0x1A]&0x18==(0 if effective else 8)
            assert bytes(ram)==saved_late
            if effective:
                assert reads and all(size==4 for address,size in reads)
                assert all(any(a<=address<a+0x10000 for address,size in reads) for a in range(0,0x80000,0x10000))
                assert reads[-1]==(0x7FFF8,4)
                assert m.registers[0x1E]&0x20
            m.call('post_cache_name');name=bytes(u.mem_read(0xF0000+u.reg_read(x.UC_X86_REG_SI),40)).split(b'\0')[0].decode()
            if 0<kib<128:assert name=='Present / unknown'
            elif not kib:assert name=='Disabled'
            else:assert name==(f'{kib} KB' if enabled else f'{kib} KB Off')
            m.cpu.mem_write(m.base+0x51,b'\x05');m.call('post_debug_summary')
            assert m.text(4,20,len(name))==name,(kib,enabled,name,m.text(4,20,len(name)))
            rows.append({'sram_kib_input':kib,'present':present,'code':code,'qualified':qualified,'requested':enabled,'effective':bool(effective),'display':name,'ram_preserved':True,'last_flush_read':reads[-1] if reads else None})
    return rows


def shadow(image,seed):
    import hashlib
    rows=[]
    for onboard in (False,True):
        for system in (False,True):
            n=seed();chip=bytes((0,1,1,int(system),0 if onboard else 1,1))+bytes(18)
            n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
            m=ACC(image,n,external_video=not onboard);m.cpu.mem_write(m.base+0x1007,bytes((int(onboard),)))
            original=bytes(m.cpu.mem_read(0xC0000,32768));system_input=Path(image).read_bytes()[65536:]
            m.continue_reset=True
            m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
            seen=[]
            def observer(model):
                if model.script==[0x44,28] and not model.pending:
                    value=model.text(9,49,25).strip()
                    expected='Enabled (required)' if onboard else 'Disabled'
                    assert value==expected,(onboard,value)
                    seen.append(value);model.observer=None
            m.observer=observer
            m.open([0x50]*4+[28,28]+[0x50]*4+([] if onboard else [0x4D])+[0x44,28])
            assert seen and m.reset_count==1
            assert m.cmos[0x6F]==0
            assert bool(m.registers[2]&0x10)==system,(onboard,system,m.cmos[0x6E],hex(m.registers[2]))
            assert bool(m.registers[2]&1)==onboard
            assert m.cpu.mem_read(0xC0000,32768)==original
            assert m.cpu.mem_read(0xF0000,65536)==system_input
            fallback=struct.pack('<HH',0xF065,0xF000) if onboard and system_input[0xF065:0xF068]==bytes.fromhex('80fc1d') else bytes(m.cpu.mem_read(0x40,4))
            assert m.cpu.mem_read(0x108,4)==fallback
            # A second actual Save/warm retains onboard origin and the fixed field.
            assert m.posts[-1]==0xE4 and 'Press any key to retry' in m.console
            if onboard:
                event=0xF0000+m.listing.symbol('post_ui_begin');injected=[]
                def repeat_input(model,address):
                    if address==event and not injected:
                        model.pending.extend((0xE0,0x53));injected.append(True)
                m.code_observer=repeat_input
                m.after_reset_script=[0x50]*4+[28,28]+[0x50]*4+[0x44,28]
                # Real IRQ1 Ctrl+Alt+Delete creates the next POST input window.
                m.irq_scans([0x1D,0x38,0xE0,0x53]);assert m.reset_pending
                m.complete_reset()
                assert injected and m.reset_count==3
                assert m.cpu.mem_read(m.base+0x1007,1)==b'\x01'
                assert m.cmos[0x6F]==0 and m.registers[2]&1
                assert m.posts[-1]==0xE4
            # These installed services belong to this same UI/Save/reset/provider path.
            assert m.registers[2]&0x31==0x20|(int(system)<<4)|int(onboard) #bit3 is retained by the proved mappings.
            assert m.public(0x12,0)[0]==632 and m.public(0x15,0x8800)[0]==15360
            for vector in (0x10,0x42):
                result,_=m.public(vector,0x1130,bx=0x0600)
                assert m.cpu.reg_read(x.UC_X86_REG_ES)==0xC000 and m.cpu.reg_read(x.UC_X86_REG_BP)==m.provider_font_offset
                assert m.cpu.reg_read(x.UC_X86_REG_CX)==16 and m.cpu.reg_read(x.UC_X86_REG_DX)==24
                assert m.cpu.mem_read(0xC0000+m.provider_font_offset,4096)==original[m.provider_font_offset:m.provider_font_offset+4096]
            assert m.cpu.mem_read(0xC0000,32768)==original
            rows.append({'onboard':onboard,'system_shadow':system,'video_effective':bool(m.registers[2]&1),'provider_sha256':hashlib.sha256(original).hexdigest(),'reset_count':m.reset_count,'same_path_public_int12_int15_int10_int42':True,'protected_provider_and_original_font':True})
    # External-ROM inputs own their declared header extent and font service.
    # The opaque provider returns INT10/42 C000:0100 and a 16-byte font at1000.
    # The original4096 font bytes are held equal across all three sizes.
    from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    original_font=(PORT/'reference/pb430-m27c1001.bin').read_bytes()[28169:32265]
    provider_cases=[(length,enabled,None) for length in (16384,32768,65536) for enabled in (False,True)]
    provider_cases += [(32768,False,'zero'),(32768,False,'too-large'),(65536,False,'late-checksum')]
    for length,enabled,bad in provider_cases:
        provider=bytearray((i*17+3)&255 for i in range(length))
        provider[:4]=bytes((0x55,0xAA,length//512,0xCB))
        provider[0x1000:0x2000]=original_font
        provider[-1]=0;provider[-1]=(-sum(provider))&255
        if bad=='zero':provider[2]=0
        elif bad=='too-large':provider[2]=129
        elif bad=='late-checksum':provider[-127]^=1
        n=seed();chip=bytes((0,1,1,1,int(not enabled),1))+bytes(18)
        n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
        m=ACC(image,n,font_offset=0x1000,external_video=True);u=m.cpu
        u.mem_write(m.base+0x1007,b'\0');m.registers[2]=0xB8 # Both C000/C800 windows initially external.
        u.mem_write(0xC0000,bytes(provider)+bytes([0xFF])*(65536-length))
        window=bytearray([0xA7])*32768
        m.continue_reset=True
        m.stop_address=0xF0000+m.listing.symbol('video_failed' if bad else '.wait',None if bad else 'boot_retry')
        entries={0xF0000+m.listing.symbol(owner):owner for owner in ('initialize_video','shadow_external_video')}
        waiting={};active=[];seen=[];provider_calls=[];copied=[];staged=[]
        def observe(model,address):
            if not m.starting:return
            if address==0xC0003:provider_calls.append(address)
            if address in entries:
                owner=entries[address]
                ret=0xF0000+struct.unpack('<H',u.mem_read(u.reg_read(x.UC_X86_REG_SS)*16+u.reg_read(x.UC_X86_REG_SP),2))[0]
                waiting[owner]=ret;active.append(owner);seen.append(owner)
                if owner=='shadow_external_video':staged.append(bytes(u.mem_read(0x20000,32768)))
            for owner,ret in tuple(waiting.items()):
                if address==ret:
                    if owner=='shadow_external_video':
                        extent=min(length,32768)
                        assert bytes(u.mem_read(0x20000,extent))==bytes(provider[:extent])
                        assert bytes(u.mem_read(0x20000+extent,32768-extent))==staged[0][extent:]
                    active.remove(owner);del waiting[owner]
        def provider_read(cpu,access,address,size,value,context):
            offset=address-0xC0000
            if active:assert offset+size<=length,('owner reads outside declared provider',active,offset,size,length)
            if offset<32768 and m.registers[2]&1:data=bytes(window[offset:offset+size])
            else:data=bytes(provider[offset:offset+size]) if offset<length else bytes([0xFF])*size
            cpu.mem_write(address,data)
        def provider_write(cpu,access,address,size,value,context):
            offset=address-0xC0000
            assert 'shadow_external_video' in active and offset+size<=min(length,32768)
            assert m.registers[2]&1 and not m.registers[2]&0x20
            window[offset:offset+size]=value.to_bytes(size,'little');copied.extend(range(offset,offset+size))
        u.hook_add(UC_HOOK_MEM_READ,provider_read,begin=0xC0000,end=0xCFFFF)
        u.hook_add(UC_HOOK_MEM_WRITE,provider_write,begin=0xC0000,end=0xCFFFF)
        m.code_observer=observe
        before=bytes(m.cmos);draft_seen=[]
        def draft(model):
            if model.script==[0x44,28] and not model.pending:
                assert model.cpu.mem_read(model.base+0x264,1)==bytes((int(enabled),))
                assert bytes(model.cmos)==before;draft_seen.append(True);model.observer=None
        m.observer=draft;m.open([0x50]*4+[28,28]+[0x50]*4+[0x4D,0x44,28])
        assert draft_seen and m.reset_count==1
        if bad:
            assert m.posts[-1]==0xE5 and provider_calls==[] and seen==['initialize_video']
            rows.append({'external_declared_bytes':length,'malformed':bad,'terminal':0xE5,'provider_not_called':True});continue
        assert m.posts[-1]==0xE4 and provider_calls==[0xC0003]
        assert m.cmos[0x6F]==int(enabled) and m.registers[2]&0x23==0x20|int(enabled)
        extent=min(length,32768)
        assert seen==(['initialize_video','shadow_external_video'] if enabled else ['initialize_video'])
        assert copied==(list(range(extent)) if enabled else [])
        assert bytes(window[:extent])==(bytes(provider[:extent]) if enabled else bytes([0xA7])*extent)
        assert bytes(window[extent:])==bytes([0xA7])*(32768-extent)
        assert bytes(u.mem_read(0xC0000,length))==bytes(provider)
        assert m.public(0x12,0)[0]==632 and m.public(0x15,0x8800)[0]==15360
        assert u.mem_read(0x40,4)==u.mem_read(0x108,4)==struct.pack('<HH',0x100,0xC000)
        for vector in (0x10,0x42):
            m.public(vector,0x1130,bx=0x0600)
            assert u.reg_read(x.UC_X86_REG_ES)==0xC000 and u.reg_read(x.UC_X86_REG_BP)==0x1000
            assert u.reg_read(x.UC_X86_REG_CX)==16 and u.reg_read(x.UC_X86_REG_DX)==24
            assert bytes(u.mem_read(0xC1000,4096))==original_font
        assert 'Press any key to retry' in m.console
        rows.append({'external_declared_bytes':length,'video_shadow_enabled':enabled,'actual_ui_save_reset_provider_services_retry':True,'copied_bytes':len(copied),'upper_window_external':True,'short_extent_not_read_or_copied':True,'complete_provider_sha256':hashlib.sha256(provider).hexdigest(),'same_font_int10_int42':True,'terminal':0xE4})
    # Hold the original32KiB provider/font/policy equal; only its returned far
    # vector differs. Three aliases address the same physical opaque handler.
    for offset,segment,accepted in ((0x100,0xC000,True),(0,0xC010,True),(0x110,0xBFFF,True),(0xF,0xBFFF,False),(0,0xD000,False)):
        n=seed();chip=bytes((0,1,1,1,1,1))+bytes(18)
        n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
        m=ACC(image,n,video_vector=(offset,segment),external_video=True);u=m.cpu
        u.mem_write(m.base+0x1007,b'\0');m.registers[2]=0xB8
        provider=bytes(u.mem_read(0xC0000,32768));raw=struct.pack('<HH',offset,segment)
        old_int42=[];m.continue_reset=True
        m.stop_address=0xF0000+m.listing.symbol('.wait' if accepted else 'video_failed','boot_retry' if accepted else None)
        entry=0xF0000+m.listing.symbol('initialize_video');returned=[];provider_calls=[];context=[];ret=[]
        regs=(x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX,x.UC_X86_REG_ESI,x.UC_X86_REG_EDI,x.UC_X86_REG_EBP,x.UC_X86_REG_DS,x.UC_X86_REG_ES,x.UC_X86_REG_FS,x.UC_X86_REG_GS,x.UC_X86_REG_SS,x.UC_X86_REG_EFLAGS)
        def observe(model,address):
            if not m.starting:return
            if address==0xC0003:provider_calls.append(address)
            if address==entry:
                old_int42.append(bytes(u.mem_read(0x108,4)))
                context.append((tuple(u.reg_read(reg) for reg in regs),u.reg_read(x.UC_X86_REG_SP)))
                ret.append(0xF0000+struct.unpack('<H',u.mem_read(u.reg_read(x.UC_X86_REG_SS)*16+u.reg_read(x.UC_X86_REG_SP),2))[0])
            elif ret and address==ret[0]:
                before,sp=context[0];after=tuple(u.reg_read(reg) for reg in regs)
                assert after[:-1]==before[:-1] and after[-1]==((before[-1]&~1)|int(not accepted))
                assert u.reg_read(x.UC_X86_REG_SP)==sp+2
                returned.append(True);ret.clear()
        m.code_observer=observe;before=bytes(m.cmos);draft_seen=[]
        def draft(model):
            if model.script==[0x44,28] and not model.pending:
                assert model.cpu.mem_read(model.base+0x264,1)==b'\0' and bytes(model.cmos)==before
                draft_seen.append(True);model.observer=None
        m.observer=draft;m.open([0x50]*4+[28,28]+[0x50]*4+[0x4D,0x44,28])
        assert draft_seen and returned==[True] and m.reset_count==1 and provider_calls==[0xC0003]
        assert bytes(u.mem_read(0xC0000,32768))==provider and u.mem_read(0x40,4)==raw
        assert m.registers[2]&0x23==0x20
        if accepted:
            assert m.posts[-1]==0xE4 and m.cmos[0x6F]==0 and u.mem_read(0x108,4)==raw
            assert m.public(0x12,0)[0]==632 and m.public(0x15,0x8800)[0]==15360
            for vector in (0x10,0x42):
                m.public(vector,0x1130,bx=0x0600)
                assert u.reg_read(x.UC_X86_REG_ES)==0xC000 and u.reg_read(x.UC_X86_REG_BP)==m.provider_font_offset
                assert u.reg_read(x.UC_X86_REG_CX)==16 and u.reg_read(x.UC_X86_REG_DX)==24
                assert u.mem_read(0xC0000+m.provider_font_offset,4096)==provider[m.provider_font_offset:m.provider_font_offset+4096]
            assert 'Press any key to retry' in m.console
        else:
            assert m.posts[-1]==0xE5 and bytes(u.mem_read(0x108,4))==old_int42[0]
        rows.append({'provider_vector':[offset,segment],'physical_handler':segment*16+offset,'accepted_existing_window':accepted,'actual_ui_save_reset_provider':True,'provider_calls':1,'raw_int10_int42_preserved':accepted,'initializer_context_restored':True,'same_provider_font_policy':True,'terminal':m.posts[-1]})
    return rows




def settings_load(image,seed):
    rows=[]
    def nondefault(version=5):
        n=seed();n[0x10]=0x30;n[0x3A]=version
        n[0x3B]=1 if version==1 else 0x0B
        n[0x3C]=1 if version<4 else 3 if version==4 else 4
        n[0x3E:0x40]=bytes((0xA5,0xA5)) if version==1 else bytes((2,0))
        n[0x3D]=(-sum(n[0x38:0x3D])-n[0x10]-(sum(n[0x3E:0x40]) if version>=2 else 0))&255
        n[0x2E:0x30]=struct.pack('>H',sum(n[0x10:0x2E]))
        ports_record(n,(3,4,2,3,1,0,0,0))
        chip=bytes((1,0,0,0,0,0))+bytes(18)
        n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
        payload=bytearray.fromhex('01000000000004103fffff0004000000000004103fffff0004');payload[0]=0
        n[0x40:0x5D]=b'ID\x01'+bytes((-(ord('I')+ord('D')+1+sum(payload))&255,))+payload
        return n
    for version in range(1,6):
        n=nondefault(version);m=ACC(image,n)
        assert m.cmos==n[:128]
        assert m.cpu.mem_read(m.base+0x174,1)==b'\x01'
        assert m.cpu.mem_read(m.base+0x170,1)==b'\x30'
        expected_boot=2 if version==1 else n[0x3C]
        expected_order=(2,1,0,0) if version==1 else (expected_boot,2,0,0)
        assert tuple(m.cpu.mem_read(m.base+i,1)[0] for i in (0x172,0x189,0x18A,0x1F6))==expected_order
        assert m.cpu.mem_read(m.base+0x60,6)==bytes((1,0,0,0,0,0))
        assert m.cpu.mem_read(m.base+0x1E6,8)==bytes((3,4,2,3,1,0,0,1)),(version,bytes(m.cpu.mem_read(m.base+0x1E6,8)).hex())
        assert m.cpu.mem_read(m.base+0x190,1)==b'\0'
        if version==1:assert m.cpu.mem_read(m.base+0x173,1)==b'\0' and m.cpu.mem_read(m.base+0x177,1)==b'\0'
        rows.append({'base_version':version,'boot_order':expected_order,'nondefault_base_and_extensions':True,'saved_pair_retained':True,'no_persistent_writes':True})
    for kind in ('base','chip-checksum','chip-field','ports-checksum','ports-irq','ide-checksum'):
        n=nondefault()
        if kind=='base':n[0x3D]^=1
        elif kind=='chip-checksum':n[0x6A]^=1
        elif kind=='chip-field':n[0x70]=2;n[0x6A]=(-0xC2-sum(n[i] for i in (*range(0x6B,0x80),0x33,0x34,0x35)))&255
        elif kind=='ports-checksum':n[0x68]^=1
        elif kind=='ports-irq':ports_record(n,(3,1,2,3,1,0,0,0))
        elif kind=='ide-checksum':n[0x43]^=1
        m=ACC(image,n);assert m.cmos==n[:128]
        assert m.cpu.mem_read(m.base+0x174,1)==b'\0'
        assert bool(m.cpu.mem_read(m.base+0x17C,1)[0])==(kind!='base')
        assert m.cpu.mem_read(m.base+0x60,6)==(bytes((0,1,1,1,1,0)) if kind.startswith('chip') else bytes((1,0,0,0,0,0)))
        assert m.cpu.mem_read(m.base+0x1E6,8)==(bytes((1,2,1,2,0,1,1,1)) if kind.startswith('ports') else bytes((3,4,2,3,1,0,0,1)))
        assert m.cpu.mem_read(m.base+0x190,1)==bytes((int(kind.startswith('ide') or kind=='base'),)),(kind,bytes(m.cpu.mem_read(m.base+0x190,1)).hex())
        if kind!='base':assert m.cpu.mem_read(m.base+0x172,1)==b'\x04' and m.cpu.mem_read(m.base+0x17F,1)==b'\x01'
        rows.append({'kind':kind,'invalid_owner_fallback':True,'unrelated_nondefault_records_retained':True,'no_persistent_writes':True})
    return rows


def setup_actions(image,seed):
    rows=[]
    for action in ('discard','defaults-discard','save'):
        n=seed()
        if action=='defaults-discard':
            chip=bytes((1,0,0,0,1,0))+bytes(18)
            n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
        m=ACC(image,n);m.call('chipset_apply');before=bytes(m.cmos);m.continue_reset=action=='save'
        m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        hardware=bytes(m.registers);cache_cr0=m.cpu.reg_read(x.UC_X86_REG_CR0);active=bytes(m.cpu.mem_read(m.base+0x60,24));defaults_seen=[]
        keys=[0x50]*4+[28,28,0x4D]
        if action=='defaults-discard':keys += [0x43,28]
        keys += [0x44,28] if action=='save' else [1,1,1,28]
        if action=='defaults-discard':
            def observer(model):
                if model.script==[1,1,1,28] and not model.pending:
                    assert model.cpu.mem_read(model.base+0x260,24)==bytes((0,1,1,1,1,0,0,0,0,0,0,0,0,0,0,0x15,0,0,0,0,0,0x10,0,0xA3))
                    assert model.cpu.mem_read(model.base+0x1EE,8)==bytes((1,2,1,2,0,1,1,1))
                    assert bytes(model.cmos)==before and bytes(model.registers)==hardware
                    defaults_seen.append(True);model.observer=None
            m.observer=observer
        m.open(keys)
        if action=='save':assert m.cmos[0x6B]==1 and m.reset_count==1
        else:
            assert bytes(m.cmos)==before and not m.reset_count and bytes(m.registers)==hardware
            assert m.cpu.mem_read(m.base+0x60,24)==active and m.cpu.reg_read(x.UC_X86_REG_CR0)==cache_cr0
        if action=='defaults-discard':assert defaults_seen
        cold=False
        if action=='save':
            import importlib
            cold_result=importlib.import_module('test-port').native('setup-saved-cold',cmos=m.cmos,saved_ads=False)
            assert cold_result['terminal']==0x60;cold=True
            assert (PORT/'build/test-results/setup-saved-cold/vm/nvr/pb430.nvr').read_bytes()[0x69:0x80]==bytes(m.cmos[0x69:0x80])
        # Runtime keyboard after UI/reset: same installed INT16 owns next input.
        m.cpu.mem_write(0x49E,b'\x02');m.scans([0x1E]);result,_=m.public(0x16,0x0000);assert result==0x1E61
        rows.append({'action':action,'saved':action=='save','defaults_draft_observed':bool(defaults_seen),'discard_hardware_preserved':action!='save','actual_cold_reload':cold,'runtime_int16':result})
    return rows


def cache_composed(image,seed):
    from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    rows=[]
    for kib,cpu_enabled,requested in ((0,True,True),(32,True,True),(64,True,True),(128,True,False),(128,True,True),(256,True,True),(512,True,True),(512,False,True)):
        n=seed();chip=bytes((0,int(cpu_enabled),int(requested),1,1,1))+bytes(18)
        n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
        m=ACC(image,n);u=m.cpu;m.continue_reset=True
        m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        fill_pc=0xF0000+m.listing.symbol('.reads','cache_stock_fill')
        ram=bytearray((i*13+7)&255 for i in range(0x60000));sram=bytearray(kib*1024);saved=bytes(ram);reads=[];preserved=[]
        u.mem_write(0x20000,bytes(ram))
        def probing():return m.registers[0x1A]&0x18==0x10
        def read(cpu,access,address,size,value,unused):
            if probing():data=bytes(sram[(address-0x20000+i)%len(sram)] for i in range(size)) if sram else bytes([255])*size
            else:
                if not 0x20000<=address<0x80000:return
                data=bytes(ram[address-0x20000:address-0x20000+size])
                if m.registers[4]&1 and m.registers[0x1A]&8 and size==4 and cpu.reg_read(x.UC_X86_REG_CS)*16+cpu.reg_read(x.UC_X86_REG_IP)==fill_pc:reads.append((address,size))
            cpu.mem_write(address,data)
        def write(cpu,access,address,size,value,unused):
            data=value.to_bytes(size,'little')
            if probing():
                if sram:
                    for i,b in enumerate(data):sram[(address-0x20000+i)%len(sram)]=b
            elif 0x20000<=address<0x80000:ram[address-0x20000:address-0x20000+size]=data
        u.hook_add(UC_HOOK_MEM_READ,read,begin=0x10000,end=0x90003)
        u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0x10000,end=0x90003)
        entry=0xF0000+m.listing.symbol('cache_initial_policy')
        gate=0xF0000+m.listing.symbol('setup_post_gate');late=0xF0000+m.listing.symbol('chipset_late_cache')
        milestones=[];late_state=[];late_return=[];late_writes=[]
        def observe(model,address):
            if not m.starting:return
            if address==entry:assert bytes(ram)==saved;preserved.append(True)
            if address==gate:
                assert not m.registers[4]&1 and u.mem_read(m.base+0x1006,1)==b'\0'
                assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
                milestones.append('final_gate_off')
            if address==late:
                assert milestones==['final_gate_off'] and not m.registers[4]&1
                assert u.mem_read(0x49E,1)==b'\x02'
                late_state.append((bytes(ram),bytes(u.mem_read(0x10000,0x10000)),bytes(m.registers)))
                late_return.append(0xF0000+struct.unpack('<H',u.mem_read(u.reg_read(x.UC_X86_REG_SS)*16+u.reg_read(x.UC_X86_REG_SP),2))[0])
                late_writes.append(len(m.acc_writes));milestones.append('late_begin_off')
            if late_return and address==late_return[0]:
                assert bytes(ram)==late_state[0][0] and bytes(u.mem_read(0x10000,0x10000))==late_state[0][1]
                milestones.append('late_return_ram_restored');late_return.clear()
        def low_read(cpu,access,address,size,value,unused):
            if m.registers[4]&1 and m.registers[0x1A]&8 and size==4 and cpu.reg_read(x.UC_X86_REG_CS)*16+cpu.reg_read(x.UC_X86_REG_IP)==fill_pc:reads.append((address,size))
        u.hook_add(UC_HOOK_MEM_READ,low_read,begin=0,end=0x1FFFF)
        m.code_observer=observe
        # One actual UI/Save/reset/startup/shared POST/late-cache/summary/retry path.
        m.open([0x50]*4+[28,28,0x4D,0x44,28])
        assert m.reset_count==1 and preserved==[True]
        required=('startup','cache_initialize','cache_initial_policy','chipset_apply','init_peripherals','init_floppy','ata_detect_primary','init_mouse','init_fpu','chipset_late_cache','option_rom_discovery','post_debug_summary','int19','boot_retry')
        visited=[m.trace_owners[a] for a in m.trace_seen]
        assert all(owner in visited for owner in required),(kib,visited)
        present,code,qualified=bytes(u.mem_read(m.base+0x1003,3))
        effective=cpu_enabled and requested and kib>=128
        assert present==bool(kib) and qualified==(kib>=128)
        assert bool(m.registers[4]&1)==bool(effective)
        assert u.mem_read(m.base+0x1006,1)==bytes((int(effective),))
        assert bool(u.reg_read(x.UC_X86_REG_CR0)&0x40000000)==(not cpu_enabled)
        assert m.cmos[0x6D]==int(requested)
        if kib and kib<128:
            assert code==0 and 0x16 in m.posts
            assert m.text(4,20,17)=='Present / unknown'
            assert u.mem_read(m.base+0x100A,1)==bytes((int(kib==64),))
        elif kib:assert m.text(4,20,20).strip()==(f'{kib} KB' if requested else f'{kib} KB Off')
        else:assert m.text(4,20,8)=='Disabled'
        assert 'No boot device available' in m.console and 'Press any key to retry' in m.console
        assert m.posts[-1]==0xE4 and m.registers[0x1A]&0x18==(0 if effective else 8)
        assert milestones==['final_gate_off','late_begin_off','late_return_ram_restored']
        assert bytes(ram)==late_state[0][0] and bytes(u.mem_read(0x10000,0x10000))==late_state[0][1]
        if effective:
            assert reads==[(segment*0x10000+offset,4) for segment in range(8) for offset in range(0,0xFFFC,4)]
            old=late_state[0][2]
            sequence=[(index,value) for index,value in m.acc_writes[late_writes[0]:] if index in (0x1A,4,0x1E)]
            assert sequence==[(0x1A,(old[0x1A]&0xE7)|8),(4,old[4]|1),(0x1E,old[0x1E]|0x20),(0x1A,old[0x1A]&0xE7)],sequence
        else:assert not reads
        rows.append({'sram_kib_input':kib,'cpu_enabled':cpu_enabled,'l2_request':requested,'present':present,'qualified':qualified,'effective':bool(effective),'terminal':'actual boot_retry wait after E4','reset_vector':True,'production_owners':required,'probe_ram_preserved':True,'late_terminal_ram_preserved':True,'actual_chronology':milestones,'flush_reads':len(reads)})
    return rows


def cache_interrupts(image,seed):
    """Inject IRQ0/IRQ1 inside the stock STI window, including index/data pairs."""
    from capstone import Cs,CS_ARCH_X86,CS_MODE_16
    from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    m=ACC(image,seed());u=m.cpu;m.continue_reset=True
    m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
    m.open([0x44,28]);assert m.posts[-1]==0xE4
    raw=Path(image).read_bytes()[65536:];listing=m.listing
    start,end=listing.symbol('cache_stock_enable'),listing.symbol('cache_stock_enable_end')
    instructions=list(Cs(CS_ARCH_X86,CS_MODE_16).disasm(raw[start:end],start))
    sti=next(ins.address for ins in instructions if ins.mnemonic=='sti')
    cli=next(ins.address for ins in instructions if ins.address>sti and ins.mnemonic=='cli')
    sites=[ins.address for ins in instructions if sti<ins.address<=cli][1:]
    for owner,stop in (('acc_read','acc_write'),('cache_stock_write','cache_stock_write_end')):
        a,b=listing.symbol(owner),listing.symbol(stop)
        sites += [ins.address for ins in Cs(CS_ARCH_X86,CS_MODE_16).disasm(raw[a:b],a)]
    registers=(x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX,x.UC_X86_REG_ESI,x.UC_X86_REG_EDI,x.UC_X86_REG_EBP,x.UC_X86_REG_SS,x.UC_X86_REG_SP,x.UC_X86_REG_DS,x.UC_X86_REG_ES,x.UC_X86_REG_FS,x.UC_X86_REG_GS,x.UC_X86_REG_EFLAGS)
    rows=[];entered=[];returned=[];high_accesses=[]
    def memory(cpu,access,address,size,value,unused):
        if entered and not returned:high_accesses.append((address,size))
    u.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,memory,begin=0x80000,end=0x9FFFF)
    runtime_vector=bytes(u.mem_read(0x20,4))
    stock_vector=struct.pack('<HH',listing.symbol('cache_stock_timer'),0xF000)
    for vector in (8,9):
        for target in sites:
            m.registers[0x1E]=0x5B
            m.call('chipset_apply');assert not m.registers[4]&1
            entered=[];returned=[];high_accesses=[]
            def observe(model,address):
                if address!=0xF0000+target or not u.reg_read(x.UC_X86_REG_EFLAGS)&0x200 or m.registers[0x1A]&0x18!=8:return
                state=(tuple(u.reg_read(reg) for reg in registers),m.acc_index)
                if not entered:
                    assert bytes(u.mem_read(0x20,4))==stock_vector,'Transient mode uses the runtime timer'
                    entered.append(state)
                    if vector==9:m.pending.append(0x3A)
                    rtc.Clock.interrupt(m,u,vector,None)
                elif not returned:
                    assert state==entered[0],(vector,hex(target),'IRQ return registers/index differ',state,entered[0])
                    returned.append(True)
            m.code_observer=observe
            m.call('chipset_late_cache');m.code_observer=None
            assert entered and returned,(vector,hex(target),'injection did not return')
            assert bytes(u.mem_read(0x20,4))==runtime_vector,'Runtime timer vector was not restored'
            if vector==8:assert not high_accesses,('Stock timer touched high BIOS RAM',high_accesses)
            assert m.registers[4]&1 and m.registers[0x1E]&0x20 and not m.registers[0x1A]&0x18
            rows.append({'vector':vector,'address':hex(target),'registers_flags_and_chipset_index_preserved':True,'high_memory_accesses':high_accesses,'normal_cache_state_restored':True,'runtime_timer_restored':True})
    class ParityACC(ACC):
        def port_in(self,cpu,port,size,unused):
            return 0x80 if port==0x61 else super().port_in(cpu,port,size,unused)
    parity=ParityACC(image,seed());cpu=parity.cpu
    for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_IP,parity.listing.symbol('chipset_nmi')),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x7000),(x.UC_X86_REG_EFLAGS,2)):
        cpu.reg_write(reg,value)
    target=parity.listing.symbol('print_string')
    cpu.emu_start(0xF0000+parity.listing.symbol('chipset_nmi'),0xF0000+target,count=10000)
    assert cpu.reg_read(x.UC_X86_REG_IP)==target and parity.posts[-1:]==[0xE8]
    rows.append({'vector':2,'parity_marker_before_print':True})
    return rows


def reset_dispatch(image,seed):
    """Service shutdown codes remain distinct from the normal POST branch."""
    rows=[]
    for system_flag,shutdown in ((4,5),(4,0x0A),(4,0),(4,6),(0,5),(0,0x0A)):
        m=ACC(image,seed());u=m.cpu;m.continue_reset=True;m.sys_flag=system_flag
        m.cmos[0x0F]=shutdown
        u.mem_write(0x467,struct.pack('<HH',0,0x9000))
        service=bool(system_flag&4) and shutdown in (5,0x0A)
        m.stop_address=0x90000 if service else 0xF0000+m.listing.symbol('.normal','startup')
        m.reset_pending=True;m.complete_reset(count=100000)
        assert m.cmos[0x0F]==0
        assert m.posts==([shutdown] if service else [])
        if service:assert u.reg_read(x.UC_X86_REG_DS)==0x40 and u.reg_read(x.UC_X86_REG_SP)==0
        rows.append({'system_flag':system_flag,'shutdown':shutdown,'service_resume':service,'post_codes':m.posts,'shutdown_consumed':True})
    for owner in ('warm_reset','controlled_defaults_restart'):
        for shutdown in (5,0x0A):
            m=ACC(image,seed());u=m.cpu;m.cmos[0x0F]=shutdown
            for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_IP,m.listing.symbol(owner)),(x.UC_X86_REG_DS,0x40),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x7000),(x.UC_X86_REG_EFLAGS,2)):
                u.reg_write(reg,value)
            u.emu_start(0xF0000+m.listing.symbol(owner),0xFFFFF,count=1000000)
            assert m.reset_pending and m.cmos[0x0F]==0,('normal reset retained service shutdown',owner,shutdown)
            rows.append({'owner':owner,'previous_shutdown':shutdown,'reset_pulse':True,'shutdown_cleared_before_reset':True})
    return rows


def cache_warm(image,seed):
    """Actual IRQ1 Caps Lock and Ctrl+Alt+Del with already active L2."""
    from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
    from shared.tools.ram_proof import constants
    ram_flags=constants(PORT.parent/'shared/src/pc/state.inc')['P_RAM_FLAGS']
    m=ACC(image,seed());u=m.cpu;m.continue_reset=True
    m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
    restore=0xF0000+m.listing.symbol('cache_late_restore')
    registers=(x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX,x.UC_X86_REG_ESI,x.UC_X86_REG_EDI,x.UC_X86_REG_EBP,x.UC_X86_REG_SS,x.UC_X86_REG_SP,x.UC_X86_REG_DS,x.UC_X86_REG_FS)
    handoff=[]
    def observe(model,address):
        if not m.starting or address!=restore:return
        current=tuple(u.reg_read(reg) for reg in registers)
        ticks=int.from_bytes(u.mem_read(0x46C,4),'little')
        if not handoff:
            assert m.registers[4]&1 and u.reg_read(x.UC_X86_REG_EFLAGS)&0x200
            handoff.append((current,ticks));rtc.Clock.interrupt(m,u,8,None)
        elif len(handoff)==1:
            assert current==handoff[0][0] and ticks==handoff[0][1]+1
            handoff.append('IRQ0 returned after54 with caller intact')
    m.code_observer=observe
    m.open([0x44,28]);assert m.posts[-1]==0xE4
    assert len(handoff)==2;m.code_observer=None
    facts=bytes(u.mem_read(m.base+0x1003,3))
    extended=m.public(0x15,0x8800)[0]
    assert facts==bytes((1,2,1)) and m.registers[0x1E]&0x20
    raw=Path(image).read_bytes()[65536:]
    flushes=[]
    def flush(cpu,address,size,unused):
        if not m.starting:return
        assert not (m.registers[4]&1 and not m.registers[0x1E]&0x20),('WBINVD before warm L2 holdoff',hex(address),m.posts[-1])
        flushes.append({'address':hex(address),'register04':m.registers[4],'register1E':m.registers[0x1E]})
    for offset in range(len(raw)-1):
        if raw[offset:offset+2]==b'\x0F\x09':
            for segment_base in (0xF0000,0x30000):
                address=segment_base+offset
                u.hook_add(UC_HOOK_CODE,flush,begin=address,end=address)
    rows=[]
    for valid,high,shutdown in ((True,True,5),(True,False,0x0A),(False,False,0)):
        skipped=[]
        def skip_ram(cpu,address,size,unused):
            if m.starting and not high and not skipped:
                m.pending.append(1);skipped.append(True)
        keyboard=0xF0000+m.listing.symbol('.keyboard','chipset_visible_ram_test')
        skip_hook=u.hook_add(UC_HOOK_CODE,skip_ram,begin=keyboard,end=keyboard)
        m.irq_scans([0x3A,0xBA]);caps=u.mem_read(0x417,1)[0]&0x40
        if not valid:u.mem_write(m.base+0x100C,b'\0')
        m.registers[0x1E]=(m.registers[0x1E]&0x7F)|(0x80 if high else 0)
        old=m.registers[0x1E];start=len(m.posts);writes=len(m.acc_writes);first=[];flushed=len(flushes)
        m.cmos[0x0F]=shutdown
        def write(cpu,access,address,size,value,unused):
            if m.starting and not first:
                # Stock9631 uses retained low RAM for its fill frame before clearing1E.
                if 0x7BE0<=address and address+size<=0x7C00:
                    return
                assert not m.registers[0x1E]&0x20,('warm RAM write before stock tag clear',hex(address))
                assert not m.registers[4]&1,('warm state write before L2 off',hex(address))
                first.append(address)
        hook=u.hook_add(UC_HOOK_MEM_WRITE,write,begin=0,end=0x9FFFF)
        m.irq_scans([0x1D,0x38,0xE0,0x53]);assert m.reset_pending
        stock_vector=struct.pack('<HH',m.listing.symbol('cache_stock_timer'),0xF000)
        assert bytes(u.mem_read(0x20,4))==stock_vector,'Reset pulse lost the stock timer'
        assert m.cmos[0x0F]==0,('normal reset retained service shutdown',shutdown)
        teardown=m.acc_writes[writes:]
        assert [index for index,value in teardown]==[0x18,4,1,0x1A,4,0x1A,2],teardown
        assert teardown[0][1]&1==0 and teardown[1][1]&0x10 and teardown[2]==(1,0x93)
        assert not m.registers[4]&1 and not m.registers[0x1A]&0x18
        writes=len(m.acc_writes)
        early_timer=[]
        early_entry=0xF0000+m.listing.symbol('cache_stock_warm_entry')
        def early_observer(model,address):
            if address==early_entry:
                assert bytes(u.mem_read(0x20,4))==stock_vector,'Early warm entry lost the stock timer'
                early_timer.append(True)
        m.code_observer=early_observer
        m.complete_reset();m.code_observer=None;u.hook_del(hook);u.hook_del(skip_hook)
        assert bool(skipped)==(not high)
        assert u.mem_read(m.base+ram_flags,1)==bytes((2 if skipped else 4,))
        assert early_timer
        assert bytes(u.mem_read(0x20,4))==struct.pack('<HH',m.listing.symbol('int08'),0xF000)
        stages=m.posts[start:];changed=m.acc_writes[writes:]
        assert m.posts[-1]==0xE4 and first
        assert [code for code in stages if 0xD0<=code<=0xD4]==list(range(0xD0,0xD5))
        assert [index for index,value in changed[:9]]==[0x18,0x18,4,5,0x1A,4,0x1E,0x1A,0x1E],changed[:9]
        assert changed[0][1]&1==0 and changed[1][1]&1==0 and changed[2][1]&0x10
        assert changed[3][1]&3==0
        assert changed[6]==(0x1E,old&0xDF)
        assert 0x1B in stages and 0x20 not in stages
        assert (0x1C in stages)==valid and (0x12 in stages)!=valid
        assert any(index==4 and value==0x33 for index,value in changed)!=valid
        assert bytes(u.mem_read(m.base+0x1003,3))==facts
        assert u.mem_read(m.base+0x100C,1)==b'\xA8'
        assert m.registers[0x1E]==old and m.registers[4]&1
        assert m.public(0x12,0)[0]==632
        assert m.public(0x15,0x8800)[0]==extended
        rows.append({'prior_detection_valid':valid,'reserved_bit7':high,'previous_shutdown':shutdown,'normal_reset_shutdown_cleared':True,'caps_lock_flag':bool(caps),'actual_ctrl_alt_del':True,'visible_ram_test_skipped':bool(skipped),'irq0_after54_preserves_caller':True,'stock_pre_reset_writes':teardown,'first_acc_write':changed[0],'first_warm_ram_write':first[0],'cold_cache_probe_skipped':valid,'no_writeback_flush_before_l2_holdoff':True,'writeback_flush_states':flushes[flushed:],'cache_facts':list(facts),'post_codes':[f'{p:02X}' for p in stages],'terminal':'boot_retry E4'})
    return rows


def warm_boot_device(image,seed):
    """Keep a signed ATA boot working through real Save/reset and both CAD keys."""
    import importlib
    from unicorn import UC_HOOK_CODE
    class BootDevice(ACC):
        def __init__(self):
            self.disk_device=None
            self.disk_word=0
            self.boot_sector=bytearray(512)
            self.boot_sector[:4]=b'BOOT'
            self.boot_sector[510:]=b'\x55\xAA'
            super().__init__(image,seed())
            self.disk_device=importlib.import_module('test-legacy-disk').Pair(('ata','absent'))
            self.disk_device.cpu=self.cpu
        def port_in(self,cpu,port,size,unused):
            if self.disk_device is not None and (0x1F0<=port<=0x1F7 or port==0x3F6):
                if port==0x1F0 and self.disk_device.ata.get(0x1F7)==0x20:
                    value=struct.unpack_from('<H',self.boot_sector,self.disk_word*2)[0]
                    self.disk_word+=1
                    return value
                return self.disk_device.port_in(cpu,port,size,unused)
            return super().port_in(cpu,port,size,unused)
        def port_out(self,cpu,port,size,value,unused):
            if self.disk_device is not None and (0x1F0<=port<=0x1F7 or port==0x3F6):
                if port==0x1F7 and value==0x20:self.disk_word=0
                return self.disk_device.port_out(cpu,port,size,value,unused)
            return super().port_out(cpu,port,size,value,unused)
    m=BootDevice();u=m.cpu;m.continue_reset=True;m.stop_address=0x7C00
    owners=('chipset_visible_ram_test','init_floppy','ata_detect_primary','int19')
    addresses={0xF0000+m.listing.symbol(name):name for name in owners}
    visited=[]
    fill_entry=0xF0000+m.listing.symbol('cache_stock_fill')
    fill_frames=[]
    def observe(model,address):
        if m.starting and address in addresses:visited.append(addresses[address])
        if m.starting and address==fill_entry:
            fill_frames.append(tuple(u.reg_read(reg) for reg in (x.UC_X86_REG_DS,x.UC_X86_REG_SS,x.UC_X86_REG_SP)))
    m.code_observer=observe
    ram=0xF0000+m.listing.symbol('chipset_visible_ram_test')
    # The normal ACC observer excludes the long RAM loop; observe its entry only.
    u.hook_add(UC_HOOK_CODE,lambda cpu,address,size,unused:observe(m,address),begin=ram,end=ram)
    def booted():
        assert u.reg_read(x.UC_X86_REG_CS)==0 and u.reg_read(x.UC_X86_REG_IP)==0x7C00
        assert bytes(u.mem_read(0x7C00,512))==bytes(m.boot_sector)
        assert bytes(u.mem_read(0x475,1))==b'\x01'
        assert bytes(u.mem_read(m.base+0x20,1))==b'\x01'
        assert [owner for owner in visited if owner in owners]==list(owners),visited
        assert fill_frames==[(0,0,0x7BFE),(0,0x30,0xEA)],fill_frames
        assert m.kbc_p1&0x20
        assert 0xE4 not in m.posts and 'No boot device available' not in m.console
        assert (0,0xEC) in m.disk_device.selected_commands
        assert (0,0x20) in m.disk_device.selected_commands
        ax,flags=m.public(0x13,0x0201,dx=0x80,cx=1,bx=0x7E00)
        assert not flags&1 and ax==1,(hex(ax),hex(flags))
        assert bytes(u.mem_read(0x7E00,512))==bytes(m.boot_sector)
    m.open([0x44,28]);booted()
    rows=[{'producer':'setup Save','post_owners':visited.copy(),'signed_boot':True,'disk_count':1,'public_int13_read':True}]
    for extended in (False,True):
        for shutdown in (5,0x0A):
            visited.clear();fill_frames.clear();m.posts.clear();m.console='';m.disk_device.selected_commands.clear()
            before=m.disk_device.reset_count
            shadow=m.registers[2]
            m.disk_device.needs_reset=True
            u.mem_write(0x475,b'\0');u.mem_write(m.base+0x20,b'\0')
            m.cmos[0x0F]=shutdown
            m.irq_scans([0x1D,0x38]+([0xE0] if extended else [])+[0x53])
            assert m.reset_pending and m.cmos[0x0F]==0
            assert m.registers[2]==shadow&0x98
            assert not m.registers[4]&1 and not m.registers[0x1A]&0x18
            assert u.reg_read(x.UC_X86_REG_CR0)&0x60000000==0x60000000
            m.complete_reset();booted()
            assert m.disk_device.reset_count>before and not m.disk_device.needs_reset
            assert 0x90 in m.posts and 0x10 in m.posts and 0x1B in m.posts
            rows.append({'producer':'Ctrl+Alt+Del','extended_delete':extended,'previous_shutdown':shutdown,'post_owners':visited.copy(),'ata_redetected_after_poisoned_publication':True,'channel_reset':True,'signed_boot':True,'disk_count':1,'public_int13_read':True,'boot_retry':False})
    return rows


def cache_cold_entry(image,seed):
    rows=[]
    for jumper in range(8):
        m=ACC(image,seed());m.jumper=jumper;m.sys_flag=0
        m.cpu.mem_write(0x472,b'\0\0');m.reset_pending=True;m.continue_reset=True
        m.stop_address=0xF0000+m.listing.symbol('memory_initialize')
        m.complete_reset(count=100000)
        expected=0x33 if jumper==4 else 0xB7 if jumper==5 else 0x13
        assert m.port78_writes==[0] and m.registers[6]==expected
        assert [value for index,value in m.acc_writes if index==6]==[0xB7 if jumper==5 else 0xB3,0x13,expected]
        assert 0x1B not in m.posts and 0x20 in m.posts
        rows.append({'jumper':jumper,'stock_reset_write78':m.port78_writes,'clock_register06':expected,'initial06_before_selection':True,'terminal':'actual memory_initialize entry'})
    return rows


def cache_timing_rows(image,seed):
    """Supplemental register-row proof; composed cache paths remain separate."""
    from unicorn import UC_HOOK_MEM_READ,UC_HOOK_MEM_WRITE
    safe={4:(0x94,0x54,0x54,0x14),6:(0x13,0x33,0xB7,0x12),7:(0x18,0x18,0x14,0x18),11:(4,5,5,0x15),24:(0x20,0x20,0,0),26:(0x24,)*4}
    live={4:(0x14,0x14,0x14,0x34),6:(0x23,0x33,0xB7,0x12),7:safe[7],11:(4,0x15,0x15,0x15),24:(0x20,0,0,0),26:safe[26]}
    rows=[]
    for present,cpu_enabled in ((False,True),(True,False),(True,True)):
        for jumper in range(8):
            n=seed();chip=bytes((0,int(cpu_enabled),1,1,1,1))+bytes(18)
            n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
            m=ACC(image,n);m.jumper=jumper;m.registers[0x1A]=0xC0
            sram=bytearray(512*1024)
            def read(u,access,address,size,value,unused):
                if m.registers[0x1A]&0x18==0x10:u.mem_write(address,bytes(sram[(address-0x20000+i)%len(sram)] for i in range(size)) if present else bytes([255])*size)
            def write(u,access,address,size,value,unused):
                if present and m.registers[0x1A]&0x18==0x10:
                    for i,b in enumerate(value.to_bytes(size,'little')):sram[(address-0x20000+i)%len(sram)]=b
            m.cpu.hook_add(UC_HOOK_MEM_READ,read,begin=0x20000,end=0x7FFFF)
            m.cpu.hook_add(UC_HOOK_MEM_WRITE,write,begin=0x20000,end=0x7FFFF)
            m.call('cache_initialize');assert m.cpu.mem_read(m.base+0x1005,1)==bytes((int(present),))
            m.call('cache_initial_policy');s=max(0,min(jumper-3,3));table=live if present and cpu_enabled else safe
            expected={reg:(0xA5 & {7:0xE0,24:0x8C}.get(reg,0))|values[s] for reg,values in table.items()}
            expected[26]=0x6C
            expected[6]=0x33 if jumper==4 else 0xB7 if jumper==5 else 0x13
            assert all(m.registers[reg]==value for reg,value in expected.items()),(present,cpu_enabled,jumper,expected)
            assert m.registers[0x1D]==(0xF0 if present and cpu_enabled else 0xA5)
            assert m.registers[0x1E]==(0xDB if present and cpu_enabled else 0x85)
            assert m.registers[0x0C:0x12]==(bytes((0x0C,0x80,0,0,0,0)) if present else bytes(6))
            rows.append({'present':present,'cpu_enabled':cpu_enabled,'port78':jumper,'speed_index':s,'register_oracle':expected,'qualified_probe_executed':True})
    return rows


def disabled_ide(image,seed):
    n=seed();payload=bytearray.fromhex('00000000000004103fffff0004000000000004103fffff0004')
    n[0x40:0x5D]=b'ID\x01'+bytes((-(ord('I')+ord('D')+1+sum(payload))&255,))+payload
    m=ACC(image,n);m.continue_reset=True;m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
    before=len(m.acc_writes);m.open([0x44,28])
    assert m.reset_count==1 and m.posts[-1]==0xE4 and m.registers[0xFE]&2 and not m.ata_commands
    assert m.cpu.mem_read(0x475,1)==b'\0' and m.cpu.mem_read(m.base+0x190,1)==b'\0'
    ax,flags=m.public(0x13,0x0201,dx=0x80,cx=1,bx=0x8000)
    assert ax==0x8001 and flags&1 and m.cpu.mem_read(0x474,1)==b'\x80'
    return {'saved_disabled_ide':True,'actual_save_reset_probe':True,'bda_disk_count':0,'int13_ax':ax,'cf':True,'absent_drive_status':0x80,'error_al_preserved':1,'terminal':0xE4}


def rom_inputs(image):
    import importlib
    legacy=importlib.import_module('test-legacy-boot')
    legacy.BUILD=Path(image).parent/'external-rom-fixtures'
    def rom(index,length=4,dirty=False):return legacy.rom(index,length,dirty=dirty)
    return rom


def bootstrap_path(image,seed,inactive=False):
    import importlib
    helper=importlib.import_module('test-port');folder=Path(image).parent/'bootstrap-proof';folder.mkdir(exist_ok=True)
    source=PORT/'tests'/('core-inactive-int18.asm' if inactive else 'core-return-boot.asm')
    helper.assemble(source,folder/'provider.bin',[PORT/'tests'])
    data=bytearray((folder/'provider.bin').read_bytes());data[-1]=(-sum(data))&255
    n=seed();n[0x3C]=0 if inactive else 4;n[0x3E]=0;n[0x3F]=0;helper.repair_checksum(n)
    m=ACC(image,n);m.cpu.mem_write(0xC8000,bytes(data));m.continue_reset=True
    m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
    entry=0xF0000+m.listing.symbol('int18' if inactive else 'int19');observed=[]
    def observe(model,address):
        if m.starting and address==entry:
            active=m.cpu.mem_read(m.base+0x49,1)[0]
            chain=struct.unpack('<HH',m.cpu.mem_read(m.base+0x4C,4))
            if inactive:assert active!=0xA5
            else:assert chain[0]!=0 and chain[1]==0xC800
            observed.append({'public_entry':address,'active_before':active,'captured_chain':chain})
    m.code_observer=observe;m.open([0x44,28])
    assert observed and m.posts[-1]==0xE4 and m.cpu.mem_read(m.base+0x49,1)==b'\xA5'
    assert m.cpu.mem_read(m.base+0x48,1)==b'\x04'
    assert struct.unpack('<3H',m.cpu.mem_read(0x620,6))==((1,0,0) if inactive else (1,1,0))
    assert 'No boot device available' in m.console and 'Press any key to retry' in m.console
    return {'inactive_public_int18':inactive,'actual_discovery_provider_public_cursor_retry':observed,'provider_init':1,'provider_bootstrap':int(not inactive),'terminal':0xE4,'cursor':4}


def option_roms(image,seed):
    rom=rom_inputs(image);rows=[]
    cases={
        'empty':(),
        'one':((0xC8000,rom(0)),),
        'multiple':((0xC8000,rom(0)),(0xC9000,rom(1)),(0xD0000,rom(2,128,True))),
        'late-only':((0xD8000,rom(1)),),
    }
    covered=rom(0,16);covered[2048:4096]=rom(1);covered[-1]=0;covered[-1]=(-sum(covered))&255
    cases['covered-interior']=((0xC8000,covered),)
    interior_bad=rom(1);interior_bad[-1]^=1
    cases['video64-covered-interior']=((0xC8000,rom(0)),(0xC9000,interior_bad),(0xD0000,rom(2)))
    for kind in ('zero','checksum','extent'):
        bad=rom(0)
        if kind=='zero':bad[2]=0
        elif kind=='checksum':bad[-1]^=1
        elif kind=='extent':bad[2]=193
        cases[kind+'-then-valid']=((0xC8000,bad),(0xD8000,rom(1)))
    for name,inputs in cases.items():
        n=seed();n[0x3B]=(n[0x3B]&~0x18)|8;n[0x3D]=(-sum(n[0x38:0x3D])-n[0x10]-sum(n[0x3E:0x40]))&255
        if name=='video64-covered-interior':
            chip=bytes((0,1,1,1,0,1))+bytes(18)
            n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
        m=ACC(image,n)
        if name=='video64-covered-interior':
            m.external_video=True
            provider=bytearray(Path(image).read_bytes()[:32768])+bytearray([255])*32768
            provider[2]=128
            for address,data in inputs:
                if address<0xD0000:provider[address-0xC0000:address-0xC0000+len(data)]=data
            provider[-1]=0;provider[-1]=(-sum(provider))&255
            m.cpu.mem_write(0xC0000,bytes(provider));m.cpu.mem_write(m.base+0x1007,b'\0');m.registers[2]=0xB8
        for address,data in inputs:m.cpu.mem_write(address,bytes(data))
        m.continue_reset=True;m.stop_address=0xF0000+m.listing.symbol('.wait','boot_retry')
        scan=0xF0000+m.listing.symbol('option_rom_discovery');summary=0xF0000+m.listing.symbol('post_debug_summary');context=[];invocations=[];video_calls=[]
        regs=(x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX,x.UC_X86_REG_ESI,x.UC_X86_REG_EDI,x.UC_X86_REG_EBP,x.UC_X86_REG_ESP,x.UC_X86_REG_DS,x.UC_X86_REG_ES,x.UC_X86_REG_FS,x.UC_X86_REG_GS,x.UC_X86_REG_SS,x.UC_X86_REG_EFLAGS)
        def observer(model,address):
            if address==0xC0003:video_calls.append(address)
            if address in [location+3 for location,data in inputs]:invocations.append(address)
            if address==scan:context.append(tuple(model.cpu.reg_read(reg) for reg in regs))
            elif address==summary:
                assert context==[tuple(model.cpu.reg_read(reg) for reg in regs)],'Immediate scanner return context'
                context.append(True)
        m.code_observer=observer
        m.open([0x44,28]);assert context[-1] is True and m.posts[-1]==0xE4
        expected=(0,0,1,0) if name=='video64-covered-interior' else (1,1,1,0) if name=='multiple' else (0,1,0,0) if name=='late-only' or name.endswith('then-valid') else (1,0,0,0) if name in ('one','covered-interior') else (0,0,0,0)
        assert struct.unpack('<4H',m.cpu.mem_read(0x600,8))==expected
        wanted=[0xD0003] if name=='video64-covered-interior' else [0xC8003,0xC9003,0xD0003] if name=='multiple' else [0xD8003] if name=='late-only' or name.endswith('then-valid') else [0xC8003] if name in ('one','covered-interior') else []
        assert invocations==wanted,(name,invocations,wanted)
        assert bool(m.cpu.mem_read(m.base+0x175,1)[0]&16)==name.endswith('then-valid')
        assert m.cpu.reg_read(x.UC_X86_REG_SS)==0 and 0x6F00<=m.cpu.reg_read(x.UC_X86_REG_SP)<=0x7000
        assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x400==0
        assert m.cpu.mem_read(0x64,4)==struct.pack('<HH',m.listing.symbol('int19'),0xF000)
        if name=='video64-covered-interior':
            assert video_calls==[0xC0003] and m.cpu.mem_read(m.base+0x1007,1)==b'\0'
            assert bytes(m.cpu.mem_read(0xC0000,65536))==bytes(provider)
            assert m.registers[2]&0x23==0x20
            assert m.public(0x12,0)[0]==632 and m.public(0x15,0x8800)[0]==15360
            for vector in (0x10,0x42):
                m.public(vector,0x1130,bx=0x0600)
                assert m.cpu.reg_read(x.UC_X86_REG_ES)==0xC000 and m.cpu.reg_read(x.UC_X86_REG_BP)==m.provider_font_offset
                assert m.cpu.mem_read(0xC0000+m.provider_font_offset,4096)==(PORT/'reference/pb430-m27c1001.bin').read_bytes()[28169:32265]
        m.code_observer=None;m.call('option_rom_discovery');assert struct.unpack('<4H',m.cpu.mem_read(0x600,8))==expected
        rows.append({'name':name,'invocations':expected,'actual_ordered_entries':invocations,'complete_scan':True,'save_reset_to_retry':True,'immediate_return_context':True,'single_initialization':True,'dirty_return_restored':name=='multiple','video_extent_bytes':65536 if name=='video64-covered-interior' else 32768,'interior_video_signatures_skipped':name=='video64-covered-interior'})
    return rows
