"""Check MP386 images and execute the real adapter against synthetic devices."""
import argparse
import importlib
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from build import PORT, run, validate
from fixture import Tiger, rtc

OUT = PORT/'build/tests/results'


def boot_sector(a20=0xCD, board_gate=1):
    OUT.mkdir(parents=True, exist_ok=True)
    image = OUT/f'boot-{a20:02x}-{board_gate:02x}.bin'
    nasm = Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe'
    subprocess.run([str(nasm), '-w+error', '-f', 'bin', f'-DA20_OUTPUT={a20}',
                    f'-DA20_BOARD_OUTPUT={board_gate}',
                    '-o', str(image), str(PORT/'tests/boot.asm')], check=True)
    raw = image.read_bytes()
    assert len(raw) == 512 and raw[-2:] == b'\x55\xaa'
    return raw+b'DATA'+bytes(508)


def machine(image, **options):
    m = Tiger(image, **options)
    m.disk = boot_sector()
    return m


def image_checks(image):
    subprocess.run([sys.executable, '-B', str(PORT/'tools/build.py')],
                   check=True, capture_output=True, text=True)
    checked = validate(image)
    raw = Path(image).read_bytes()
    folder = OUT/'image-invalid'
    folder.mkdir(exist_ok=True)
    target = folder/'bad.bin'
    try:
        changes = []
        for offset in (0, 0xFFF0, 0xFFF1, 0xFFF5, 0xFFFE):
            altered = bytearray(raw)
            altered[offset] ^= 1
            altered[0xFFEF] = 0
            altered[0xFFEF] = (-sum(altered)) & 255
            changes.append(altered)
        for data in [raw[:-1], raw+b'\xff', raw[:100]+bytes((raw[100]^1,))+raw[101:]]+changes:
            target.write_bytes(data)
            try:
                validate(target)
            except ValueError:
                pass
            else:
                raise AssertionError('Invalid ROM accepted')
        target.write_bytes(raw)
        target.with_name('baios-mp386-even.bin').write_bytes(raw[1::2])
        target.with_name('baios-mp386-odd.bin').write_bytes(raw[::2])
        try:
            validate(target)
        except ValueError:
            pass
        else:
            raise AssertionError('Reversed lanes accepted')
    finally:
        for name in ('bad.bin', 'baios-mp386-even.bin', 'baios-mp386-odd.bin'):
            (folder/name).unlink(missing_ok=True)
        folder.rmdir()
    return checked


def boot_checks(image, reference=False):
    memory = importlib.import_module('test-memory')
    if reference:
        return memory.original_windows(image) + [
            memory.mapper_comparison(image, ((16,16),(64,64),(64,64))),
            memory.mapper_comparison(image, ((16,16),(0,0),(64,16))),
            *memory.early_sequence_checks(image),
            memory.reset_reference(image)]
    return memory.boot_checks(image)


def disk_controls_checks(image):
    rows = []
    # OEM0E8F..0EA7 gives these disk-control fields for the four switch states.
    for switches, field in ((0, 0), (0x10, 8), (0x40, 4), (0x50, 12)):
        m = machine(image, cache=True)
        m.disk_switches = switches
        observed = []
        def peripherals(mm, address):
            if address == 0xF0000+mm.symbol('init_floppy'):
                assert mm.controls[0xE2] == 0x80 | field
                assert mm.ti[0x801] == 0x06A4 and mm.ti[0x803] == 0
                observed.append(True)
        m.code_observer = peripherals
        m.boot()
        assert observed and m.booted
        assert bytes(m.cpu.mem_read(m.base+0x190, 1)) == b'\x01'
        assert bytes(m.cpu.mem_read(m.base+0x20, 1)) == b'\x01'
        assert m.processor_reset_count == 0
        rows.append(dict(switches=switches, control=m.controls[0xE2],
                         signed_disk_boot=True, ide_policy_preserved=True))
    return rows


def a20_boot_checks(image):
    rows = boot_checks(image)
    for gate, board_gate in ((0xCD, 0x81), (0xCD, 0xA1), (0xCF, 0x81), (0xCF, 0xA1)):
        m = machine(image, cache=True)
        m.disk = boot_sector(gate, board_gate)
        sent = []
        def key(mm, address):
            if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
                mm.pending.append(1)  # Keep A20 checks separate from the full RAM sweep.
            if address == 0xF0000+mm.symbol('move_extended_memory') and not sent:
                sent.append(True)
                mm.pending.append(0x1E)
        m.code_observer = key
        m.boot()
        assert sent and m.kbc_output == gate
        assert m.controls[0xE1] == board_gate
        assert m.pending == [0x1E], 'A20 gate consumed the queued scan'
        m.irq_scans([m.pending.pop(0)])
        head, tail = struct.unpack('<HH', m.cpu.mem_read(0x41A, 4))
        words = struct.unpack('<16H', m.cpu.mem_read(0x41E, 32))
        assert tail != head and 0x1E61 in words, (head, tail, words)
        assert bytes(m.cpu.mem_read(0x120000, 4)) == bytes.fromhex('44332211')
        rows.append(dict(kbc_unchanged=gate, a20_initial=board_gate, restored=board_gate, queued_key_preserved=True,
                         registers_preserved=True, signed_boot=True))
    return rows


def setup_checks(image):
    rows = []
    saved = machine(image, cache=True)
    def skip_RAM(m,address):
        if address == 0xF0000+m.symbol('chipset_visible_ram_test'):
            m.pending.append(1)
    saved.code_observer = skip_RAM
    saved.script_after_post = [0xE0, 0x53, 0x3F, 0x44, 28]
    saved.boot()
    assert saved.setup_entries == 1 and saved.reset_count == 1
    assert saved.cpu.mem_read(saved.base+0x13C, 1) == b'\x01'
    assert saved.nv_writes and all(0x200 <= a < 0x240 for a,v in saved.nv_writes)
    rows.append(dict(save_reopen_theme=1, signed_boot=True, extended_storage='OEM NVRAM'))
    saved_record = bytes(saved.cmos[0x38:0x40])
    saved_nvram = bytes(saved.nvram)
    cold_bytes = len(saved.ti_trace['cold'])
    resets = saved.reset_count
    trials = []
    def after_completion(m,address):
        if address == 0xF0000+m.symbol('chipset_visible_ram_test'):
            trials.append(m.cmos[0x36])
            assert m.cmos[0x36] == 0xAB
        skip_RAM(m,address)
    saved.code_observer = after_completion
    saved.irq_scans([0x1D, 0x38, 0xE0, 0x53])
    assert saved.reset_pending
    saved.boot(warm=True)
    assert saved.cpu.mem_read(saved.base+0x13C, 1) == b'\x01'
    assert bytes(saved.cmos[0x38:0x40]) == saved_record
    assert bytes(saved.nvram) == saved_nvram
    assert len(saved.ti_trace['cold']) == cold_bytes
    assert trials == [0xAB] and saved.cmos[0x36] == 0 and saved.reset_count == resets+1
    screen = bytes(saved.cpu.mem_read(0xB8000,4000))[::2].decode('cp437')
    assert 'RAM recovered' not in screen and 'RAM test failed' not in screen and 0xE7 not in saved.posts
    rows.append(dict(ctrl_alt_del=True, settings_preserved=True, signed_boot=True,
                     false_RAM_failure=False, internal_retries=0, intentional_resets=1))

    discarded = machine(image, cache=True)
    discarded.cmos[:] = saved.cmos
    discarded.nvram[:] = saved_nvram
    discarded.script_after_post = []
    entered = []
    captured = []
    rendered = set()
    def user(m, address):
        skip_RAM(m,address)
        if address == 0xF0000+m.symbol('post_early_setup') and not entered:
            entered.append(True)
            m.pending.extend((0xE0, 0x53))
            # Visit the switch guide and chipset categories, then discard the theme edit.
            m.script = [0x3F, 0x44, 1]+[0xE0,0x50]*3+[28,0x3B,1,0xE0,0x50,28,0x3B,1,1,1,28]
            m.post_script_armed = True
        if address == 0xF0000+m.symbol('chipset_ui_draw'):
            captured.append('chipset')
        if address == 0xF0000+m.symbol('mp_ports_draw'):
            captured.append('devices')
        if address == 0xF0000+m.symbol('.input','setup_main') and m.cpu.mem_read(m.base+0xFD,1) == b'\x01':
            page = m.cpu.mem_read(m.base+0xF5,1)[0]
            if page in (3,5):
                if page == 3:
                    assert m.cpu.mem_read(m.base+0xF6,1) == b'\x00'
                    assert 'Off 6 / On 8 MHz' in m.text(6,24,28)
                else:
                    assert 'Bus and DMA' in m.text(5,24,24)
                rendered.add(page)
    discarded.code_observer = user
    discarded.boot()
    assert discarded.setup_entries == 1 and not discarded.reset_count
    assert discarded.cpu.mem_read(discarded.base+0x13C, 1) == b'\x01'
    assert bytes(discarded.cmos[0x38:0x40]) == saved_record
    assert bytes(discarded.nvram) == saved_nvram
    assert {'chipset', 'devices'} <= set(captured)
    assert rendered == {3,5}
    rows.append(dict(canceled_save_and_discard=True, readonly_switch_guide=True,
                     saved_theme=1, signed_boot=True))
    return rows


def ram_checks(image):
    # A completed first setup record avoids an unrelated defaults/reset sweep.
    seed = machine(image, cache=True)
    seed.boot()
    assert seed.cpu.mem_read(seed.base+0x50,1) == b'\x04'
    rows = []
    for enabled,command in ((enabled,command) for enabled in (False,True)
                            for command in ('complete','escape','delete','pause')):
        m = machine(image, cache=enabled)
        m.cmos[:] = seed.cmos
        m.nvram[:] = seed.nvram
        m.script_after_post = []
        state = {'sent': False, 'paused': False, 'resumed': False}
        events = []
        before = bytes.fromhex('739a25e1')*512
        canaries, tested = {}, set()
        read = m.cache_read
        def track(address,value):
            if state.get('active') and address in canaries and value == 0xAA:
                tested.add(address)
            return read(address,value)
        m.cache_read = track
        def restored():
            for address,key in canaries.items():
                unit,bank,offset = key
                assert m.ram_banks[unit,bank][offset:offset+len(before)] == before,(enabled,command,hex(address))
        def user(mm, address):
            if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
                events.append('ram')
                state['active'] = True
                gate = mm.controls[0xE1]
                mm.controls[0xE1] |= 0x20
                for target in (0x10000,0x88000,0x180000):
                    canaries[target] = mm.ram_key(target)
                    mm.write_bus(target,before)
                mm.controls[0xE1] = gate
            if address == 0xF0000+mm.symbol('init_peripherals'):
                state['active'] = False
                events.append('peripherals')
                expected = 'Skipped' if command in ('escape','delete') else 'Passed'
                assert expected in mm.text(6,34,19)
            if address == 0xF0000+mm.symbol('post_keyboard_wait'):
                active = mm.cpu.mem_read(mm.base+0x50, 1)[0] & 1
                if active and not state['sent'] and command != 'complete':
                    state['sent'] = True
                    mm.pending.extend({'escape': [1], 'delete': [0xE0,0x53],
                                       'pause': [0xE1,0x1D,0x45,0xE1,0x9D,0xC5]}[command])
                    if command == 'delete':
                        mm.script = [1, 28]
                        mm.post_script_armed = True
            if command == 'pause' and mm.cpu.mem_read(0x4A7, 1) == b'\x01':
                state['paused'] = True
                if not state['resumed'] and not mm.pending:
                    mm.pending.append(0x1E)
                    state['resumed'] = True
        m.code_observer = user
        m.boot(count=30000000)
        restored()
        flags = m.cpu.mem_read(m.base+0x50, 1)[0]
        assert flags == (2 if command in ('escape', 'delete') else 4), (command, flags)
        if command == 'delete':
            assert m.setup_entries == 1
        if command == 'pause':
            assert state['paused'] and state['resumed']
        if command in ('complete','pause'):
            assert tested == set(canaries),(enabled,command,tested)
        assert int.from_bytes(m.cpu.mem_read(m.base+0xD0, 2), 'little') == 1024
        assert m.kbc_output == 0xCD and not m.port92_accesses
        assert events[:2] == ['ram','peripherals']
        if command == 'complete':
            assert m.ram_reads > 100000
            read_count = m.ram_reads
            m.boot(warm=True, count=30000000)
            assert m.ram_reads-read_count > 100000
            assert m.cpu.mem_read(m.base+0x50,1) == b'\x04'
            restored()
            assert events == ['ram','peripherals','ram','peripherals']
        rows.append(dict(cache=enabled,command=command,ram_flags=flags,restored_blocks=list(canaries),
                         later_blocks_tested=sorted(tested),signed_boot=True))
    return rows


def retained_checks(image):
    root = PORT.parent
    # Public base a8d0542, before MP386 and the authorized Auto CHS repair.
    baseline = {'pb430': '327dda7210f4a73d6249bf47f196c7334f3d0e01595b4fda3b354ccb741aa999',
                'm919': '1bfed215c3da785ec656a49093ab2526681131273662d09124d7e88b9f9cbc73',
                'presario-800': '6d2ad1cb91c7b9aca8cf4ed877a2f1eeb85c3d879f3b488b0a1cc158fa1dbaae'}
    from shared.tools.rom import build, configuration
    rows = []
    nasm = Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe'
    for name in ('pb430', 'm919', 'presario-800'):
        port = root/name
        folder = OUT/'retained-source'/name
        folder.mkdir(parents=True, exist_ok=True)
        includes = ['-I', str(port/'src')+'/', '-I', str(root/'shared/src')+'/']
        if name == 'presario-800':
            target = folder/'production.bin'
            subprocess.run([str(nasm), '-f', 'bin', *includes, '-o', str(target),
                            str(port/'src/bios.asm')], cwd=root, check=True)
            ide = port/'src/ide.inc'
            override = folder/'ide.inc'
            data = None
        else:
            result = build(port, 'build/tests/mp386-regression')
            target = Path(result['path'])
            includes += ['-I', str(target.parent)+'/']
            ide = root/'shared/src/firmware/ide.inc'
            override = folder/'firmware/ide.inc'
            _, data = configuration(port)
        production_hash = hashlib.sha256(target.read_bytes()).hexdigest()
        assert production_hash != baseline[name], name
        # Reverse only the two-instruction repair in a generated include.
        # Production source and the current port images remain untouched.
        source = ide.read_text()
        gate = 'ide_initialize_geometry:\n    cmp byte [fs:S_CHS_ONLY], 1\n    jne .unchanged\n'
        assert source.count(gate) == 1
        override.parent.mkdir(exist_ok=True)
        override.write_text(source.replace(gate, gate+
            '    cmp byte [fs:S_IDE + IDE_TYPE], 0\n    je .unchanged\n'))
        proof = folder/'before-chs-fix.bin'
        subprocess.run([str(nasm), '-f', 'bin', '-I', str(folder)+'/', *includes,
                        '-o', str(proof), str(port/'src/bios.asm')], cwd=root, check=True)
        raw = bytearray(proof.read_bytes())
        if data:
            raw[data['rom']['checksum_offset']] = 0
            raw[data['rom']['checksum_offset']] = (-sum(raw)) & 255
            proof.write_bytes(raw)
        assert hashlib.sha256(raw).hexdigest() == baseline[name], name
        rows.append(dict(port=name, identical_except_auto_chs=True,
                         production_sha256=production_hash, size=len(raw)))
    return rows


def recovery_checks(image):
    seed = machine(image,cache=False)
    def skip(m,address):
        if address == 0xF0000+m.symbol('chipset_visible_ram_test'):
            m.pending.append(1)
    seed.code_observer = skip
    seed.boot()
    rows = []
    for marker in (0x1A,0xAB,0x5A,0xDA):
        m = machine(image,cache=False)
        m.cmos[:],m.nvram[:] = seed.cmos,seed.nvram
        m.cmos[0x36] = marker
        m.script_after_post = []
        observed = []
        def observe(mm,address):
            if address == 0xF0000+mm.symbol('chipset_post_recovery_notice'):
                assert mm.cmos[0x36] == (0xDA if marker in (0x5A,0xDA) and not observed else 0xAB)
            if address == 0xF0000+mm.symbol('.done','post_debug_summary'):
                recovered = 'RAM recovered' in mm.text(13,54,13)
                assert recovered == (marker in (0x5A,0xDA) and not observed), (marker,observed,mm.text(13,0,80))
                observed.append(recovered)
            skip(mm,address)
        m.code_observer = observe
        m.boot()
        m.boot(warm=True)
        assert len(observed) == 2 and not observed[1] and m.cmos[0x36] == 0
        rows.append(dict(marker=f'{marker:02X}',cold_notice=observed[0],warm_notice=False))
        print('PASS recovery marker',f'{marker:02X}','cold/warm',flush=True)
    for persistent in (False,True):
        m = machine(image,cache=False)
        m.cmos[:],m.nvram[:] = seed.cmos,seed.nvram
        m.nvram[0x22B] = 1
        m.nvram[0x22D] = 0xA5
        m.nvram[0x22A] = (-0xD3-sum(m.nvram[0x22B:0x240])) & 255
        m.cmos[0x36] = 0
        m.script_after_post = []
        attempts,failed,before = [],[],[]
        def observe(mm,address):
            if address == 0xF0000+mm.symbol('controlled_defaults_restart'):
                assert mm.ti[0x801] == 0x06A4 and mm.ti[0x802] == 0x1515
                assert mm.ti[3] == 0x4101 and mm.ti[4] == mm.ti[5] == 0x10E4
                assert mm.controls[0xE0] == 0 and mm.nvram[0x229] == 0xD2
            if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
                attempts.append(mm.cmos[0x36])
                assert mm.ti[0x801] == (0x06A5 if len(attempts) == 1 else 0x06A4)
                assert mm.controls[0xE0] == 0
                key = mm.ram_key(0x10000)
                before.append(bytes(mm.ram_banks[key[0],key[1]][key[2]:key[2]+4]))
        read = m.cache_read
        def bad_dram(address,value):
            if attempts and (persistent or len(attempts) == 1) and address == 0x10000:
                key = m.ram_key(address)
                unit,bank,offset = key
                if m.ram_banks[unit,bank][offset:offset+4] == bytes.fromhex('aa55aa55'):
                    failed.append(len(attempts))
                    return value ^ 1
            return read(address,value)
        m.code_observer,m.cache_read = observe,bad_dram
        try:
            m.boot(count=30000000)
        except AssertionError as error:
            assert persistent and 'firmware halt' in str(error),str(error)
        else:
            assert not persistent and m.booted
            assert m.cpu.mem_read(m.base+0x50,1) == b'\x04'
        assert attempts == [0xAB,0x1A] and m.reset_count == 1,(attempts,m.reset_count,m.posts[-8:])
        assert set(failed) == ({1,2} if persistent else {1}),failed
        assert m.ram_banks[0,0][0x10000:0x10004] == before[-1],(before,bytes(m.ram_banks[0,0][0x10000:0x10004]))
        if persistent:
            assert m.posts[-1] == 0xE7
        rows.append(dict(persistent=persistent,external_DRAM_fault=True,internal_retry=1,
                         terminal='E7' if persistent else 'signed boot'))
        print('PASS real RAM failure',persistent,'one internal retry',flush=True)
    rows.extend(timing_recovery_checks(image,seed))
    return rows


def timing_recovery_checks(image, seed):
    from unicorn import UC_HOOK_CODE, UC_HOOK_INSN
    from unicorn import x86_const as x
    rows = []
    def factory(guard=0xD3):
        m = machine(image,cache=True)
        m.cmos[:],m.nvram[:] = seed.cmos,seed.nvram
        m.script_after_post = []
        m.nvram[0x229] = guard
        m.nvram[0x22B] = 1  # Fast Boot shortens this timing/reset proof, not the detected RAM.
        m.nvram[0x22D] = 0xA5
        m.nvram[0x22A] = (-0xD3-sum(m.nvram[0x22B:0x240])) & 255
        m.cmos[0x36] = 0
        return m
    def skip(mm,address):
        if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
            mm.pending.append(1)
    def safe(mm):
        assert mm.ti[0x801] == 0x06A4
        assert mm.ti[0x802] == 0x1515
        assert mm.ti[3] == 0x4101
        assert mm.ti[4] == mm.ti[5] == 0x10E4
    def interrupted(m,label):
        events,stopped = [],[]
        target = 0xF0000+m.symbol(label)
        def observe(mm,address):
            if address == 0xF0000+mm.symbol('mp_timing_apply'):
                assert mm.cmos[0x36] == 0xAB, 'Timings preceded the persistent trial'
            if label != 'chipset_timing_trial_finish':
                skip(mm,address)
            for name in ('option_rom_discovery','post_debug_summary'):
                if address == 0xF0000+mm.symbol(name):
                    events.append(name)
            if address == target:
                assert mm.cmos[0x36] == 0xAB
                assert mm.ti[0x801] == 0x06A5
                if label == 'chipset_timing_trial_finish':
                    assert events == ['option_rom_discovery','post_debug_summary'],events
                    assert mm.cpu.mem_read(mm.base+0x50,1) == b'\x04'
                stopped.append(True)
                mm.cpu.emu_stop()
        m.code_observer = observe
        try:
            m.boot(count=5000000)
        except AssertionError as error:
            assert stopped and error.args[0][0] == 'no signed boot',str(error)
        else:
            raise AssertionError('External interruption did not stop POST')
        assert m.nvram[0x229] == 0xD3 and not m.reset_count
    def reopen(m,warm=False,script=None,stop=True):
        entered,shown = [],[]
        def observe(mm,address):
            skip(mm,address)
            if address == 0xF0000+mm.symbol('post_early_setup') and not entered:
                safe(mm)
                assert mm.nvram[0x229] == 0xD2
                assert mm.cmos[0x36] not in (0x1A,0x5A,0xDA)
                entered.append(True)
                mm.pending.extend((0xE0,0x53))
                mm.script = list(script or ())
                mm.post_script_armed = True
            if address == 0xF0000+mm.symbol('.input','setup_main') and entered and not shown:
                shown.append(True)
                assert mm.setup_entries >= 1
                if stop:
                    mm.cpu.emu_stop()
        m.code_observer = observe
        try:
            m.boot(warm=warm,count=5000000)
        except AssertionError as error:
            assert stop and shown and error.args[0][0] == 'no signed boot',str(error)
        else:
            assert not stop and m.booted
        assert entered and shown
        assert 0xE7 not in m.posts
        assert 'RAM recovered' not in m.text(13,54,13)
        return shown
    # Real reset events at both ends of the timing-dependent POST window.
    for label in ('cache_test','chipset_timing_trial_finish'):
        for power in (False,True):
            m = factory()
            interrupted(m,label)
            payload = bytes(m.nvram[0x22A:0x240])
            if power:
                old = m
                m = factory()
                m.cmos[:],m.nvram[:] = old.cmos,old.nvram
            else:
                assert m.sys_flag & 4
            cold = len(m.ti_trace['cold'])
            reopen(m,warm=not power)
            assert len(m.ti_trace['cold']) > cold,'Pending CPU reset used unsafe retained warm RAM'
            assert bytes(m.nvram[0x22A:0x240]) == payload
            assert not m.reset_count
            rows.append(dict(interrupted_at=label,power_loss=power,safe_Setup=True,
                             payload_preserved=True,false_RAM_failure=False,internal_retries=0))
            print('PASS interrupted timing',label,'power' if power else 'CPU reset',flush=True)
    # Completed POST retires the trial; an ordinary reset retains the saved choice.
    m = factory()
    m.code_observer = skip
    m.boot(count=5000000)
    assert m.cmos[0x36] == 0 and m.nvram[0x229] == 0xD3 and m.ti[0x801] == 0x06A5
    m.boot(warm=True,count=5000000)
    assert m.cmos[0x36] == 0 and m.nvram[0x229] == 0xD3 and m.ti[0x801] == 0x06A5
    rows.append(dict(completed_trial=True,saved_timings_retained=True))
    # Cancel Save, then Discard, finish POST and reopen after a later reset.
    m = factory(0xD2)
    payload = bytes(m.nvram[0x22A:0x240])
    reopen(m,script=[0x3F,0x44,1,1,28],stop=False)
    assert m.nvram[0x229] == 0xD2 and m.cmos[0x36] == 0
    assert bytes(m.nvram[0x22A:0x240]) == payload
    reopen(m,warm=True)
    assert bytes(m.nvram[0x22A:0x240]) == payload and not m.reset_count
    rows.append(dict(cancel_Discard_then_reset=True,safe_Setup=True,payload_preserved=True))
    # A real keyboard reset during POST retires the trial after safe restoration.
    m = factory()
    sent,reset_seen = [],[]
    def deliberate(mm,address):
        if address == 0xF0000+mm.symbol('post_keyboard_wait') and not sent:
            if mm.cpu.mem_read(mm.base+0x50,1)[0] & 1:
                sent.append(True)
                mm.pending.extend((0x1D,0x38,0xE0,0x53))
        if address == 0xF0000+mm.symbol('warm_reset'):
            reset_seen.append(True)
        if sent and reset_seen:
            skip(mm,address)
    m.code_observer = deliberate
    m.boot(count=5000000)
    assert sent and reset_seen and m.reset_count == 1
    assert m.nvram[0x229] == 0xD3 and m.cmos[0x36] == 0 and m.ti[0x801] == 0x06A5
    assert 'RAM recovered' not in m.text(13,54,13) and 0xE7 not in m.posts
    rows.append(dict(intentional_POST_reset=True,saved_timings_retained=True,false_RAM_failure=False))
    # The whole-save terminal owner, including its final marker write, owns release.
    for fault in (None,'timing-cell','base-cell','marker-clear','power-before-commit'):
        m = factory(0xD2)
        oem = bytes(m.nvram[0x240:])
        entered,errors,stopped,blocked = [],[],[],[]
        down,enter = [0xE0,0x50],[28]
        keys = [0x3F]+down*4+enter+enter+down*5+[0xE0,0x4D]*2+[0x44,28]
        class Storage(bytearray):
            def __setitem__(self,index,value):
                reject = fault == 'timing-cell' and index == 0x22D
                if reject:
                    blocked.append(True)
                else:
                    super().__setitem__(index,value)
        class Clock(bytearray):
            def __setitem__(self,index,value):
                reject = fault == 'base-cell' and index == 0x3C
                reject |= (fault == 'marker-clear' and index == 0x36 and value == 0
                           and m.nvram[0x229] == 0xD3 and not blocked)
                if reject:
                    blocked.append(True)
                else:
                    super().__setitem__(index,value)
        m.nvram,m.cmos = Storage(m.nvram),Clock(m.cmos)
        def saving(mm,address):
            skip(mm,address)
            if address == 0xF0000+mm.symbol('post_early_setup') and not entered:
                safe(mm)
                entered.append(True)
                mm.pending.extend((0xE0,0x53))
                mm.script,mm.post_script_armed = keys.copy(),True
            if address == 0xF0000+mm.symbol('chipset_timing_saved'):
                assert mm.nvram[0x229] == 0xD2 and mm.nvram[0x22D] == 0xA6
                if fault == 'power-before-commit':
                    stopped.append(True)
                    mm.cpu.emu_stop()
            if address == 0xF0000+mm.symbol('.save_error','setup_main'):
                assert mm.nvram[0x229] == 0xD2
                errors.append(True)
                mm.script = [1,1,1,28]
        m.code_observer = saving
        try:
            m.boot(count=5000000)
        except AssertionError as error:
            assert stopped and fault == 'power-before-commit' and error.args[0][0] == 'no signed boot',str(error)
        assert entered and bytes(m.nvram[0x240:]) == oem
        if fault is None:
            assert m.booted and m.reset_count == 1
            assert m.nvram[0x229] == 0xD3 and m.nvram[0x22D] == 0xA6
            assert m.cmos[0x36] == 0 and m.ti[0x801] == 0x06A6
        else:
            assert m.nvram[0x229] == 0xD2 and not m.reset_count
            if fault != 'power-before-commit':
                assert blocked and errors and m.booted
            fresh = factory()
            fresh.cmos[:],fresh.nvram[:] = m.cmos,m.nvram
            reopen(fresh)
            assert fresh.nvram[0x229] == 0xD2 and not fresh.reset_count
            assert bytes(fresh.nvram[0x240:]) == oem
        rows.append(dict(whole_Save=fault or 'verified',safe_until_whole_commit=True,
                         safe_reopen=fault is not None,OEM_records_preserved=True))
        print('PASS whole timing Save',fault or 'verified',flush=True)
    # Reference service resumes bypass ordinary POST and trial classification.
    for shutdown in (5,0x0A):
        m = factory()
        m.code_observer = skip
        m.boot(count=5000000)
        m.cpu.mem_write(0x467,struct.pack('<HH',0x9000,0))
        m.cpu.mem_write(0x9000,b'\xF4')
        m.cmos[0x0F],m.cmos[0x36] = shutdown,0xAB
        before = (dict(m.ti),dict(m.maps),bytes(m.nvram),m.controls[0xE0])
        io,reached = [],[]
        def output(cpu,port,size,value,unused):
            io.append((port,value))
        hook = m.cpu.hook_add(UC_HOOK_INSN,output,None,1,0,x.UC_X86_INS_OUT)
        def resume(mm,address):
            if address == 0x9000:
                reached.append(True)
                assert mm.cpu.reg_read(x.UC_X86_REG_DS) == 0x40
                mm.cpu.emu_stop()
        m.code_observer = resume
        try:
            m.boot(warm=True,count=10000)
        except AssertionError as error:
            assert reached and error.args[0][0] == 'no signed boot',str(error)
        m.cpu.hook_del(hook)
        assert reached and m.cmos[0x0F] == 0 and m.cmos[0x36] == 0xAB
        assert (dict(m.ti),dict(m.maps),bytes(m.nvram),m.controls[0xE0]) == before
        assert [(port,value) for port,value in io if port in (0x20,0xA0)] == ([(0x20,0x20)] if shutdown == 5 else [])
        assert not any(port in (0x24,0x26,0x5A,0x5B) for port,value in io)
        rows.append(dict(service_resume=f'{shutdown:02X}',reference_vector=True,trial_unchanged=True))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=PORT/'build/baios-mp386.bin')
    parser.add_argument('--case', choices=('image', 'reference', 'boot', 'disk', 'setup', 'ram', 'recovery', 'retained'), required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    image = args.image.resolve()
    checks = {'image': image_checks, 'reference': lambda p: boot_checks(p, True),
              'boot': a20_boot_checks, 'disk': disk_controls_checks, 'setup': setup_checks, 'ram': ram_checks,
              'recovery': recovery_checks, 'retained': retained_checks}
    result = checks[args.case](image)
    (OUT/(args.case+'.json')).write_text(json.dumps(dict(case=args.case, image_sha256=hashlib.sha256(image.read_bytes()).hexdigest(), result=result), indent=2)+'\n')
    print('PASS', args.case, json.dumps(result, default=str)[:1500])


if __name__ == '__main__':
    main()
