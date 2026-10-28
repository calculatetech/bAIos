"""Run PB430 production firmware with independent terminal observers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import time
import traceback

PORT = Path(__file__).resolve().parents[1]
REPOSITORY = PORT.parent
sys.path.insert(0, str(REPOSITORY))
sys.path.insert(0, str(PORT / 'tools'))
from build import run as build
from shared.tools.emulator import run_86box
from shared.tools.vga_text import render
from shared.tools.cd_fixture import disc
from shared.tools.ram_proof import Listing

EMULATOR = PORT.parent/'tools/deps/86box-b10408/86Box.exe'
CASES = ('image','native','display','chipset-settings','diagnostics-input','reset','memory',
         'settings-load','clock','setup','shadow','cache','serial','parallel','floppy',
         'disk-services','cd','option-roms','boot-order','ram','build-hygiene','setup-policy','boot-defaults','vga60','slow-refresh','fast-writes')


def assemble(source, output, includes=()):
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    cmd = [nasm, '-w+error', '-f', 'bin']
    for folder in includes:
        cmd += ['-I', str(folder)+'/']
    subprocess.run(cmd + ['-o', str(output), str(source)], check=True)


def nvram():
    raw = bytearray(256)
    for index,value in {0:6,2:7,4:8,6:1,7:0x14,8:0x10,9:0x26,10:0x26,11:2,13:0x80,0x32:0x20}.items():
        raw[index] = value
    raw[0x10] = 0
    raw[0x2E:0x30] = struct.pack('>H',sum(raw[0x10:0x2E]))
    raw[0x38:0x40] = bytes((ord('B'),ord('8'),5,0x13,2,0,1,0))
    raw[0x3D] = (-sum(raw[0x38:0x3D])-raw[0x10]-raw[0x3E]) & 255
    return raw


def _native(name='native', ram=16384, defines=(), positions=(0,), expected=0x60, types=0, cmos=None, dirty_vga=False, dirty_option=False, floppy_media=False, swap=False, cdroms=None, boot_source="native-boot.asm", disk_services=False, cd_media=0, ram_flags=4, runtime_input=False, cpu_family="i486dx", fpu=True, external_video=False, shadow_policy=None, cache_expected="512 KB", option_source=None, option_blob=None, rom_counts=None, warnings=0, mouse="none", missing_floppy=False,saved_ads=None,preserve_boot_order=False,bootable_floppy=False,expected_boot_unit=0x80,vga60=True,saved_refresh=None):
    result = build('build/tests/results/'+name+'/image', defines,vga60=vga60)
    folder = PORT/'build/tests/results'/name
    vm,roms = folder/'vm',folder/'roms'
    vm.mkdir(parents=True,exist_ok=True)
    target = roms/'machines/pb430/PB430-Dump-2.bin'
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(result['path'],target)
    if external_video:
        external=roms/'video/cirruslogic/cl5422.bin';external.parent.mkdir(parents=True,exist_ok=True);external.write_bytes((PORT/'reference/pb430-m27c1001.bin').read_bytes()[:32768])
    cdroms=cdroms or {}
    cd_slot=next((slot for slot,bootable in cdroms.items() if bootable),0)
    test_listing=Listing(Path(result['path']).with_suffix('.lst'))
    int13_offset=test_listing.symbol('int13')
    restore_offset=test_listing.symbol('core_ram_restore_check') if 'EMULATOR_RAM_SKIP_TEST' in defines else 0
    (folder/'test-configuration.inc').write_text(f'%define TEST_CHIP_REFRESH_CHECK {int(saved_refresh is not None)}\n%define TEST_CHIP_REFRESH_VALUE {3 if saved_refresh else 0}\n%define TEST_VGA60 {int(vga60 and not external_video)}\n%define TEST_EXPECT_BOOT_UNIT {expected_boot_unit}\n%define TEST_EXPECT_ERROR {warnings}\n%define TEST_OPTION_SCAN {int(rom_counts is not None)}\n%define TEST_ROM_ERROR {warnings}\n%define TEST_ROM_COUNT0 {rom_counts[0] if rom_counts else 0}\n%define TEST_ROM_COUNT1 {rom_counts[1] if rom_counts else 0}\n%define TEST_ROM_COUNT2 {rom_counts[2] if rom_counts else 0}\n%define TEST_ROM_COUNT3 {rom_counts[3] if rom_counts else 0}\n%define TEST_BOOT_PROVIDER {int(option_source is not None)}\n%define TEST_CHIP_ADS_CHECK {int(saved_ads is not None)}\n%define TEST_CHIP_ADS_VALUE {0x80 if saved_ads else 0}\n%define TEST_SHADOW_CHECK {int(shadow_policy is not None)}\n%define TEST_SHADOW_MASK {((int(shadow_policy[0])<<4)|int(shadow_policy[1])) if shadow_policy else 0}\n%define TEST_ONBOARD_ORIGIN {int(shadow_policy[2]) if shadow_policy else 0}\n%define TEST_RAM_FLAGS {ram_flags}\n%define TEST_RAM_OBSERVER {int("EMULATOR_RAM_SKIP_TEST" in defines)}\n%define TEST_RUNTIME_INPUT {int(runtime_input)}\n%define TEST_RAM_KIB {ram}\n%define TEST_DIRTY_VGA {int(dirty_vga)}\n%define TEST_DIRTY_OPTION {int(dirty_option)}\n%define TEST_FLOPPY_B {int(bool(types&15))}\n%define TEST_FLOPPY_COUNT {2 if types&15 else 1}\n%define TEST_FLOPPY {int(floppy_media)}\n%define TEST_FLOPPY_WORD {0x4242 if swap else 0x4141}\n%define TEST_FLOPPY_WORD_B {0x4141 if swap else 0x4242}\n%define TEST_DISK_UNITS {len(positions)}\n%define TEST_DISK_FIRST {0x31564C53 if positions and positions[0]==1 else 0x41544144}\n%define TEST_RAM_RESTORE_OFFSET {restore_offset}\n%define TEST_DISK_SERVICES {int(disk_services)}\n%define TEST_CD_MEDIA {cd_media}\n%define TEST_CD_SLOT {cd_slot}\n%define TEST_INT13_OFFSET {int13_offset}\n')
    assemble(PORT/'tests'/boot_source,folder/'boot.bin',[folder,PORT/'tests'])
    if dirty_vga:
        vga=bytearray(target.read_bytes());original=6+struct.unpack_from('<H',vga,4)[0]
        (folder/'vga-entry.inc').write_text(f'%define ORIGINAL_VGA_ENTRY {original}\n')
        assemble(PORT/'tests/core-vga-entry.asm',folder/'vga-entry.bin',[folder,PORT/'tests'])
        wrapper=(folder/'vga-entry.bin').read_bytes()
        assert len(wrapper)<=0x12C-0xE4 and vga[0xE4:0xE4+len(wrapper)]==bytes(len(wrapper))
        vga[0xE4:0xE4+len(wrapper)]=wrapper;struct.pack_into('<H',vga,4,0xE4-6)
        vga[32767]=(vga[32767]-sum(vga[:32768]))&255
        target.write_bytes(vga)
    net=''
    if dirty_option or option_source or option_blob is not None:
        if option_blob is None:
            assemble(PORT/'tests'/(option_source or 'core-option-rom.asm'),folder/'observer.bin',[PORT/'tests'])
            blob=bytearray(32768);observer=bytearray((folder/'observer.bin').read_bytes());observer[-1]=(-sum(observer))&255
            blob[:len(observer)]=observer
        else:blob=bytearray(option_blob);assert len(blob)==32768
        op=roms/'network/ne2000/ne2000.rom';op.parent.mkdir(parents=True,exist_ok=True);op.write_bytes(blob)
        net='[Network]\nnet_01_card = novell_ne2k\nnet_01_link = 506\n[Novell NE2000 #1]\nbase = 0300\nirq = 3\nbios_addr = C8000\n'
    floppy=''
    if floppy_media:
        for i,marker in enumerate((0x4141,0x4242),1):
            payload=bytearray(80*2*18*512);struct.pack_into('<H',payload,512,marker)
            if bootable_floppy:payload[:512]=(folder/'boot.bin').read_bytes()
            fp=vm/f'floppy-{i}.img';fp.write_bytes(payload)
            floppy+=f'fdd_{i:02}_fn = {fp.name}\nfdd_{i:02}_writeprot = 0\n'
    disks = ''
    for i,position in enumerate(positions,1):
        path = vm/f'disk-{position}.img'
        with path.open('wb') as stream:
            stream.write((folder/'boot.bin').read_bytes())
            stream.truncate(32*16*63*512)
            stream.seek(17*512);stream.write(b'DATA' if position==0 else b'SLV1')
        disks += f'hdd_{i:02}_fn = {path.name}\nhdd_{i:02}_parameters = 63, 16, 32, 0, ide\nhdd_{i:02}_ide_channel = 0:{position}\nhdd_{i:02}_speed = ramdisk\n'
    optical=''
    for i,(slot,bootable) in enumerate(cdroms.items(),1):
        iso=disc(media=cd_media,count=1) if bootable else bytearray(64*2048)
        if bootable:iso[21*2048:21*2048+512]=(folder/'boot.bin').read_bytes()
        media=vm/f'cd-{slot}.iso';media.write_bytes(iso)
        optical+=f'cdrom_{i:02}_parameters = 1, atapi\ncdrom_{i:02}_ide_channel = 0:{slot}\ncdrom_{i:02}_type = 86cd\ncdrom_{i:02}_host_drive = 200\ncdrom_{i:02}_image_path = {media.as_posix()}\n'
    (vm/'86box.cfg').write_text(f'''[General]
vid_renderer = qt_software
[Machine]
machine = pb430
cpu_family = {cpu_family}
cpu_speed = 33333333
cpu_multi = 1
cpu_use_dynarec = 0
fpu_type = {'internal' if fpu else 'none'}
mem_size = {ram}
time_sync = disabled
[Video]
gfxcard = {'cl_gd5422_migrated_isa' if external_video else 'internal'}
[Cirrus Logic GD5422 (ISA)]
bios = cl_gd5422_isa
memory = 1024
[Input devices]
keyboard_type = keyboard_ps2
mouse_type = {mouse}
[Hard disks]
{disks}
[Floppy and CD-ROM drives]
fdd_01_type = {'35_2hd' if types>>4 and not missing_floppy else 'none'}
fdd_02_type = {'35_2hd' if types&15 else 'none'}
{floppy}
{optical}
{net}
[Other peripherals]
postcard_enabled = 1
unittester_enabled = 1
[86Box Unit Tester]
exit_enabled = 1
''')
    (vm/'nvr').mkdir(exist_ok=True)
    n=nvram() if cmos is None else bytearray(cmos)
    n[0x10]=types
    if swap:n[0x3B]|=4
    if cdroms and not preserve_boot_order:
        n[0x3C]=3;n[0x3E]=2;n[0x3F]=0
    n[0x2E:0x30]=struct.pack('>H',sum(n[0x10:0x2E]))
    n[0x3D]=(-sum(n[0x38:0x3D])-types-(sum(n[0x3E:0x40]) if n[0x3A]>=2 else 0))&255
    (vm/'nvr/pb430.nvr').write_bytes(n)
    if not EMULATOR.is_file():
        raise FileNotFoundError('PB430 requires the recorded PB430-capable86Box build10408 in build/deps.')
    actual = run_86box(vm,roms,timeout=100,executable=EMULATOR)
    assert actual == expected, (name,hex(actual),str(vm))
    if expected != 0x60 or any(flag.startswith('PB430_TRACE_STAGE=') for flag in defines):
        return {'terminal':actual,'image':result}
    raw = (vm/f'disk-{positions[0]}.img').read_bytes()[512:17*512]
    cells,font = raw[:4000],raw[4096:8192]
    assert len(cells)==4000 and len(font)==4096 and any(font)
    if shadow_policy is not None:
        visible=(vm/f'disk-{positions[0]}.img').read_bytes()[17*512:145*512]
        assert visible==Path(result['path']).read_bytes()[65536:],'Visible F000 bytes changed across staged shadow transitions'
    from frame_proof import check
    frame_oracle=check(cells,font,PORT/'reference/pb430-m27c1001.bin',ram,positions,types,cache=cache_expected,fpu=fpu,warnings=warnings)
    render(cells,font,folder/'display.png')
    (folder/'cells.bin').write_bytes(cells)
    (folder/'font.bin').write_bytes(font)
    return {'terminal':actual,'ram_kib':ram,'positions':positions,'image':result,'frame_oracle':frame_oracle,'frame_sha256':hashlib.sha256(cells+font).hexdigest()}


def native(name='native',**options):
    folder=PORT/'build/tests/results'/name
    marker=folder/'.retain-diagnosis'
    try:
        result=_native(name,**options)
    except Exception as error:
        folder.mkdir(parents=True,exist_ok=True)
        marker.write_text(f'{type(error).__name__}: {error}\n',encoding='utf-8')
        raise
    marker.unlink(missing_ok=True)
    return result


def repair_checksum(n):
    n[0x2E:0x30]=struct.pack('>H',sum(n[0x10:0x2E]))
    n[0x3D]=(-sum(n[0x38:0x3D])-n[0x10]-sum(n[0x3E:0x40]))&255
    return n


def chipset_record(n,manual=0,cpu=1,l2=1,system=1,video=1,ads=0,fast=0,slow=0,writes=0,ras_off=0,c800=0,d000=0,e000=0,shadow_uncached=0):
    chip=bytes((manual,cpu,l2,system,video,ads,fast,slow,writes))+bytes(15)
    if any((ras_off,c800,d000,e000,shadow_uncached)):
        chip=bytes((manual,cpu,l2,system,video,ads,fast,slow,writes,ras_off,c800,d000,e000,shadow_uncached,2,4 if writes else 0x15,0,0,0,0,0,0x10,0,0xA3))
    n[0x69]=0xC2;n[0x6A]=(-0xC2-sum(chip))&255;n[0x6B:0x80]=chip[:21];n[0x33:0x36]=chip[21:]
    return n


def image_checks(image):
    from build import validate
    raw=Path(image).read_bytes();folder=PORT/'build/tests/results/image';folder.mkdir(parents=True,exist_ok=True)
    result={'valid':validate(image),'rejected':[]}
    result['cli_selections']=[]
    for arguments,vga60,relative,clock in ((['--output','build/tests/results/image/default'],True,'build/tests/results/image/default',60),
            (['--stock-vga','--output','build/tests/results/image/stock'],False,'build/tests/results/image/stock',60),
            (['--vga50','--output','build/tests/results/image/vga50-default'],True,'build/tests/results/image/vga50-default',50),
            (['--vga60','--output','build/tests/results/image/vga60'],True,'build/tests/results/image/vga60',60),
            (['--vga50','--output','build/tests/results/image/vga50'],True,'build/tests/results/image/vga50',50)):
        output=subprocess.check_output([sys.executable,'-B',str(PORT/'tools/build.py'),*arguments],cwd=REPOSITORY,text=True)
        delivered=json.loads(output)
        selected=PORT/relative/'baios-pb430.bin'
        assert Path(delivered['path'])==selected
        checked=validate(selected,vga60=vga60,vga_clock=clock)
        assert checked['size']==131072
        if vga60 and clock==60:assert selected.read_bytes()==raw
        if clock==50:
            pair=selected.read_bytes()
            assert [i for i,(a,b) in enumerate(zip(raw,pair)) if a!=b]==[0x08E7,0x7FFF]
            assert raw[0x08E7]==0x22 and pair[0x08E7]==0x1C
            assert raw[65536:]==pair[65536:] and sum(raw[:32768])%256==sum(pair[:32768])%256==0
        result['cli_selections'].append({'arguments':arguments,'checked':checked})
    from shared.tools.ram_proof import Listing
    for flag, name in (('--cache-burst','cache-burst'),('--interleave','interleave')):
        output=subprocess.check_output([sys.executable,'-B',str(PORT/'tools/build.py'),flag],cwd=REPOSITORY,text=True)
        delivered=json.loads(output)
        selected=PORT/'build/diagnostics'/name/'baios-pb430.bin'
        assert Path(delivered['path'])==selected
        checked=validate(selected)
        data=selected.read_bytes();listing=Listing(selected.with_suffix('.lst'))
        assert data[:65536]==raw[:65536] and data[65536:]!=raw[65536:]
        assert data[0x1F065:0x1F070]==bytes.fromhex('80fc1d7305ea972800c0cf')
        assert 0xF070 < listing.symbol('pb430_rom_extensions_end') <= listing.symbol('cd_boot_clear') < listing.symbol('cd_boot') < listing.symbol('rom_code_end') < 0xFFEF
        result['cli_selections'].append({'arguments':[flag],'checked':checked})
    for kind in ('size','vga','padding','reset','checksum'):
        bad=bytearray(raw)
        if kind=='size':bad.pop()
        elif kind=='vga':bad[12]^=1
        elif kind=='padding':bad[40000]=0
        elif kind=='reset':bad[-15]^=1;bad[-17]=(-sum(bad[65536:-17])-sum(bad[-16:]))&255
        else:bad[70000]^=1
        path=folder/(kind+'.bin');path.write_bytes(bad)
        try:validate(path)
        except (AssertionError,ValueError):result['rejected'].append(kind)
        else:raise AssertionError('Invalid image accepted: '+kind)
    assert len(result['rejected'])==5
    return result


def memory_checks(image):
    from memory_proof import run
    cases=(((1,0,0,0),1,0,0),((2,0,0,0),2,0x30,0),((3,0,0,0),4,0x20,0),
           ((4,0,0,0),3,0x10,0),((8,0,0,0),4,0x20,0),((16,0,0,0),4,0x20,0),
           ((2,2,0,0),0x22,0x31,0),((16,16,16,16),0x4444,0x29,0),
           ((4,4,1,0),0x133,0x15,0x22),((0,4,0,0),0x30,0x10,0x0D),
           ((8,2,0,0),0x24,0x37,0x0D),((8,2,4,0),0,None,0))
    rows=[]
    for banks,pattern,mapping,routing in cases:
        rows.append(run(image,banks,pattern,mapping,routing))
        print('MEMORY banks '+str(banks)+' passed',flush=True)
        (PORT/'build/tests/results/memory-bank-results.json').write_text(json.dumps(rows,indent=2))
    rows += [run(image,jumper=jumper) for jumper in range(8)]
    rows += [native('memory-native-'+str(ram),ram=ram) for ram in (4096,8192,32768,65536)]
    return rows


def diagnostic_checks(image):
    import scenarios
    rows=scenarios.diagnostics(image,nvram)+scenarios.diagnostic_callbacks(image,nvram)+[scenarios.input_irq_policy(image,nvram)]
    for flag in ('KEYBOARD_DIAGNOSTIC','FLOPPY_DIAGNOSTIC','MOUSE_DIAGNOSTIC'):
        rows.append(native('diagnostic-'+flag.lower(),defines=(flag,),vga60=False))
    rows.append(native('diagnostic-mouse-present',boot_source='native-mouse.asm',expected=0x65,mouse='ps2',defines=('MOUSE_DIAGNOSTIC',),vga60=False))
    return rows


def floppy_checks():
    from scenarios import ports_record
    from core_proof import ACC
    n=nvram();n[0x10]=0x50;n[0x3B]=(n[0x3B]&~0x18)|8
    m=ACC(PORT/'build/baios-pb430.bin',repair_checksum(n));m.continue_reset=True;m.open([0x44,28])
    assert m.cpu.mem_read(m.base+0x1008,2)==b'\x80\0'
    ax,flags=m.public(0x13,0x0201,bx=0x8000,cx=1)
    assert ax==0x100 and flags&1 and m.cpu.mem_read(0x441,1)==b'\x01'
    rows=[{'legacy_version':0x80,'enhanced':False,'unsupported_2880_int13_ax':ax,'cf':True,'actual_save_reset_probe_service':True}]
    # Both floppy payload checks need the boot-sector space used by VGA60 probes.
    rows += [native('floppy-swap-'+str(swap),floppy_media=True,types=0x44,swap=swap,vga60=False) for swap in (False,True)]
    for disabled in (False,True):
        n=nvram();n[0x3B]=(n[0x3B]&~0x18)|8
        if disabled:ports_record(n,(1,2,1,2,0,0,1,1))
        name='floppy-'+('disabled' if disabled else 'absent')
        rows.append(native(name,cmos=n,types=0x40,missing_floppy=True,boot_source='native-floppy-failure.asm',expected=0x65,defines=('FLOPPY_DIAGNOSTIC',),warnings=0 if disabled else 2,vga60=False))
        raw=(PORT/'build/tests/results'/name/'vm/disk-0.img').read_bytes()[17*512:18*512]
        ax,flags=struct.unpack_from('<HH',raw,0x50)
        assert ax==(0x100 if disabled else 0x4000)
        rows[-1]['int13_error_ax']=ax
    return rows


def option_checks(image):
    import scenarios
    rows=scenarios.option_roms(image,nvram)+[scenarios.bootstrap_path(image,nvram)];rom=scenarios.rom_inputs(image)
    blob=bytearray(32768);blob[:2048]=rom(0);blob[4096:6144]=rom(1);blob[16384:18432]=rom(2)
    rows.append(native('rom-native-multiple',option_blob=blob,rom_counts=(1,1,1,0)))
    blob=bytearray(32768);bad=rom(0);bad[-1]^=1;blob[:2048]=bad;blob[28672:30720]=rom(1)
    n=nvram();n[0x3B]=(n[0x3B]&~0x18)|8
    rows.append(native('rom-native-bad-later',cmos=repair_checksum(n),option_blob=blob,rom_counts=(0,1,0,0),warnings=16))
    return rows


def boot_checks(image):
    import scenarios
    rows=[native('boot-first')]
    for source in ('core-return-boot.asm','core-int18-boot.asm'):
        n=nvram();n[0x3C]=4;n[0x3E]=2
        rows.append(native('boot-'+source[:-4],option_source=source,cmos=repair_checksum(n)))
    n=nvram();n[0x3C]=1;n[0x3E]=2;n[0x3B]=(n[0x3B]&~0x18)|8
    rows.append(native('boot-failed-floppy-then-disk',types=0x40,missing_floppy=True,cmos=repair_checksum(n),warnings=2))
    # Boot-retry instrumentation needs the space below VGA60's fixed F065 entry.
    rows.append(native('boot-fresh-key-retry',positions=(),defines=('PB430_BOOT_RETRY_PROOF','EMULATOR_BOOT_RETRY_EXIT=0x71'),expected=0x71,vga60=False))
    n=nvram();n[0x3B]=9;n[0x3C]=1;n[0x3E]=0;n[0x3F]=0
    rows.append(native('boot-stale-signed-buffer',positions=(),cmos=repair_checksum(n),types=0x40,missing_floppy=True,defines=('EMULATOR_TEST','EMULATOR_BOOT_STALE','PB430_BOOT_RETRY_PROOF','EMULATOR_BOOT_RETRY_EXIT=0x71'),expected=0x71,vga60=False))
    rows.append(scenarios.bootstrap_path(image,nvram,inactive=True))
    return rows


def ram_checks(image):
    from shared.tools.ram_proof import run,constants
    config=json.loads((PORT/'port.json').read_text());state=constants(REPOSITORY/'shared/src/pc/state.inc')
    state.update(constants(REPOSITORY/'shared/src/setup/layout.inc'))
    state['BOARD_POST_RAM_ROW']=constants(PORT/'src/hardware/board-definition.inc')['BOARD_POST_RAM_ROW']
    rows=[run(image,config['rom'],state,ebda=0x9E00,kib=2049,decode=True)]
    for key in ('esc','delete'):rows.append(run(image,config['rom'],state,ebda=0x9E00,kib=2049,input_case=key,coverage=False))
    rows.append(run(image,config['rom'],state,ebda=0x9E00,kib=2049,fault=(0x10000,'first'),defaults=True))
    rows.append(native('ram-pause',vga60=False,defines=('EMULATOR_RAM_SKIP_TEST','EMULATOR_RAM_PROOF','EMULATOR_RAM_PROOF_PAUSE'),runtime_input=True))
    rows.append(native('ram-esc',vga60=False,defines=('EMULATOR_RAM_SKIP_TEST','EMULATOR_RAM_PROOF'),ram_flags=2,runtime_input=True))
    rows.append(native('ram-delete-save',vga60=False,types=0x40,floppy_media=True,defines=('EMULATOR_RAM_SKIP_TEST','EMULATOR_RAM_PROOF','EMULATOR_RAM_PROOF_DELETE','EMULATOR_SETUP_TEST','EMULATOR_SETUP_SAVE_FIELDS','EMULATOR_RAM_SETUP_BOOT'),runtime_input=True))
    fast=chipset_record(nvram(),fast=1)
    rows.append(native('ram-fast-pause',vga60=False,cmos=fast,defines=('EMULATOR_RAM_SKIP_TEST','EMULATOR_RAM_PROOF','EMULATOR_RAM_PROOF_PAUSE'),runtime_input=True))
    rows.append(native('ram-fast-esc',vga60=False,cmos=fast,defines=('EMULATOR_RAM_SKIP_TEST','EMULATOR_RAM_PROOF'),ram_flags=2,runtime_input=True))
    rows.append(native('ram-fast-delete-save',vga60=False,cmos=fast,types=0x40,floppy_media=True,defines=('EMULATOR_RAM_SKIP_TEST','EMULATOR_RAM_PROOF','EMULATOR_RAM_PROOF_DELETE','EMULATOR_SETUP_TEST','EMULATOR_SETUP_SAVE_FIELDS','EMULATOR_RAM_SETUP_BOOT'),runtime_input=True))
    return rows


def run_case(case,image):
    import scenarios
    if case=='setup-policy':return scenarios.setup_policy(image,nvram)
    if case=='boot-defaults':return scenarios.boot_defaults(image,nvram)
    if case=='image':return image_checks(image)
    if case=='vga60':return native('vga60-display',vga60=True)
    if case=='slow-refresh':return scenarios.slow_refresh(image,nvram)
    if case=='fast-writes':return scenarios.fast_writes(image,nvram)
    if case=='native':
        from inventory_proof import run
        return {'compiled_inventory':run(Path(image)),'boots':[native(),native('native-sx',cpu_family='i486sx',fpu=False)]}
    if case=='display':return [native('display-clean'),native('display-dirty',dirty_vga=True,dirty_option=True),native('display-setup-return',types=0x40,floppy_media=True,defines=('EMULATOR_SETUP_TEST','EMULATOR_RAM_SETUP_BOOT'))]
    if case=='chipset-settings':return scenarios.chipset(image,nvram)
    if case=='diagnostics-input':return diagnostic_checks(image)
    if case=='reset':
        from memory_proof import run
        return scenarios.reset(image,nvram)+scenarios.reset_dispatch(image,nvram)+scenarios.warm_boot_device(image,nvram)+[run(image,warm_marker=True,sys_flag=flag) for flag in (4,0)]+[native('reset-a20-handoff',types=0x40,floppy_media=True,boot_source='native-a20.asm',defines=('EMULATOR_SETUP_TEST','EMULATOR_SETUP_SAVE_FIELDS','EMULATOR_RAM_SETUP_BOOT')),native('reset-disk-warm',boot_source='native-warm-boot.asm',expected=0x67)]
    if case=='memory':return memory_checks(image)
    if case=='settings-load':return scenarios.settings_load(image,nvram)
    if case=='clock':return scenarios.clock(image,nvram)
    if case=='setup':return scenarios.setup_actions(image,nvram)+[native('setup-edit-discard',types=0x40,floppy_media=True,defines=('EMULATOR_SETUP_TEST',),expected=0x67),native('setup-save-warm',types=0x40,floppy_media=True,defines=('EMULATOR_SETUP_TEST','EMULATOR_SETUP_SAVE_FIELDS','EMULATOR_RAM_SETUP_BOOT'))]
    if case=='shadow':return scenarios.shadow(image,nvram)+[native('shadow-'+str(external)+'-'+str(system),cmos=chipset_record(nvram(),manual=1,system=system,video=0),external_video=external,shadow_policy=(system,not external,not external)) for external in (False,True) for system in (0,1)]
    if case=='cache':
        from stock_cache_proof import verify
        from memory_proof import run
        cold=run(image,banks=(1,0,0,0),expected_pattern=1,expected_map=0,cache_kib=512,complete_post=True)
        return {'stock_reference':verify(image,cold),'cold_entry':scenarios.cache_cold_entry(image,nvram),'cold_post':cold,'component':scenarios.cache(image,nvram),'composed':scenarios.cache_composed(image,nvram),'warm_reset':scenarios.cache_warm(image,nvram),'warm_boot_device':scenarios.warm_boot_device(image,nvram),'interrupt_window':scenarios.cache_interrupts(image,nvram),'timing_rows':scenarios.cache_timing_rows(image,nvram)}
    if case=='serial':return scenarios.serial(image,nvram)
    if case=='parallel':return scenarios.parallel(image,nvram)
    if case=='floppy':return floppy_checks()
    if case=='disk-services':return [native('disk-master',boot_source='native-disk.asm',expected=0x65,disk_services=True),native('disk-slave',positions=(1,),boot_source='native-disk.asm',expected=0x65,disk_services=True),native('disk-both',positions=(0,1),boot_source='native-disk.asm',expected=0x65,disk_services=True),scenarios.disabled_ide(image,nvram)]
    if case=='cd':return [native('cd-master',cdroms={0:True},positions=(),boot_source='native-cd.asm',expected=0x68),native('cd-slave-only',cdroms={1:True},positions=(),boot_source='native-cd.asm',expected=0x68),native('cd-later-slave',cdroms={0:False,1:True},positions=(),boot_source='native-cd.asm',expected=0x68),native('cd-unusable',cdroms={0:False},positions=(),defines=('PB430_BOOT_RETRY_PROOF','EMULATOR_BOOT_RETRY_EXIT=0x71'),expected=0x71,vga60=False),native('cd-emulated',cdroms={0:True},positions=(),cd_media=2,boot_source='native-cd.asm',expected=0x68)]
    if case=='option-roms':return option_checks(image)
    if case=='boot-order':return boot_checks(image)
    if case=='ram':return ram_checks(image)
    if case=='build-hygiene':
        from hygiene_proof import run
        return run()
    raise AssertionError(case)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',choices=CASES+('all',),required=True)
    args = parser.parse_args()
    image=build('build/tests/results/current/image')['path'];folder=PORT/'build/tests/results';folder.mkdir(exist_ok=True)
    for case in CASES if args.case=='all' else (args.case,):
        begin=time.monotonic();print('BEGIN '+case,flush=True)
        try:
            result={'case':case,'status':'passed','candidate_sha256':hashlib.sha256(Path(image).read_bytes()).hexdigest(),'result':run_case(case,image),'seconds':round(time.monotonic()-begin,2)}
        except Exception as error:
            (folder/(case+'.json')).write_text(json.dumps({'case':case,'status':'failed','error':str(error),'traceback':traceback.format_exc()},indent=2))
            raise
        output=folder/(case+'.json');output.write_text(json.dumps(result,indent=2)+'\n')
        print(json.dumps({'case':case,'status':'passed','seconds':result['seconds'],'candidate_sha256':result['candidate_sha256'],'result_file':str(output)}),flush=True)


if __name__ == '__main__':
    main()
