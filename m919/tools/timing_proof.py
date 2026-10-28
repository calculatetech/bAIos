"""Exercise the compiled profile, persistence and external write-back owners."""
import binascii
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from unicorn import x86_const as x
from cache_proof import PORT, REPOSITORY, SRAM, POSTHardware, DRAM, composed, guest, dma
from geometry_proof import mapped, invoke

DOWN=0x50
RIGHT=0x4D
ENTER=28
SAVE=[0x44,ENTER]


def options(clock=1,speed=0,mode=0,l1=1,l2=1,wb=False,edo=False):
    # Independent AMI/manual expectations; do not read candidate profile tables.
    waits,burst,edoburst=(0xF0,0x20,0) if clock<2 else (0x50,0,0)
    if mode==1:waits,burst,edoburst=0,0,0
    if mode==3:waits,burst,edoburst=0xF0,0x30,2
    return bytes((waits,l1,l2,burst|(0x40 if wb else 0),0,edoburst|int(edo),0,clock,(mode<<6)|(speed<<4),0))+bytes(14)


def menu(group=0):
    return [DOWN]*4+[ENTER]+[DOWN]*group+[ENTER]


def active(fixture):
    u,d,_,s,_,_=fixture
    return d.read((u.reg_read(x.UC_X86_REG_FS)<<4)+s['C_CHIP'],24)


def put_record(d,raw):
    c=bytearray(d.saved_cmos)
    c[0x69]=0x56;c[0x6B:0x80]=raw[:21];c[0x33:0x36]=raw[21:]
    c[0x6A]=(-0x56-sum(raw))&255
    d.saved_cmos=bytes(c)


def crc():
    row,f=mapped([(16,False,False),None,None,None],expected=16,memory=SRAM(kib=64))
    u,d,listing,_,_,_=f
    vectors=[]
    for raw in (b'',b'123456789',bytes(range(256))):
        for i,value in enumerate(raw):d.write(0x20000+i,1,value)
        u.reg_write(x.UC_X86_REG_DS,0);u.reg_write(x.UC_X86_REG_ESI,0x20000);u.reg_write(x.UC_X86_REG_ECX,len(raw))
        saved_edx=u.reg_read(x.UC_X86_REG_EDX)
        invoke(f,'checksum_crc32',count=100000)
        assert u.reg_read(x.UC_X86_REG_EAX)==binascii.crc32(raw)
        assert u.reg_read(x.UC_X86_REG_ESI)==0x20000 and u.reg_read(x.UC_X86_REG_ECX)==len(raw)
        assert u.reg_read(x.UC_X86_REG_EDX)==saved_edx and u.reg_read(x.UC_X86_REG_EFLAGS)&0xFFFF==0x247
        vectors.append({'length':len(raw),'crc':f'{binascii.crc32(raw):08X}'})
    invoke(f,'cache_validation_identity',count=2000000)
    base=u.reg_read(x.UC_X86_REG_FS)<<4
    before=d.read(base+0x10A0,4)
    image=bytes(u.mem_read(0xF0000,0x10000))
    assert int.from_bytes(before,'little')==binascii.crc32(image)
    u.mem_write(0xFFE00,b'\x01')
    invoke(f,'cache_validation_identity',count=2000000)
    assert d.read(base+0x10A0,4)!=before
    return [dict(row,vectors=vectors,changed_rom_byte_rejected=True)]


class ProfileCapture(POSTHardware):
    def prepare(self,u):
        super().prepare(u)
        self.profile_cells=None

    def observe(self,u,address,size):
        if self.continuing and address in self.key_points and self.profile_cells is None:
            base=u.reg_read(x.UC_X86_REG_FS)<<4
            if tuple(self.read(base+self.state[n],1)[0] for n in ('U_PAGE','U_FOCUS','U_CHIP_SCREEN','U_FIELD'))==(5,1,1,0):
                self.profile_cells=bytes(u.mem_read(0xB8000,4000))
                for row,label in ((4,'Profiles'),(5,'Timing Profile Clock'),(6,'DRAM Speed'),(7,'Memory Timing'),(9,'Memory Access')):
                    cells=self.profile_cells[row*160+48:row*160+48+len(label)*2]
                    assert cells[::2]==label.encode(),(row,cells)
                    assert cells[1::2]==bytes([0x0B if row in (4,9) else 0x0F if row==5 else 7])*len(label),(row,cells)
                cells=self.profile_cells[5*160+98:5*160+98+12]
                assert cells[::2]==b'33 MHz' and cells[1::2]==b'\x1F'*6,cells
        super().observe(u,address,size)


def fast_restoration():
    results=[]
    row,f=mapped([(16,False,False),None,None,None],expected=16,memory=SRAM(kib=512))
    u,d,listing,s,cmos,step=f;base=u.reg_read(x.UC_X86_REG_FS)<<4
    for clock in range(4):
        for edo in (False,True):
            raw=bytearray(options(clock=clock,mode=3,l2=0,wb=True,edo=edo))
            raw[10:]=bytes((0xA5,))+bytes(13)
            for i,v in enumerate(raw):d.write(base+s['U_CHIP']+i,1,v)
            u.reg_write(x.UC_X86_REG_SI,s['U_CHIP']);invoke(f,'chipset_profile_apply')
            out=d.read(base+s['U_CHIP'],24)
            assert out==raw,out.hex()
            d.write(base+s['U_CHIP_SCREEN'],1,1);d.write(base+s['U_FIELD'],1,2)
            invoke(f,'chipset_ui_parameters')
            assert u.reg_read(x.UC_X86_REG_CX)==4
            choices=u.reg_read(x.UC_X86_REG_SI)
            names=[]
            for i in range(4):
                ptr=int.from_bytes(u.mem_read(0xF0000+choices+i*2,2),'little')
                names.append(bytes(u.mem_read(0xF0000+ptr,32)).split(b'\0')[0].decode())
            assert names==['Fast','Normal','Compatibility','Manual'],names
            results.append(dict(row,clock_mhz=(25,33,40,50)[clock],edo=edo,
                fast_tuple=out[:10].hex(),choices=names,certificate_preserved_by_apply=True))
    for edo in (False,True):
        row,f=composed(kib=512,chip=options(mode=3,l2=0,wb=True,edo=edo))
        assert row['terminal']=='POST FF' and row['enabled']
        assert active(f)[:10]==options(mode=3,l2=0,wb=True,edo=edo)[:10]
        assert 'cache_qualify' in row['post_visits']
        assert f[1].registers[0x50]&0xF0==0xF0 and f[1].registers[0x51]&0xF0==0xF0
        assert f[1].registers[0x61]&8
        results.append(dict(row,saved_fast_cold_boot=True,edo=edo))
    keys=menu()+[DOWN,DOWN]+[RIGHT]*3+SAVE
    row,f=composed(kib=512,chip=options(l2=0),keys=keys)
    saved=bytes(f[4][0x6B:0x80])+bytes(f[4][0x33:0x36])
    assert row['terminal']=='reset' and saved[:10]==options(mode=3,l2=0)[:10]
    assert f[1].keys_sent==keys
    assert any(bytes.fromhex(entry[-1])[8]&0xC0==0xC0 for entry in f[1].key_log)
    results.append(dict(row,fast_popup_selection_and_save=True))
    return results


def profiles():
    results=[]
    # Real popup/save/reload reaches each of the four independent table rows.
    for clock in range(4):
        chip=options()
        keys=menu()+[ENTER]+[0x48]+[DOWN]*clock+[ENTER]+SAVE
        row,f=composed(chip=chip,keys=keys,hardware=ProfileCapture)
        assert row['terminal']=='reset' and f[1].keys_sent==keys and not f[1].keys
        saved=bytes(f[4][0x6B:0x80])+bytes(f[4][0x33:0x36])
        assert saved[:10]==options(clock=clock)[:10],(clock,saved.hex())
        cells=f[1].profile_cells
        assert cells is not None
        reload,g=composed(memory=f[1])
        assert reload['terminal']=='POST FF' and active(g)[:10]==saved[:10]
        assert g[1].registers[0x51]&0xF0==(0xF0 if clock<2 else 0x50)
        assert g[1].registers[0x50]&0x30==(0x20 if clock<2 else 0)
        results.append(dict(row,clock_mhz=(25,33,40,50)[clock],profile_cells=cells.hex(),reload=reload))
    # Compiled profile owner covers speed fallback and all presets, not a tuple mirror.
    row,f=mapped([(16,False,False),None,None,None],expected=16,memory=SRAM(kib=64))
    u,d,_,s,_,_=f;base=u.reg_read(x.UC_X86_REG_FS)<<4
    inputs=[]
    for clock,speed,mode in ((1,0,0),(1,2,0),(2,1,0),(3,2,1),(1,1,2),(2,0,3)):
        raw=bytearray(options(clock,speed,mode,l2=0))
        raw[0]=0xA0;raw[3]=(raw[3]&0x40)|0x10;raw[5]=1
        for i,v in enumerate(raw):d.write(base+s['U_CHIP']+i,1,v)
        u.reg_write(x.UC_X86_REG_SI,s['U_CHIP']);invoke(f,'chipset_profile_apply')
        out=d.read(base+s['U_CHIP'],24)
        expected=bytes(raw) if mode==2 else options(clock,speed,mode,l2=0,edo=True)
        assert out==expected,(clock,speed,mode,out.hex(),expected.hex())
        inputs.append({'clock':clock,'speed':speed,'mode':mode,'actual':out[:10].hex()})
    results.append(dict(row,profile_inputs=inputs))
    keys=menu()+[DOWN,DOWN,RIGHT,DOWN,RIGHT,0x48,RIGHT,RIGHT,DOWN,RIGHT]+SAVE
    row,f=composed(chip=options(),keys=keys)
    saved=bytes(f[4][0x6B:0x80])+bytes(f[4][0x33:0x36])
    assert saved[:10]==options()[:10],saved.hex()
    drafts=[entry[-1] for entry in f[1].key_log]
    assert any(bytes.fromhex(v)[8]&0xC0==0xC0 for v in drafts),'Fast was never selected'
    assert any(entry[4]==5 for entry in f[1].key_log),'Preset did not skip locked raw timing rows'
    results.append(dict(row,preset_locked_navigation=True,fast_removed_after_FPM_edit=True))
    results.extend(control_categories())
    for offset,value in ((7,4),(8,0x30),(0,0x50),(10,2)):
        bad=bytearray(options());bad[offset]=value
        row,f=composed(chip=bytes(bad))
        assert row['terminal']=='reset' and not row['enabled']
        reload,g=composed(memory=f[1])
        assert reload['terminal']=='POST FF' and active(g)[:10]==options(l1=1,l2=0,wb=False)[:10]
        results.append(dict(row,invalid_option_offset=offset,invalid_option_value=value,reload=reload))
    return results


def control_categories():
    results=[]
    # One real edit reaches all hardware categories. Manual keeps selected raw values.
    raw=bytearray(options(mode=2));raw[0]=0;raw[3]=0;raw[5]=1
    keys=menu()+[RIGHT]*2+[DOWN,RIGHT,RIGHT,DOWN,DOWN,RIGHT,RIGHT,DOWN,0x4B,
                       DOWN,DOWN,RIGHT,DOWN,RIGHT,DOWN,RIGHT,1,DOWN,ENTER,
                       RIGHT,DOWN,DOWN,RIGHT,DOWN,RIGHT,RIGHT,RIGHT,DOWN,RIGHT,
                       1,DOWN,ENTER,RIGHT,DOWN,RIGHT,DOWN,RIGHT]+SAVE
    row,f=composed(chip=bytes(raw),keys=keys)
    assert row['terminal']=='reset' and f[1].keys_sent==keys and not f[1].keys
    saved=bytes(f[4][0x6B:0x80])+bytes(f[4][0x33:0x36])
    assert saved[:10]==bytes((0x90,0,1,0x70,0x90,3,1,3,0xA0,7)),saved.hex()
    parity_memory=ParityHardware(kib=64)
    parity_memory.saved_cmos=f[1].saved_cmos
    reload,g=composed(memory=parity_memory)
    r=g[1].registers
    # Disabled L2 keeps WT mode without activating the saved WB choice.
    assert not reload['enabled'] and not reload['l1']
    assert r[0x51]&0xF1==0x91 and r[0x50]&0xF0==0x30
    assert r[0x5D]&0x90==0x90 and r[0x61]&0xC8==0xC8 and r[0x5A]&0x10
    assert r[0x52]&0x80 and r[0x53]&0xC0==0xC0
    assert r[0x52]&0x7F==reload['hb52'] and r[0x53]&0x3F==reload['hb53']&0x3F
    assert r[0x61]&0x37==reload['hb61']&0x37 and r[0x5D]&0x6F==0x20
    results.append(dict(row,all_control_categories=saved[:10].hex(),reload=reload))
    return results


def ui_review():
    row,f=mapped([(16,False,False),None,None,None],expected=16,memory=SRAM(kib=64))
    u,d,listing,s,_,_=f
    base=u.reg_read(x.UC_X86_REG_FS)<<4
    code=u.reg_read(x.UC_X86_REG_CS)<<4

    def draft(raw):
        for i,value in enumerate(raw):d.write(base+s['U_CHIP']+i,1,value)

    def text(at):
        return bytes(u.mem_read(code+at,64)).split(b'\0')[0].decode('ascii')

    # Exercise both directions of the UI mapping, preserving stored bit meanings.
    cases=[]
    fields=((1,3,0,6,3),(1,4,0,4,3),(1,8,6,0,1),
            (2,0,1,0,1),(2,1,2,0,1),(2,4,4,7,1),
            (3,0,9,0,1),(3,1,9,1,1),(3,2,9,2,1))
    for group,field,offset,shift,mask in fields:
        choices=('0','1','2','3') if mask==3 else ('Enabled','Disabled')
        for value in range(len(choices)):
            raw=bytearray(options(mode=2,edo=True))
            encoded=3-value if mask==3 else value if (group,field)==(2,1) else 1-value
            raw[offset]=(raw[offset]&~(mask<<shift))|(encoded<<shift)
            draft(raw)
            d.write(base+s['U_CHIP_SCREEN'],1,group);d.write(base+s['U_FIELD'],1,field)
            invoke(f,'chipset_ui_parameters')
            assert d.read(base+s['U_CHIP_VALUE'],1)==bytes([value]),(group,field,value,d.read(base+s['U_CHIP_VALUE'],1).hex(),hex(u.reg_read(x.UC_X86_REG_AX)),hex(u.reg_read(x.UC_X86_REG_SI)))
            table=u.reg_read(x.UC_X86_REG_SI)
            assert u.reg_read(x.UC_X86_REG_CX)==len(choices)
            rendered=tuple(text(int.from_bytes(u.mem_read(code+table+i*2,2),'little')) for i in range(len(choices)))
            assert rendered==choices,(group,field,rendered)
            for selected in range(len(choices)):
                draft(raw);d.write(base+s['U_CHIP_VALUE'],1,selected)
                invoke(f,'chipset_ui_commit')
                actual=d.read(base+s['U_CHIP'],24)
                expected=bytearray(raw)
                bits=3-selected if mask==3 else selected if (group,field)==(2,1) else 1-selected
                expected[offset]=(expected[offset]&~(mask<<shift))|(bits<<shift)
                assert actual==bytes(expected),(group,field,value,selected,actual.hex(),expected.hex())
        cases.append({'group':group,'field':field,'choices':choices,'stored_bits_preserved':True})

    u.reg_write(x.UC_X86_REG_DI,s['U_CHIP']);invoke(f,'chipset_defaults')
    defaults=d.read(base+s['U_CHIP'],24)
    assert defaults[:10]==options(l1=1,l2=0,wb=False)[:10]
    invoke(f,'chipset_safe_defaults')
    safe=d.read(base+s['U_CHIP'],24)
    assert safe[1]==0 and safe[2]==1 and safe[8]==0x40 and safe[10:]==bytes(14)

    draft(options(mode=2,edo=True))
    for name,value in (('U_PAGE',5),('U_FOCUS',1),('U_CHIP_SCREEN',1),('U_FIELD',0)):
        d.write(base+s[name],1,value)
    u.reg_write(x.UC_X86_REG_DS,code>>4);u.reg_write(x.UC_X86_REG_ES,0xB800)
    invoke(f,'setup_draw',count=500000)
    cells=bytes(u.mem_read(0xB8000,4000))
    labels=((5,'Timing Profile Clock'),(6,'DRAM Speed'),(7,'Memory Timing'),
            (10,'DRAM Read Wait States'),(11,'DRAM Write Wait States'),
            (12,'DRAM Type'),(13,'EDO Burst Timing'),(14,'DRAM Refresh Rate'),(15,'Memory Parity'))
    for screen_row,label in labels:
        assert cells[screen_row*160+48:screen_row*160+48+len(label)*2:2]==label.encode(),(screen_row,label)
    assert b'Page 1  / 1' in cells[3*160:4*160:2],cells[3*160:4*160:2]
    assert cells[10*160+98:10*160+106:2]==b'0   '
    from shared.tools.vga_text import render
    output=PORT/'build/research/hardware'
    (output/'timing-review-cells.bin').write_bytes(cells)
    font=(REPOSITORY/'tools/86box/roms/video/cirruslogic/5446bv.vbi').read_bytes()[0x6E5F:0x7E5F]
    render(cells,font,output/'timing-review-memory.png')
    results=[dict(row,choices=cases,normal_defaults=defaults[:10].hex(),safe_defaults=safe[:10].hex(),memory_rows=labels)]
    saved,h=composed(kib=128,chip=options(l2=1),keys=[0x43,ENTER]+SAVE)
    record=bytes(h[4][0x6B:0x80])+bytes(h[4][0x33:0x36])
    assert saved['terminal']=='reset' and record[:10]==options(l1=1,l2=0,wb=False)[:10]
    reload,g=composed(kib=128,memory=h[1])
    assert reload['terminal']=='POST FF' and reload['enabled'] and reload['l1']
    assert active(g)[:10]==record[:10]
    assert not g[1].registers[0x50]&0x40 and g[1].registers[0x51]&1
    results.append(dict(saved,operation='F9 defaults WT save/reload/qualification',reload=reload))
    return results


class WTSequence(POSTHardware):
    def prepare(self,u):
        super().prepare(u)
        from geometry_proof import Listing
        self.pattern_entry=0xF0000+Listing(PORT/'build/hardware-tests/geometry/baios-m919.lst').symbol('.patterns','cache_qualify')

    def observe(self,u,address,size):
        if self.continuing and address==self.qualify_entry:
            self.flush_start=len(self.flush_states)
            self.write_start=len(self.writes)
        if self.continuing and address==self.pattern_entry:
            self.startup_flushes=self.flush_states[self.flush_start:]
            self.startup_writes=self.writes[self.write_start:]
            assert all(not external for _,_,external in self.startup_flushes),self.startup_flushes
            writes=[(offset,size,value) for offset,size,value in self.startup_writes if offset in (0x50,0x51)]
            assert writes==[(0x50,1,self.registers[0x50])],writes
            assert self.registers[0x50]&0xC0==0x80 and self.registers[0x51]&1
        super().observe(u,address,size)


def wt_regression():
    results=[]
    for fault in (None,0x101):
        row,f=composed(kib=64,banks=2,chip=options(l2=0),hardware=WTSequence,ordinary_fault=fault)
        if fault is None:
            assert row['terminal']=='POST FF' and row['summary']=='64 KB WT'
        else:
            detail=row['cache_failure']
            assert row['terminal']=='reset' and detail['stage']==1
            assert detail['expected']==0x55AA55AA
            mismatch=detail['expected']^detail['observed']
            assert mismatch and not mismatch&~0xFF00,detail
            assert 'Bank 0 byte 1 D8-15' in ' '.join(detail['screen'].split()),detail
            cells=bytes(f[0].mem_read(0xB8000+21*160,160))[::2]
            assert cells[3:20]==b'Expected 55AA55AA' and cells[24:37]==f'Read {detail["observed"]:08X}'.encode(),cells
            assert cells[40:52]==b'RAM 55AA55AA',cells
            registers=f[1].read(0x9E000+0x121C,2)
            assert registers[0]&0xC0==0x80 and registers[1]&0xF1==0xF1,registers.hex()
            assert cells[54:59]==f'50={registers[0]:02X}'.encode(),cells
            assert cells[61:66]==f'51={registers[1]:02X}'.encode(),cells
            assert cells[68:74]==b'Map=09',cells
        results.append(dict(row,pre_pattern_flushes=f[1].startup_flushes,pre_pattern_writes=f[1].startup_writes))
    return results


class PowerOnTags(POSTHardware):
    def prepare(self,u):
        super().prepare(u)
        self.poisoned=False
        self.poison_copybacks=0

    def l2_writeback(self,index):
        if index in self.l2_dirty:
            if not self.l2_wb():
                self.l2_dirty.remove(index)
                return
            if bytes(self.lines[index][1])==b'\xDE\xAD\xBA\xD0'*4:
                self.poison_copybacks+=1
        super().l2_writeback(index)

    def observe(self,u,address,size):
        if self.continuing:
            if self.points.get(address)=='post_ui_cache':
                phase=self.read((u.reg_read(x.UC_X86_REG_FS)<<4)+self.state['P_PHASE'],1)[0]
                if phase==1:
                    assert not self.registers[0x50]&0xC0 and self.registers[0x51]&1
            if address==self.qualify_entry and not self.poisoned:
                self.lines={i:(0,bytearray(b'\xDE\xAD\xBA\xD0'*4)) for i in range(0,self.capacity,16)}
                self.l2_dirty=set(self.lines)
                self.poisoned=True
        super().observe(u,address,size)


def wb_transition():
    results=[]
    # An unprimed WB miss can copy arbitrary SRAM back into low RAM.
    for wb in (False,True):
        d=PowerOnTags(kib=512,banks=2)
        d.registers[0x50]=0x8C|(0x40 if wb else 0)
        d.registers[0x51]=0 if wb else 1
        d.lines[0]=(0,bytearray(b'\xDE\xAD\xBA\xD0'*4));d.l2_dirty.add(0)
        d.poison_copybacks=0
        before=DRAM.read(d,0,16)
        d.external_read(0x100000,16)
        assert (DRAM.read(d,0,16)!=before)==wb
        results.append({'unprimed_mode':'WB' if wb else 'WT','poison_copybacks':d.poison_copybacks})
    for mode in (0,1):
        row,f=composed(kib=512,banks=2,chip=options(mode=mode,l2=0,wb=True),hardware=PowerOnTags)
        d=f[1]
        assert row['terminal']=='POST FF' and row['enabled'] and row['summary']=='512 KB WB'
        assert d.poisoned and not d.poison_copybacks
        assert d.qualification_policies=={(0x60 if mode==0 else 0x40,0xF0 if mode==0 else 0,0,0,0)}
        assert d.prime_reads=={'before':512*256,'after':512*256}
        results.append(dict(row,power_on_dirty_tags=True,poison_copybacks=d.poison_copybacks))
    return results


class CacheProgress(POSTHardware):
    def observe(self,u,address,size):
        if self.continuing:
            point=self.points.get(address)
            if point in ('cache_qualify','cache_validation_save'):
                cells=bytes(u.mem_read(0xB8000+7*160,160))
                assert cells[6:32:2]==b'L2 Cache Test',cells
                status=b'Testing...' if point=='cache_qualify' else b'Passed'
                assert cells[48:48+2*len(status):2]==status,cells
                assert cells[7:32:2]==b'\x0B'*13,cells
                assert not self.registers[0x50]&0x80
        super().observe(u,address,size)


def order():
    results=[]
    for chip in (options(l2=0),options(clock=3,mode=1,l2=0),options(l2=1)):
        row,f=composed(chip=chip,hardware=CacheProgress)
        visits=row['post_visits']
        assert visits.index('chipset_visible_ram_test')<visits.index('chipset_post_ram_cache')<visits.index('init_peripherals')<visits.index('chipset_late_cache')
        if chip[2]==0:
            assert visits.index('chipset_post_ram_cache')<visits.index('cache_qualify')<visits.index('init_peripherals')
            expected=(chip[3]&0x70,chip[0]|1,chip[4],((0xC0 if chip[5]&1 else 0)|(8 if chip[5]&2 else 0)),chip[6]<<4)
            assert f[1].qualification_policies=={expected},f[1].qualification_policies
        else:assert 'cache_qualify' not in visits and not f[1].qualification_policies
        assert row['enabled']==(chip[2]==0) and all(bytes.fromhex(s['l2_row'])==b' \x07'*80 for s in row['ui'])
        assert active(f)[:10]==chip[:10]
        results.append(dict(row,qualification_policy=sorted(f[1].qualification_policies)))
    from timing_boundaries import RAMDelete
    delete=RAMDelete(kib=128)
    delete.ordinary_fault=0x103
    row,f=composed(kib=128,chip=options(l2=0,wb=True),hardware=lambda **_:delete,keys=SAVE)
    assert delete.delete_sent and row['terminal']=='reset'
    assert 'setup_main' in row['post_visits'] and 'settings_save' in row['post_visits']
    assert 'chipset_post_ram_cache' not in row['post_visits']
    assert 'cache_validation_identity' not in row['post_visits'] and 'cache_qualify' not in row['post_visits']
    assert not any(active(f)[10:]),'Entering Setup certified untested L2'
    results.append(dict(row,mid_RAM_Delete_enters_Setup_before_L2=True))
    return results


def persistence():
    results=[]
    row,f=composed(kib=64,l1=1)
    d=f[1]
    assert row['enabled'] and 'cache_qualify' in row['post_visits'] and active(f)[10]==0xA5
    first_work=d.cache_interval_instructions
    repeat,g=composed(kib=64,memory=d)
    assert repeat['enabled'] and 'cache_qualify' not in repeat['post_visits'] and not any(d.coverage[n]-set(range(0x100000,0x110000,4)) for n in d.coverage)
    assert d.cache_interval_instructions<first_work
    results.append(dict(row,repeat=repeat,first_work=first_work,repeat_work=d.cache_interval_instructions))
    # Draft-only edit, unchanged save, canceled defaults and unrelated theme save.
    for name,keys in (('discard',menu()+[RIGHT,1,1,1,ENTER]),('unchanged-save',SAVE),
                      ('cancel-defaults',[0x43,1]+SAVE),('theme-save',[0x3F]+SAVE)):
        before=d.saved_cmos
        edit,h=composed(kib=64,memory=d,keys=keys)
        assert 'cache_qualify' not in edit['post_visits']
        assert bytes(h[4][0x75:0x80])+bytes(h[4][0x33:0x36])==before[0x75:0x80]+before[0x33:0x36]
        reload,j=composed(kib=64,memory=d)
        assert reload['enabled'] and 'cache_qualify' not in reload['post_visits']
        results.append(dict(edit,operation=name,reload=reload))
    # Accepted clock edit invalidates before reset; a new pass publishes success.
    edit,h=composed(kib=64,memory=d,keys=menu()+[RIGHT]+SAVE)
    assert h[4][0x75]==0
    reload,j=composed(kib=64,memory=d)
    assert reload['enabled'] and 'cache_qualify' in reload['post_visits'] and j[4][0x75]==0xA5
    results.append(dict(edit,operation='changed-memory-setting',reload=reload))
    # A changed native-discovery input disqualifies the old certificate.
    for name,change in (('RAM map',lambda: d.modules.__setitem__(0,(8,False,False))),
                        ('cache banks',lambda: setattr(d,'banks',2))):
        change()
        reload,j=composed(kib=64,memory=d)
        assert 'cache_qualify' in reload['post_visits'] and reload['enabled']
        results.append(dict(reload,operation=name))
    for name,inputs in (('CPU identity',{'cpu_signature':0xDEAD0430}),('ROM contents',{'cpu_signature':0xDEAD0430,'rom_change':True})):
        reload,j=composed(kib=64,memory=d,**inputs)
        assert 'cache_qualify' in reload['post_visits'] and reload['enabled']
        results.append(dict(reload,operation=name))
    defaults,h=composed(kib=64,memory=d,keys=[0x43,ENTER]+SAVE)
    assert h[4][0x75]==0
    reload,j=composed(kib=64,memory=d)
    assert 'cache_qualify' in reload['post_visits'] and reload['enabled']
    results.append(dict(defaults,operation='accepted-defaults',reload=reload))
    edit,h=composed(kib=64,memory=d,keys=menu()+[RIGHT]+SAVE)
    assert h[4][0x75]==0
    d.ordinary_fault=0x103
    failure,j=composed(kib=64,memory=d)
    assert failure['terminal']=='reset' and j[4][0x69]==0xD2 and not failure['enabled']
    assert not any(active(j)[10:])
    d.ordinary_fault=None
    retry,j=composed(kib=64,memory=d,keys=menu(1)+[DOWN,0x4B]+SAVE)
    assert retry['terminal']=='reset' and j[4][0x69]==0x56 and j[4][0x75]==0
    healed,j=composed(kib=64,memory=d)
    assert healed['enabled'] and 'cache_qualify' in healed['post_visits'] and j[4][0x75]==0xA5
    results.append(dict(failure,repaired_retry=retry,healed=healed))
    results.extend(crc())
    return results


def writeback():
    results=[]
    # Mode-dependent tag range: 64KiB WT covers16MiB; WB covers8MiB.
    for ram,wb,expected,mode in ((8,True,True,0),(16,True,False,0),(16,False,True,0),(16,True,False,3)):
        row,f=composed(kib=64,ram=ram,chip=options(l2=0,wb=wb,mode=mode))
        assert row['enabled']==expected and ('cache_qualify' in row['post_visits'])==expected
        if expected:assert bool(f[1].registers[0x51]&1)==(not wb)
        expected_options=options(l2=0,wb=wb)
        assert row['terminal']=='POST FF' and active(f)[:10]==expected_options[:10]
        if expected:assert f[1].qualification_policies=={(0x60 if wb else 0x20,0xF0|int(not wb),0,0,0)},f[1].qualification_policies
        results.append(dict(row,tag_bits=7 if wb else 8,ram_mib=ram,input_mode=mode,qualification_policy=sorted(f[1].qualification_policies)))
    normal,f=composed(kib=64,ram=8,chip=options(l2=0,wb=True))
    d=f[1];d.kind='absent'
    absent,g=composed(kib=64,memory=d)
    assert absent['terminal']=='POST FF' and not absent['enabled'] and active(g)[:10]==options(l2=0,wb=True)[:10]
    assert g[4][0x75]==0 and g[4][0x69]==0x56
    d.kind='real'
    restored,g=composed(kib=64,memory=d)
    assert restored['enabled'] and 'cache_qualify' in restored['post_visits']
    results.append(dict(normal,cache_removed=absent,cache_restored=restored,unrelated_settings_preserved=True))
    row,f=composed(kib=128,chip=options(l2=0,wb=True),cpu_policy='wt')
    u,d,listing,_,_,_=f
    assert row['summary']=='128 KB WB'
    old=DRAM.read(d,0x20000,4)
    guest(f,'external-dirty','mov ax,0x2000\nmov ds,ax\nmov dword [0],0xC0DEFACE')
    assert DRAM.read(d,0x20000,4)==old and d.l2_dirty
    # Evict this physical L2 index while L1 policy remains WT.
    guest(f,'external-evict','mov ax,0x5000\nmov ds,ax\nxor esi,esi\nmov cx,1025\n.evict_l1: mov eax,[esi]\nadd esi,16\nloop .evict_l1\nmov ax,0x4000\nmov ds,ax\nmov eax,[0]')
    assert DRAM.read(d,0x20000,4)==bytes.fromhex('CEFADEC0') and d.l2_copybacks,(DRAM.read(d,0x20000,4).hex(),d.l2_copybacks,d.lines.get(0),d.l2_dirty)
    guest(f,'external-warm',f'mov ax,0x2000\nmov ds,ax\nmov dword [0],0x12345678\nxor ax,ax\nmov ds,ax\ncall 0xF000:0x{listing.symbol("warm_reset"):04X}',reset=True)
    assert DRAM.read(d,0x20000,4)==bytes.fromhex('78563412')
    reload,g=composed(kib=128,memory=d)
    assert reload['enabled'] and 'cache_qualify' not in reload['post_visits']
    results.append(dict(row,dirty_external_eviction=True,warm_copyback=True,reload=reload))
    edit,h=composed(kib=128,memory=d,keys=menu(1)+[DOWN,DOWN,0x4B]+SAVE)
    assert edit['terminal']=='reset' and h[4][0x75]==0 and not h[4][0x6E]&0x40
    wt,g=composed(kib=128,memory=d)
    assert wt['summary']=='128 KB WT' and 'cache_qualify' in wt['post_visits']
    guest(g,'external-wt','mov ax,0x2000\nmov ds,ax\nmov dword [0],0x88445522')
    assert DRAM.read(d,0x20000,4)==bytes.fromhex('22554488') and not d.l2_dirty
    results.append(dict(wt,write_policy_save=edit,same_hardware_L1_WT=True,immediate_backing_publication=True))
    bad,h=composed(kib=128,chip=options(l2=0,wb=True),lost_writeback=True)
    assert bad['terminal']=='reset' and not bad['enabled'] and h[4][0x69]==0xD2
    results.append(dict(bad,lost_external_copyback_disproved=True))
    results.extend(dma(l2_wb=True))
    return results


class ParityHardware(POSTHardware):
    def prepare(self,u):
        super().prepare(u)
        from geometry_proof import Listing
        l=Listing(PORT/'build/hardware-tests/geometry/baios-m919.lst')
        self.parity_seed=0xF0000+l.symbol('.seed','chipset_parity_apply')
        self.parity_done=0xF0000+l.symbol('.seeded','chipset_parity_apply')
        self.seeding=False;self.seed_count=0;self.seed_ranges=[];self.ram_testing=False;self.ram_pattern_count=0

    def observe(self,u,address,size):
        if address==self.ram_protected:self.ram_testing=True
        if address==self.ram_done:self.ram_testing=False
        if address==self.parity_seed:
            self.seeding=True
            a=u.reg_read(x.UC_X86_REG_EDI)
            if not self.seed_ranges or self.seed_ranges[-1][1]!=a:self.seed_ranges.append([a,a])
            self.seed_ranges[-1][1]=a+4
            self.seed_count+=1
            assert self.registers[0x5A]&0x10 and self.gates[0x61]&4
        if address==self.parity_done:self.seeding=False
        super().observe(u,address,size)

    def write(self,address,size,value):
        if self.seeding and size==4 and (address<0xA0000 or address>=0x100000):
            assert value==int.from_bytes(self.read(address,size),'little'),'Parity initialization destroyed data'
            return  # Read/rewrite changes parity metadata, not the unchanged payload.
        result=super().write(address,size,value)
        if self.ram_testing:
            self.ram_pattern_count+=int(value in (0x55AA55AA,0xAA55AA55))
            self.pattern_writes.clear()
            # Sparse backing retains all changed bytes; restored initial bytes
            # need no dictionary entry or retained geometry-probe bookkeeping.
            for a in range(address,address+size):
                key=self.physical(a)
                if key is not None and self.data.get(key,self.initial(key))==self.initial(key):
                    self.data.pop(key,None);self.touched.discard(key)
        return result


def parity():
    results=[]
    for enabled,full in ((False,False),(True,False),(True,True)):
        d=ParityHardware(kib=64,ram=8)
        d.ram_escape=not full
        # Install input through the same independent CMOS format as composed().
        row,f=composed(kib=64,ram=8,chip=options(l2=1))
        edit,h=composed(kib=64,memory=f[1],keys=menu()+[DOWN]*5+([RIGHT] if enabled else [RIGHT,RIGHT])+SAVE)
        assert edit['terminal']=='reset' and h[4][0x71]==int(enabled)
        d.saved_cmos=h[1].saved_cmos
        row,g=composed(kib=64,memory=d)
        assert row['terminal']=='POST FF' and bool(d.registers[0x5A]&0x10)==enabled
        assert bool(d.gates[0x61]&4)==(not enabled)
        assert d.seed_ranges==([[0,0xA0000]] if full else [[0,0xA0000],[0x100000,0x800000]]) if enabled else not d.seed_ranges
        if full:assert active(g)[6]==1 and d.ram_pattern_count and not row['ram_escaped']
        u=d.machine
        d.gates[0x61]|=0x80
        if enabled:
            d.cpu_interrupt(u,2)
            u.emu_start((u.reg_read(x.UC_X86_REG_CS)<<4)+u.reg_read(x.UC_X86_REG_IP),0xFFFFF,count=200000)
            assert d.ports[0x80]==0xE8
            assert b'RAM parity error' in bytes(u.report_output)
        else:
            assert d.ports[0x80]==0xFF
        results.append(dict(row,setup_save=edit,parity_initialized=d.seed_ranges,full_ram_test=full,ram_pattern_writes=d.ram_pattern_count,parity_checking=enabled,terminal_parity=hex(d.ports[0x80])))
    return results


def speed():
    from shared.tools.rom import build, configuration, verify
    _,cfg=configuration(PORT)
    folder=PORT/'build/hardware-tests/cache-baseline'
    result=build(PORT,str(folder.relative_to(PORT)))
    previous=(PORT/'tests/baselines/cache.inc').read_text(encoding='utf-8')
    current=(PORT/'src/hardware/cache.inc').read_text()
    begin='%macro cache_pattern 1';end='%endmacro'
    old_macro=previous[previous.index(begin):previous.index(end,previous.index(begin))+len(end)]
    current=current[:current.index(begin)]+old_macro+current[current.index(end,current.index(begin))+len(end):]
    start=current.index('.clear:\n',current.index('cache_qualify:'))
    stop=current.index('    test bl,bl',start)
    old_start=previous.index('.clear:\n',previous.index('cache_qualify:'))
    old_stop=previous.index('    test bl,bl',old_start)
    current=current[:start]+previous[old_start:old_stop]+current[stop:]
    overlay=folder/'hardware';overlay.mkdir(exist_ok=True)
    (overlay/'cache.inc').write_text(current)
    image=Path(result['path'])
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    subprocess.run([nasm,'-w+error','-f','bin','-I',str(folder)+'/', '-I',str(PORT/'src')+'/',
                    '-I',str(REPOSITORY/'shared/src')+'/', '-l',str(image.with_suffix('.lst')),
                    '-o',str(image),str(PORT/'src/bios.asm')],check=True)
    raw=bytearray(image.read_bytes());at=cfg['rom']['checksum_offset'];raw[at]=0;raw[at]=(-sum(raw))&255;image.write_bytes(raw)
    verify(PORT,image)
    results=[]
    expected=set(range(0x100000,0x180000,4))
    for name,rom in (('baseline',image),('candidate',None)):
        d=SRAM(kib=512)
        row,f=mapped(d.modules,expected=16,memory=d,rom_image=rom)
        d.cache_interval_instructions=0
        invoke(f,'cache_qualify',count=30000000)
        base=f[0].reg_read(x.UC_X86_REG_FS)<<4
        assert d.read(base+0x1038,1)==b'\x01'
        assert all(v==expected for v in d.coverage.values())
        assert DRAM.read(d,0x100000,0x80000)==bytes(0x80000)
        results.append(dict(row,name=name,instructions=d.cache_interval_instructions,coverage={k:len(v) for k,v in d.coverage.items()}))
    assert results[1]['instructions']<results[0]['instructions']
    results[1]['instruction_ratio']=results[1]['instructions']/results[0]['instructions']
    return results


CASES={'timing-settings':profiles,'timing-review':ui_review,'timing-controls':control_categories,'timing-order':order,'cache-wt-regression':wt_regression,'cache-wb-transition':wb_transition,'cache-persistence':persistence,'cache-writeback':writeback,'timing-crc':crc,'timing-parity':parity,'cache-speed':speed,'fast-restoration':fast_restoration}


def check(case):
    result={'cases':CASES[case]()}
    sources=('m919/port.json','m919/tools/timing_proof.py','m919/tools/cache_proof.py','m919/tools/geometry_proof.py',
             'm919/src/hardware/cache.inc','m919/src/hardware/chipset-core.inc','m919/src/hardware/timing.inc',
             'm919/src/hardware/cache-validation.inc','m919/src/hardware/chipset-data.inc','m919/src/hardware/chipset-ui.inc',
             'shared/src/setup/enum-ui.inc','shared/src/pc/crc32.inc','shared/src/firmware/bios.asm')
    result['source_sha256']={p:hashlib.sha256((REPOSITORY/p).read_bytes()).hexdigest() for p in sources}
    target=PORT/'build/research/hardware'/f'{case}.json'
    target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{case}: {len(result["cases"])} cases PASS; {target}',flush=True)
    return result


if __name__=='__main__':check(sys.argv[1])
