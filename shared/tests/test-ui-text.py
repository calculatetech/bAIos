"""Build current production images and prove compact Setup text against P0."""
import argparse
from functools import cache
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

from unicorn import UC_HOOK_MEM_WRITE, UC_HOOK_INTR
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.tools.rom import verify

spec = importlib.util.spec_from_file_location('pnp_settings', Path(__file__).with_name('test-pnp-settings.py'))
pnp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pnp)
MANIFEST = json.loads((ROOT/'shared/tests/fixtures/ui-text-p0.json').read_text())
POST_LAYOUT_MANIFEST = json.loads((ROOT/'shared/tests/fixtures/pnp-placement-p1.json').read_text())
SPACE_MANIFEST = json.loads((ROOT/'shared/tests/fixtures/ui-text-p1-space.json').read_text())
PORTS = ('m919', 'mp386', 'pb430', 'presario-800')
OUTPUT = 'build/tests/ui-text'

# Current UI wording supersedes these labels; the historical P0/P1 oracles stay frozen.
LIVE_PNP_TEXT={
    'pnp_available':b'Available','pnp_bios':b'BIOS','pnp_os':b'Operating System','pnp_keep':b'Keep',
    'pnp_irqs':b'IRQ Reservations','pnp_windows':b'Reserved I/O Ports',
    'pnp_clear':b'Clear ESCD','pnp_io1':b'Range 1 Start','pnp_len1':b'Range 1 Port Count',
    'pnp_io2':b'Range 2 Start','pnp_len2':b'Range 2 Port Count',
    'pnp_help1':b'Reserve resources for manual cards.',
    'pnp_help2':b'Example: Start 220h, decimal Count 16.',
    'pnp_help3':b'Count 0 disables the range.'}
LIVE_PNP_MAIN=['pnp_irqs','pnp_dmas','pnp_windows','pnp_memory','pnp_config','pnp_clear']


def build(port):
    if port == 'presario-800':
        command = ['pwsh', '-NoProfile', '-File', str(ROOT/port/'tools/build.ps1'), '-OutputDirectory', OUTPUT]
    elif port == 'm919':
        command = [sys.executable, '-B', str(ROOT/'tools/build-rom.py'), str(ROOT/port), '--output', OUTPUT]
    else:
        command = [sys.executable, '-B', str(ROOT/port/'tools/build.py'), '--output', OUTPUT]
    subprocess.run(command, cwd=ROOT, check=True, stdout=sys.stderr)


def model(port):
    s = pnp.ui_model(port, OUTPUT)
    s.listing.symbol = cache(s.listing.symbol)
    return s


def address(s, name):
    cache = getattr(s,'text_addresses',{})
    if name in cache:
        return cache[name]
    declaration = re.compile(r'\b'+re.escape(name)+r'\s+(?:db|dw)\b')
    label = re.compile(r'(?<![\w.])'+re.escape(name)+r':\s*$')
    for index,line in enumerate(s.listing.lines):
        if declaration.search(line):
            match = re.match(r'\s*\d+\s+([0-9A-F]{8})\s+', line)
            if match:
                cache[name]=int(match[1],16)
                break
        if label.search(line):
            # A board macro also lists its definition. Select an emitted DB,
            # never the next unrelated instruction after an inactive label.
            for following in s.listing.lines[index+1:index+12]:
                if re.search(r'(?<![\w.%])\w+:\s*$',following):
                    break
                match = re.match(r'\s*\d+\s+([0-9A-F]{8})\s+',following)
                if match and re.search(r'\bdb\b',following):
                    cache[name]=int(match[1],16)
                    break
            if name in cache:
                break
    assert name in cache, ('Missing compiled label',name)
    s.text_addresses=cache
    return cache[name]


def cstring(s, at):
    return bytes(s.cpu.mem_read(0xF0000+at, 1024)).split(b'\0', 1)[0]


def render(s, at, length, **registers):
    s.cpu.mem_write(0xB8000, b'\xcd'*4096)
    s.call('setup_text', SI=at, DI=160, BX=0x0700, **registers)
    observed = bytes(s.cpu.mem_read(0xB8000, 4096))
    assert observed[:160] == b'\xcd'*160
    assert observed[160+length*2:] == b'\xcd'*(4096-160-length*2)
    return observed[160:160+length*2]


def authored_strings(s, port):
    directory = ROOT/port/OUTPUT
    rows = [('empty',b''),('short_label',b'Hi'),
            ('duplicate_a',b'Choose how the BIOS addresses this hard disk.'),
            ('duplicate_b',b'Choose how the BIOS addresses this hard disk.'),
            ('suffix_a',b'This repeated prefix has a later distinct first suffix.'),
            ('suffix_b',b'This repeated prefix has a later distinct second suffix.'),
            ('new_sentence',b'Zebras can use the existing menu without retraining.'),
            ('unsuitable',b'\x80CP437')]
    source = '%include "setup/ui-text.inc"\n'
    for name,plain in rows:
        literal = "'"+plain.decode('ascii')+"'" if plain[:1]!=b'\x80' else '`\\x80CP437`'
        source += f'{name}:\n    ui_string {literal}\n'
    asm, binary, listing = (directory/f'authored.{suffix}' for suffix in ('asm','bin','lst'))
    asm.write_text(source)
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    grammar = ROOT/'shared/src/setup/ui-text-pairs.inc'
    before = grammar.read_bytes()
    subprocess.run([nasm,'-w+error','-f','bin','-I',str(ROOT/'shared/src')+'/',
                    '-l',str(listing),'-o',str(binary),str(asm)],check=True)
    assert grammar.read_bytes() == before
    probe = pnp.Listing(listing)
    compiled = binary.read_bytes()
    rom = s.image.read_bytes()[-65536:]
    hole = next(m for m in re.finditer(b'\xff{'+str(len(compiled)+16).encode()+b',}',rom[:0xFFF0]))
    offset = hole.start()+8
    s.cpu.mem_write(0xF0000+offset,compiled)
    s.put('U_THEME_ACTIVE',[0])
    for name,plain in rows:
        assert render(s,offset+probe.symbol(name),len(plain)) == b''.join(bytes((v,7)) for v in plain),name
    assert probe.symbol('duplicate_a') != probe.symbol('duplicate_b')
    assert compiled[probe.symbol('empty')] == 0
    assert compiled[probe.symbol('short_label'):probe.symbol('short_label')+3] == b'Hi\0'
    assert compiled[probe.symbol('unsuitable'):probe.symbol('unsuitable')+7] == b'\x80CP437\0'
    # Reuse a real cached label with changed full text, then a different suffix.
    original = bytes.fromhex(MANIFEST['ports'][port]['strings']['u_help_halt1']['hex'])
    for suffix in (b' Later first suffix.',b' Later different second suffix.'):
        plain = original+suffix
        asm.write_text('%include "setup/ui-text.inc"\nu_help_halt1:\n ui_string '+
                       repr(plain.decode('ascii'))+',u_help_halt1\n')
        subprocess.run([nasm,'-w+error','-f','bin','-I',str(ROOT/'shared/src')+'/',
                        '-o',str(binary),str(asm)],check=True)
        changed = binary.read_bytes()
        assert cstring(s,offset) != plain # It still holds the previous probe.
        s.cpu.mem_write(0xF0000+offset,changed)
        assert render(s,offset,len(plain)) == b''.join(bytes((v,7)) for v in plain)
    # Reject a compiled marker collision rather than silently reinterpret it.
    asm.write_text('%include "setup/ui-text.inc"\ncollision:\n ui_string `\\x01Raw`\n')
    rejected = subprocess.run([nasm,'-f','bin','-I',str(ROOT/'shared/src')+'/',
                               '-o',str(binary),str(asm)],capture_output=True)
    assert rejected.returncode and b'Leading01 is reserved' in rejected.stderr
    invalid = directory/'invalid-grammar/setup'
    invalid.mkdir(parents=True,exist_ok=True)
    asm.write_text(f'%include "{(invalid/"ui-text-pairs.inc").as_posix()}"\n%include "setup/ui-text.inc"\n')
    for case in ('cycle','depth'):
        definitions = []
        for index in range(128):
            a = 128 if case=='cycle' and index==0 else 127+index if case=='depth' and index else 97
            definitions += [f'%assign UI_PAIR_A{index} {a}',f'%assign UI_PAIR_B{index} 98']
        definitions.append('%define UI_TEXT_PAIRS 0')
        (invalid/'ui-text-pairs.inc').write_text('\n'.join(definitions)+'\n')
        rejected = subprocess.run([nasm,'-f','bin','-I',str(invalid.parent)+'/',
                                  '-I',str(ROOT/'shared/src')+'/','-o',str(binary),str(asm)],capture_output=True)
        assert rejected.returncode,(case,rejected.stderr.decode(errors='replace'))
    return len(rows)+2


def strings(port):
    s, baseline = model(port), MANIFEST['ports'][port]
    encoded = 0
    s.put('U_THEME_ACTIVE', [0])
    for name, row in baseline['strings'].items():
        if port=='mp386' and name.startswith('pnp_'):continue  # Forward chipset-scope correction.
        if name=='pnp_irqs_high':continue
        expected = LIVE_PNP_TEXT.get(name,bytes.fromhex(row['hex']))
        at = address(s, name)
        actual = render(s, at, len(expected))
        assert actual == b''.join(bytes((v,7)) for v in expected), name
        stored = cstring(s, at)
        if stored[:1] == b'\x01':
            assert (row['compress'] or name in LIVE_PNP_TEXT or name in SPACE_MANIFEST['ports'][port]['strings']) and len(stored) < len(expected), name
            encoded += 1
        else:
            assert stored == expected, name
    for table, labels in baseline['tables'].items():
        if port=='mp386' and table.startswith('pnp_'):continue
        if table=='pnp_main_labels':labels=LIVE_PNP_MAIN
        pointers = struct.unpack('<'+'H'*len(labels), s.cpu.mem_read(0xF0000+address(s,table),len(labels)*2))
        assert pointers == tuple(address(s,label) for label in labels), table
    assert encoded > 0
    depths = [0]*128
    pairs = bytes(s.cpu.mem_read(0xF0000+address(s,'ui_text_pairs'),256))
    for index,(a,b) in enumerate(zip(pairs[::2],pairs[1::2])):
        assert 2 <= a < 128+index and 2 <= b < 128+index
        depths.append(1+max(depths[a],depths[b]))
    assert max(depths) <= 32
    samples = authored_strings(s,port)
    return dict(strings=len(baseline['strings']), collections=len(baseline['tables']), encoded=encoded,
                authored_without_retraining=samples, grammar_depth=max(depths))


def supplementary_strings(port,output='build/tests/pnp-allocation'):
    """Newly eligible labels use frozen compiled P1 plaintext, not source text."""
    s=pnp.Settings(port,output)
    s.listing.symbol=cache(s.listing.symbol)
    s.put('U_THEME_ACTIVE',[0])
    saving=0
    unchanged=0
    for name,row in SPACE_MANIFEST['ports'][port]['strings'].items():
        expected=LIVE_PNP_TEXT.get(name,bytes.fromhex(row['hex']));at=address(s,name)
        assert render(s,at,len(expected))==b''.join(bytes((v,7)) for v in expected),name
        actual=cstring(s,at)
        if name in LIVE_PNP_TEXT:
            assert actual[:1]==b'\1' or actual==expected,name
        elif row['saving']:
            assert actual[:1]==b'\1' and len(actual)<len(expected),name
        else:
            assert actual==expected,name  # Existing codec's exact literal fallback.
        saving+=len(expected)-len(actual)
        if name not in LIVE_PNP_TEXT:
            unchanged+=len(expected)-len(actual)
    assert unchanged==sum(row['saving'] for name,row in SPACE_MANIFEST['ports'][port]['strings'].items() if name not in LIVE_PNP_TEXT)
    return {'selected_strings':len(SPACE_MANIFEST['ports'][port]['strings']),'bytes_recovered':saving,
            'full_rendered_plaintext_and_canaries':True}


def renderer(port):
    s = model(port)
    s.base = 0x78000
    s.cpu.mem_write(0x40E, struct.pack('<H', s.base >> 4))
    # Poison the original theme location; the actual relocated FS owner wins.
    s.cpu.mem_write(0x80000+s.state['U_THEME'], b'\xff')
    maximum_stack = 0
    stack_writes = []
    def writes(cpu, access, at, size, value, _):
        assert at < 0xE0000, ('ROM write', hex(at))
        if 0x6000 <= at < 0x7000:
            stack_writes.append(at)
    hook = s.cpu.hook_add(UC_HOOK_MEM_WRITE, writes)
    try:
        for row in MANIFEST['ports'][port]['renderer']:
            s.put('U_THEME', [row['theme']])
            s.put('U_THEME_ACTIVE', [row['active']])
            if 'label' in row:
                si, ds = address(s,row['label']), 0xF000
            else:
                si, ds = 0x200, 0x5000
                s.cpu.mem_write(ds*16+si, bytes.fromhex(row['hex'])+b'\0')
            expected = bytes.fromhex(row['rendered_hex'])
            initial = dict(EAX=0x12345678, EBX=0xABCD0000|(row['attribute']<<8)|0x35,
                           ECX=0x23456789, EDX=0x3456789A, EBP=0x456789AB,
                           ESI=0x56780000|si, EDI=0x67890000|row['di'], ESP=0x789A7000,
                           DS=ds, GS=0x1234)
            s.cpu.mem_write(0x6D00, b'\xa5'*128)
            s.cpu.mem_write(0xB8000, b'\xcd'*4096)
            s.call('setup_text', **initial)
            for reg, value in initial.items():
                if reg == 'ESP':
                    value += 2 # The existing near RET consumes the caller return.
                assert s.cpu.reg_read(getattr(x,'UC_X86_REG_'+reg)) == value, reg
            assert s.cpu.reg_read(x.UC_X86_REG_ES) == 0xB800
            assert s.cpu.reg_read(x.UC_X86_REG_FS) == s.base >> 4
            assert s.cpu.mem_read(0x6D00,128) == b'\xa5'*128
            screen = bytes(s.cpu.mem_read(0xB8000,4096))
            at = row['di']
            assert screen[at:at+len(expected)] == expected, row
            assert screen[:at] == b'\xcd'*at and screen[at+len(expected):] == b'\xcd'*(4096-at-len(expected))
        maximum_stack = 0x7000-min(stack_writes)
        assert maximum_stack <= 160, maximum_stack
    finally:
        s.cpu.hook_del(hook)
    return dict(vectors=6, relocated_theme=True, literal_01_cp437_controls=True,
                preserved_registers_segments=True, maximum_stack_bytes=maximum_stack)


def setup(port):
    s = model(port)
    s.call('settings_load')
    s.call('setup_defaults')
    assert s.call('settings_save')
    s.call('settings_load')
    down, enter, esc, tab = 0x5000, 13, 27, 9
    clock, theme = s.get('C_CLOCK24'), s.get('C_THEME')
    saved = s.snapshot()
    s.writes.clear()
    # Cancel a changed popup, then leave through the actual Discard owner.
    s.ui([tab,down,down,enter,down,esc,esc,esc,enter])
    assert s.get('U_CLOCK24') == clock
    assert not s.reset and not s.writes and s.snapshot() == saved
    s.screen.clear()
    # Apply the sorted choice, open its help, change theme, and really Save.
    s.ui([tab,down,down,enter,down,enter,0x3B00,esc,0x3F00,0x4400,enter])
    assert s.reset
    chosen_clock, chosen_theme = s.get('U_CLOCK24'), s.get('U_THEME')
    assert chosen_clock == bytes((1-clock[0],)) and chosen_theme != theme
    assert any(b'12 Hour' in screen and b'24 Hour' in screen for screen in s.screen)
    help_text = MANIFEST['ports'][port]['strings']['u_help_format1']['hex']
    assert any(bytes.fromhex(help_text) in screen for screen in s.screen)
    s.call('settings_load')
    assert s.get('C_CLOCK24') == chosen_clock and s.get('C_THEME') == chosen_theme
    saved = s.snapshot()
    s.writes.clear()
    # Applied draft changes still disappear on Discard, without a write/reset.
    s.ui([tab,down,down,enter,down,enter,0x3F00,esc,esc,enter])
    assert not s.reset and not s.writes and s.snapshot() == saved
    s.call('settings_load')
    assert s.get('C_CLOCK24') == chosen_clock and s.get('C_THEME') == chosen_theme
    if port == 'presario-800':
        env = dict(os.environ, BAIOS_BUILD_DIRECTORY=OUTPUT)
        for script, cases in (('test-modular-setup.py',('numeric','abi')),('test-chipset.py',('ui',))):
            command = [sys.executable,'-B',str(ROOT/port/'tools'/script)]
            for case in cases:
                command += ['--case',case]
            subprocess.run(command,cwd=ROOT,env=env,check=True,stdout=sys.stderr)
        # Python3.14's Windows0700 tempfile ACL blocks this NASM child here.
        # Keep the established validation-only inherited-ACL launcher local.
        integration = """import os,sys,importlib
sys.path.insert(0,'presario-800/tools')
original=os.mkdir
if os.name=='nt':
    def inherited_acl(path,mode=0o777,*args,**kwargs):
        return original(path,0o777,*args,**kwargs)
    os.mkdir=inherited_acl
importlib.import_module('test-modular-setup').integration()
"""
        subprocess.run([sys.executable,'-B','-c',integration],cwd=ROOT,env=env,check=True,stdout=sys.stderr)
    return dict(mapped_Apply_Cancel=True, help=True, theme=True, verified_Save_reload=True,
                Discard_without_write_or_reset=True, calculated_CAS_owners=port=='presario-800')


def compatibility(port):
    s = model(port)
    baseline = MANIFEST['ports'][port]
    emitted = bytearray()
    def vga(cpu, vector, _):
        if vector == 0x10 and cpu.reg_read(x.UC_X86_REG_AH) == 0x0E:
            emitted.append(cpu.reg_read(x.UC_X86_REG_AL))
    hook = s.cpu.hook_add(UC_HOOK_INTR,vga)
    warnings = ('u_clock_unset','u_clock_save_error','u_cmos_invalid',
                'u_cmos_clock_invalid','u_cmos_recover','u_keyboard_absent')
    try:
        for label in warnings:
            expected = bytes.fromhex(baseline['strings'][label]['hex'])
            at = address(s,label)
            assert cstring(s,at) == expected and expected[:1] != b'\x01'
            emitted.clear()
            s.call('print_string',SI=at)
            assert emitted == expected,label
        for error,label in ((1,'u_clock_unset'),(4,'u_cmos_invalid'),(5,'u_cmos_clock_invalid')):
            s.call('settings_load')
            s.put('C_VALID',[int(error==1)])
            s.put('C_BASE_VALID',[1])
            s.put('C_HALT',[1])
            s.put('C_ERROR',[error])
            emitted.clear()
            before=s.snapshot()
            s.call('post_clock_alert')
            assert emitted == bytes.fromhex(baseline['strings'][label]['hex']), (error,emitted)
            assert s.snapshot()==before
    finally:
        s.cpu.hook_del(hook)
    s = model(port)
    s.call('settings_load')
    s.cpu.mem_write(0x400+s.state['KB_POST_STATE'],b'\x01') # Frozen live-screen input; early-screen case proves the unarmed contrast.
    for owner,expected in baseline['post_screens'].items():
        if owner=='post_debug_summary':
            # Frozen P0 renderer input was zero KiB. This is a cell-compatibility
            # oracle, not the actual-startup memory-accounting proof.
            s.cpu.mem_write(0x413,bytes(2))
        s.call(owner)
        assert s.cpu.mem_read(0xB8000,4000) == bytes.fromhex(expected), owner
    if port == 'presario-800':
        subprocess.run([sys.executable,'-B',str(ROOT/port/'tools/test-post-ui.py'),'--case','display'],
                       cwd=ROOT,env=dict(os.environ,BAIOS_BUILD_DIRECTORY=OUTPUT),check=True,stdout=sys.stderr)
    if port == 'pb430':
        subprocess.run([sys.executable,'-B',str(ROOT/port/'tools/test-post-layout.py'),str(s.image)],
                       cwd=ROOT,check=True,stdout=sys.stderr)
    return dict(raw_warning_consumers=len(warnings), actual_notice_variants=3,
                actual_POST_and_summary=True, plaintext_fragments=True)


def owned_post_layout(full,port):
    """Current B35 owner replaces only qualified padding; P0/P1 fixtures stay frozen."""
    frozen=POST_LAYOUT_MANIFEST['ports'][port]
    first,last=frozen['retained_start'],frozen['retained_end']
    assert hashlib.sha256(full[first:last]).hexdigest()==frozen['retained_sha256'],(port,'retained prefix')
    start,end=frozen['new_owned_start'],frozen['new_owned_end']
    payload=full[start:end]
    if port=='presario-800':
        from shared.tools.post_module import inspect_bank
        decoded,info=inspect_bank(payload)
        return {'retained_range':[first,last],'owned_range':[start,end],'module_length':len(decoded),
                'entry':info['entry'],'module_sha256':info['raw_sha256'],'storage':info['storage'],'SUM8':0}
    assert payload[:8]==b'BAIPNP2\0'
    length,entry=struct.unpack_from('<HH',payload,8)
    assert 15<=length<len(payload) and not length&1 and 12<=entry<length
    assert payload[entry:entry+3]==bytes.fromhex('FFD3CB')
    assert payload[length:-1]==b'\xFF'*(len(payload)-length-1)
    assert sum(full[:65536] if port=='m919' else payload)&255==0
    return {'retained_range':[first,last],'owned_range':[start,end],'module_length':length,
            'entry':entry,'module_sha256':hashlib.sha256(payload[:length]).hexdigest(),'SUM8':0}



def image_contract(port):
    s = model(port)
    raw = s.image.read_bytes()
    rom = raw[-65536:]
    if port != 'presario-800':
        verify(ROOT/port,s.image)
    else:
        assert len(raw)==65536 and sum(raw)&255==0
        assert rom[0xFFF0]==0xEA and struct.unpack_from('<HH',rom,0xFFF1)==(s.listing.symbol('startup'),0xF000)
    # Read actual assembler padding directives, excluding FF runs within data.
    regions = []
    for line in s.listing.lines:
        if re.search(r'\btimes\s+(?:0xF065|0xFFF0|CFG_ROM_CHECKSUM_OFFSET)',line) and 'db 0xFF' in line:
            found = re.match(r'\s*\d+\s+([0-9A-F]{8})\s+FF<rep ([0-9A-F]+)h>',line)
            if found:
                regions.append((int(found[1],16),int(found[2],16)))
    assert regions
    free = sum(length for at,length in regions if at < 0xFFF0)
    baseline = MANIFEST['ports'][port]['free_system_bytes']
    additional_post_owner=any(re.search(r'\bpnp_journal_begin:\s*$',line) for line in s.listing.lines)
    if not additional_post_owner:assert free > baseline, (port,free,baseline)
    if port in ('pb430','presario-800'):
        assert rom[0xF065:0xF070] == bytes.fromhex('80fc1d7305ea972800c0cf')
    physical = s.image.with_name('baios-presario800-vga60.bin') if port=='presario-800' else s.image
    full = physical.read_bytes()
    frozen = MANIFEST['ports'][port]['physical']
    assert len(full)==frozen['size']
    if additional_post_owner and port in POST_LAYOUT_MANIFEST['ports']:
        owned_post_layout(full,port)
    else:assert hashlib.sha256(full[:-65536]).hexdigest()==frozen['retained_sha256']
    if additional_post_owner and port=='mp386':
        fixed=POST_LAYOUT_MANIFEST['mp386_fixed_compatibility']
        assert hashlib.sha256(rom[fixed['start']:fixed['end']]).hexdigest()==fixed['sha256']
    assert full[-65536:]==rom
    assert sum(rom)&255 == 0 and sum(full)&255 == int(frozen['sum32'],16)&255
    return dict(free_system_bytes=free, prior_free_bytes=baseline, net_recovered_bytes=free-baseline,
                padding_regions=regions, physical_image=str(physical.relative_to(ROOT)),
                size=len(full), sum32=f'{sum(full)&0xFFFFFFFF:08X}',
                sha256=hashlib.sha256(full).hexdigest(), system_sha256=hashlib.sha256(rom).hexdigest())


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', choices=('all',)+PORTS, default='all')
    parser.add_argument('--case', choices=('strings','renderer','setup','compatibility','image-contract'))
    args = parser.parse_args()
    selected = PORTS if args.port=='all' else (args.port,)
    cases = {'strings':strings,'renderer':renderer,'setup':setup,'compatibility':compatibility,'image-contract':image_contract}
    results = {}
    for port in selected:
        build(port)
        results[port]={}
        for name,check in cases.items():
            if not args.case or args.case==name:
                results[port][name]=check(port)
                print(f'PASS {port} {name}: '+json.dumps(results[port][name]),file=sys.stderr,flush=True)
        (ROOT/port/OUTPUT/'ui-text-results.json').write_text(json.dumps(results[port],indent=2)+'\n')
    print(json.dumps(results,indent=2))
