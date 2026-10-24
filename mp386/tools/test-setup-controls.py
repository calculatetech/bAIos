"""Exercise saved MP386 timings, sorted choices and Setup pages in assembled code."""
import argparse
import importlib
import json
import re
import struct
from pathlib import Path
from unicorn import x86_const as x

port = importlib.import_module('test-port')
memory = importlib.import_module('test-memory')
cache = importlib.import_module('test-cache')


def invoke(m, name, **registers):
    stop = m.symbol('core_verify_initialization')
    m.cpu.mem_write(0x6FFE, struct.pack('<H', stop))
    values = dict(SS=0, SP=0x6FFE, FS=0x9E00, DS=0xF000, ES=0xB800)
    values.update(registers)
    entry = m.symbol(name)
    if name == 'chipset_ui_draw':
        # NASM lists the shared macro-renamed label before the board wrapper.
        row = max(i for i,line in enumerate(m.listing.lines) if re.search(r'\bchipset_ui_draw:\s*$',line))
        entry = m.listing.offset(row)
    memory.window(m, entry, stop,
                  tuple((getattr(x, 'UC_X86_REG_'+key), value) for key, value in values.items()))
    assert m.cpu.reg_read(x.UC_X86_REG_SP) == 0x7000


def text(m, pointer):
    return bytes(m.cpu.mem_read(0xF0000+pointer, 128)).split(b'\0')[0].decode('ascii')


def data_address(m, name):
    line = next(line for line in m.listing.lines if re.search(r'\b'+name+r'\s+(?:db|dw)\b', line))
    return int(re.match(r'\s*\d+\s+([0-9A-F]{8})', line)[1], 16)


def check(image):
    m = cache.configured(image)
    m.cpu.mem_write(0x40E,struct.pack('<H',0x9E00))
    m.cpu.mem_write(0x413,struct.pack('<H',632))
    invoke(m, 'chipset_defaults', DI=0x60)
    defaults = bytes(m.cpu.mem_read(m.base+0x60, 24))
    for strap in (0,1,6,7):
        m.clock_switches = strap
        invoke(m,'chipset_defaults',DI=0x260)
        expected = bytes((0xA4 if strap & 6 else 0x80,7 if strap & 1 else 6))
        assert m.cpu.mem_read(m.base+0x262,2) == expected
    m.clock_switches = 0xBE
    before, maps = dict(m.ti), dict(m.maps)
    invoke(m, 'mp_timing_apply')
    assert m.ti == before and m.maps == maps, 'Defaults changed working hardware'
    requested = bytearray(defaults)
    requested[0] = 1
    requested[2:7] = bytes((0x6B, 3, 0x2A, 2, 0x30))
    for bank in range(6):
        struct.pack_into('<H', requested, 7+bank*2, (bank*0x123+0x57) & 0x1FFF)
    m.cpu.mem_write(m.base+0x60, bytes(requested))
    invoke(m, 'mp_timing_apply')
    expected = dict(before)
    expected[0x801] = (before[0x801] & 0xF810) | 0x036B
    atu802 = (before[0x802] & 0xFFC0) | 0x2A
    assert ('out',0x24,2,atu802) in m.io
    expected[0x802] = (atu802 & 255)*0x101  # The modeled readback mirrors the low byte.
    for unit in range(3):
        expected[unit*256+3] = (before[unit*256+3] & 0x8FFC) | 0x3002
        for bank in range(2):
            index = unit*256+4+bank
            word = struct.unpack_from('<H', requested, 7+(unit*2+bank)*2)[0]
            expected[index] = (before[index] & 0xE000) | word
    assert m.ti == expected and m.maps == maps, [(hex(k),hex(expected.get(k,0)),hex(v)) for k,v in m.ti.items() if expected.get(k) != v]
    m.cpu.mem_write(m.base+0x260, bytes(requested))
    original_nv = bytes(m.nvram)
    invoke(m, 'chipset_settings_save')
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert m.nvram[0x229] == 0xD2, 'Local Save released recovery before whole-save verification'
    invoke(m, 'chipset_timing_saved')
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert all(0x229 <= address <= 0x23F for address, value in m.nv_writes)
    assert bytes(m.nvram[0x240:]) == original_nv[0x240:]
    saved = bytes(m.nvram)
    m.cpu.mem_write(m.base+0x60, bytes(24))
    invoke(m, 'chipset_settings_load')
    assert bytes(m.cpu.mem_read(m.base+0x60, 24)) == requested
    m.nvram[0x22B] ^= 1
    invoke(m, 'chipset_settings_load')
    assert bytes(m.cpu.mem_read(m.base+0x60, 24)) == defaults
    m.nvram[:] = saved
    m.nvram[0x22B] = 2  # Correct checksum cannot make an out-of-range Fast Boot valid.
    m.nvram[0x22A] = (-0xD3-sum(m.nvram[0x22B:0x240])) & 255
    invoke(m, 'chipset_settings_load')
    assert bytes(m.cpu.mem_read(m.base+0x60, 24)) == defaults
    m.nvram[:] = saved
    m.cpu.mem_write(m.base+0x260, defaults)

    groups = struct.unpack('<8H', m.cpu.mem_read(0xF0000+data_address(m,'chipset_groups'), 16))
    counts = bytes(m.cpu.mem_read(0xF0000+data_address(m,'chipset_group_counts'), 8))
    titles = struct.unpack('<8H',m.cpu.mem_read(0xF0000+data_address(m,'chipset_group_titles'),16))
    assert [text(m,p) for p in titles] == [
        'Bus and DMA','Memory and ROM','Onboard Bank 1','Onboard Bank 2',
        'Expansion Bank 1','Expansion Bank 2','Expansion Bank 3','Expansion Bank 4']
    for group,offset in zip(groups[2:],(8,10,12,14,16,18)):
        assert m.cpu.mem_read(0xF0000+group+2,1) == bytes((offset,))
    checked = 0
    for screen, (pointer, count) in enumerate(zip(groups, counts), 1):
        m.cpu.mem_write(m.base+0x278, bytes((screen,)))
        for field in range(count):
            m.cpu.mem_write(m.base+0xF7, bytes((field,)))
            label, offset, shift, mask, size, values, h1, h2, flip = struct.unpack(
                '<HBBBHHHHB', m.cpu.mem_read(0xF0000+pointer+field*14, 14))
            assert 'Cache' not in text(m, label), 'Cache option remained in Setup'
            invoke(m, 'chipset_ui_parameters')
            choices = m.cpu.reg_read(x.UC_X86_REG_SI)
            pointers = struct.unpack('<'+'H'*size, m.cpu.mem_read(0xF0000+choices, size*2))
            labels = [text(m, p) for p in pointers]
            assert len(set(labels)) == len(labels)
            numeric = all(re.match(r'^/?\d', value) for value in labels)
            order = sorted(labels, key=(lambda value: float(re.search(r'[\d.]+', value)[0])) if numeric else None)
            assert labels == order, labels
            for choice in range(size):
                m.cpu.mem_write(m.base+0x260, defaults)
                m.cpu.mem_write(m.base+0x279, bytes((choice,)))
                invoke(m, 'chipset_ui_commit')
                result = bytearray(defaults)
                result[offset] = (result[offset] & ~(mask << shift)) | ((choice ^ flip) << shift)
                assert bytes(m.cpu.mem_read(m.base+0x260, 24)) == result
                invoke(m, 'chipset_ui_parameters')
                assert m.cpu.mem_read(m.base+0x279, 1) == bytes((choice,))
            checked += 1
        m.cpu.mem_write(0xB8000, b' \x07'*2000)
        invoke(m, 'chipset_ui_draw')
        for field in range(count):
            assert m.text(5+field, 24, 24).strip(), (screen, field)
        if screen == 2:
            assert 'Page Mode' in m.text(12,24,24)
            assert 'RAM Interleave' in m.text(13,24,24)
    # Empty banks cannot be edited, and they do not affect the live timing map.
    m.cpu.mem_write(m.base+0x1014, b'\0\0')
    m.cpu.mem_write(m.base+0x278, b'\x05')
    invoke(m, 'chipset_ui_editable', CX=0)
    assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    m.cpu.mem_write(0xB8000, b' \x07'*2000)
    invoke(m, 'mp_ports_draw')
    assert 'Off 6 / On 8 MHz' in m.text(6, 24, 28)
    assert 'IDE controller' in m.text(7, 53, 25)
    assert 'Off/On LPT2' in m.text(15, 24, 53)
    assert 'On/On Disabled' in m.text(16, 24, 53)
    invoke(m, 'setup_draft_defaults')
    rows = bytes(m.cpu.mem_read(0xF0000+data_address(m,'u_boot_rows'), 8))
    pointers = struct.unpack('<8H', m.cpu.mem_read(0xF0000+data_address(m,'u_boot_pointers'), 16))
    labels = struct.unpack('<8H', m.cpu.mem_read(0xF0000+data_address(m,'u_boot_labels'), 16))
    assert [text(m, p) for p in labels][-1] == 'Fast Boot'
    assert bytes(m.cpu.mem_read(m.base+pointers[0], 1)) == b'\x03'
    assert bytes(m.cpu.mem_read(m.base+pointers[1], 1)) == b'\x01'
    assert bytes(m.cpu.mem_read(m.base+pointers[2], 1)) == b'\x02'
    assert pointers[-1] == 0x260 and rows[-1] == 12
    invoke(m,'ide_defaults',DI=0x1B0)
    invoke(m,'ports_defaults',DI=0x1EE)
    invoke(m,'chipset_defaults',DI=0x260)
    m.cpu.mem_write(m.base+0x260,b'\x01')
    invoke(m,'settings_save')
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    invoke(m,'settings_load')
    assert m.cpu.mem_read(m.base+0x174,1) == b'\x01',(bytes(m.cmos[0x38:0x40]).hex(),bytes(m.cpu.mem_read(m.base+0x170,16)).hex(),bytes(m.nvram[0x22A:0x240]).hex())
    assert m.cpu.mem_read(m.base+0x60,1) == b'\x01'
    assert m.cpu.mem_read(m.base+0x172,1) == b'\x03'
    seed = (bytes(m.cmos),bytes(m.nvram))
    class FailedCell(bytearray):
        def __setitem__(self,index,value):
            if index != 0x22F:
                super().__setitem__(index,value)
    m.nvram = FailedCell(m.nvram)
    m.cpu.mem_write(m.base+0x264,bytes((defaults[4]^1,)))
    invoke(m,'chipset_settings_save')
    assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert m.nvram[0x229] == 0xD2, 'Failed save released safe selection'
    return dict(fields=checked, defaults_unchanged=True, writes_preserve_maps_geometry=True,
                saved_and_loaded=True, bad_records_rejected=True, sorted_unique_choices=True,
                switches=True, cache_option_removed=True, standard_boot_and_fast_boot=True), seed


def boot_check(image, seed):
    from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_WRITE
    results = []
    for fast in (0,1):
        m = port.machine(image,controllers=((16,16),(64,64),(64,64)),cache=True)
        m.cmos[:],m.nvram[:] = seed
        m.nvram[0x22B] = fast
        m.nvram[0x22A] = (-0xD3-sum(m.nvram[0x22B:0x240])) & 255
        m.script_after_post = []
        decoder = m.ram_key
        m.ram_key = lambda address: None if 0xFE0000 <= address < 0x1000000 else decoder(address)
        active, bounds, extended = [False], [], []
        ready = 0xF0000+m.symbol('.test_limit_ready','chipset_visible_ram_test')
        def limit(cpu,address,size,unused):
            bounds.append(cpu.reg_read(x.UC_X86_REG_EBX))
            assert bounds[-1] == (0x100000 if fast else 0xFE0000)
        def written(cpu,access,address,size,value,unused):
            if active[0]:
                assert address+size <= (0x100000 if fast else 0xFE0000),hex(address)
                if address == 0x100000 and value == 0x55AA55AA:
                    extended.append(True)
        def observe(mm,address):
            if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
                active[0] = True
                extended.clear()
            if address == 0xF0000+mm.symbol('post_keyboard_wait') and active[0] and extended and not fast:
                mm.pending.append(1)  # Off must reach and restore an extended block before skipping.
            if address == 0xF0000+mm.symbol('init_peripherals'):
                active[0] = False
                assert ('Passed' if fast else 'Skipped') in mm.text(6,34,19)
        m.code_observer = observe
        m.cpu.hook_add(UC_HOOK_CODE,limit,begin=ready,end=ready)
        m.cpu.hook_add(UC_HOOK_MEM_WRITE,written)
        for warm in (False,True):
            if warm:
                m.controls[0xE1] |= 0x20
                m.write_bus(0x180000,b'KEEP')
                m.nvram[0x22C] = 0
                m.nvram[0x22D] = 0xA5
                m.nvram[0x22F] = 0x19
                m.nvram[0x232] = 0xE5
                m.nvram[0x22A] = (-0xD3-sum(m.nvram[0x22B:0x240])) & 255
            m.boot(warm=warm,count=5000000)
            assert m.booted and bool(extended) == (not fast)
            assert m.cpu.mem_read(m.base+0x60,1) == bytes((fast,))
            assert struct.unpack('<H',m.cpu.mem_read(m.base+0xD0,2))[0] == 15232
            assert m.controls[0xE0] == 0x6B
            assert m.cpu.mem_read(m.base+0x101E,1) == bytes((1 if warm else 2,))
            assert all(m.ti[unit*256+7] == (0 if warm else 0xAA00) for unit in range(3))
            if warm:
                assert m.ram_banks[0,1][0x80000:0x80004] == b'KEEP'
            assert m.ti[0x801] == (0x06A5 if warm else 0x06A4)
            assert m.ti[0x802] == (0x1919 if warm else 0x1515)
            assert m.ti[4] == (0x10E5 if warm else 0x10E4)
            assert '32 KB' in m.text(4,20,28)
        assert bounds == [0x100000 if fast else 0xFE0000]*2
        results.append(dict(fast_boot=fast,cold_and_warm=True,extended_block_tested=not fast,
                            extended_KiB=15232,shadow_On_Off_hardware=True,warm_payload_retained=True))
    return results


def empty_bank_navigation(image, seed):
    results = []
    for pairs in (((16,16),),((16,16),(0,0),(64,0))):
        m = port.machine(image,controllers=pairs,cache=False)
        m.cmos[:],m.nvram[:] = seed
        m.script_after_post = []
        saved = bytes(m.nvram)
        down,enter,escape = [0xE0,0x50],[28],[1]
        later = len(pairs) == 3
        target = 7 if later else 3
        # Empty Expansion Bank1, then a populated later or onboard bank.
        keys = down*4+enter+down*4+enter+enter+[15]+escape
        keys += (down*2 if later else [0xE0,0x48]*2)+enter
        keys += [0xE0,0x4D]+escape*3+enter
        entered,empty,returned,selected = [],[],[],[]
        initial = []
        def user(mm,address):
            if address == 0xF0000+mm.symbol('post_early_setup') and not entered:
                entered.append(True)
                mm.pending.extend((0xE0,0x53))
                mm.script = keys.copy()
                mm.post_script_armed = True
            if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
                mm.pending.append(1)
            if address != 0xF0000+mm.symbol('.input','setup_main'):
                return
            if mm.cpu.mem_read(mm.base+0xF5,1) != b'\x05':
                return
            screen = mm.cpu.mem_read(mm.base+0x278,1)[0]
            draft = bytes(mm.cpu.mem_read(mm.base+0x260,24))
            if not initial:
                initial.append(draft)
            if screen == 5:
                assert mm.cpu.mem_read(mm.base+0xF6,1) == b'\x00'
                assert draft == initial[0], 'Empty-bank input changed the draft'
                empty.append(True)
            if empty and screen == 0 and not returned:
                assert mm.cpu.mem_read(mm.base+0xF6,1) == b'\x01'
                returned.append(True)
            if screen == target:
                assert returned and mm.cpu.mem_read(mm.base+0xF6,1) == b'\x01'
                if draft != initial[0]:
                    differences = [i for i,(old,new) in enumerate(zip(initial[0],draft)) if old != new]
                    assert differences == [7+(target-3)*2+1],differences
                    selected.append(True)
        m.code_observer = user
        m.boot(count=5000000)
        assert m.booted and entered and empty and returned and selected
        assert bytes(m.nvram) == saved and not m.reset_count
        results.append(dict(topology=pairs,empty_bank_noneditable=True,returned_to_categories=True,
                            edited_populated_group=target,Discard_preserved_saved_record=True,signed_boot=True))
    return results


def interactive_setup(image, seed):
    m = port.machine(image,controllers=((16,16),(64,64),(64,64)),cache=True)
    m.cmos[:],m.nvram[:] = seed
    m.nvram[0x22B] = 0
    m.nvram[0x22A] = (-0xD3-sum(m.nvram[0x22B:0x240])) & 255
    m.script_after_post = []
    decoder = m.ram_key
    m.ram_key = lambda address: None if 0xFE0000 <= address < 0x1000000 else decoder(address)
    down,right,enter,escape = [0xE0,0x50],[0xE0,0x4D],[28],[1]
    up = [0xE0,0x48]
    # Boot: enable Fast Boot. Chipset: bus wait, refresh/shadow, then every bank.
    keys = down*2+enter+down*7+right+escape+down*2+enter+enter+down*5+right+escape
    keys += down+enter+right+down*4+right+[0x3B]+escape+escape
    for choice in (0,1,2,3,5,6):
        move = up*(4-choice) if choice < 4 else down*(choice-4)
        keys += down+enter+down*6+enter+move+enter+escape
    keys += [0x44,28]
    entered, screens, drafts = [], set(), []
    titles = ['Bus and DMA','Memory and ROM','Onboard Bank 1','Onboard Bank 2',
              'Expansion Bank 1','Expansion Bank 2','Expansion Bank 3','Expansion Bank 4']
    original = (0x10E4,0x10E4,0x16E4,0x16E4,0x16E4,0x16E4)
    selected = (0x10E0,0x10E1,0x16E2,0x16E3,0x16E5,0x16E6)
    expected_drafts = [selected[:n]+original[n:] for n in range(7)]
    input_entry = 0xF0000+m.symbol('.input','setup_main')
    def user(mm,address):
        if address == input_entry and mm.cpu.mem_read(mm.base+0xF5,1) == b'\x05':
            screen = mm.cpu.mem_read(mm.base+0x278,1)[0]
            screens.add(screen)
            if screen:
                assert mm.text(3,23,len(titles[screen-1])) == titles[screen-1]
            else:
                assert [mm.text(5+i,24,len(title)) for i,title in enumerate(titles)] == titles
                draft = struct.unpack('<6H',mm.cpu.mem_read(mm.base+0x267,12))
                if not drafts or drafts[-1] != draft:
                    drafts.append(draft)

        if address == 0xF0000+mm.symbol('post_early_setup') and not entered:
            entered.append(True)
            mm.pending.extend((0xE0,0x53))
            mm.script = keys.copy()
            mm.post_script_armed = True
    m.code_observer = user
    m.boot(count=5000000)
    assert entered and m.setup_entries == 1 and m.reset_count == 1
    assert m.booted and not m.script
    assert m.cpu.mem_read(m.base+0x60,2) == b'\x01\x00'
    assert m.ti[0x801] == 0x06A5
    assert all(m.ti[unit*256+3] == 0x4102 for unit in range(3))
    assert [m.ti[unit*256+4+bank] for unit in range(3) for bank in range(2)] == [0x10E0,0x10E1,0x36E2,0x36E3,0x36E5,0x36E6]
    assert m.cpu.mem_read(m.base+0x101E,1) == b'\x01'
    assert m.controls[0xE0] == 0x6B
    assert drafts == expected_drafts,(drafts,expected_drafts)
    assert screens == set(range(9)),screens
    return dict(rendered_category_order=titles,isolated_bank_drafts=drafts,keyboard_only_edits=True,all_six_banks=True,fast_boot=True,
                refresh_bus_shadow=True,verified_Save_warm_restart_and_signed_boot=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--boot',action='store_true')
    args = parser.parse_args()
    result,seed = check(args.image.resolve())
    print('PASS controls',json.dumps(result),flush=True)
    if args.boot:
        result['boot'] = boot_check(args.image.resolve(),seed)
        result['interactive'] = interactive_setup(args.image.resolve(),seed)
        result['empty_banks'] = empty_bank_navigation(args.image.resolve(),seed)
    output = port.OUT/'setup-controls.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2)+'\n')
    print('PASS', json.dumps(result), flush=True)
