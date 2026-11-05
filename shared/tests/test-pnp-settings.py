"""Execute the production settings owners against physical RTC/NVRAM adapters."""
import argparse
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys

from unicorn import (Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_INTR,
                     UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE)
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.tools.ram_proof import Listing, constants

PAYLOAD_INDICES=list(range(0x40,0x69))+list(range(0x6A,0x80))+[0x11,0x13,0x2D]


def at_checksum(cmos):
    assert sum(cmos[0x10:0x2E])==(cmos[0x2E]<<8 | cmos[0x2F]),'AT checksum'


def check_mutation(port,before,after,writes,owner):
    logical=set(PAYLOAD_INDICES)|{0x33,0x34,0x35,0x0E,0x2E,0x2F}
    if owner in ('settings_save','setup_main'):
        logical|={0x10,0x36,0x69}|set(range(0x38,0x40))
    if owner=='settings_recovery_publish':logical={0x69}
    if owner=='recovery_continuation':logical={0x0F,0x36,0x69}
    allowed={('nvram',0x200+i-0x40) if port=='mp386' and i>=0x40 else ('cmos',i)
             for i in logical}
    assert all((kind,at) in allowed for kind,at,value in writes),(owner,writes)
    for kind,index in (('cmos',0),('nvram',1)):
        assert len(before[index])==len(after[index])
        assert all(a==b or (kind,at) in allowed for at,(a,b) in enumerate(zip(before[index],after[index]))),owner
    if writes:at_checksum(after[0])


def failure_branch(listing,owner):
    """Return the actual JNC immediately after this owner's runtime RAM checker."""
    start=listing.row(owner)
    row=next(i for i in range(start,len(listing.lines)) if 'call chipset_runtime_ram_check' in listing.lines[i])
    line=next(line for line in listing.lines[row+1:] if re.match(r'\s*\d+\s+[0-9A-F]{8}\s+[0-9A-F]',line))
    assert 'jnc ' in line,line
    return int(re.match(r'\s*\d+\s+([0-9A-F]{8})',line)[1],16)


class Settings:
    def __init__(self, port, build_directory='build/tests/pnp-settings'):
        self.port = port
        build = ROOT / port / build_directory
        self.image = build / ('baios-presario800-system.rom' if port == 'presario-800' else f'baios-{port}.bin')
        self.listing = Listing(self.image.with_suffix('.lst'))
        self.state = constants(ROOT / 'shared/src/pc/state.inc')
        self.state.update(constants(ROOT / 'shared/src/setup/layout.inc'))
        self.state.update(C_IDE=0xA00 if port == 'm919' else 0x190,
                          U_IDE=0xA40 if port == 'm919' else 0x1B0)
        self.cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        self.cpu.mem_map(0, 0x200000)
        raw = self.image.read_bytes()
        self.cpu.mem_write(0x100000-len(raw), raw)
        self.base = 0x80000
        self.allocated = 1024 if port == 'presario-800' else 8192
        self.cpu.mem_write(0x40E, struct.pack('<H', self.base >> 4))
        self.cmos, self.nvram = bytearray(128), bytearray(0x10000)
        self.cmos[0xD], self.cmos[0xB], self.cmos[0x32] = 0x80, 2, 0x20
        self.cmos[7:10] = bytes((1,1,0x26))
        self.index = self.phase = self.nvindex = 0
        self.nvread = False
        self.writes, self.keys = [], []
        self.fail = None
        self.reset = False
        self.screen = []
        self.pit = 0xFFFF
        self.pit_byte = 0
        self.cpu.hook_add(UC_HOOK_INSN, self.inp, None, 1, 0, x.UC_X86_INS_IN)
        self.cpu.hook_add(UC_HOOK_INSN, self.out, None, 1, 0, x.UC_X86_INS_OUT)
        self.cpu.hook_add(UC_HOOK_INTR, self.interrupt)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.bounds)

    def bounds(self, cpu, access, address, size, value, _):
        assert not self.base+self.allocated <= address < self.base+0x2000, ('EBDA overflow',hex(address))

    def inp(self, cpu, port, size, _):
        if port == 0x40:
            value = self.pit >> (8*self.pit_byte) & 255
            self.pit_byte ^= 1
            if not self.pit_byte:
                self.pit = (self.pit-0x1000) & 65535
            return value
        if port == 0x48:
            if self.phase == 0:
                return 0
            assert self.phase == 3
            self.nvread = True
            return self.nvram[self.nvindex]
        if port == 0x71:
            return self.cmos[self.index]
        return 0

    def out(self, cpu, port, size, value, _):
        if port == 0x48:
            if self.phase == 0:
                self.nvread = False
            elif self.phase == 1:
                self.nvindex = value << 8
            elif self.phase == 2:
                self.nvindex |= value
            else:
                if not self.nvread:
                    self.writes.append(('nvram', self.nvindex, value))
                    if self.fail != ('nvram', self.nvindex):
                        self.nvram[self.nvindex] = value
            self.phase = (self.phase+1) % 4
        elif port == 0x70:
            self.index = value & 127
        elif port == 0x71:
            self.writes.append(('cmos', self.index, value))
            if self.fail != ('cmos', self.index):
                self.cmos[self.index] = value

    def interrupt(self, cpu, vector, _):
        if vector == 0x10:
            return # External VGA provider; text cells are real firmware writes.
        if vector == 0x1A:
            flags = cpu.reg_read(x.UC_X86_REG_EFLAGS)
            sp = cpu.reg_read(x.UC_X86_REG_SP)-6
            segment = cpu.reg_read(x.UC_X86_REG_SS)<<4
            cpu.mem_write(segment+sp,struct.pack('<HHH',cpu.reg_read(x.UC_X86_REG_IP),
                                                cpu.reg_read(x.UC_X86_REG_CS),flags & 65535))
            cpu.reg_write(x.UC_X86_REG_SP,sp)
            cpu.reg_write(x.UC_X86_REG_EFLAGS,flags & ~0x300)
            cpu.reg_write(x.UC_X86_REG_CS,0xF000)
            cpu.reg_write(x.UC_X86_REG_IP,self.listing.symbol('RTC_INTERRUPT_LABEL'))
            return
        assert vector == 0x16, vector
        ax = cpu.reg_read(x.UC_X86_REG_AX)
        if ax >> 8 == 1:
            flags = cpu.reg_read(x.UC_X86_REG_EFLAGS)
            cpu.reg_write(x.UC_X86_REG_EFLAGS, flags & ~64 if self.keys else flags | 64)
        else:
            assert self.keys, 'unexpected keyboard wait'
            self.screen.append(bytes(cpu.mem_read(0xB8000,4000))[::2])
            cpu.reg_write(x.UC_X86_REG_AX, self.keys.pop(0))

    def call(self, name, **registers):
        cpu = self.cpu
        values=dict(CS=0xF000, DS=0xF000, ES=0xB800, FS=self.base >> 4,
                    SS=0, SP=0x7000, EFLAGS=0x202)
        values.update(registers)
        for reg, value in values.items():
            cpu.reg_write(getattr(x, 'UC_X86_REG_'+reg), value)
        cpu.mem_write(0x7000, b'\xff\xff')
        before=self.snapshot()
        write_start=len(self.writes)
        try:
            cpu.emu_start(0xF0000+self.listing.symbol(name), 0xFFFFF, count=20000000 if name in ('setup_main','pnp_resource_next','pnp_census','pnp_post_invoke') else 2000000)
        finally:
            if name in ('settings_save','setup_main','ide_settings_save','ports_settings_save',
                        'chipset_settings_save','settings_recovery_publish'):
                self.check_mutation(before,self.writes[write_start:],name)
        assert cpu.reg_read(x.UC_X86_REG_IP) == 0xFFFF, (name, hex(cpu.reg_read(x.UC_X86_REG_IP)))
        return not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1

    def check_mutation(self,before,writes,owner):
        check_mutation(self.port,before,self.snapshot(),writes,owner)

    def get(self, name, size=1):
        return bytes(self.cpu.mem_read(self.base+self.state[name], size))

    def put(self, name, data):
        self.cpu.mem_write(self.base+self.state[name], bytes(data))

    def logical(self, at):
        return self.nvram[0x200+at-0x40] if self.port == 'mp386' and at >= 0x40 else self.cmos[at]

    def snapshot(self):
        return bytes(self.cmos), bytes(self.nvram)

    def draft(self):
        for active, draft, size in [('C_IDE','U_IDE',51 if self.port=='m919' else 25),
                                    ('C_PORTS','U_PORTS',8),('C_CHIP','U_CHIP',24),('C_PNP','U_PNP',15)]:
            self.put(draft, self.get(active,size))

    def ui(self, keys):
        self.keys = list(keys)
        self.reset = False
        def reset(cpu,address,size,_):
            self.reset=True
            cpu.emu_stop()
        at=0xF0000+self.listing.symbol('warm_reset')
        hook=self.cpu.hook_add(UC_HOOK_CODE,reset,None,at,at)
        try:
            try:
                self.call('setup_main')
            except AssertionError:
                if not self.reset:
                    raise
        finally:
            self.cpu.hook_del(hook)
        assert not self.keys, self.keys


def migration(port):
    fixture = json.loads((Path(__file__).parent/'fixtures/pnp-legacy-settings.json').read_text())['ports'][port]
    expected = {key:bytes.fromhex(value) for key,value in fixture['expected'].items()}
    new=Settings(port)
    new.cmos[:]=bytes.fromhex(fixture['cmos'])
    new.nvram[0x200:0x240]=bytes.fromhex(fixture['nvram_0200_023f'])
    before=new.snapshot()
    new.call('settings_load')
    assert new.snapshot()==before and not new.writes
    for key,value in expected.items():
        assert new.get(key,len(value))==value,(port,key)
    new.call('setup_defaults')
    new.draft()
    # Base settings are explicitly preserved by the real complete Save as well.
    new.put('U_BOOT',b'\x02')
    new.put('U_BOOT_THIRD',b'\x03')
    assert new.call('settings_save')
    new.call('settings_load')
    for key,value in expected.items():
        assert new.get(key,len(value))==value,(port,key,'after migration')
    assert new.get('C_PNP',15)==bytes(15),'empty reservation migration'
    allowed=set(range(0x33,0x36))|set(range(0x38,0x40))|{0x10,0x11,0x13,0x2D,0x2E,0x2F,0x0E,0x36}
    assert all((kind=='nvram' and 0x200<=at<0x240) or
               (kind=='cmos' and (at in allowed or port!='mp386' and 0x40<=at<=0x7F))
               for kind,at,value in new.writes)
    return new,expected


def ui_checks(s):
    down,right,enter,esc,tab=0x5000,0x4D00,13,27,9
    s.cpu.mem_write(s.base+0x27A,b'\x03\x02\x02')
    s.cpu.mem_write(s.base-16,b'BEFORE-PNP-STATE')
    s.cpu.mem_write(s.base+s.allocated,b'AFTER-PNP-STATE!')
    def edit(text):
        return [enter]+list(map(ord,text))+[enter]
    keys=[down]*5+[tab,enter]+[down]*7+[right,esc]
    keys+=[down,enter]+[down]*7+[enter,right,enter,0x3B00,esc,esc]
    keys+=[down,enter]+[down]*7+[right,esc]
    keys+=[down,enter]+edit('65535')+[down]+edit('2')+[esc]+edit('1')
    keys+=[down]+edit('768')+[down]+edit('0')+[esc]
    keys+=[down,enter]+[down]*11+[right,esc]
    keys+=[down,enter,right,enter,down,enter,right,enter,0x4400,enter]
    s.ui(keys)
    assert s.reset
    expected=struct.pack('<HBHHHHHBB',0x8080,0x80,65535,1,768,0,0x800,1,1)
    s.call('settings_load')
    assert s.get('C_PNP',15)==expected,s.get('C_PNP',15).hex()
    assert s.cpu.mem_read(s.base+0x27A,3)==b'\x03\x02\x02','Setup changed live APM state'
    assert s.cpu.mem_read(s.base-16,16)==b'BEFORE-PNP-STATE'
    assert s.cpu.mem_read(s.base+s.allocated,16)==b'AFTER-PNP-STATE!'
    # Last IRQ is a real rendered/navigated row, above the shared help panel.
    assert any(b'IRQ 15' in screen[12*80:13*80] for screen in s.screen)
    assert any(b'EC000h (16 KiB)' in screen[16*80:17*80] for screen in s.screen)
    assert any(b'Available (Default)' in screen and b'Reserved' in screen for screen in s.screen)
    saved=s.snapshot()
    s.writes.clear()
    # Discard a changed pending-clear draft; the persisted request must survive.
    s.ui([down]*5+[tab]+[down]*6+[0x4B00,esc,esc,enter])
    assert not s.reset and s.snapshot()==saved and not s.writes
    s.ui([down]*5+[tab,0x4300,enter,esc,esc,enter])
    assert s.get('U_PNP',15)==bytes(15)
    assert not s.reset and s.snapshot()==saved and not s.writes
    assert s.cpu.mem_read(s.base+0x27A,3)==b'\x03\x02\x02'
    # Reopen the real menu, change only clock display, and perform another F10.
    s.ui([tab,down,down,right,0x4400,enter])
    assert s.reset
    s.call('settings_load')
    assert s.get('C_PNP',15)==expected
    # Release one saved resource through the same real choice/commit/save owner.
    s.ui([down]*5+[tab,down,enter]+[down]*7+[0x4B00,0x4400,enter])
    s.call('settings_load')
    expected=bytes((0x80,0))+expected[2:]
    assert s.get('C_PNP',15)==expected
    groups=[['IRQ 0-7','IRQ 8-15','DMA Reservations','I/O Windows','Upper Memory','Configuration','Clear ESCD on Reset'],
            *[[f'IRQ {i}' for i in range(start,start+8)] for start in (0,8)],
            [f'DMA {i}' for i in range(8)],
            ['Window 1 Base','Window 1 Length','Window 2 Base','Window 2 Length'],
            [f'{0xC0000+i*0x4000:X}h (16 KiB)' for i in range(12)]]
    rendered=[]
    for screen in s.screen:
        if b'Plug and Play' in screen[3*80:4*80]:
            rendered.append([screen[row*80+24:row*80+48].strip().decode('ascii')
                             for row in range(5,22) if screen[row*80+24:row*80+48].strip()])
    assert all(group in rendered for group in groups),[group for group in groups if group not in rendered]
    choices=[[b'Available (Default)',b'Reserved'],[b'BIOS (Default)',b'Operating System'],
             [b'Keep (Default)',b'Request']]
    popups=[[screen[row*80+26:row*80+78].strip() for row in range(10,22)
             if screen[row*80+26:row*80+78].strip()] for screen in s.screen]
    assert all(values in popups for values in choices),'PnP choice order/count/identity'
    failed=Settings(s.port,str(s.image.parent.relative_to(ROOT/s.port)))
    failed.cmos[:],failed.nvram[:]=s.snapshot()
    failed.call('settings_load')
    failed.fail=('cmos',0x3B)
    failed.ui([tab,down,down,right,0x4400,enter,esc,esc,enter])
    assert not failed.reset
    assert any(b'CMOS verification failed.' in screen[19*80:20*80] for screen in failed.screen)
    return expected


def startup_checks(port,cmos_hex,nv_hex,pnp_hex):
    """Reuse the established board hardware seams; execute reset to saved policy."""
    import importlib
    sys.path.insert(0,str(ROOT/port/'tools'))
    image=ROOT/port/'build/tests/pnp-settings'/('baios-presario800-system.rom' if port=='presario-800' else f'baios-{port}.bin')
    saved=bytes.fromhex(cmos_hex)
    expected_pnp=bytes.fromhex(pnp_hex)
    assert len(expected_pnp)==15
    indices=list(range(0x40,0x69))+list(range(0x6A,0x80))+[0x11,0x13,0x2D]
    if port=='mp386':
        fixture=importlib.import_module('fixture')
        m=fixture.Tiger(image,cache=True)
        m.cmos[:]=saved
        m.nvram[0x200:0x240]=bytes.fromhex(nv_hex)
        oem=bytes(m.nvram[0x240:])
        payload=bytes(m.nvram[0x200:0x229]+m.nvram[0x22A:0x240])+bytes(saved[i] for i in (0x11,0x13,0x2D))
        stop=0xF0000+m.symbol('chipset_apply')
        seen=[]
        def observe(mm,address):
            if address==stop:
                seen.append(True)
                mm.cpu.emu_stop()
        m.code_observer=observe
        for warm in (False,True):
            if warm:
                m.sys_flag=4
                m.seed_physical(0,0x472,b'\x34\x12')
            try:m.boot(warm=warm,count=5000000)
            except AssertionError as error:
                assert error.args[0][0]=='no signed boot' and len(seen)==1+warm,str(error)
            else:raise AssertionError('startup did not reach the selected policy boundary')
            assert bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
            assert bytes(m.nvram[0x240:])==oem
            assert bytes(m.nvram[0x200:0x229]+m.nvram[0x22A:0x240])+bytes(m.cmos[i] for i in (0x11,0x13,0x2D))==payload
        m.cmos[0x36]=0xAB # An interrupted actual timing trial, consumed by reset.
        try:m.boot(warm=True,count=5000000)
        except AssertionError as error:
            assert error.args[0][0]=='no signed boot' and len(seen)==3,str(error)
        assert m.nvram[0x229]==0xD2
        assert bytes(m.nvram[0x200:0x229]+m.nvram[0x22A:0x240])+bytes(m.cmos[i] for i in (0x11,0x13,0x2D))==payload
        assert bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
        assert bytes(m.cpu.mem_read(m.base+0x60,3))==bytes((0,1,0xA4))
        # The visible RAM owner's already-detected failure continuation is separate
        # from the interrupted timing-trial producer above.
        m.cmos[:]=saved
        m.nvram[0x200:0x240]=bytes.fromhex(nv_hex)
        m.cmos[0x36]=0
        before=(bytes(m.cmos),bytes(m.nvram))
        trace=(len(m.writes),len(m.nv_writes))
        m.running=True
        m.reset_pending=False
        for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_DS,0),
                          (x.UC_X86_REG_FS,m.segment),(x.UC_X86_REG_SS,0),
                          (x.UC_X86_REG_ESP,0x7000),(x.UC_X86_REG_EFLAGS,2)):
            m.cpu.reg_write(reg,value)
        m.cpu.emu_start(0xF0000+m.symbol('.retry','chipset_visible_ram_test'),0xFFFFF,count=5000000)
        assert m.reset_pending and m.nvram[0x229]==0xD2
        check_mutation(port,before,(bytes(m.cmos),bytes(m.nvram)),
                       [('cmos',a,v) for a,v in m.writes[trace[0]:]]+
                       [('nvram',a,v) for a,v in m.nv_writes[trace[1]:]],'recovery_continuation')
        try:m.boot(warm=True,count=5000000)
        except AssertionError as error:
            assert error.args[0][0]=='no signed boot' and len(seen)==4,str(error)
        assert bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
        assert bytes(m.cpu.mem_read(m.base+0x60,3))==bytes((0,1,0xA4))
        assert bytes(m.nvram[0x200:0x229]+m.nvram[0x22A:0x240])+bytes(m.cmos[i] for i in (0x11,0x13,0x2D))==payload
        return {'cold_and_warm_policy':True,'oem_nvram_preserved':True,
                'actual_interrupted_trial_producer_and_early_safe_selection':True,
                'visible_ram_failure_continuation_reset_and_safe_selection':True}
    if port=='pb430':
        timing=importlib.import_module('test-timing-setup')
        m=timing.model(image)
        m.cmos[:]=saved
        m.stop_address=0xF0000+m.listing.symbol('chipset_apply')
        payload=bytes(m.cmos[i] for i in indices)
        m.cold_boot()
        assert bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
        m.sys_flag=4
        m.cpu.mem_write(0x472,b'\x34\x12')
        m.reset_pending=True
        m.complete_reset()
        assert bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
        assert payload==bytes(m.cmos[i] for i in indices)
        # The real advanced-timing owner publishes37; NV6 never aliases it.
        m=timing.model(image)
        m.cmos[:]=saved
        m.call('settings_load')
        for at,value in timing.BASE.items():m.registers[at]=value
        m.cpu.mem_write(m.base+0x1005,b'\x01\x01')
        chip=bytearray(m.cpu.mem_read(m.base+0x60,24))
        chip[14]=2
        chip[22]|=0x0A
        m.cpu.mem_write(m.base+0x60,bytes(chip))
        m.call('chipset_memory_policy')
        cookie=m.cmos[0x37]
        assert cookie&0xF0==0xB0,hex(cookie)
        m.cpu.mem_write(m.base+0x1B0,bytes(m.cpu.mem_read(m.base+0x190,25)))
        before=(bytes(m.cmos),b'')
        trace=len(m.writes)
        m.call('ide_settings_save')
        check_mutation(port,before,(bytes(m.cmos),b''),[('cmos',a,v) for a,v in m.writes[trace:]],'ide_settings_save')
        assert m.cmos[0x37]==cookie
        timing.restore(m)
        assert m.cmos[0x37]==0 and payload==bytes(m.cmos[i] for i in indices)
        patterned,failed,restarted=[],[],[]
        def write_pattern(cpu,access,address,size,value,unused):
            if value==0x55AA55AA:patterned.append(True)
        def read_fault(cpu,access,address,size,value,unused):
            if patterned and not failed:
                cpu.mem_write(address,bytes(4))
                failed.append(True)
        terminal=0xF0000+m.listing.symbol('controlled_defaults_restart')
        def observe(mm,address):
            if address==terminal:
                restarted.append(True)
                mm.cpu.emu_stop()
        hooks=[m.cpu.hook_add(UC_HOOK_MEM_WRITE,write_pattern,begin=0x10000,end=0x10003),
               m.cpu.hook_add(UC_HOOK_MEM_READ,read_fault,begin=0x10000,end=0x10003)]
        m.code_observer=observe
        m.script=[0x20]
        m.cmos[0x36]=0xAB
        # restore() deliberately proves an arbitrary high ESP in its stackless window.
        m.cpu.reg_write(x.UC_X86_REG_ESP,0x7000)
        m.registers[4]&=0xFE # The production visible RAM owner runs before L2 activation.
        before=(bytes(m.cmos),b'')
        trace=len(m.writes)
        try:
            try:m.call('chipset_visible_ram_test',count=2000000)
            except AssertionError:assert restarted
        finally:
            for hook in hooks:m.cpu.hook_del(hook)
            m.code_observer=None
        assert failed and restarted and m.cmos[0x69]==0xD2
        check_mutation(port,before,(bytes(m.cmos),b''),[('cmos',a,v) for a,v in m.writes[trace:]],'recovery_continuation')
        assert payload==bytes(m.cmos[i] for i in indices)
        m.stop_address=0xF0000+m.listing.symbol('chipset_apply')
        m.continue_reset=True
        m.call('controlled_defaults_restart')
        assert bytes(m.cpu.mem_read(m.base+0x60,3))==bytes((0,1,0))
        assert bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
        return {'cold_and_warm_policy':True,'advanced_cookie_preserved_and_restored':True,
                'actual_ram_failure_producer_reset_and_early_safe_selection':True}
    if port=='presario-800':
        os.environ['BAIOS_BUILD_DIRECTORY']='build/tests/pnp-settings'
        chipset=importlib.import_module('test-chipset')
        m=chipset.Chipset()
        m.cmos[:]=saved
        m.call('chipset_settings_load')
        chip=m.record()
        payload=bytes(m.cmos[i] for i in indices)
        m.chipset[0x24]|=0x40
        m.startup(reset=True,before_notice=True,expected_record=chip)
        assert m.cmos[0x37]==0xE0,hex(m.cmos[0x37])
        assert bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
        m.warm=True
        m.startup(before_notice=True,expected_record=chip)
        assert m.cmos[0x37]==0xE0
        assert bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
        # Enter the actual stackless failure continuation after its RAM compare.
        listing=Listing(image.with_suffix('.lst'))
        begin=0xF0000+listing.symbol('.real','chipset_ram_test')
        end=0xF0000+listing.symbol('.controlled_restart','startup')
        for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_EDI,1),
                          (x.UC_X86_REG_EDX,0),(x.UC_X86_REG_EFLAGS,2)):
            m.cpu.reg_write(reg,value)
        memory=[]
        before=(bytes(m.cmos),b'')
        trace=len(m.writes)
        m.starting=True
        m.delayed=False
        hook=m.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE,
                            lambda c,a,p,z,v,u:memory.append(p) if not 0xF0000<=p<0x100000 else None)
        try:m.cpu.emu_start(begin,end,count=1000000)
        finally:
            m.cpu.hook_del(hook)
            m.starting=False
        assert m.cpu.reg_read(x.UC_X86_REG_IP)==end-0xF0000
        assert not memory,'stackless producer acquired a RAM/stack read or write'
        assert m.cmos[0x69]==0xD2 and payload==bytes(m.cmos[i] for i in indices)
        check_mutation(port,before,(bytes(m.cmos),b''),[('cmos',a,v) for a,v in m.writes[trace:]],'recovery_continuation')
        m.startup(entry='.controlled_restart',before_notice=True,expected_record=chipset.RECOVERY)
        assert m.record()==chipset.RECOVERY and m.cmos[0x37]==0xE0
        assert bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
        assert payload==bytes(m.cmos[i] for i in indices)
        strap=m.cmos[0x37]
        m.cmos[:]=saved
        m.cmos[0x37]=strap
        m.cmos[0x36]=0
        before=(bytes(m.cmos),b'')
        trace=len(m.writes)
        for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_DS,0),
                          (x.UC_X86_REG_FS,m.segment),(x.UC_X86_REG_SS,0),
                          (x.UC_X86_REG_ESP,0x7000),(x.UC_X86_REG_EFLAGS,3)):
            m.cpu.reg_write(reg,value)
        begin=0xF0000+failure_branch(listing,'chipset_late_cache')
        end=0xF0000+listing.symbol('controlled_defaults_restart')
        m.cpu.emu_start(begin,end,count=1000000)
        assert m.cpu.reg_read(x.UC_X86_REG_IP)==end-0xF0000 and m.cmos[0x69]==0xD2
        check_mutation(port,before,(bytes(m.cmos),b''),[('cmos',a,v) for a,v in m.writes[trace:]],'recovery_continuation')
        m.startup(entry='controlled_defaults_restart',before_notice=True,expected_record=chipset.RECOVERY)
        assert m.record()==chipset.RECOVERY and bytes(m.cpu.mem_read(m.base+0x300,15))==expected_pnp
        assert m.cmos[0x37]==strap
        assert payload==bytes(m.cmos[i] for i in indices)
        return {'cold_and_warm_policy':True,'cold_strap_and_warm_reuse':True,
                'stackless_producer_and_early_compatibility_restart':True,
                'late_cache_runtime_failure_continuation_restart_and_safe_selection':True}
    if port=='m919':
        cache=importlib.import_module('cache_proof')
        geometry=importlib.import_module('geometry_proof')
        class Hardware(cache.POSTHardware):
            def outgoing(self,cpu,port,size,value):
                if port==0x71:
                    self.pnp_writes.append(('cmos',self.ports.get(0x70,0)&127,value))
                super().outgoing(cpu,port,size,value)
            def observe(self,cpu,address,size):
                if address==getattr(self,'policy_stop',None):
                    self.policy_seen=True
                    cpu.emu_stop()
                    return
                super().observe(cpu,address,size)
        d=Hardware(kib=64,ram=4)
        d.rom_image=image
        d.initial_cmos=saved
        d.keys=[]
        d.points={}
        d.ui_returns=[]
        d.pnp_writes=[]
        payload=bytes(saved[i] for i in indices)
        for warm in (False,True):
            d.continuing=False
            d.policy_seen=False
            if warm:d.write(0x472,2,0x1234)
            _,fixture=geometry.mapped(d.modules,expected=4,memory=d,rom_image=image)
            cpu,d,listing,state,cmos,step=fixture
            d.state=state
            d.policy_stop=0xF0000+listing.symbol('chipset_apply')
            d.continuing=True
            step.execute(0xF0000+cpu.reg_read(x.UC_X86_REG_IP),0xFFFFF,5000000)
            assert d.policy_seen
            base=cpu.reg_read(x.UC_X86_REG_FS)<<4
            assert d.read(base+0x300,15)==expected_pnp
            assert payload==bytes(cmos[i] for i in indices)
            d.initial_cmos=bytes(cmos)
        from shared.tools.ram_proof import run as ram_run
        cfg=json.loads((ROOT/'m919/port.json').read_text())
        proof=ram_run(image,cfg['rom'],state,kib=1025,fault=(0x10000,'first'),
                      coverage=False,cmos_seed=bytes(cmos),through_restart=True)
        d.initial_cmos=bytes.fromhex(proof['cmos_after'])
        assert payload==bytes(d.initial_cmos[i] for i in indices)
        d.continuing=False
        d.policy_seen=False
        _,fixture=geometry.mapped(d.modules,expected=4,memory=d,rom_image=image)
        cpu,d,listing,state,cmos,step=fixture
        d.continuing=True
        step.execute(0xF0000+cpu.reg_read(x.UC_X86_REG_IP),0xFFFFF,5000000)
        base=cpu.reg_read(x.UC_X86_REG_FS)<<4
        assert d.policy_seen and d.read(base+0x61,2)==b'\x00\x01'
        assert d.read(base+0x300,15)==expected_pnp
        continuations=[]
        for owner in ('chipset_post_ram_cache','cache_recovery'):
            d.initial_cmos=saved
            d.continuing=False
            d.policy_seen=False
            _,fixture=geometry.mapped(d.modules,expected=4,memory=d,rom_image=image)
            cpu,d,listing,state,cmos,step=fixture
            d.continuing=True
            step.execute(0xF0000+cpu.reg_read(x.UC_X86_REG_IP),0xFFFFF,5000000)
            base=cpu.reg_read(x.UC_X86_REG_FS)<<4
            before=(bytes(cmos),b'')
            trace=len(d.pnp_writes)
            d.qualifying=False
            d.policy_stop=None # The failure continuation itself applies safe timing.
            d.queue.append(0x20)
            d.reset_requests.clear()
            d.write(base+state['P_PHASE'],1,0)
            d.write(base+0x1218,1,2)
            for at,value in ((0x1208,0x100000),(0x1210,0x55AA55AA),(0x1214,0xAA55AA55)):
                d.write(base+at,4,value)
            for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_DS,0),
                              (x.UC_X86_REG_FS,base>>4),(x.UC_X86_REG_SS,0),
                              (x.UC_X86_REG_ESP,0x7000),(x.UC_X86_REG_EFLAGS,3),
                              (x.UC_X86_REG_CR0,0x60000010)):
                cpu.reg_write(reg,value)
            entry=failure_branch(listing,owner) if owner=='chipset_post_ram_cache' else listing.symbol(owner)
            step.execute(0xF0000+entry,0xFFFFF,5000000)
            assert d.reset_requests==[0xFE] and cmos[0x69]==0xD2,owner
            check_mutation(port,before,(bytes(cmos),b''),d.pnp_writes[trace:],'recovery_continuation')
            d.initial_cmos=bytes(cmos)
            d.continuing=False
            d.policy_seen=False
            d.policy_stop=0xF0000+listing.symbol('chipset_apply')
            _,fixture=geometry.mapped(d.modules,expected=4,memory=d,rom_image=image)
            cpu,d,listing,state,cmos,step=fixture
            d.continuing=True
            step.execute(0xF0000+cpu.reg_read(x.UC_X86_REG_IP),0xFFFFF,5000000)
            base=cpu.reg_read(x.UC_X86_REG_FS)<<4
            assert d.policy_seen and d.read(base+0x61,2)==b'\x00\x01'
            assert d.read(base+0x300,15)==expected_pnp and payload==bytes(cmos[i] for i in indices)
            continuations.append(owner)
        return {'cold_and_warm_policy':True,'early_bus_timing_executed':True,
                'actual_ram_failure_producer_reset_and_early_safe_selection':True,
                'additional_recovery_continuations':continuations}
    raise AssertionError(port)


def run(port):
    migrated,expected=migration(port)
    ui_policy=ui_checks(migrated)
    argv=[sys.executable,'-B',str(Path(__file__).resolve()),'--startup-port',port,
          '--startup-cmos',migrated.cmos.hex(),'--startup-nv',migrated.nvram[0x200:0x240].hex(),'--startup-pnp',ui_policy.hex()]
    startup=json.loads(subprocess.check_output(argv,cwd=ROOT,text=True).splitlines()[-1])
    s=Settings(port)
    s.call('settings_load')
    assert not s.writes
    s.call('setup_defaults')
    # Exercise full geometry bytes even when Auto currently ignores them.
    ide = bytearray(s.get('U_IDE',51 if port=='m919' else 25))
    ide[1:13] = bytes((0,3,8,1))+bytes.fromhex('45230f3e34127856')
    s.put('U_IDE',ide)
    pnp = struct.pack('<HBHHHHHBB',0x8408,0xA2,0x300,0x20,0x310,0x10,0xA05,1,1)
    assert len(pnp)==15
    s.put('U_PNP',pnp)
    s.cmos[0x37]=0xE0 if port=='presario-800' else 0xB5
    assert s.call('settings_save'), s.get('U_SAVE_TRACE',3).hex()
    assert s.cmos[0x37]==(0xE0 if port=='presario-800' else 0xB5)
    assert s.logical(0x33)==ord('N') and s.logical(0x34)==6
    assert s.logical(0x69)==0
    assert not sum(s.cmos[0x10:0x2E]) - (s.cmos[0x2E]<<8 | s.cmos[0x2F])
    written = s.snapshot()
    s.writes.clear()
    for _ in range(2):
        s.put('C_PNP',bytes(15))
        s.call('settings_load')
        assert s.get('C_PNP',15)==pnp
        assert s.get('C_IDE',len(ide))==ide
        assert s.get('C_VALID')==b'\x01'
        assert s.snapshot()==written and not s.writes
    # Unrelated component updates must retain saved policy, not U_ scratch.
    s.put('U_PNP',bytes(15))
    s.put('U_PORTS',bytes(8))
    s.put('U_CHIP',bytes(24))
    s.put('U_IDE',ide)
    assert s.call('ide_settings_save')
    s.call('settings_load')
    assert s.get('C_PNP',15)==pnp
    for owner,active,draft,size in [('ports_settings_save','C_PORTS','U_PORTS',8),
                                  ('chipset_settings_save','C_CHIP','U_CHIP',24)]:
        saved=bytes(s.get(active,size))
        s.put(draft,saved)
        assert s.call(owner)
        s.call('settings_load')
        assert s.get('C_PNP',15)==pnp and s.get(active,size)==saved
    descriptors=s.listing.symbol('nv6_descriptors')
    total=0
    for at in range(4):
        offset,length,count,masks=struct.unpack('<4H',s.cpu.mem_read(0xF0000+descriptors+8*at,8))
        bits=sum(byte.bit_count() for byte in s.cpu.mem_read(0xF0000+masks,count))
        assert length==(bits+7)//8 and offset+length<=66
        total+=bits
    assert total==(520 if port=='m919' else 463)
    # Validate the original numeric domain, including disabled remembered bases.
    for window,valid in [((0xFFFF,0),True),((0xFFFF,1),True),((0xFFFF,2),False)]:
        draft=bytearray(pnp)
        struct.pack_into('<HH',draft,3,*window)
        s.put('U_PNP',draft)
        assert s.call('pnp_settings_valid',SI=s.state['U_PNP'])==valid
    for at in (12,13,14):
        draft=bytearray(pnp)
        draft[at]=0xF0 if at==12 else 2
        s.put('U_PNP',draft)
        assert not s.call('pnp_settings_valid',SI=s.state['U_PNP'])
    # A valid additive checksum must not hide nonzero unused bits.
    before=s.snapshot()
    pad=offset+length-1
    indices=list(range(0x40,0x69))+list(range(0x6A,0x80))+[0x11,0x13,0x2D]
    index=indices[pad]
    if port=='mp386':s.nvram[0x200+index-0x40]|=0x80
    else:s.cmos[index]|=0x80
    s.cmos[0x35]=(-ord('N')-6-sum(s.logical(i) for i in indices))&255
    s.writes.clear()
    s.call('settings_load')
    assert s.get('C_VALID')==b'\x00' and not s.writes
    s.cmos[:],s.nvram[:]=before
    s.call('settings_load')
    # Recovery publication is outside the payload checksum.
    payload = bytes(s.logical(i) for i in list(range(0x40,0x69))+list(range(0x6A,0x80))+[0x11,0x13,0x2D])
    s.call('settings_recovery_publish')
    s.call('chipset_settings_load')
    assert payload==bytes(s.logical(i) for i in list(range(0x40,0x69))+list(range(0x6A,0x80))+[0x11,0x13,0x2D])
    s.call('setup_defaults')
    s.fail=('cmos',0x3F)
    s.put('U_BOOT_THIRD',b'\x04')
    assert not s.call('settings_save')
    assert s.logical(0x69)==0xD2
    s.fail=None
    selected=s.get('U_CHIP',24)
    assert s.call('settings_save')
    assert s.logical(0x69)==0
    s.call('settings_load')
    assert s.get('C_CHIP',24)==selected and s.get('C_VALID')==b'\x01'
    assert s.cmos[0x37]==(0xE0 if port=='presario-800' else 0xB5)
    return {'port':port,'migration':True,'nv6_roundtrip':True,'actual_setup':True,
            'empty_migration':True,'rendered_control_census':True,'failed_ui_save_without_reset':True,
            'successful_prior_d2_release':True,'physical_write_and_protected_byte_oracles':True,
            'logical_bits':total,'payload_bytes':66,'startup':startup,'physical_writes':len(s.writes)}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', choices=('all','m919','pb430','presario-800'),default='all')
    parser.add_argument('--startup-port',choices=('m919','pb430','presario-800'))
    parser.add_argument('--startup-cmos')
    parser.add_argument('--startup-nv',default='')
    parser.add_argument('--startup-pnp')
    args=parser.parse_args()
    if args.startup_port:
        print(json.dumps(startup_checks(args.startup_port,args.startup_cmos,args.startup_nv,args.startup_pnp)))
    else:
        ports=('m919','pb430','presario-800') if args.port=='all' else (args.port,)
        for port in ports:
            if port=='presario-800':
                command=['pwsh','-NoProfile','-File',str(ROOT/port/'tools/build.ps1'),'-OutputDirectory','build/tests/pnp-settings']
            elif port=='m919':
                command=[sys.executable,'-B',str(ROOT/'tools/build-rom.py'),str(ROOT/port),'--output','build/tests/pnp-settings']
            else:
                command=[sys.executable,'-B',str(ROOT/port/'tools/build.py'),'--output','build/tests/pnp-settings']
            subprocess.run(command,cwd=ROOT,check=True,stdout=sys.stderr)
        print(json.dumps([run(port) for port in ports],indent=2))
