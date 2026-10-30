"""Focused native checks of the full donor firmware and UMC adapters."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import re
import subprocess
import sys
PORT=Path(__file__).resolve().parents[1]
REPOSITORY=PORT.parent
sys.path.insert(0,str(REPOSITORY))
from shared.tools.rom import build,configuration
from shared.tools.emulator import run_86box
from shared.tools.fat12 import Fat12
from shared.tools.fat16 import Fat16
from shared.tools.vga_text import render
from shared.tools.cd_fixture import disc
ALL_CASES=('boot','setup','policy','policy-clock','ram','no-media','cd','warm','floppy-swap',
    'aux-policy','fdc-capabilities','a20','himem','keyboard-policy','keyboard','keyboard-absent',
    'floppy-missing','alternate-ram','cpu','positions','option-roms','policy-clock-no-errors','dos')

def assemble(source,output,includes):
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    command=[nasm,'-w+error','-f','bin']
    for folder in includes:
        command+=['-I',str(folder)+'/']
    subprocess.run(command+['-o',str(output),str(source)],check=True)

def nvram(types=0,valid=True,clock='valid',boot=2,l1=False,swap=False):
    n=bytearray(256)
    for i,v in {0:6,2:7,4:8,6:1,7:8,8:9,9:0x24,10:0x26,11:2,13:0x80,0x32:0x20}.items():n[i]=v
    n[0x10]=types
    n[0x2E:0x30]=struct.pack('>H',sum(n[0x10:0x2E]))
    n[0x38:0x40]=bytes((ord('B'),ord('8'),5,0x13,boot,0,3-boot,0))
    if swap:n[0x3B]|=4
    n[0x3D]=(-sum(n[0x38:0x3D])-types-n[0x3E])&255
    if not valid:n[0x38]=0
    if clock=='loss':n[0xE]=0x80;n[2]=0xFF;n[4]=0xFF;n[8]=0
    if l1:n[0x69]=0x55;n[0x6C]=1;n[0x6A]=(-0x56)&255
    return n

def fixture(name,disks,ram=16384,types=0,valid=True,clock='valid',defines=(),cdroms=(),dirty_display=False,cpu=None,ram_flags=4,l1=False,missing_floppy=False,legacy_mouse=False,bpb_heads=16,dirty_vga_init=False,no_errors_clock=False,failed_provider=False):
    _,c=configuration(PORT)
    r=build(PORT,'build/tests/post/'+name+'/image',defines)
    folder=PORT/'build/tests/post'/name;vm=folder/'vm';roms=folder/'roms'
    vm.mkdir(parents=True,exist_ok=True)
    em=dict(c['emulator']);em.update(cpu or {})
    for f in em['rom_files']:
        target=roms/f;target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(REPOSITORY/'tools/86box/roms'/f,target)
    target=roms/em['rom_path'];target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(r['path'],target)
    cfg={'TEST_RAM_BYTES':ram*1024,'TEST_BOOT_POSITION':min(disks,default=255),'TEST_RAM_FLAGS':ram_flags,
         'TEST_LOGICAL_RECORD':int(bool(cdroms) and min(cdroms)<min(disks,default=255)),
         'TEST_DIRTY_DISPLAY':int(dirty_display),'TEST_CPU_FIRST':ord('4') if cpu else ord('A'),
         'TEST_ERROR_BITS':2 if missing_floppy else 1 if no_errors_clock else 0,'TEST_FLOPPY_FAILED':int(missing_floppy),'TEST_CLOCK_NO_ERRORS':int(no_errors_clock)}
    cfg.update(TEST_BPB_HEADS=bpb_heads,TEST_EXPECT_HEADS=bpb_heads,TEST_DIRTY_VGA_INIT=int(dirty_vga_init))
    cfg['TEST_L2_ENABLED']=1
    (folder/'test-configuration.inc').write_text(''.join(f'%define {k} {v}\n' for k,v in cfg.items()))
    assemble(PORT/('tests/core-failed-provider.asm' if failed_provider else 'tests/core-boot.asm'),folder/'boot.bin',[folder,PORT/'tests'])
    hd=''
    for pos,cyl in disks.items():
        disk=vm/f'disk-{pos}.img'
        with disk.open('wb') as f:f.write((folder/'boot.bin').read_bytes());f.truncate(cyl*16*63*512)
        i=pos+1
        hd+=f'hdd_{i:02}_fn = {disk.name}\nhdd_{i:02}_parameters = 63, 16, {cyl}, 0, ide\nhdd_{i:02}_ide_channel = {pos//2}:{pos%2}\nhdd_{i:02}_speed = ramdisk\n'
    optical=''
    for i,pos in enumerate(cdroms,1):optical+=f'cdrom_{i:02}_parameters = 1, atapi\ncdrom_{i:02}_ide_channel = {pos//2}:{pos%2}\ncdrom_{i:02}_type = 86cd\n'
    net=''
    if dirty_display:
        assemble(PORT/'tests/core-option-rom.asm',folder/'observer.bin',[PORT/'tests'])
        blob=bytearray(32768);raw=bytearray((folder/'observer.bin').read_bytes());raw[-1]=(-sum(raw))&255;blob[:len(raw)]=raw
        p=roms/'network/ne2000/ne2000.rom';p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(blob)
        net='[Network]\nnet_01_card = novell_ne2k\nnet_01_link = 506\n[Novell NE2000 #1]\nbase = 0300\nirq = 3\nbios_addr = C8000\n'
    if dirty_vga_init:
        image=bytearray((roms/em['rom_files'][0]).read_bytes())
        assert image[3]==0xE9 and sum(image)%256==0
        original=6+struct.unpack_from('<H',image,4)[0]
        (folder/'vga-entry.inc').write_text(f'%define ORIGINAL_VGA_ENTRY {original}\n')
        assemble(PORT/'tests/core-vga-entry.asm',folder/'vga-entry.bin',[folder,PORT/'tests'])
        wrapper=(folder/'vga-entry.bin').read_bytes()
        assert len(wrapper)<=0x12C-0xE0 and image[0xE0:0xE0+len(wrapper)]==bytes(len(wrapper)),'Wrapper is restricted to validated padding'
        image[0xE0:0xE0+len(wrapper)]=wrapper
        struct.pack_into('<H',image,4,0xE0-6)
        image[-1]=(image[-1]-sum(image))&255
        (roms/em['rom_files'][0]).write_bytes(image)
    (vm/'86box.cfg').write_text(f'''[General]
vid_renderer = qt_software
[Machine]
machine = {em['machine']}
cpu_family = {em['cpu_family']}
cpu_speed = {em['cpu_speed']}
cpu_multi = {em['cpu_multi']}
cpu_use_dynarec = 0
fpu_type = internal
mem_size = {ram}
time_sync = disabled
[Video]
gfxcard = {em['gfxcard']}
[{em['gfx_section']}]
bios = {em['gfx_bios']}
memory = {em['gfx_memory']}
[Input devices]
keyboard_type = keyboard_ps2
mouse_type = none
[Hard disks]
{hd}
[Floppy and CD-ROM drives]
fdd_01_type = {'35_2hd' if types>>4 and not missing_floppy else 'none'}
fdd_02_type = {'35_2hd' if types&15 else 'none'}
{optical}
{net}
[Other peripherals]
postcard_enabled = 1
unittester_enabled = 1
[86Box Unit Tester]
exit_enabled = 1
''')
    (vm/'nvr').mkdir(exist_ok=True)
    n=nvram(types,valid,clock,l1=l1)
    if missing_floppy or no_errors_clock:
        n[0x3B]=(n[0x3B]&~0x18)|8  # Real persisted No Errors policy permits bootstrap.
        n[0x3D]=(-sum(n[0x38:0x3D])-types-n[0x3E])&255
    if legacy_mouse:
        n[0x5D:0x68]=b'P1\x01'+bytes((1,2,1,2,0,1,1,1))
        n[0x68]=(-sum(n[0x5D:0x68]))&255
    (vm/'nvr'/(em['machine']+'.nvr')).write_bytes(n)
    return vm,roms,r

def execute(name,disks,expected=0x60,**options):
    vm,roms,r=fixture(name,disks,**options)
    actual=run_86box(vm,roms,timeout=100)
    print(f'{name}: {actual:02X} (expected {expected:02X})',flush=True)
    if actual!=expected:raise AssertionError(f'{name}: {actual:02X}')
    if expected==0x60:
        raw=(vm/f'disk-{min(disks)}.img').read_bytes()[512:17*512]
        cells=raw[:4000];font=raw[8*512:16*512]
        _,c=configuration(PORT)
        def field(row,column,value,attribute):
            span=cells[row*160+column*2:row*160+(column+len(value))*2]
            assert span[::2]==value.encode('cp437'),(name,row,column,span[::2],value)
            assert span[1::2]==bytes((attribute,))*len(value),(name,row,column,'attributes')
        field(0,3,c['identity']['vendor']+' '+c['identity']['model'],0x1B)
        field(0,37,'bAIos',0x1F)
        field(0,58,'ROM build:',0x1B)
        field(0,69,c['identity']['release_date'][:6]+c['identity']['release_date'][-2:],0x1F)
        field(1,0,'╔'+'═'*78+'╗',0x0B)
        field(5,0,'╠'+'═'*78+'╣',0x0B)
        field(8,0,'╠'+'═'*78+'╣',0x0B)
        field(11,0,'╚'+'═'*78+'╝',0x0B)
        for row,label in ((2,'Processor'),(3,'FPU'),(4,'L2 cache'),(6,'Floppy Drive A'),(7,'Floppy Drive B')):field(row,3,label,0x0B)
        field(2,20,'486+' if options.get('cpu') else 'AMD 5x86',7)
        field(4,20,'Disabled',7)
        field(2,40,'Base Memory',0x0B);field(2,58,'632',7)
        field(3,40,'Extended Memory',0x0B);field(3,58,str(options.get('ram',16384)-1024),7)
        field(4,40,'Memory Banks',0x0B);field(4,58,'0',7)
        field(6,40,'COM Ports',0x0B);field(7,40,'LPT Ports',0x0B)
        for row in (2,3,4,6,7,9,10):field(row,0,'║',0x0B);field(row,79,'║',0x0B)
        expected_font=(REPOSITORY/'tools/86box/roms/video/cirruslogic/5446bv.vbi').read_bytes()[0x6E5F:0x7E5F]
        assert len(font)==4096 and font==expected_font,'Retained provider 8x16 font differs'
        first_blank=15 if options.get('missing_floppy') else 14 if options.get('no_errors_clock') else 12
        assert cells[first_blank*160:]==b' \x07'*80*(25-first_blank),'Unused/message/footer cells contain residual text'
        (vm.parent/'post-cells.bin').write_bytes(cells)
        (vm.parent/'post-font.bin').write_bytes(font)
        (vm.parent/'post.txt').write_text('\n'.join(bytes(cells[y*160:y*160+160:2]).decode('cp437') for y in range(25))+'\n',encoding='utf-8')
        render(cells,font,vm.parent/'post-dump-render.png')
    return {'name':name,'exit':actual,'rom_sha256':r['sha256'],'options':options,
        'display_oracle':'full donor frame/header/label/value attributes, CPU/cache/RAM/bank and retained4096-byte8x16 font' if expected==0x60 else None}

def fdc_capabilities():
    """External765/82077 result-phase behavior, not firmware state setters."""
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_16,UC_HOOK_INSN
    from unicorn import x86_const as x
    r=build(PORT,'build/full-core/fdc-device');raw=Path(r['path']).read_bytes()
    listing=Path(r['path']).with_suffix('.lst').read_text().splitlines()
    def symbol(name):
        i=next(i for i,s in enumerate(listing) if re.search(r'(?<![\w.])'+name+r':\s*$',s))
        for line in listing[i+1:]:
            m=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line)
            if m:return int(m[1],16)
        raise AssertionError(name)
    results=[]
    for version,expected in ((0x80,[0x10,3,0xDF,2]),(0x90,[0x10,0x13,0,0x0C,0,3,0xDF,2,0x12,0x80])):
        cpu=Uc(UC_ARCH_X86,UC_MODE_16);cpu.mem_map(0,2*1024*1024);cpu.mem_write(0xF0000,raw[65536:])
        cpu.mem_write(0x40E,struct.pack('<H',0x9E00))
        queue=[];writes=[];params=0
        def incoming(uc,port,size,context):
            if port==0x3F4:return 0xC0 if queue else 0x80
            if port==0x3F5:return queue.pop(0)
            return 0
        def outgoing(uc,port,size,value,context):
            nonlocal params
            if port!=0x3F5:return
            assert not queue,'Host wrote while controller still had a result'
            writes.append(value)
            if params:params-=1;return
            if value==0x10:queue.append(version)
            elif value==3:params=2
            elif value==0x13:
                if version==0x90:params=3
                else:queue.append(0x80)
            elif value==0x12:
                if version==0x90:params=1
                else:queue.append(0x80)
            else:raise AssertionError(('unexpected controller command',value))
        cpu.hook_add(UC_HOOK_INSN,incoming,None,1,0,x.UC_X86_INS_IN)
        cpu.hook_add(UC_HOOK_INSN,outgoing,None,1,0,x.UC_X86_INS_OUT)
        for entry in ('board_floppy_configure','fdc_specify'):
            for register,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_FS,0x9E00),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x6FFE)):
                cpu.reg_write(register,value)
            cpu.mem_write(0x6FFE,struct.pack('<H',0xFFF0))
            cpu.emu_start(0xF0000+symbol(entry),0xFFFF0,count=100000)
            assert cpu.reg_read(x.UC_X86_REG_IP)==0xFFF0
            assert not(cpu.reg_read(x.UC_X86_REG_EFLAGS)&1)
        assert writes==expected,(version,writes)
        assert not queue and params==0
        results.append({'version':version,'commands_and_parameters':writes,'result_phase_drained':True})
    print('Legacy80/enhanced90 FDC capability/result-phase checks: PASS',flush=True)
    return results

def aux_policy():
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_16,UC_HOOK_INSN
    from unicorn import x86_const as x
    r=build(PORT,'build/full-core/aux-policy')
    raw=Path(r['path']).read_bytes();lines=Path(r['path']).with_suffix('.lst').read_text().splitlines()
    def symbol(name):
        i=next(i for i,s in enumerate(lines) if re.search(r'(?<![\w.])'+name+r':\s*$',s))
        return next(int(m[1],16) for s in lines[i+1:] if (m:=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',s)))
    cpu=Uc(UC_ARCH_X86,UC_MODE_16);cpu.mem_map(0,2*1024*1024);cpu.mem_write(0xF0000,raw[65536:]);base=0x9E000
    cpu.mem_write(0x40E,struct.pack('<H',0x9E00));cpu.mem_write(base+0x174,b'\x01')
    cmos=bytearray(128);record=bytes((3,4,1,3,2,1,1,1));cmos[0x5D:0x68]=b'P1\x01'+record;cmos[0x68]=(-sum(cmos[0x5D:0x68]))&255
    original=bytes(cmos);index=0;writes=[]
    def incoming(uc,port,size,context):
        assert port not in (0x60,0x64),'Unavailable AUX touched the keyboard controller'
        if port==0x71:return cmos[index]
        if port==0xA1:return 0xE3
        return 0
    def outgoing(uc,port,size,value,context):
        nonlocal index
        assert port not in (0x60,0x64,0x92),'Unavailable AUX modified keyboard/A20'
        writes.append((port,value))
        if port==0x70:index=value&127
        if port==0x71:cmos[index]=value
    cpu.hook_add(UC_HOOK_INSN,incoming,None,1,0,x.UC_X86_INS_IN)
    cpu.hook_add(UC_HOOK_INSN,outgoing,None,1,0,x.UC_X86_INS_OUT)
    def run(name,ax=0,cx=0,di=0,interrupt=False):
        for reg,val in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_FS,0x9E00),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_AX,ax),(x.UC_X86_REG_CX,cx),(x.UC_X86_REG_DI,di),(x.UC_X86_REG_EFLAGS,0x202)):
            cpu.reg_write(reg,val)
        cpu.reg_write(x.UC_X86_REG_SP,0x6FF8 if interrupt else 0x6FFE)
        cpu.mem_write(0x6FF8 if interrupt else 0x6FFE,struct.pack('<HHH',0xFFF0,0xF000,0x202) if interrupt else struct.pack('<H',0xFFF0))
        cpu.emu_start(0xF0000+symbol(name),0xFFFF0,count=100000)
        assert cpu.reg_read(x.UC_X86_REG_IP)==0xFFF0,name
    run('ports_settings_load')
    expected=record[:6]+b'\x00'+record[7:]
    assert bytes(cpu.mem_read(base+0x1E6,8))==expected
    assert bytes(cpu.mem_read(base+0x174,1))==b'\x01','Valid CMOS record was discarded'
    assert bytes(cmos)==original,'Load rewrote persistent CMOS'
    cpu.mem_write(base+0x1EE,record);run('board_ports_no_aux_save')
    assert bytes(cpu.mem_read(base+0x1EE,8))==expected
    cpu.mem_write(base+0x1EE,record);run('ports_defaults',di=0x1EE)
    assert bytes(cpu.mem_read(base+0x1EE+6,1))==b'\x00'
    run('ports_ui_available',cx=6);assert cpu.reg_read(x.UC_X86_REG_EFLAGS)&1
    for field in (2,6,7):
        run('ports_ui_visible',cx=field);assert cpu.reg_read(x.UC_X86_REG_EFLAGS)&1
        run('ports_ui_available',cx=field);assert cpu.reg_read(x.UC_X86_REG_EFLAGS)&1
    cpu.mem_write(0x410,b'\xff\xff');cpu.mem_write(base+0xB0,b'\xff'*10)
    writes.clear();run('board_mouse_no_aux');assert writes==[(0xA1,0xF3)],writes
    assert bytes(cpu.mem_read(0x410,2))==b'\xfb\xff'
    assert bytes(cpu.mem_read(base+0xB0,9))==b'\x00'*9
    writes.clear()
    for function in range(8):
        run('int15',ax=0xC200|function,interrupt=True)
        assert cpu.reg_read(x.UC_X86_REG_AX)>>8==3 and cpu.reg_read(x.UC_X86_REG_EFLAGS)&1
    assert not writes,'Disabled C2 interface issued controller operations'
    print('Valid legacyCMOS retained; onlyMouse normalized; SetupMouseHidden; allC2 functions unavailable/noKBC commands: PASS',flush=True)
    composed=execute('core-aux-setup',{0:65},types=0x40,expected=0x67,legacy_mouse=True,
        defines=('EMULATOR_POST_SUMMARY_TEST','EMULATOR_SETUP_TEST','EMULATOR_SETUP_SAVE_FIELDS','EMULATOR_SETUP_AUX_POLICY'))
    return {'name':'no-AUX-board-policy','rom_sha256':r['sha256'],'legacy_ports_before':list(record),'active_ports_after':list(expected),'CMOS_valid_and_unchanged':True,'only_Mouse_selector_normalized':True,'Setup_Mouse_hidden_uneditable':True,'C2_functions_0_through_7':'AH03/CF1/no controller I/O','UARTs_unchanged':True,'composed_Setup_save_restart_reload':composed}

def keyboard_policy():
    """Execute the real adapter and IRQ decoder against controller I/O."""
    from unicorn import Uc,UC_ARCH_X86,UC_MODE_16,UC_HOOK_INSN,UC_HOOK_INTR,UC_HOOK_CODE
    from unicorn import x86_const as x
    r=build(PORT,'build/full-core/keyboard-policy');raw=Path(r['path']).read_bytes()
    lines=Path(r['path']).with_suffix('.lst').read_text().splitlines()
    def symbol(name):
        i=next(i for i,s in enumerate(lines) if re.search(r'(?<![\w.])'+name+r':\s*$',s))
        for line in lines[i+1:]:
            m=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line)
            if m:return int(m[1],16)
        raise AssertionError(name)
    results=[]
    for failed_readback in (False,True):
        cpu=Uc(UC_ARCH_X86,UC_MODE_16);cpu.mem_map(0,2*1024*1024);cpu.mem_write(0xF0000,raw[65536:])
        cpu.mem_write(0x41A,struct.pack('<HH',0x1E,0x1E));cpu.mem_write(0x480,struct.pack('<HH',0x1E,0x3E))
        cb=0x6F;queue=[0x1E];write_data=False;writes=[];post=[];pic=0xFF;irq_entries=[]
        def incoming(uc,port,size,context):
            if port==0x64:return int(bool(queue))
            if port==0x60:return queue.pop(0) if queue else 0
            if port==0x21:return pic
            return 0
        def outgoing(uc,port,size,value,context):
            nonlocal cb,write_data,pic
            writes.append((port,value))
            if port==0x64:
                if value==0xAD:cb|=0x10
                elif value==0xAE:cb&=~0x10
                elif value==0x20:queue.append(cb ^ (1 if failed_readback and write_data else 0))
                elif value==0x60:write_data=True
                else:raise AssertionError(('Unexpected KBC command',value))
            elif port==0x60:
                assert write_data;cb=value
            elif port==0x21:pic=value
            elif port==0x80:post.append(value);uc.emu_stop()
        def interrupt(uc,number,context):
            assert number in (9,0x15),number
            irq_entries.append(number)
            sp=uc.reg_read(x.UC_X86_REG_SP)
            for value in (uc.reg_read(x.UC_X86_REG_EFLAGS),uc.reg_read(x.UC_X86_REG_CS),uc.reg_read(x.UC_X86_REG_IP)):
                sp-=2;uc.mem_write(sp,struct.pack('<H',value&65535))
            uc.reg_write(x.UC_X86_REG_SP,sp)
            uc.reg_write(x.UC_X86_REG_EFLAGS,uc.reg_read(x.UC_X86_REG_EFLAGS)&~0x300)
            uc.reg_write(x.UC_X86_REG_CS,0xF000);uc.reg_write(x.UC_X86_REG_IP,symbol('int09' if number==9 else 'int15'))
        cpu.hook_add(UC_HOOK_INSN,incoming,None,1,0,x.UC_X86_INS_IN)
        cpu.hook_add(UC_HOOK_INSN,outgoing,None,1,0,x.UC_X86_INS_OUT)
        cpu.hook_add(UC_HOOK_INTR,interrupt)
        for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_FS,0x9E00),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x6FFE)):
            cpu.reg_write(reg,value)
        cpu.mem_write(0x6FFE,struct.pack('<H',0xFFF0))
        cpu.emu_start(0xF0000+symbol('board_keyboard_handoff'),0xFFFF0,count=100000)
        assert bytes(cpu.mem_read(0x41E,2))==b'a\x1e','Pending real scan was lost or changed'
        assert bytes(cpu.mem_read(0x41C,2))==b' \x00'
        if failed_readback:assert post==[0xE6],post
        else:
            assert cpu.reg_read(x.UC_X86_REG_IP)==0xFFF0
            assert cb==0x4F and pic==0xFD and not queue,(cb,pic,queue)
        results.append({'readback_fault':failed_readback,'pending_scan_preserved':True,'command_byte':cb,'PIC_mask':pic,'POST':post,'rom_sha256':r['sha256']})
    print('Keyboard handoff/queued scan/AUX-bit preservation/E6 readback fault: PASS',flush=True)
    return results

def a20():
    vm,roms,r=fixture('core-a20',{0:65},types=0x40)
    boot=vm.parent/'a20.bin';assemble(PORT/'tests/core-a20.asm',boot,[PORT/'tests'])
    with (vm/'disk-0.img').open('r+b') as disk:disk.write(boot.read_bytes())
    actual=run_86box(vm,roms,timeout=90)
    assert actual==0x6A,('Physical8042 alias control and normal FDC seek',actual)
    print('Actual8042 A20 alias disable/enable plus FDC VERSION/seek: 6A',flush=True)
    return {'name':'8042-A20-alias/FDC-seek','exit':actual,'rom_sha256':r['sha256']}

def floppy_missing():
    _,config=configuration(PORT)
    em=config['emulator']
    results=[execute('core-floppy-missing',{0:65},types=0x40,missing_floppy=True)]
    vm,roms,r=fixture('core-floppy-disabled',{0:65},types=0x40)
    boot=vm.parent/'disabled.bin';assemble(PORT/'tests/core-disabled-floppy.asm',boot,[PORT/'tests'])
    with (vm/'disk-0.img').open('r+b') as f:f.write(boot.read_bytes())
    n=nvram(0x40)
    n[0x5D:0x68]=b'P1\x01'+bytes((1,2,1,2,0,0,0,1))
    n[0x68]=(-sum(n[0x5D:0x68]))&255
    (vm/'nvr'/(em['machine']+'.nvr')).write_bytes(n)
    media=vm.parent/'present.img';shutil.copyfile(REPOSITORY/'tools/deps/ms-dos/6.22-boot.ima',media)
    cfg=(vm/'86box.cfg').read_text().replace('[Floppy and CD-ROM drives]',f'[Floppy and CD-ROM drives]\nfdd_01_fn = {media.as_posix()}')
    (vm/'86box.cfg').write_text(cfg)
    actual=run_86box(vm,roms,timeout=100)
    assert actual==0x69,('Disabled controller with physical drive/media; native absence/read rejection',actual)
    print('Configured absent seek/error identity; persisted disabled FDC with real media AH15/AH02/BDA: PASS',flush=True)
    results.append({'name':'core-floppy-disabled','exit':actual,'rom_sha256':r['sha256'],
        'oracle':'persisted FDC0 + present1.44MB media; F_TYPES0/BDAabsent; AH15 no drive; AH02 CF1/AH01'})
    return results

def dos(warm=False,swap=False,himem=False,keyboard=False):
    _,config=configuration(PORT)
    em=config['emulator']
    source=REPOSITORY/'tools/deps/ms-dos/6.22-boot.ima'
    if not source.exists():raise FileNotFoundError('Copy the read-only MS-DOS6.22 boot IMA into '+str(source))
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='9d620dc19afb29a77324bc0e262ceffeac918632ff2a0ccea685427ff85e27cd'
    vm,roms,r=fixture('core-keyboard' if keyboard else 'core-himem' if himem else 'core-dos-warm' if warm else 'core-dos-swap' if swap else 'core-dos',{0:65},types=0x40,l1=warm,defines=('EMULATOR_DOS_WARM_STATE',) if warm else ())
    folder=vm.parent;disk=folder/'dos622.vhd';floppy=folder/'dos622.img';com=folder/'coretest.com'
    assemble(PORT/'tests/core-dos.asm',com,[PORT/'tests'])
    if keyboard:
        emm=REPOSITORY/'tools/deps/ms-dos/EMM386.EXE'
        assert hashlib.sha256(emm.read_bytes()).hexdigest()=='d4a011769db9415402d7be129fffb762fa7d174096bcc921aa5ce85734072635'
        source_com=folder/'keyboard-probe.asm'
        source_com.write_text('%define EMULATOR_DMA_TEST 1\n%include "core-emm-keyboard.asm"\n')
        assemble(source_com,folder/'kiot.com',[PORT/'tests'])
    shutil.copyfile(REPOSITORY/'reference/media/dos/test-card.vhd',disk)
    f=Fat16(disk)
    assert f.vhd.sector(1)==bytes(512),'Independent second-sector CHS oracle'
    with disk.open('r+b') as out:
        drivers=b'DEVICE=A:\\HIMEM.SYS /TESTMEM:OFF\r\nDEVICE=C:\\EMM386.EXE NOEMS\r\nDOS=HIGH,UMB\r\n' if keyboard else b'DEVICE=A:\\HIMEM.SYS /TESTMEM:OFF\r\nDOS=HIGH\r\n' if himem else b''
        f.replace(out,'CONFIG.SYS',drivers+b'FILES=30\r\nBUFFERS=20\r\nSTACKS=9,256\r\n')
        f.replace(out,'AUTOEXEC.BAT',b'@ECHO OFF\r\nC:\\KIOT.COM\r\n' if keyboard else b'@ECHO OFF\r\nC:\\CORETEST.COM '+(b'Y' if himem else b'W' if warm else b'H')+b'\r\n')
        f.replace(out,'CONFIG.B~K',com.read_bytes(),rename=b'CORETESTCOM')
    f.vhd.file.close()
    f=Fat12(source)
    f.replace(floppy,'CONFIG.SYS',(b'DEVICE=A:\\HIMEM.SYS /TESTMEM:OFF\r\n' if himem else b'')+b'FILES=30\r\nBUFFERS=20\r\nSTACKS=9,256\r\n')
    f.replace(floppy,'DEBUG.EXE',com.read_bytes(),rename=b'CORETESTCOM')
    if keyboard:
        f.replace(floppy,'QBASIC.EXE',emm.read_bytes(),rename=b'EMM386  EXE')
        f.replace(floppy,'MEM.EXE',(folder/'kiot.com').read_bytes(),rename=b'KIOT    COM')
    f.replace(floppy,'AUTOEXEC.BAT',b'@ECHO OFF\r\n'+(b'COPY A:\\EMM386.EXE C:\\EMM386.EXE >NUL\r\nCOPY A:\\KIOT.COM C:\\KIOT.COM >NUL\r\n' if keyboard else b'')+b'A:\\SYS.COM C: >C:\\SYS.LOG\r\nC:\\CORETEST.COM '+(b'X' if himem else b'F')+b'\r\n')
    cfg=(vm/'86box.cfg').read_text().replace('hdd_01_fn = disk-0.img',f'hdd_01_fn = {disk.as_posix()}').replace('63, 16, 65','63, 16, 3941')
    cfg=cfg.replace('[Floppy and CD-ROM drives]',f'[Floppy and CD-ROM drives]\nfdd_01_fn = {floppy.as_posix()}')
    if swap:
        cfg=cfg.replace('fdd_01_fn','fdd_02_fn').replace('fdd_01_type = 35_2hd','fdd_01_type = none').replace('fdd_02_type = none','fdd_02_type = 35_2hd')
    (vm/'86box.cfg').write_text(cfg)
    (vm/'nvr'/(em['machine']+'.nvr')).write_bytes(nvram(0x40,boot=1,l1=warm,swap=swap))
    result=run_86box(vm,roms,timeout=110)
    assert result==0x67,('DOS6.22 SYS and native HDD/FDD read/write',result)
    f=Fat16(disk)
    assert b'System transferred' in f.read('SYS.LOG')
    for n in ('IO.SYS','MSDOS.SYS','COMMAND.COM'):assert f.read(n)==Fat12(source).read(n)
    f.vhd.file.close()
    (vm/'86box.cfg').write_text(cfg if himem or keyboard else '\n'.join(line for line in cfg.splitlines() if not line.startswith(('fdd_01_fn','fdd_02_fn')))+'\n')
    (vm/'nvr'/(em['machine']+'.nvr')).write_bytes(nvram(0x40,boot=2,l1=warm,swap=swap))
    result=run_86box(vm,roms,timeout=150)
    assert result==(0x68 if keyboard else 0x67),('DOS6.22 HDD boot/keyboard IRQ1 and native services',result)
    dma_evidence=None
    if keyboard:
        f=Fat16(disk);raw=f.vhd.sector(1);f.vhd.file.close()
        assert raw[:8]==b'DMA/EMM1'
        count=struct.unpack_from('<H',raw,8)[0]
        assert count==5,count
        dma_evidence={'completed_floppy_transactions':count,'transactions':'save/write/read/restore/read under loaded EMM386'}
    print('DOS6.22 floppy, SYS, HDD'+('/EMM386 keyboard' if keyboard else '/Ctrl-Alt-Delete warm' if warm else '')+f': {result:02X}',flush=True)
    return {'name':'DOS6.22-HIMEM/EMM386/IRQ1/timer/console/LED' if keyboard else 'DOS6.22-HIMEM/XMS/HMA' if himem else 'DOS6.22-warm' if warm else 'DOS6.22','exit':result,'swap':swap,'rom_sha256':r['sha256'],'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'DMA_EMM386':dma_evidence}

def cd():
    _,config=configuration(PORT)
    em=config['emulator']
    vm,roms,r=fixture('core-cd-secondary',{},cdroms=(2,))
    boot=vm.parent/'cd-boot.bin';assemble(PORT/'tests/core-cd.asm',boot,[PORT/'tests'])
    iso=disc(media=0,count=1);iso[21*2048:21*2048+512]=boot.read_bytes()
    media=vm.parent/'cd.iso';media.write_bytes(iso)
    cfg=(vm/'86box.cfg').read_text().replace('cdrom_01_parameters = 1, atapi',f'cdrom_01_parameters = 1, atapi\ncdrom_01_host_drive = 200\ncdrom_01_image_path = {media.as_posix()}')
    (vm/'86box.cfg').write_text(cfg);(vm/'nvr'/(em['machine']+'.nvr')).write_bytes(nvram(boot=3))
    actual=run_86box(vm,roms,timeout=100)
    assert actual==0x68,('Secondary El Torito load/status',actual)
    print('Secondary native El Torito: 68',flush=True)
    return {'name':'secondary-El-Torito','exit':actual,'rom_sha256':r['sha256'],'media':'synthetic no-emulation fixture'}

def floppy_warm():
    """Boot real DOS/HIMEM twice through IRQ1 Ctrl-Alt-Delete."""
    _,config=configuration(PORT)
    em=config['emulator']
    source=REPOSITORY/'tools/deps/ms-dos/6.22-boot.ima'
    assert hashlib.sha256(source.read_bytes()).hexdigest()=='9d620dc19afb29a77324bc0e262ceffeac918632ff2a0ccea685427ff85e27cd'
    vm,roms,r=fixture('core-floppy-warm-himem',{},types=0x40)
    folder=vm.parent
    assemble(PORT/'tests/core-floppy-warm.asm',folder/'warm.com',[PORT/'tests'])
    f=Fat12(source)
    f.replace(folder/'dos622.img','DEBUG.EXE',(folder/'warm.com').read_bytes(),rename=b'WARM    COM')
    f.replace(folder/'dos622.img','CONFIG.SYS',b'DEVICE=A:\\HIMEM.SYS /TESTMEM:OFF\r\nFILES=30\r\nBUFFERS=30\r\nSTACKS=9,256\r\nLASTDRIVE=Z\r\n')
    f.replace(folder/'dos622.img','AUTOEXEC.BAT',b'@ECHO OFF\r\nA:\\WARM.COM\r\n')
    cfg=(vm/'86box.cfg').read_text().replace('[Floppy and CD-ROM drives]',f'[Floppy and CD-ROM drives]\nfdd_01_fn = {(folder/"dos622.img").as_posix()}')
    (vm/'86box.cfg').write_text(cfg)
    n=nvram(0x40,boot=1)
    chip=bytes((0xF0,1,0,0x20,0,0,0,1,0,0))+bytes(14)
    n[0x69]=0x56;n[0x6A]=(-0x56-sum(chip))&255
    n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
    (vm/'nvr'/(em['machine']+'.nvr')).write_bytes(n)
    result=run_86box(vm,roms,timeout=120)
    assert result==0x67,('DOS6.22 floppy/HIMEM Ctrl-Alt-Delete warm reset',result)
    print(f'DOS6.22 floppy/HIMEM Ctrl-Alt-Delete warm: {result:02X}',flush=True)
    return {'name':'DOS6.22-floppy-HIMEM-warm','exit':result,'rom_sha256':r['sha256']}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=['all','cold','boot','warm','setup','policy','clock','policy-clock','policy-clock-no-errors','devices','no-media','option-roms','ram','dos','floppy-swap','floppy-missing','cd','himem','fdc-capabilities','a20','keyboard-policy','keyboard','keyboard-absent','aux-policy','alternate-ram','cpu','positions'],default='cold')
    args=parser.parse_args();case=args.case
    if case=='all':
        for case in ALL_CASES:subprocess.run([sys.executable,'-B',str(Path(__file__).resolve()),'--case',case],check=True)
        return
    results=[];flags=('EMULATOR_POST_SUMMARY_TEST','EMULATOR_SETUP_TEST')
    if case in ('cold','boot','devices'):
        results.append(execute('core-primary',{0:65}))
        if case!='cold':
            results.append(execute('core-secondary',{2:65},dirty_display=True))
            results.append(execute('core-atapi-first',{2:65},cdroms=(0,)))
    elif case in ('setup','clock'):
        results.append(execute('core-setup',{0:65},types=0x40,expected=0x67,defines=flags))
        results.append(execute('core-save',{0:65},types=0x40,expected=0x67,defines=flags+('EMULATOR_SETUP_SAVE_FIELDS',)))
    elif case=='policy':results.append(execute('core-recovery',{0:65},expected=0x67,valid=False,clock='loss',defines=flags+('EMULATOR_SETUP_BAD_CMOS','EMULATOR_SETUP_RECOVERY')))
    elif case=='policy-clock':results.append(execute('core-powerloss',{0:65},expected=0x67,clock='loss',defines=flags+('EMULATOR_SETUP_POWERLOSS',)))
    elif case=='policy-clock-no-errors':results.append(execute('core-clock-no-errors',{0:65},clock='loss',no_errors_clock=True,defines=('EMULATOR_CLOCK_NO_ERRORS',)))
    elif case=='ram':results.append(execute('core-ram-skip',{0:65},defines=('EMULATOR_RAM_SKIP_TEST',),ram_flags=2))
    elif case=='option-roms':
        results.append(execute('core-dirty-vga',{0:65},dirty_display=True))
        results.append(execute('core-c000-entry',{0:65},dirty_vga_init=True))
    elif case=='no-media':
        results.append(execute('core-no-media',{},expected=0x71,defines=('EMULATOR_POST_SUMMARY_TEST','EMULATOR_BOOT_RETRY_EXIT=113')))
        results.append(execute('core-failed-provider',{0:65},expected=0x74,failed_provider=True,
            defines=('EMULATOR_POST_SUMMARY_TEST','EMULATOR_BOOT_FAILURE_INT18','EMULATOR_BOOT_RETRY_EXIT=116')))
    elif case=='cd':results.append(cd())
    elif case=='fdc-capabilities':results.extend(fdc_capabilities())
    elif case=='a20':results.append(a20())
    elif case=='keyboard-policy':results.extend(keyboard_policy())
    elif case=='aux-policy':results.append(aux_policy())
    elif case=='alternate-ram':results.append(execute('core-8m',{0:65},ram=8192))
    elif case=='cpu':results.append(execute('core-intel-486',{0:65},cpu={'cpu_family':'i486dx','cpu_speed':33333333,'cpu_multi':1}))
    elif case=='positions':
        results.append(execute('core-primary-slave',{1:65}))
        results.append(execute('core-secondary-slave',{3:65}))
        # Installed86Box reports CHS-only for small <=16-head disks. Its
        # >=1024-cylinder LBA device leaves Auto geometry to the loaded BPB.
        results.append(execute('core-bpb-16',{1:1024},bpb_heads=16))
        results.append(execute('core-bpb-32',{1:1024},bpb_heads=32))
    elif case=='floppy-missing':results.extend(floppy_missing())
    elif case=='keyboard-absent':
        from keyboard_absence import check
        results.extend(check(PORT,build,nvram))
    else:
        results.append(dos(warm=case=='warm',swap=case=='floppy-swap',himem=case=='himem',keyboard=case=='keyboard'))
        if case=='warm':results.append(floppy_warm())
    record=REPOSITORY/'.agent/test-results/m919-post.json'
    record.parent.mkdir(parents=True,exist_ok=True)
    data=json.loads(record.read_text()) if record.exists() else {}
    data.setdefault('physical_iteration',{}).setdefault('full_core_checks',{})[args.case]=results
    record.write_text(json.dumps(data,indent=2)+'\n')

if __name__=='__main__':main()
