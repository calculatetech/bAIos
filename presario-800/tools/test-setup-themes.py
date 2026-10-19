"""Production keyboard/render/save proofs for the nine native VGA themes."""
from pathlib import Path


def run(m):
    x = m.x
    leave = [1, 21]
    body = (0x07, 0x1F, 0x70, 0x1F, 0x1F, 0x57, 0x0E, 0x0F, 0x0E)
    selected = (0x1F, 0xE1, 0x1F, 0x5F, 0x30, 0x70, 0xE0, 0x70, 0x30)
    border = (0x0B, 0x1F, 0x70, 0x1D, 0x1B, 0x2A, 0x0E, 0x0F, 0x0E)
    def byte(s, offset): return s.cpu.mem_read(s.base+offset,1)[0]
    def attr(s,row,col): return s.cpu.mem_read(0xB8000+row*160+col*2+1,1)[0]
    def fixture(s, schema, packed, second=1, third=0):
        record = bytearray((66,56,schema,1 if schema==1 else 0x13,packed,0,second,third))
        record[5] = -(sum(record[:5] if schema==1 else record)+s.cmos[0x10])&255
        s.cmos[0x38:0x40] = record
        s.writes.clear()
        before = bytes(s.cmos)
        s.call('settings_load')
        assert bytes(s.cmos)==before and not s.writes
    # Ordered collection and both wrap points through actual IRQ1/INT16.
    s=m.Setup(); seen=[]; screens=[]
    def observe(s):
        theme=byte(s,0xFC)
        if not seen or seen[-1]!=theme:
            seen.append(theme); screens.append(bytes(s.cpu.mem_read(0xB8000,4000)))
            assert attr(s,5,1)==selected[theme]  # Selected blank cell.
            assert attr(s,9,49)==body[theme]     # Numeric RAM count.
            assert attr(s,2,20)==border[theme]  # CP437 junction.
            if theme in (5,6):
                assert attr(s,0,34)==(0x2F if theme==5 else 0x0E)
                assert attr(s,24,2)==(0x20 if theme==5 else 0x0E)
            assert 'F4/F5 Theme' in s.text(24,2,70)
    s.observer=observe
    s.open([0x3F]*9+[0x3E]*9+leave)
    assert seen==list(range(9))+[0]+list(range(8,-1,-1)),seen
    assert all(screen[:3840:2]==screens[0][:3840:2] for screen in screens)
    baseline=m.ROOT/'tests/setup-default-screen.bin'
    assert baseline.is_file(), 'Retained default-screen fixture is required'
    expected=bytearray(baseline.read_bytes())
    expected[3840:]=b' \x07'*80
    footer=b'F1 Help   F4/F5 Theme   F9 Defaults   F10 Save'
    for col,ch in enumerate(footer,2): expected[3840+col*2:3842+col*2]=bytes((ch,0x0B))
    assert screens[0]==expected
    assert byte(s,0xFD)==0 and s.vga[-1]==0x1003 and s.vga_bx[-1]==1
    # Shared helper ABI and POST isolation with DS independent of CS.
    for active in (0,1):
        s=m.Setup();s.cpu.mem_write(s.base+0xFC, b'\x02')
        s.cpu.mem_write(s.base+0xFD,bytes((active,)))
        regs={x.UC_X86_REG_AX:0x0761,x.UC_X86_REG_BX:0x1234,
              x.UC_X86_REG_CX:0x5678,x.UC_X86_REG_DX:0x9ABC,
              x.UC_X86_REG_SI:0x4321,x.UC_X86_REG_DI:800,x.UC_X86_REG_BP:0x6543}
        for r,v in regs.items(): s.cpu.reg_write(r,v)
        s.call('setup_color',flags=0x246)
        assert s.cpu.reg_read(x.UC_X86_REG_AX)==(0x7061 if active else 0x0761)
        for r,v in regs.items():
            if r!=x.UC_X86_REG_AX: assert s.cpu.reg_read(r)==v
        assert s.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0xFFFF==0x246
    # Schema contrasts use independently packed bytes, including duplicate boots.
    cases=[(1,0,1,0,True),(2,0,1,0,True),(3,0,1,0,True),
           (3,4,1,0,False),(4,4,1,0,True),(4,0x1E,2,0,False),
           (4,0x1E,1,0,True),(4,0x20,1,0,True),(4,0x21,2,0,True),
           (4,0x22,1,0,True),(4,0x22,2,0,False),(4,0x24,1,0,False),
           (4,0x40,1,0,False),(4,0x80,1,0,False),(4,3,1,0,True),
           (5,0x44,1,3,True),(5,0x45,1,0,False),(5,0x48,1,0,False),
           (5,0x80,1,0,False),(5,4,4,0,False)]
    for schema,packed,second,third,valid in cases:
        s=m.Setup();fixture(s,schema,packed,second,third)
        assert bool(byte(s,0x17C))==valid,(schema,packed,second)
        assert byte(s,0x13C)==(packed>>(3 if schema==5 else 2) if valid and schema>=4 else 0)
        if valid and schema>=4:
            assert byte(s,0x172)==packed&(7 if schema==5 else 3)
            assert (byte(s,0x189),byte(s,0x18A))==(second,third)
    # Every theme survives a verified F10 and a fresh loader/Setup entry.
    for theme in range(9):
        s=m.Setup();s.open([0x3F]*theme+[0x44,28])
        assert s.warm and s.cmos[0x3A]==5 and s.cmos[0x3C]==theme*8+1
        assert (sum(s.cmos[0x38:0x40])+s.cmos[0x10])&255==0
        n=m.Setup();n.cmos[:]=s.cmos;n.call('settings_load')
        assert byte(n,0x13C)==theme
        states=[];n.observer=lambda n:states.append(byte(n,0xFC))
        n.open(leave.copy());assert states and set(states)=={theme}
    s=m.Setup();fixture(s,4,34,1);before=bytes(s.cmos)
    s.open([0x3F,0x43,1,0x44,1]+leave) # Cancel defaults/save, then discard.
    assert bytes(s.cmos)==before and byte(s,0x13C)==8
    s=m.Setup();fixture(s,4,25,2)
    s.open([0x43,28,0x3F,0x3F,0x3F,0x44,28])
    assert s.cmos[0x3C]==25 # F9 then custom theme, first boot Floppy.
    # The two new palettes recolor help, including its blank panel cells.
    for theme,color in ((5,0x67),(6,0x0E)):
        s=m.Setup();help_seen=[]
        def help_panel(s):
            if s.text(18,25,14)=='Standard Setup':
                assert byte(s,0xFC)==theme
                assert attr(s,18,25)==color and attr(s,17,23)==color
                help_seen.append(True)
        s.observer=help_panel;s.open([0x3F]*theme+[0x3B,1]+leave)
        assert help_seen
    # Pending meridiem/cursor survive redraw, idle, help and ignored modal keys.
    s=m.Setup();phase=[0];pending=[]
    def edit(s):
        if s.script or s.pending:return
        if phase[0]==0:
            pending.extend((bytes(s.cpu.mem_read(s.base+0x100,12)),byte(s,0xF9)))
            s.script=[0x3F];phase[0]=1
        elif phase[0]==1 and s.idles:
            assert byte(s,0xFC)==1
            assert attr(s,19,24+byte(s,0xF9))==0xE1
            s.script=[0x3B,0x3E,1,0x3E];phase[0]=2
        elif phase[0]==2:
            assert byte(s,0xFC)==0
            assert bytes(s.cpu.mem_read(s.base+0x100,12))==pending[0]
            assert byte(s,0xF9)==pending[1]
            assert attr(s,19,24+byte(s,0xF9))==0x70
            s.observer=None;s.script=[28,1]+leave;phase[0]=3
    s.observer=edit;s.open([15,0x50,28]+m.keys('014559p'))
    assert phase[0]==3 and s.invoke(2)[1]==0x1345
    # Popup and confirmation owners consume theme keys without mutation.
    s=m.Setup();state=[]
    def popup(s):
        if s.text(8,26,12)=='SELECT VALUE':
            state.append((byte(s,0xFC),attr(s,10,26)))
    s.observer=popup
    s.open([0x3F,0x3F,15,0x50,0x50,28,0x3F,0x3E,1,0x44,0x3F,0x3E,1,1]+leave)
    assert state and all(theme==2 for theme,_ in state)
    assert any(color==0x1F for _,color in state)
    s=m.Setup();confirmation=[];phase=[0]
    def confirm(s):
        if s.script or s.pending or 'Save' not in s.text(21,23,50):return
        current=(byte(s,0xFC),bytes(s.cpu.mem_read(s.base+0xF5,3)),
                 bytes(s.cpu.mem_read(s.base+0x180,0x13A)))
        assert current[0]==2 and not s.text(24,2,76).strip()
        if phase[0]==0:
            confirmation.append(current);s.script=[0x3F];phase[0]=1
        else:
            assert current==confirmation[0]
            s.observer=None;s.script=[1,1,28];phase[0]=2
    s.observer=confirm;s.open([0x3F,0x3F,0x44])
    assert phase[0]==2
    # Numeric repaint and modal key containment on an actual User disk form.
    import importlib
    ide=importlib.import_module('test-ide-options')
    s=m.Setup();numbers=[];repaint=[]
    def numeric(s):
        if byte(s,0xF5)!=1 or byte(s,0x188)!=0:return
        if byte(s,0xF7)==2 and s.text(7,49,5)=='120  ':
            assert all(attr(s,7,col)==0x1F for col in range(49,54))
            assert all(attr(s,8,col)==0x70 for col in range(49,54))
            repaint.append(True)
        if byte(s,0xF7)==2 and s.text(22,24,5)=='Enter':
            assert byte(s,0xFC)==2
            assert all(attr(s,7,col)==0x1F for col in range(49,54))
            assert all(attr(s,8,col)==0x70 for col in range(49,54))
            if byte(s,0xF9)==3:
                assert s.text(22,49,3)=='120'
                assert s.cpu.mem_read(s.base+0x100,4)==b'120\0'
                assert all(attr(s,22,col)==0x1F for col in range(49,52))
                assert all(attr(s,22,col)==0x70 for col in range(52,55))
                numbers.append(True)
            assert not s.text(24,2,76).strip()
    s.observer=numeric
    s.open([0x3F]*2+ide.TYPE_MENU+[0x51]*4+[28,0x50,28]+m.keys('120')+
           [0x3F,0x3E,28,0x44,28])
    assert numbers and repaint and s.cmos[0x3C]==17 and s.cmos[0x49:0x4B]==b'x\0'
    # Short24-hour suffix clearing carries the gray body background.
    s=m.Setup();suffix=[]
    def short(s):
        if byte(s,0xFB)==1:
            assert s.text(6,57,3)=='   '
            assert all(attr(s,6,col)==0x70 for col in (57,58,59))
            suffix.append(True)
    s.observer=short;s.open([0x3F]*2+[15,0x50,0x50,0x4D,1]+leave)
    assert suffix
    # Locked RAM timings remain gray after label masks and field navigation.
    s=m.Setup();locked=[]
    def ram(s):
        if byte(s,0xF5)==5 and byte(s,0x278)==1:
            assert all(attr(s,row,49)==0x78 for row in (10,11,12,13,14))
            assert all(attr(s,row,24)==0x78 for row in (10,11,12,13,14))
            locked.append(True)
    s.observer=ram
    s.open([0x3F]*2+[0x50]*4+[28,28,1,1]+leave)
    assert locked
    # Disabled Ports fields use the mapped body mask on the Devices page.
    ports_module=importlib.import_module('test-ports')
    s=ports_module.Ports();s.post(bytes((1,0,1,0,0,1,1,1)));ports=[]
    def devices(s):
        if byte(s,0xF5)==3 and byte(s,0xFC)==2:
            assert attr(s,5,24)==0x70
            assert attr(s,5,49)==(0x1F if byte(s,0xF6)==1 else 0x70)
            assert attr(s,6,24)==0x70
            assert attr(s,7,24)==0x78 and attr(s,7,49)==0x78
            ports.append(byte(s,0xF6))
    s.observer=devices;s.open([0x3F]*2+[0x50]*3+[28,1]+leave)
    assert 1 in ports
    for theme,label_color in ((0,0x0F),(2,0x70)):
        s=m.Setup();labels=[]
        def drive_label(s):
            if byte(s,0xF5)==1 and byte(s,0xF6)==1 and byte(s,0xF7)==2:
                assert attr(s,8,24)==label_color
                assert attr(s,8,49)==0x1F
                labels.append(True)
        s.observer=drive_label
        s.open([0x3F]*theme+[0x50,28,0x50,0x50,1]+leave)
        assert labels
    class Mismatch(m.Setup):
        def port_in(self,cpu,port,size,unused):
            value=super().port_in(cpu,port,size,unused)
            return value^4 if port==0x71 and self.index==0x3C and (0x38,66) in self.writes else value
    s=Mismatch();errors=[]
    def failed(s):
        if 'CMOS verification failed.' in s.text(19,23,46):
            assert not s.warm and byte(s,0x13C)==0 and byte(s,0xFC)==2
            assert attr(s,19,23)==0x74 and attr(s,19,68)==0x74
            errors.append(True);s.observer=None;s.script=leave.copy()
    s.observer=failed;s.open([0x3F,0x3F,0x44,28]);assert errors
    post_return(m)
    print('Themes: ordered palette/geometry/ABI, legacy and packed CMOS, save/discard/defaults/failure, pending edit and modal keys: PASS',flush=True)


def post_return(m):
    """Real early/final Setup discard must restore ordinary POST and boot."""
    for entry in ('chipset_apply','setup_post_gate'):
        screens=[]
        for theme in (0,2):
            s=m.production_post_model()
            m.schema2_fixture(s,types=0,flags=0x13,order=(2,0,0))
            seen=[]; post=[]
            def observe(s,name):
                if name==entry and not seen:
                    s.pending.extend((0xE0,0x53));seen.append('delete')
                    if entry=='setup_post_gate':
                        m.rtc.Clock.interrupt(s,s.cpu,9,None)
                        m.rtc.Clock.interrupt(s,s.cpu,9,None)
                if name=='setup_main':
                    seen.append('setup');s.script=[0x3F]*theme+[1,28]
                if name=='post_debug_summary':
                    assert s.cpu.mem_read(s.base+0xFD,1)==b'\0'
                    assert [bx for ax,bx in zip(s.vga,s.vga_bx) if ax==0x1003][-1]==1
                    if entry=='chipset_apply':
                        assert s.text(5,3,8)=='RAM Test'
                        assert s.cpu.mem_read(0xB8000+5*160+3*2+1,1)==b'\x0B'
                        assert s.cpu.mem_read(0xB8000+5*160+24*2+1,1)==b'\x07'
                    post.append(bytes(s.cpu.mem_read(0xB8000,4000)))
                if name=='int19':
                    assert s.cpu.mem_read(s.base+0xFD,1)==b'\0'
                    post.append(bytes(s.cpu.mem_read(0xB8000,4000)))
            s.startup_observer=observe
            s.startup(reset=True,production_controls=True,through_boot=True)
            assert seen==['delete','setup'] and len(post)==2
            assert s.cpu.mem_read(0x7C00,4)==b'BOOT'
            assert s.cpu.mem_read(s.base+0xFC,1)==bytes((theme,))
            screens.append(post)
        assert screens[0]==screens[1],entry
    print('Themes: default/Gray early and final Setup return -> unchanged POST attributes/summary/blink/gate -> BOOT PASS',flush=True)
