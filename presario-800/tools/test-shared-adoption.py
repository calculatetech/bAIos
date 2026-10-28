"""Prove active shared owners and complete retained Presario hardware transactions."""
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tempfile

PORT = Path(__file__).resolve().parents[1]
ROOT = PORT.parent
sys.path.insert(0, str(ROOT))
from shared.tools.ram_proof import Listing
from shared.tools.cpu_proof import check as cpu_check

# Fixed manifest of the reviewed production hardware windows, including all I/O,
# stack accesses and original POST writes. It needs no private ROM or Git history.
WINDOWS = {'startup': {'end': 'enable_cpu_full_speed',
             'length': 1470,
             'sha256': 'a4c5568afee7f6968fbda01420f8355c6475159e43d81fdfccda68473bfca2fa',
             'fixups': [(7, 2, 'absolute', 'startup.normalized'),
                        (549, 2, 'near', 'init_memory'),
                        (562, 2, 'near', 'chipset_memory_prepare'),
                        (565, 2, 'near', 'memory_interleave_options'),
                        (568, 2, 'near', 'chipset_interleave_policy'),
                        (590, 2, 'near', 'chipset_ram_test'),
                        (664, 2, 'near', 'shadow_system_bios'),
                        (726, 2, 'near', 'validate_vga_image'),
                        (754, 2, 'near', 'validate_vga_image'),
                        (777, 2, 'absolute', 'default_iret'),
                        (796, 2, 'absolute', 'int08'),
                        (810, 2, 'absolute', 'chipset_nmi'),
                        (824, 2, 'absolute', 'int09'),
                        (838, 2, 'absolute', 'int0e'),
                        (852, 2, 'absolute', 'default_iret'),
                        (866, 2, 'absolute', 'int11'),
                        (880, 2, 'absolute', 'int12'),
                        (894, 2, 'absolute', 'int13'),
                        (908, 2, 'absolute', 'int15'),
                        (922, 2, 'absolute', 'int16'),
                        (936, 2, 'absolute', 'int18'),
                        (950, 2, 'absolute', 'int19'),
                        (964, 2, 'absolute', 'RTC_INTERRUPT_LABEL'),
                        (978, 2, 'absolute', 'floppy_dpt_1440'),
                        (992, 2, 'absolute', 'int70'),
                        (1006, 2, 'absolute', 'int74'),
                        (1020, 2, 'absolute', 'int75'),
                        (1034, 2, 'absolute', 'int76'),
                        (1139, 2, 'near', 'publish_memory_cmos'),
                        (1142, 2, 'near', 'init_pic_pit'),
                        (1145, 2, 'near', 'init_rtc'),
                        (1148, 2, 'near', 'init_superio'),
                        (1151, 2, 'near', 'init_at_prerequisites'),
                        (1177, 2, 'near', 'video_failed'),
                        (1211, 2, 'near', 'init_keyboard'),
                        (1220, 2, 'near', 'arm_keyboard_runtime'),
                        (1224, 2, 'near', 'keyboard_runtime_failed'),
                        (1233, 2, 'near', 'load_bios_state'),
                        (1248, 2, 'near', 'post_ui_begin'),
                        (1251, 2, 'near', 'settings_load'),
                        (1254, 2, 'near', 'post_numlock_apply'),
                        (1257, 2, 'near', 'post_keyboard_presence'),
                        (1260, 2, 'near', 'chipset_apply'),
                        (1263, 2, 'near', 'publish_memory_cmos'),
                        (1266, 2, 'near', 'chipset_post_recovery_notice'),
                        (1275, 2, 'near', 'post_ui_cache'),
                        (1278, 2, 'near', 'post_early_setup'),
                        (1281, 2, 'near', 'chipset_visible_ram_test'),
                        (1290, 2, 'near', 'post_early_setup'),
                        (1293, 2, 'near', 'post_clock_alert'),
                        (1296, 2, 'near', 'post_early_setup'),
                        (1299, 2, 'near', 'load_bios_state'),
                        (1302, 2, 'near', 'init_peripherals'),
                        (1305, 2, 'near', 'init_floppy'),
                        (1314, 2, 'near', 'post_ui_floppy'),
                        (1317, 2, 'near', 'post_early_setup'),
                        (1320, 2, 'near', 'post_floppy_seek'),
                        (1323, 2, 'near', 'post_early_setup'),
                        (1326, 2, 'near', 'post_keyboard_wait'),
                        (1335, 2, 'near', 'ata_detect_primary'),
                        (1338, 2, 'near', 'post_keyboard_wait'),
                        (1347, 2, 'near', 'post_ui_disks'),
                        (1350, 2, 'near', 'post_early_setup'),
                        (1366, 2, 'near', 'init_mouse'),
                        (1376, 2, 'near', 'init_fpu'),
                        (1385, 2, 'near', 'post_keyboard_wait'),
                        (1388, 2, 'near', 'load_bios_state'),
                        (1399, 2, 'near', 'post_clock_alert'),
                        (1402, 2, 'near', 'setup_post_gate'),
                        (1405, 2, 'near', 'chipset_late_cache'),
                        (1408, 2, 'near', 'post_success_tone'),
                        (1417, 2, 'near', 'post_ui_cache'),
                        (1420, 2, 'near', 'post_ui_roms'),
                        (1423, 2, 'near', 'option_rom_discovery'),
                        (1426, 2, 'near', 'post_debug_summary'),
                        (1429, 2, 'near', 'presario_post_complete'),
                        (1448, 2, 'near', 'hard_halt'),
                        (1459, 2, 'near', 'hard_halt'),
                        (1468, 2, 'near', 'hard_halt')]},
 'enable_cpu_full_speed': {'end': 'init_external_cache',
                           'length': 79,
                           'sha256': 'd171fc66058c6c0542b40c3b25e8427c22b44b246365d02b337490f2d912d381',
                           'fixups': [(45, 2, 'near', 'init_external_cache')]},
 'init_external_cache': {'end': 'init_fpu',
                         'length': 712,
                         'sha256': '5990f424229f7df60a7a6dc9f8b11e3011037f0aa0425bff8c9d0a4c188ea116',
                         'fixups': [(262, 2, 'absolute', 'move_gdtr'),
                                    (273, 2, 'absolute', 'init_external_cache.protected'),
                                    (623, 2, 'absolute', 'init_external_cache.real')]},
 'controlled_defaults_restart': {'end': 'shadow_system_bios',
                                 'length': 25,
                                 'sha256': 'a7bff2db1fa6febb8d25826eb0595b07effda0c64932427d8b2f55da4ba85ca3',
                                 'fixups': [(21, 2, 'absolute', 'startup.controlled_restart')]},
 'shadow_system_bios': {'end': 'validate_vga_image',
                        'length': 102,
                        'sha256': 'cf76787c3e275aba3c9f5101887081f5187eee894a451d71525025bbaf399146',
                        'fixups': [(30, 2, 'absolute', 'shadow_system_bios.staged'),
                                   (85, 2, 'absolute', 'shadow_system_bios.shadowed')]},
 'validate_vga_image': {'end': 'no_disk',
                        'length': 48,
                        'sha256': '291ec603ffdd8127d9da8992968689bf950185375172ff00ca2e497eb1e16ec2',
                        'fixups': []},
 'init_at_prerequisites': {'end': 'kbc_wait_input_clear',
                           'length': 96,
                           'sha256': 'be59bdc96d6ec86e9fbe127ec110f2c076162d439e5b64035147901f514a1d59',
                           'fixups': []},
 'warm_reset': {'end': 'int16',
                'length': 98,
                'sha256': '68b072a3e997f3035e39d8fa5bacf232ebf087e1a602f883ef0eaf93e4024c5a',
                'fixups': [(22, 2, 'near', 'kbc_command'),
                           (27, 2, 'near', 'kbc_wait_input_clear_mr'),
                           (32, 2, 'near', 'kbc_drain'),
                           (51, 2, 'near', 'kbc_command'),
                           (56, 2, 'near', 'kbc_wait_input_clear_mr'),
                           (89, 2, 'absolute', 'startup.warm_start'),
                           (96, 2, 'near', 'keyboard_halt')]},
 'chipset_cpu_policy': {'end': 'chipset_shadows',
                        'length': 67,
                        'sha256': 'c93c350ce78365d51ba03217961933a43a4e5cf8fb4b163c8e559990ccb6f830',
                        'fixups': []},
 'chipset_shadows': {'end': 'chipset_late_cache',
                     'length': 108,
                     'sha256': 'c2e655d7a72649f548b8de4924fde0e9a20a9ba235932bc33ace89d35bfd7d04',
                     'fixups': []},
 'chipset_late_cache': {'end': 'chipset_late_cache_end',
                        'length': 248,
                        'sha256': '50494291c0e0591902468d0c2501938dbe977df3135b5802e5c16a75ce667294',
                        'fixups': [(7, 2, 'near', 'load_bios_state'),
                                   (46, 2, 'near', 'init_external_cache'),
                                   (165, 2, 'near', 'chipset_cpu_policy'),
                                   (168, 2, 'near', 'chipset_runtime_ram_check'),
                                   (175, 2, 'near', 'rtc_read'),
                                   (187, 2, 'near', 'rtc_write'),
                                   (193, 2, 'near', 'rtc_write'),
                                   (204, 2, 'near', 'post_message_cursor'),
                                   (207, 2, 'absolute', 'chipset_cache_retry'),
                                   (210, 2, 'near', 'print_string'),
                                   (213, 2, 'near', 'chipset_recovery_ack'),
                                   (216, 2, 'near', 'controlled_defaults_restart'),
                                   (227, 2, 'near', 'post_message_cursor'),
                                   (230, 2, 'absolute', 'chipset_cache_failure'),
                                   (233, 2, 'near', 'print_string'),
                                   (240, 2, 'near', 'hard_halt')]},
 'init_memory': {'end': 'init_memory_end',
                 'length': 2129,
                 'sha256': '5c772db6a9c128fdb58a1c78ad00cede5c82e4098824139e8436d3e8bb6f0b1a',
                 'fixups': [(58, 2, 'absolute', 'move_gdtr'),
                            (72, 2, 'absolute', 'init_memory.protected'),
                            (90, 2, 'absolute', 'memory_probe_points'),
                            (111, 2, 'absolute', 'memory_probe_points'),
                            (197, 2, 'absolute', 'memory_probe_32_end'),
                            (204, 2, 'absolute', 'memory_probe_16_end'),
                            (211, 2, 'absolute', 'memory_probe_end'),
                            (218, 2, 'absolute', 'memory_probe_single_end'),
                            (227, 2, 'absolute', 'memory_probe_points'),
                            (281, 2, 'absolute', 'memory_probe_32_end'),
                            (290, 2, 'absolute', 'memory_probe_points'),
                            (310, 2, 'absolute', 'memory_probe_points'),
                            (342, 2, 'absolute', 'memory_probe_points'),
                            (362, 2, 'absolute', 'memory_probe_points'),
                            (447, 2, 'absolute', 'memory_probe_16_end'),
                            (480, 2, 'absolute', 'memory_probe_end'),
                            (509, 2, 'absolute', 'memory_probe_single_end'),
                            (556, 2, 'absolute', 'memory_probe_32_end'),
                            (563, 2, 'absolute', 'memory_probe_16_end'),
                            (570, 2, 'absolute', 'memory_probe_end'),
                            (577, 2, 'absolute', 'memory_probe_single_end'),
                            (586, 2, 'absolute', 'memory_probe_points'),
                            (615, 2, 'absolute', 'memory_probe_points'),
                            (751, 2, 'absolute', 'memory_probe_32_end'),
                            (760, 2, 'absolute', 'memory_probe_points'),
                            (780, 2, 'absolute', 'memory_probe_points'),
                            (812, 2, 'absolute', 'memory_probe_points'),
                            (832, 2, 'absolute', 'memory_probe_points'),
                            (917, 2, 'absolute', 'memory_probe_16_end'),
                            (950, 2, 'absolute', 'memory_probe_end'),
                            (979, 2, 'absolute', 'memory_probe_single_end'),
                            (1026, 2, 'absolute', 'memory_probe_32_end'),
                            (1033, 2, 'absolute', 'memory_probe_16_end'),
                            (1040, 2, 'absolute', 'memory_probe_end'),
                            (1047, 2, 'absolute', 'memory_probe_single_end'),
                            (1056, 2, 'absolute', 'memory_probe_points'),
                            (1085, 2, 'absolute', 'memory_probe_points'),
                            (1147, 2, 'absolute', 'memory_probe_32_end'),
                            (1154, 2, 'absolute', 'memory_probe_16_end'),
                            (1161, 2, 'absolute', 'memory_probe_end'),
                            (1168, 2, 'absolute', 'memory_probe_single_end'),
                            (1177, 2, 'absolute', 'memory_probe_points'),
                            (1206, 2, 'absolute', 'memory_probe_points'),
                            (1343, 2, 'absolute', 'memory_probe_32_end'),
                            (1352, 2, 'absolute', 'memory_probe_points'),
                            (1372, 2, 'absolute', 'memory_probe_points'),
                            (1404, 2, 'absolute', 'memory_probe_points'),
                            (1424, 2, 'absolute', 'memory_probe_points'),
                            (1509, 2, 'absolute', 'memory_probe_16_end'),
                            (1542, 2, 'absolute', 'memory_probe_end'),
                            (1571, 2, 'absolute', 'memory_probe_single_end'),
                            (1618, 2, 'absolute', 'memory_probe_32_end'),
                            (1625, 2, 'absolute', 'memory_probe_16_end'),
                            (1632, 2, 'absolute', 'memory_probe_end'),
                            (1639, 2, 'absolute', 'memory_probe_single_end'),
                            (1648, 2, 'absolute', 'memory_probe_points'),
                            (1677, 2, 'absolute', 'memory_probe_points'),
                            (1739, 2, 'absolute', 'memory_probe_32_end'),
                            (1746, 2, 'absolute', 'memory_probe_16_end'),
                            (1753, 2, 'absolute', 'memory_probe_end'),
                            (1760, 2, 'absolute', 'memory_probe_single_end'),
                            (1769, 2, 'absolute', 'memory_probe_points'),
                            (1798, 2, 'absolute', 'memory_probe_points'),
                            (1860, 2, 'absolute', 'memory_probe_32_end'),
                            (1867, 2, 'absolute', 'memory_probe_16_end'),
                            (1874, 2, 'absolute', 'memory_probe_end'),
                            (1881, 2, 'absolute', 'memory_probe_single_end'),
                            (1890, 2, 'absolute', 'memory_probe_points'),
                            (1919, 2, 'absolute', 'memory_probe_points'),
                            (2048, 2, 'absolute', 'init_memory.real'),
                            (2101, 2, 'near', 'memory_bank_mib')]}}
TABLES = {'chipset_profiles': {'length': 98,
                      'sha256': 'e02dac549caf6800a7f4c32fec162319e3a24921f181d7d399a4aa6945aaa006'},
 'memory_probe_points': {'length': 256,
                         'sha256': '9fa67c4d94dfc6cd6a3afe4b0c443b09229b00a6e877d41bebf5535d524051cf'},
 'memory_interleave_pairs': {'length': 8,
                             'sha256': 'e02a58bd58022d8288039c619cd11a02ffd3b009d88954c7087b60cf942ee9ed'},
 'move_gdt': {'length': 32, 'sha256': 'e0557f153eac1f508c3312f7eb8e7a3d0f55c03155f75c09c319ef4f8323e4fc'}}

def symbol(listing, name):
    if '.' in name:
        owner, local = name.split('.', 1)
        return listing.symbol('.'+local, owner)
    try:
        return listing.symbol(name)
    except StopIteration:
        for line in listing.lines:
            if re.search(r'\b'+re.escape(name)+r'\s*:?\s+d[bwdq]\s',line):
                return int(re.match(r'\s*\d+\s+([0-9A-F]{8})',line)[1],16)
        raise AssertionError(name)


def preservation(rom):
    raw = rom.read_bytes()
    listing = Listing(rom.with_suffix('.lst'))
    for name, expected in WINDOWS.items():
        start, end = symbol(listing,name), symbol(listing,expected['end'])
        assert end-start == expected['length'], (name,'window length',end-start)
        actual = bytearray(raw[start:end])
        occupied = set()
        for offset,width,kind,target in expected['fixups']:
            assert not occupied.intersection(range(offset,offset+width))
            occupied.update(range(offset,offset+width))
            value = int.from_bytes(actual[offset:offset+width],'little')
            resolved = (start+offset+width+value)&65535 if kind=='near' else value
            assert resolved == symbol(listing,target), (name,hex(offset),target,hex(resolved))
            actual[offset:offset+width] = bytes(width)
        assert hashlib.sha256(actual).hexdigest() == expected['sha256'], name
    for name, expected in TABLES.items():
        start = symbol(listing,name)
        assert hashlib.sha256(raw[start:start+expected['length']]).hexdigest() == expected['sha256'], name
    start = symbol(listing,'chipset_profiles')
    for name,offset in (('chipset_default',8),('chipset_masks',32),('chipset_cmos',56),('chipset_registers',80),('chipset_apply_masks',89)):
        assert symbol(listing,name) == start+offset
    gdtr = symbol(listing,'move_gdtr')
    assert struct.unpack_from('<HI',raw,gdtr) == (31,0xF0000+symbol(listing,'move_gdt'))
    assert raw[0xFFF0:0xFFF5] == bytes.fromhex('EA000000F0')
    assert raw[0xF065:0xF070] == bytes.fromhex('80FC1D7305EA972800C0CF')
    return {'windows':len(WINDOWS),'tables':len(TABLES),'all_instructions_retained':True}


def dependencies(nasm):
    command = [nasm,'-M','-MT','firmware','-DVGA_BIOS_141','-f','bin','-I',(PORT/'src').as_posix()+'/',(PORT/'src/bios.asm').as_posix()]
    result = subprocess.run(command,cwd=ROOT,check=True,capture_output=True,text=True)
    names = shlex.split(result.stdout.split(': ',1)[1].replace('\\\n',' '))
    paths = [Path(p).resolve() for p in names]
    expected = [ROOT/'shared/src/firmware'/f'{name}.inc' for name in
        ('apm','boot','cdboot','floppy','ide','identity','memory','mouse','peripherals','post','setup','ram-test')]
    expected += [ROOT/'shared/src/pc'/f'{name}.inc' for name in ('cpu','primary-ata','chs-geometry')]
    assert all(p.resolve() in paths for p in expected), [str(p) for p in expected if p.resolve() not in paths]
    assert all(p.is_relative_to(ROOT) for p in paths), paths
    return {'cwd':str(ROOT),'command':command,'resolved_dependencies':[str(p) for p in paths]}


def guards(nasm):
    with tempfile.TemporaryDirectory(dir=PORT/'build') as temporary:
        target = Path(temporary)/'bad.rom'
        for definition in ('RAM_TEST_BLOCK_SIZE=3','RAM_TEST_BLOCK_SIZE=0x1000','RAM_TEST_SERVICE_MASK=0x1FF','RAM_TEST_BUFFER_ABSOLUTE=0x801','RAM_TEST_BUFFER_ABSOLUTE=0x400','RAM_TEST_BUFFER_ABSOLUTE=0xF00'):
            result = subprocess.run([nasm,'-f','bin','-DVGA_BIOS_141','-D'+definition,'-I',(PORT/'src').as_posix()+'/', '-o',str(target),(PORT/'src/bios.asm').as_posix()],cwd=ROOT,capture_output=True,text=True)
            assert result.returncode and 'RAM ' in result.stderr, (definition,result.stderr)
    return 6


def fdc_and_video():
    setup = importlib.import_module('test-setup')
    x = setup.x
    for rejected in range(3):
        class FDC(setup.Setup):
            def port_in(self,cpu,port,size,unused):
                if port==0x3F4 and len(self.writes)>=rejected: return 0
                return super().port_in(cpu,port,size,unused)
            def port_out(self,cpu,port,size,value,unused):
                if port==0x3F5: self.writes.append(value)
                return super().port_out(cpu,port,size,value,unused)
        m=FDC();m.writes=[]
        m.call('fdc_specify')
        assert m.writes == [3,0xDF,2][:rejected], (rejected,m.writes)
        assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1
        assert m.cpu.mem_read(m.base+0x88,1) == b'\x80'  # Real timeout owner publishes status.
    class VGA(setup.Setup):
        def interrupt(self,cpu,vector,unused):
            super().interrupt(cpu,vector,unused)
            if vector==0x10:
                cpu.reg_write(x.UC_X86_REG_FS,0x1234)
                cpu.reg_write(x.UC_X86_REG_GS,0x5678)
                cpu.reg_write(x.UC_X86_REG_EFLAGS,cpu.reg_read(x.UC_X86_REG_EFLAGS)|0x400)
    m=VGA();saved=bytes(m.cmos)
    m.cpu.reg_write(x.UC_X86_REG_GS,0x2468)
    m.call('setup_restore_text')
    assert m.cpu.reg_read(x.UC_X86_REG_FS)==m.segment
    assert m.cpu.reg_read(x.UC_X86_REG_GS)==0x2468
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x400
    m.call('post_ui_begin')
    assert m.text(2,3,9)=='Processor'
    assert m.cpu.reg_read(x.UC_X86_REG_FS)==m.segment
    assert m.cpu.reg_read(x.UC_X86_REG_GS)==0x2468
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x400
    m.open([1,28])
    assert m.cpu.reg_read(x.UC_X86_REG_FS)==m.segment
    assert m.cpu.reg_read(x.UC_X86_REG_GS)==0x2468
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x400
    assert bytes(m.cmos)==saved
    return {'fdc_rejection_points':3,'actual_video_restore_and_setup':True}


def diagnostics(nasm, rom):
    results = []
    with tempfile.TemporaryDirectory(prefix='diagnostic-builds-', dir=PORT/'build') as name:
        output = Path(name)/'system.rom'
        for define in (None, 'FLOPPY_DIAGNOSTIC', 'KEYBOARD_DIAGNOSTIC', 'MOUSE_DIAGNOSTIC'):
            flags = ['-D'+define] if define else []
            subprocess.run([nasm,'-f','bin','-DVGA_BIOS_141',*flags,'-I',(PORT/'src').as_posix()+'/',
                            '-o',str(output),(PORT/'src/bios.asm').as_posix()],cwd=ROOT,check=True)
            data = output.read_bytes()
            assert len(data) == 65536 and data[0xFFF0:0xFFF5] == bytes.fromhex('ea000000f0')
            assert data[0xF065:0xF06A] == rom.read_bytes()[0xF065:0xF06A]
            if define is None:
                assert data[:-1] == rom.read_bytes()[:-1], 'Normal firmware changed in diagnostic-only relocation'
            results.append(define or 'production')
    return results


def main():
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    build = PORT/os.environ.get('BAIOS_BUILD_DIRECTORY','build')
    build.mkdir(parents=True,exist_ok=True)
    rom = build/'baios-presario800-system.rom'
    if not rom.exists():
        subprocess.run([nasm,'-f','bin','-DVGA_BIOS_141','-I',(PORT/'src').as_posix()+'/', '-o',str(rom),'-l',str(rom.with_suffix('.lst')),(PORT/'src/bios.asm').as_posix()],cwd=ROOT,check=True)
    result = {'hardware':preservation(rom),'dependencies':dependencies(nasm),'compile_rejections':guards(nasm),'adapters':fdc_and_video()}
    result['diagnostic_builds'] = diagnostics(nasm, rom)
    result['cpu_cases'] = len(cpu_check(rom,{'base':0xF0000,'code_segment':0xF000},{'S_CPU_SIGNATURE':0xD4}))
    (build/'shared-adoption.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS active snapshot dependencies, complete hardware windows/tables, guards, FDC/video boundaries and guarded CPU catalogue')


if __name__=='__main__':
    main()
