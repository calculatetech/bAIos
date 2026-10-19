"""Check native POST display and input through assembled production owners."""
import argparse
import importlib
import struct

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn import x86_const as x

setup = importlib.import_module('test-setup')
rtc = setup.rtc
legacy = importlib.import_module('test-legacy-boot')


def display():
    for banks, mode, l1, l2 in ((0x0004, 0, False, 0), (0x4044, 0, True, 3),
                                (0x4444, 0x20, True, 6)):
        m = setup.Setup()
        m.chipset.update({2: banks & 255, 3: banks >> 8, 4: mode, 7: 8 if l1 else 0, 0x19: l2})
        m.cpu.reg_write(x.UC_X86_REG_CR0, 0x10 if l1 else 0x60000010)
        m.cpu.mem_write(m.base + 0x50, b'\x04\x05\x00')
        m.cpu.mem_write(m.base + 0x69, b'\x31')
        m.cpu.mem_write(m.base + 0xD4, struct.pack('<H', 0x1532))
        m.cpu.mem_write(m.base + 0x78, struct.pack('<H', 64512))
        m.cpu.mem_write(m.base + 0x80, b'\x04\x02')
        for offset in (0, 0x200):
            m.cpu.mem_write(m.base + offset + 0x1E3, b'\x01')
            m.cpu.mem_write(m.base + offset + 0x171, b'\x01')
            m.cpu.mem_write(m.base + offset + 0x20, b'\x01')
            m.cpu.mem_write(m.base + offset + 0x2E, struct.pack('<I', 0x0FFFFFFF))
            m.cpu.mem_write(m.base + offset + 0x140, b'MAXIMUM MODEL '+b'X'*26+b'\0')
        saved = bytes(m.cmos)
        m.call('post_ui_begin')
        header = bytes(m.cpu.mem_read(0xB8000, 160))
        assert m.text(2, 24, 12) == 'Pentium P24T'
        assert m.text(3, 24, 8).strip() == ('Enabled' if l1 else 'Disabled')
        assert m.text(14, 3, 2) == 'L2'
        assert m.text(14, 24, 8) == ('Enabled,' if l2 else 'Not dete')
        assert m.text(5, 24, 5) == '65536' and m.text(5, 30, 2) == 'KB'
        assert m.text(5, 34, 6) == 'Passed'
        expected = {0x0004: '0', 0x4044: '0 1 3', 0x4444: '0 1 2 3, Interleaved'}[banks]
        assert m.text(6, 24, len(expected)) == expected
        assert m.text(8, 24, 14) == '1.44 MB, 3.5 i'
        assert m.text(9, 24, 14) == '1.2 MB, 5.25 i'
        assert m.text(11, 24, 40) == 'MAXIMUM MODEL '+ 'X'*26
        assert m.text(11, 64, 16) == m.text(12, 64, 16) == ' '*16
        assert m.text(15, 3, 8) == 'VGA BIOS'
        assert m.text(16, 3, 11) == 'System BIOS'
        assert m.text(17, 24, 12) == 'Not detected'
        assert m.cpu.mem_read(0x450, 2) == b'\x03\x16'
        assert 'Pause' not in m.text(24, 0, 80)
        assert bytes(m.cmos) == saved
        if not l2:
            m.cpu.mem_write(m.base+0x69, b'\x30')
            m.call('post_ui_cache')
            assert m.text(14, 24, 8) == 'Disabled'
            m.cpu.mem_write(m.base+0x69, b'\x31')
        m.call('post_debug_summary')
        assert bytes(m.cpu.mem_read(0xB8000, 160)) == header
    m = setup.Setup()
    formatter = 0xF0000 + rtc.symbol('post_count')
    hook = m.cpu.hook_add(UC_HOOK_CODE,
                          lambda cpu, address, size, unused: cpu.reg_write(x.UC_X86_REG_ES, 0xB800),
                          None, formatter, formatter)
    for count in (0, 9, 10, 128, 8192, 65536, 128):
        m.cpu.reg_write(x.UC_X86_REG_EAX, count)
        m.cpu.reg_write(x.UC_X86_REG_DI, 5*160+24*2)
        m.call('post_count')
        assert m.text(5, 24, 5) == str(count).ljust(5)
    m.cpu.hook_del(hook)
    print('POST display: shared exact header, full aligned records, active cache/banks, DOS units PASS', flush=True)


def flow():
    for cold, kinds, signature, enabled in ((True, ('ata', 'packet'), 0x0430, True),
                                            (False, ('absent', 'ata'), 0x1532, False)):
        m = setup.production_post_model(kinds=kinds, peripherals=True)
        setup.schema2_fixture(m, types=0x42, flags=0x09, order=(2, 0, 0))
        policy = bytearray(importlib.import_module('test-chipset').NORMAL)
        if not enabled: policy[4] &= ~8
        m.cmos[0x69], m.cmos[0x6A] = 0xC2, -(0xC2+sum(policy)) & 255
        m.cmos[0x6B:0x80], m.cmos[0x33:0x36] = policy[:21], policy[21:]
        if cold: m.cpu.reg_write(x.UC_X86_REG_EDX, signature)
        else: m.cpu.mem_write(m.base+0xD4, struct.pack('<H', signature))
        seen = []
        progress, positions = [], []
        def ram_read(cpu, access, address, size, value, unused):
            if m.cpu.mem_read(m.base+0x51, 1)[0] == 1 and m.cpu.mem_read(m.base+0x50, 1)[0] & 1:
                assert m.text(5, 3, 8) == 'RAM Test'
                assert m.text(5, 34, 10) == ' '*10
                assert m.text(5, 24, 5).strip().isdigit()
                assert m.text(5, 24, 1).isdigit()
                assert m.text(6, 3, 12) == ' '*12
                progress.append(address)
        ram_hook = m.cpu.hook_add(UC_HOOK_MEM_READ, ram_read, None, 0x20000, 0x20003)
        def position(cpu, address, size, unused):
            slot = cpu.reg_read(x.UC_X86_REG_FS)*16
            slave = bool(cpu.mem_read(slot+0x25, 1)[0])  # S_ATA_DEVICE in the selected record.
            positions.append(slave)
            assert m.text(12, 3, 18) == ' '*18
            if slave:
                assert m.text(11, 3, 18) == 'Primary IDE Master'
                assert m.text(11, 24, 12) == ('FIXTURE ATA0' if kinds[0] == 'ata' else 'Not detected')
            else:
                assert m.text(11, 3, 18) == ' '*18
        identify = 0xF0000 + rtc.symbol('ata_identify_selected')
        disk_hook = m.cpu.hook_add(UC_HOOK_CODE, position, None, identify, identify)
        def observe(model, name):
            if name == 'settings_load':
                assert model.text(2, 3, 9) == 'Processor'
                for row in (3, 5, 6, 8, 9, 11, 12, 14, 15, 16, 17):
                    assert model.text(row, 0, 80) == ' '*80, (name, row, model.text(row, 0, 80))
            if name == 'chipset_visible_ram_test':
                assert model.text(3, 3, 8) == 'L1 Cache'
                assert model.text(3, 40, 37) == ' '*37
                for row in (5, 6, 8, 9, 11, 12, 14, 15, 16, 17):
                    assert model.text(row, 0, 80) == ' '*80, (name, row, model.text(row, 0, 80))
            if name == 'init_floppy':
                assert model.text(5, 34, 6) == 'Passed' and model.text(6, 3, 12) == 'Memory Banks'
                for row in (8, 9, 11, 12, 14, 15, 16, 17):
                    assert model.text(row, 0, 80) == ' '*80
            if name == 'ata_detect_primary':
                assert model.text(8, 3, 14) == 'Floppy Drive A'
                for row in (11, 12, 14, 15, 16, 17):
                    assert model.text(row, 0, 80) == ' '*80
            if name == 'chipset_late_cache':
                assert model.text(3, 40, 37) == ' '*37
                assert model.text(14, 0, 80) == ' '*80
                assert model.text(15, 0, 80) == ' '*80
                assert model.text(16, 0, 80) == ' '*80
                assert model.text(17, 0, 80) == ' '*80
            if name == 'option_rom_discovery':
                assert model.text(14, 3, 2) == 'L2'
                assert model.text(15, 3, 8) == 'VGA BIOS'
                assert model.text(16, 3, 11) == 'System BIOS'
                assert model.text(17, 24, 12) == 'Not detected'
            if name == 'post_debug_summary':
                seen.append('post')
                assert model.text(2, 24, 7 if signature == 0x0430 else 12).strip() == ('486DX2' if signature == 0x0430 else 'Pentium P24T')
                assert model.text(3, 24, 8).strip() == ('Enabled' if enabled else 'Disabled')
                assert model.text(14, 24, 12) == 'Not detected'
                assert model.text(5, 34, 6) == 'Passed'
                assert model.text(8, 24, 14) == '1.44 MB, 3.5 i'
                assert model.text(9, 24, 14) == '1.2 MB, 5.25 i'
                assert model.text(11, 24, 12) == ('FIXTURE ATA0' if kinds[0] == 'ata' else 'Not detected')
                assert model.text(12, 24, 12).startswith('FIXTURE')
                assert model.text(11, 64, 16) == model.text(12, 64, 16) == ' '*16
                for token in ('bootstrap', 'Policy:', 'RAMSET', 'COM:', 'LPT:'):
                    assert token not in model.console, model.console
        m.startup_observer = observe
        try:
            m.startup(reset=cold, production_controls=True, through_boot=True)
        finally:
            m.cpu.hook_del(ram_hook)
            m.cpu.hook_del(disk_hook)
        assert progress and positions == [False, True], (progress, positions)
        assert seen == ['post'] and m.cpu.mem_read(0x7C00, 4) == b'BOOT'
    print('POST flow: cold/warm progressive groups, live RAM count, individual IDE results -> summary -> BOOT PASS', flush=True)


def configuration_flow():
    # The chipset register fixture is opaque hardware readback. All publication,
    # readers, renderers, summary, and bootstrap owners execute normally.
    cases = (
        ('full', {}), ('short', {'full': False}), ('cpu', {'signature': 0x1532}),
        ('l1-off', {'l1': False}), ('l2-off', {'l2': False}),
        ('one-bank', {'banks': 0x0004, 'mode': 0, 'bank_text': '0'}),
        ('late-bank', {'banks': 0x5444, 'mode': 0, 'bank_text': '0 1 2 3'}),
        ('master-none', {'flags': 0x29, 'master': 'Disabled'}),
        ('slave-none', {'flags': 0x49, 'slave': 'Disabled'}),
        ('slave-absent', {'kinds': ('ata', 'absent'), 'slave': 'Not detected'}),
        ('master-absent', {'kinds': ('absent', 'ata'), 'master': 'Not detected'}),
        ('packet', {'kinds': ('ata', 'packet')}),
        ('floppy-none', {'types': 0}),
    )
    for name, options in cases:
        m = setup.production_post_model(kinds=options.get('kinds', ('ata', 'ata')))
        m.cpu.mem_write(0xB8FA0, b'Q'*32)  # First bytes beyond the80x25 screen.
        setup.schema2_fixture(m, types=options.get('types', 0x42),
                              flags=options.get('flags', 0x09), order=(2, 0, 0))
        importlib.import_module('test-ide-options').saved(m)
        importlib.import_module('test-ports').record(m, bytes((1, 2, 1, 0, 1, 1, 0, 1)))
        policy = bytearray(importlib.import_module('test-chipset').NORMAL)
        policy[10] |= 0x80  # Identical saved interleave preference in every case.
        if not options.get('l1', True): policy[4] &= ~8
        if not options.get('l2', True): policy[9] &= ~1
        m.cmos[0x69], m.cmos[0x6A] = 0xC2, -(0xC2+sum(policy)) & 255
        m.cmos[0x6B:0x80], m.cmos[0x33:0x36] = policy[:21], policy[21:]
        models = ('MASTER '+ 'M'*33, 'SLAVE '+ 'S'*34) if options.get('full', True) else ('MASTER', 'SLAVE')
        for data, model in zip(m.disk_device.payloads, models):
            encoded = model.ljust(40).encode('ascii')
            data[54:94] = bytes(value for i in range(0, 40, 2) for value in encoded[i:i+2][::-1])
        signature = options.get('signature', 0x0430)
        m.cpu.reg_write(x.UC_X86_REG_EDX, signature)
        hooks, header, checked = [], [], []
        watch_renderer_writes(m, hooks)
        def banks(cpu, address, size, unused):
            geometry = options.get('banks', 0x4444)
            m.chipset.update({2: geometry & 255, 3: geometry >> 8,
                              4: options.get('mode', 0x20)})
        point = 0xF0000+rtc.symbol('post_ui_banks')
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE, banks, None, point, point))
        def count(cpu, access, address, size, value, unused):
            if cpu.reg_read(x.UC_X86_REG_CR0) & 1 and m.cpu.mem_read(m.base+0x50, 1)[0] & 1:
                # .progress publishes the walker's address at each64KiB boundary.
                assert m.text(5, 24, 5) == '128  '
        hooks.append(m.cpu.hook_add(UC_HOOK_MEM_READ, count, None, 0x20000, 0x20003))
        def observe(model, owner):
            if owner == 'settings_load': header.append(bytes(model.cpu.mem_read(0xB8000, 160)))
            if owner == 'post_debug_summary':
                assert model.text(2, 24, 12).strip() == ('486DX2' if signature == 0x0430 else 'Pentium P24T')
                assert model.text(3, 24, 8).strip() == ('Enabled' if options.get('l1', True) else 'Disabled')
                assert model.text(14, 24, 12).strip() == ('Not detected' if options.get('l2', True) else 'Disabled')
                total = int.from_bytes(model.cpu.mem_read(model.base+0x78, 2), 'little')+1024
                assert model.text(5, 24, 5) == str(total).ljust(5)
                assert model.text(5, 30, 10) == 'KB  Passed'
                assert model.text(6, 24, 40).rstrip() == options.get('bank_text', '0 1 2 3, Interleaved')
                assert model.text(8, 24, 20).strip() == ('Not installed' if not options.get('types', 0x42) else '1.44 MB, 3.5 in')
                assert model.text(9, 24, 20).strip() == ('Not installed' if not options.get('types', 0x42) else '1.2 MB, 5.25 in')
                for row, key, expected in ((11, 'master', models[0]), (12, 'slave', models[1])):
                    assert model.text(row, 24, 40).rstrip() == options.get(key, expected)
                    assert model.text(row, 64, 16) == ' '*16
                for row, label in ((2, 'Processor'), (3, 'L1 Cache'), (5, 'RAM Test'),
                                   (6, 'Memory Banks'), (8, 'Floppy Drive A'), (9, 'Floppy Drive B'),
                                   (11, 'Primary IDE Master'), (12, 'Primary IDE Slave'), (14, 'L2'),
                                   (15, 'VGA BIOS'), (16, 'System BIOS'), (17, 'Option ROMs')):
                    assert model.text(row, 0, 3) == ' '*3 and model.text(row, 3, len(label)) == label
                    assert model.cpu.mem_read(0xB8000+(row*80+3)*2+1, 1) == b'\x0b'
                for row in (1, 4, 7, 10, 13, 18, 19, 20, 21, 22, 23):
                    assert model.text(row, 0, 80) == ' '*80
                assert model.cpu.mem_read(0xB8FA0, 32) == b'Q'*32
                hint = 'Del: Setup    Esc: Skip RAM test'
                assert model.text(24, 3, len(hint)) == hint
                assert model.record() == policy and not model.cmos[0x36]
                checked.append(True)
        m.startup_observer = observe
        try:
            m.startup(reset=True, production_controls=True, through_boot=True)
        finally:
            for hook in hooks: m.cpu.hook_del(hook)
        assert checked and header == [bytes(m.cpu.mem_read(0xB8000, 160))]
        assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
        for unit, key in enumerate(('master', 'slave')):
            published = bytes(m.cpu.mem_read(m.base+unit*512+0x140, 40)).split(b'\0', 1)[0].decode('ascii').rstrip()
            expected = '' if options.get(key) in ('Disabled', 'Not detected') else models[unit]
            assert published == expected, (name, unit, published, expected)
        types = options.get('types', 0x42)
        assert m.cpu.mem_read(m.base+0x80, 2) == bytes((types >> 4, types & 15))
        print(f'POST configuration {name}: independent readback/publication, exact grid/header -> BOOT PASS', flush=True)


def watch_renderer_writes(m, hooks):
    # Observe real calls and returns. Same-value writes must fail as well.
    for owner in ('post_ui_begin', 'post_ui_cache', 'post_ui_banks', 'post_ui_floppy',
                  'post_ui_disks', 'post_ui_disk', 'post_ui_roms', 'post_ui_rom', 'post_rom_state'):
        def entered(cpu, address, size, unused, owner=owner):
            before = tuple(m.reg_writes), tuple(m.writes), bytes(m.cmos)
            sp, ss = cpu.reg_read(x.UC_X86_REG_SP), cpu.reg_read(x.UC_X86_REG_SS)
            target = 0xF0000+int.from_bytes(cpu.mem_read(ss*16+sp, 2), 'little')
            consumed = []
            def returned(cpu, address, size, unused):
                if consumed: return
                consumed.append(True)
                assert (tuple(m.reg_writes), tuple(m.writes), bytes(m.cmos)) == before, owner
            hooks.append(cpu.hook_add(UC_HOOK_CODE, returned, None, target, target))
        point = 0xF0000+rtc.symbol(owner)
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE, entered, None, point, point))


def watch_discard_redraw(m, hooks):
    pending, redraws = [], []
    def setup_entry(cpu, address, size, unused):
        flags, phase = bytes(cpu.mem_read(m.base+0x50, 2))
        expected = (phase, flags, bytes(cpu.mem_read(0xB8000, 160)),
                    {row: m.text(row, 0, 80) for row in (2, 3, 6, 8, 9, 11, 12)})
        sp, ss = cpu.reg_read(x.UC_X86_REG_SP), cpu.reg_read(x.UC_X86_REG_SS)
        target = 0xF0000+int.from_bytes(cpu.mem_read(ss*16+sp, 2), 'little')
        consumed = []
        def discarded(cpu, address, size, unused):
            if consumed: return
            consumed.append(True)
            assert cpu.reg_read(x.UC_X86_REG_SP) == sp+2
            pending.append(expected)
        hooks.append(cpu.hook_add(UC_HOOK_CODE, discarded, None, target, target))
    def redraw(cpu, address, size, unused):
        if not pending: return
        expected = pending.pop(0)
        sp, ss = cpu.reg_read(x.UC_X86_REG_SP), cpu.reg_read(x.UC_X86_REG_SS)
        target = 0xF0000+int.from_bytes(cpu.mem_read(ss*16+sp, 2), 'little')
        consumed = []
        def returned(cpu, address, size, unused):
            if consumed: return
            consumed.append(True)
            phase, flags, header, rows = expected
            assert bytes(cpu.mem_read(0xB8000, 160)) == header
            completed = [2, *([3] if phase else []), *([6] if phase >= 2 else []),
                         *([8, 9] if phase >= 3 else []), *([11, 12] if phase >= 4 else [])]
            for row in completed: assert m.text(row, 0, 80) == rows[row], (phase, row)
            future = [*([6] if phase < 2 else []), *([8, 9] if phase < 3 else []),
                      *([11, 12] if phase < 4 else []), 14, 15, 16, 17, 18, 19, 20, 21]
            for row in future: assert m.text(row, 0, 80) == ' '*80, (phase, row, m.text(row, 0, 80))
            if flags:
                total = int.from_bytes(cpu.mem_read(m.base+0x78, 2), 'little')+1024
                assert m.text(5, 24, 5) == str(total).ljust(5)
                assert m.text(5, 30, 2) == 'KB'
                assert m.text(5, 34, 7).rstrip() == ('Skipped' if flags & 2 else 'Passed' if flags & 4 else '')
            else: assert m.text(5, 0, 80) == ' '*80
            assert m.text(22, 0, 80) == ' '*80 and m.text(24, 3, 32) == 'Del: Setup    Esc: Skip RAM test'
            redraws.append(phase)
        hooks.append(cpu.hook_add(UC_HOOK_CODE, returned, None, target, target))
    for owner, callback in (('setup_main', setup_entry), ('post_ui_begin', redraw)):
        point = 0xF0000+rtc.symbol(owner)
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE, callback, None, point, point))
    return redraws


def inputs(actions=('ordinary', 'escape', 'escape-before', 'escape-after', 'escape-release', 'pause-escape', 'delete-ram', 'delete-early', 'delete-save')):
    # Complete startup paths; hooks inject external keyboard events only.
    ordinary_writes = None
    for action in actions:
        m = setup.production_post_model(peripherals=True)
        setup.schema2_fixture(m, types=0, flags=0x0A if action in ('delete-early', 'delete-save') else 0x0B, order=(2, 0, 0))
        m.cpu.mem_write(0x20000, b'KEEP')
        events, entry = [], []
        keyboard = 0xF0000 + rtc.symbol('.keyboard')
        hooks = []
        redraws = watch_discard_redraw(m, hooks)
        warm, services, bulk_later, hops = [], [], [], []
        for owner, point in (('reset', 0xF0000+rtc.symbol('warm_reset')), ('entry', m.warm_entry)):
            hooks.append(m.cpu.hook_add(UC_HOOK_CODE,
                         lambda cpu, address, size, unused, owner=owner: warm.append(owner), None, point, point))
        contexts, restored, comparisons = [], [], {'early': False, 'final': False}
        safety_stage = [None]
        def context():
            return (tuple(m.cpu.reg_read(getattr(x, 'UC_X86_REG_'+reg))
                          for reg in ('SP', 'DS', 'ES', 'FS', 'SS', 'CR0', 'GDTR')),
                    m.a20, m.speaker,
                    bytes(m.cpu.mem_read(m.cpu.reg_read(x.UC_X86_REG_SP)+2, 16)))
        def checkpoint(cpu, address, size, unused):
            if contexts and not restored:
                assert context() == contexts[-1], (action, context(), contexts[-1])
                restored.append(True)
        point = 0xF0000+rtc.symbol('post_early_setup')
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE, checkpoint, None, point, point))
        point = 0xF0000+rtc.symbol('chipset_runtime_ram_check')
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE,
                     lambda *args: safety_stage.__setitem__(0, 'final'), None, point, point))
        def compared(cpu, access, address, size, value, unused):
            if safety_stage[0] == 'early' and address == 0x9FFFC:
                comparisons['early'] = True
            if safety_stage[0] == 'final' and address == 0x10000:
                ip = cpu.reg_read(x.UC_X86_REG_IP)
                if bytes(cpu.mem_read(0xF0000+ip, 4)) == b'\x67\x66\x8b\x07':
                    pattern = int.from_bytes(cpu.mem_read(address, 4), 'little')
                    if pattern in (0x55AA55AA, 0xAA55AA55): comparisons['final'] = True
            if safety_stage[0] == 'bulk' and address in (0x10400, 0x10800):
                bulk_later.append(address)
        for point in (0x9FFFC, 0x10000, 0x10400, 0x10800):
            hooks.append(m.cpu.hook_add(UC_HOOK_MEM_READ, compared, None, point, point+3))
        def yield_event(cpu, address, size, unused):
            services.append(cpu.reg_read(x.UC_X86_REG_EDI))
            if events or action in ('delete-early', 'delete-save', 'escape-before', 'escape-after'): return
            events.append('key')
            scans = {'escape': [1], 'escape-release': [0x81],
                     'pause-escape': [0xE1, 0x1D, 0x45, 0xE1, 0x9D, 0xC5, 0x81, 0xFA, 1],
                     'delete-ram': [0xE0, 0x53]}
            m.pending.extend(scans.get(action, [0x1E]))
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE, yield_event, None, keyboard, keyboard))
        def observe(model, name):
            hops.append(name)
            if name == 'chipset_ram_test': safety_stage[0] = 'early'
            if name == 'chipset_visible_ram_test':
                safety_stage[0] = 'bulk'
                contexts.append(context())
                model.cpu.mem_write(0x20000, b'KEEP')
            if name == 'chipset_apply' and action in ('delete-early', 'delete-save') and not events:
                events.append('key'); model.pending.append(0x53)
            if not events and ((name == 'chipset_apply' and action == 'escape-before') or
                               (name == 'post_clock_alert' and action == 'escape-after')):
                events.append('key'); model.pending.append(1)
            if name == 'setup_main':
                assert model.text(22, 3, 17) == 'Entering setup...'
                assert not model.cpu.reg_read(x.UC_X86_REG_CR0) & 1
                assert model.chipset[0x19] == 0
                assert not model.boot_reads
                assert not set(hops[hops.index('chipset_apply')+1:-1]) & {'init_peripherals', 'init_floppy', 'ata_detect_primary', 'chipset_late_cache', 'option_rom_discovery'}
                entry.append((model.cpu.reg_read(x.UC_X86_REG_SP), bytes(model.cpu.mem_read(model.base+0x50, 3)), bytes(model.cpu.mem_read(0x417, 2))))
                model.script = [0x44, 28] if action == 'delete-save' else [1, 28]
            if name == 'post_debug_summary':
                if action == 'escape' or action == 'delete-ram':
                    assert model.text(5, 34, 7) == 'Skipped'
                    assert model.cpu.mem_read(model.base+0x50, 1) == b'\x02'
                else:
                    assert model.text(5, 34, 6) == 'Passed', (action, model.text(5, 34, 19), model.cpu.mem_read(model.base+0x50, 3), entry)
        m.startup_observer = observe
        try:
            m.startup(reset=True, production_controls=True, through_boot=True)
        finally:
            for hook in hooks: m.cpu.hook_del(hook)
        assert len(entry) == int(action.startswith('delete'))
        assert m.cpu.mem_read(0x20000, 4) == b'KEEP'
        assert m.cmos[0x36] == 0 and not getattr(m, 'restarts', 0)
        assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
        assert restored and all(comparisons.values()), (action, restored, comparisons)
        if action == 'escape':
            assert services == [0x10400] and not bulk_later, (action, services, bulk_later)
        elif action == 'delete-ram':
            # E0 and53 are separate external scans. The second service accepts
            # navigation Delete and must exit before testing its next dword.
            assert services == [0x10400, 0x10800] and 0x10400 in bulk_later and 0x10800 not in bulk_later, (services, bulk_later)
        else: assert bulk_later and len(services) > 1, (action, services)
        if action == 'delete-save':
            assert warm == ['reset', 'entry'] and not redraws, (warm, redraws)
            for owner in ('init_memory', 'settings_load', 'chipset_apply', 'chipset_ram_test'):
                assert hops.count(owner) == 2, (owner, hops)
            assert hops.count('chipset_visible_ram_test') == 1  # Save entered before this owner.
        else:
            assert not warm and len(redraws) == int(action.startswith('delete')), (action, warm, redraws)
        if action == 'ordinary': ordinary_writes = tuple(m.writes)
        if action.startswith('escape') or action == 'pause-escape':
            assert tuple(m.writes) == ordinary_writes, (action, m.writes, ordinary_writes)
        print('POST input '+action+': restored RAM context / actual Setup or skip / signed BOOT PASS', flush=True)
    notice_inputs()
    skip_final_validation()


def notice_inputs(phases=('clock', 'settings', 'floppy', 'floppy-detection', 'ide-detection')):
    # Drive external scans at real notice waits and detection entries. Continue
    # through the checkpoint, actual Setup discard, remaining POST, and BOOT.
    for phase in phases:
        for event in ('ordinary', 'delete'):
            m = setup.production_post_model(peripherals=True)
            setup.schema2_fixture(m, types=0x40 if phase == 'floppy' else 0,
                                  flags=0x03, order=(2, 0, 0))  # Halt on all errors.
            if phase == 'clock': m.cmos[8] = 0
            if phase == 'settings': m.cmos[0x38] ^= 0xFF
            if phase == 'floppy': m.fdc_timeout = 0
            hops, delivered, entries = [], [], []
            hooks = []
            redraws = watch_discard_redraw(m, hooks)
            notices = [0, 0]
            def observe(model, name):
                hops.append(name)
                if name == 'post_notice_wait': notices[0] += 1
                target = {'floppy-detection': 'init_floppy',
                          'ide-detection': 'ata_detect_primary'}.get(phase)
                if name == target and not delivered:
                    model.pending.extend([0xE0, 0x53] if event == 'delete' else [28])
                    delivered.append(len(hops)-1)
                if name == 'setup_main':
                    assert event == 'delete' and delivered
                    assert model.text(22, 3, 17) == 'Entering setup...'
                    assert model.text(22, 0, 80) == ' '*3+'Entering setup...'+' '*60
                    assert model.chipset[0x19] == 0 and not model.boot_reads
                    assert not model.cpu.reg_read(x.UC_X86_REG_CR0) & 1
                    # No optional owner may interpose after a notice accepts Del.
                    between = hops[delivered[0]+1:-1]
                    assert not set(between) & {'init_peripherals', 'init_floppy',
                                               'ata_detect_primary', 'chipset_late_cache',
                                               'option_rom_discovery'}, (phase, between)
                    entries.append(model.cpu.mem_read(model.base+0x51, 1)[0])
                    model.script = [1, 28]
            def deliver(model, address):
                if model.cpu.mem_read(address, 1) != b'\xf4': return
                if not hops or hops[-1] != 'post_notice_wait': return
                if notices[0] == notices[1]: return
                notices[1] = notices[0]
                if not delivered:
                    model.pending.extend([0xE0, 0x53] if event == 'delete' else [28])
                    delivered.append(len(hops)-1)
                else:
                    model.pending.append(28)  # Any later unrelated notice.
            m.startup_observer, m.event_observer = observe, deliver
            try:
                m.startup(reset=True, production_controls=True, through_boot=True)
            finally:
                for hook in hooks: m.cpu.hook_del(hook)
            assert delivered and len(entries) == int(event == 'delete'), (phase, event, hops)
            if entries:
                assert entries == [4 if phase == 'ide-detection' else
                                   3 if phase.startswith('floppy') else 2], (phase, entries)
            assert redraws == entries, (phase, event, redraws, entries)
            assert m.cpu.mem_read(0x7C00, 4) == b'BOOT' and m.cmos[0x36] == 0
            assert hops[-6:] == ['chipset_late_cache', 'init_external_cache',
                                 'option_rom_discovery', 'post_debug_summary', 'int19', 'boot_sector']
            print(f'POST checkpoint {phase}/{event}: actual notice/detection, early Setup and BOOT PASS', flush=True)


def rom_states():
    m = setup.Setup()
    boot_cases = []
    entry = 0xF0000 + rtc.symbol('post_rom_state')
    sample = [0xC800, 0x400]
    def inputs(cpu, address, size, unused):
        cpu.reg_write(x.UC_X86_REG_DX, sample[0])
        cpu.reg_write(x.UC_X86_REG_BX, sample[1])
    hook = m.cpu.hook_add(UC_HOOK_CODE, inputs, None, entry, entry)
    def state(expected, regs=None, cr0=0x10, extent=(0xC800, 0x400)):
        if extent[0] == 0xC800 and (regs or {}).get(0x19, 3) not in (1, 2, 4, 5, 6):
            boot_cases.append((expected, regs or {}, cr0, extent))
        m.chipset.update({i: 0 for i in range(0x0D, 0x24)})
        m.chipset.update({7: 8, **(regs or {})})
        m.cpu.reg_write(x.UC_X86_REG_CR0, cr0)
        sample[:] = extent
        before = dict(m.chipset), bytes(m.cmos)
        m.call('post_rom_state')
        assert m.cpu.reg_read(x.UC_X86_REG_AX) == expected, (expected, m.cpu.reg_read(x.UC_X86_REG_AX), regs)
        assert (dict(m.chipset), bytes(m.cmos)) == before
    state(0x0202)                              # Cache only.
    state(0, {7: 0})                           # Neither.
    state(0x0101, {7: 0, 0x0F: 0x20})        # Shadow only.
    state(0x0303, {0x0F: 0x20})               # Both.
    state(0x0303, {0x0F: 0x20, 0x15: 0x20}) # Write protection is independent of NC.
    state(0x0202, {0x0F: 0x10})               # Fill-only is not shadow.
    state(0x0203, {0x0F: 0x20}, extent=(0xC800, 0x800))
    state(2, {0x15: 0x40}, extent=(0xC800, 0x800))  # Last16KiB NC.
    state(0, {7: 0})
    state(0, cr0=0x40000010)
    state(0, {0x15: 0x10})                    # Active L1, regional NC.
    state(0x0202, {7: 0, 0x19: 3, 0x15: 0x10}) # L2 ignores segments.
    state(0, {7: 0x80, 0x19: 3, 0x15: 0x10})
    state(0x0202, {7: 0x80, 0x19: 3})
    state(0, {7: 0, 0x19: 7})                 # Direct mode not active cache.
    for size in range(1, 7):
        state(0x0202, {7: 0, 0x19: size})
    # PMRA32 is C8000: eight independently selected2KiB subregions.
    state(0, {0x20: 0x72, 0x21: 0xFF})
    state(2, {0x20: 0x72, 0x21: 0x81})       # Disabled interior retains cache.
    state(0x0202, {0x15: 0x10, 0x20: 0x32, 0x21: 0xFF})
    state(0x0202, {0x0F: 0x20, 0x20: 0x32, 0x21: 0xFF}) # PMR bus overrides shadow.
    conflict = {0x20: 0x32, 0x21: 0xFF, 0x22: 0x72, 0x23: 0xFF}
    state(4, conflict)
    state(0, {**conflict, 7: 0})
    state(0, conflict, cr0=0x40000010)
    state(0x0202, {**conflict, 0x19: 3})
    state(0x0303, {0x0F: 0x0A}, extent=(0xC000, 0x800))
    state(0x0203, {0x0F: 2}, extent=(0xC000, 0x800))
    state(0x0303, {0x12: 0xAA}, extent=(0xF000, 0x1000))
    state(0x0203, {0x12: 0x2A}, extent=(0xF000, 0x1000))
    m.cpu.hook_del(hook)
    # Render both fixed extents through their real register-reader/text path.
    for regs, vga, system in (
            ({7: 0}, 'Not shadowed, Not cached', 'Not shadowed, Not cached'),
            ({7: 8, 0x0F: 0x0A, 0x12: 0xAA}, 'Shadowed, Cached', 'Shadowed, Cached'),
            ({7: 8, 0x0F: 2, 0x15: 4, 0x12: 0x2A, 0x18: 0x40},
             'Partly shadowed, Partly cached', 'Partly shadowed, Partly cached'),
            ({7: 0, 0x0F: 0x0A, 0x12: 0xAA}, 'Shadowed, Not cached', 'Shadowed, Not cached')):
        m.chipset.update({i: 0 for i in range(0x0D, 0x24)})
        m.chipset.update(regs)
        m.cpu.reg_write(x.UC_X86_REG_CR0, 0x10)
        before = dict(m.chipset), bytes(m.cmos)
        m.call('post_ui_begin')
        m.call('post_ui_roms')
        assert m.text(15, 3, 8) == 'VGA BIOS'
        assert m.text(16, 3, 11) == 'System BIOS'
        assert m.text(15, 24, 40).rstrip() == vga
        assert m.text(16, 24, 40).rstrip() == system
        assert (dict(m.chipset), bytes(m.cmos)) == before
    print('POST ROM states: whole extents, actual cache gates, sparse PMR and ambiguous overlap, read-only PASS', flush=True)
    rom_policy_flow(boot_cases)


def rom_policy_flow(card_cases):
    fixed_cases = (
        ({}, 'Shadowed, Cached', 'Shadowed, Cached'),
        ({0x0F: 0}, 'Not shadowed, Cached', 'Shadowed, Cached'),
        ({0x0F: 2}, 'Partly shadowed, Cached', 'Shadowed, Cached'),
        ({0x15: 5}, 'Shadowed, Not cached', 'Shadowed, Cached'),
        ({0x15: 4}, 'Shadowed, Partly cached', 'Shadowed, Cached'),
        ({0x12: 0}, 'Shadowed, Cached', 'Not shadowed, Cached'),
        ({0x12: 0x2A}, 'Shadowed, Cached', 'Partly shadowed, Cached'),
        ({0x18: 0x55}, 'Shadowed, Cached', 'Shadowed, Not cached'),
        ({0x18: 0x40}, 'Shadowed, Cached', 'Shadowed, Partly cached'),
    )
    # Each case follows the actual late owner and scanner to BOOT. Fixtures
    # select hardware readback only; no firmware reader or renderer is replaced.
    cases = [('card', item) for item in card_cases] + [('fixed', item) for item in fixed_cases]
    for index, (kind, case) in enumerate(cases):
        m = setup.production_post_model()
        setup.schema2_fixture(m, types=0, flags=0x0B, order=(2, 0, 0))
        if kind == 'card':
            expected, regs, cr0, extent = case
            m.cpu.mem_write(0xC8000, bytes(legacy.rom(0, extent[1]//32)))
            shadow = ('Shadowed' if expected & 0x100 else
                      'Partly shadowed' if expected & 1 else 'Not shadowed')
            cache = ('Cache status unknown' if expected & 4 else
                     'Cached' if expected & 0x200 else 'Partly cached' if expected & 2 else 'Not cached')
            card_text = shadow+', '+cache
            readback = {i: 0 for i in range(0x0D, 0x24)}
            readback.update({7: 8, **regs})
        else:
            regs, vga, system = case
            cr0 = 0x10
            readback = {i: 0 for i in range(0x0D, 0x24)}
            readback.update({7: 8, 0x0F: 0x0A, 0x12: 0xAA, **regs})
        hooks, emitted, checked, returns = [], [], [], []
        def snapshot():
            return dict(m.chipset), bytes(m.cmos), tuple(m.writes), tuple(m.reg_writes)
        def reader(cpu, address, size, unused):
            if address == 0xF0000+rtc.symbol('post_ui_cache'):
                if cpu.mem_read(m.base+0x51, 1)[0] != 5: return
                m.chipset.update(readback)
                cpu.reg_write(x.UC_X86_REG_CR0, cr0)
            before = snapshot()
            sp, ss = cpu.reg_read(x.UC_X86_REG_SP), cpu.reg_read(x.UC_X86_REG_SS)
            target = 0xF0000+int.from_bytes(cpu.mem_read(ss*16+sp, 2), 'little')
            consumed = []
            def returned(cpu, address, size, unused):
                if consumed: return
                consumed.append(True)
                assert snapshot() == before, (kind, index, 'reader changed policy/CMOS')
                returns.append(True)
            hooks.append(cpu.hook_add(UC_HOOK_CODE, returned, None, target, target))
        for owner in ('post_ui_cache', 'post_ui_roms', 'post_ui_rom'):
            point = 0xF0000+rtc.symbol(owner)
            hooks.append(m.cpu.hook_add(UC_HOOK_CODE, reader, None, point, point))
        def initialized(cpu, address, size, unused):
            assert m.text(18, 3, 5) == 'C800h'
            assert m.text(18, 16, 50).rstrip() == card_text, (index, m.text(18, 16, 50), card_text)
            emitted.append(True)
        if kind == 'card':
            hooks.append(m.cpu.hook_add(UC_HOOK_CODE, initialized, None, 0xC8003, 0xC8003))
        def observe(model, owner):
            if owner == 'chipset_late_cache':
                assert model.text(15, 0, 80) == model.text(16, 0, 80) == ' '*80
            if owner == 'post_debug_summary':
                if kind == 'fixed':
                    assert model.text(15, 24, 50).rstrip() == vga, (index, model.text(15, 24, 50), vga)
                    assert model.text(16, 24, 50).rstrip() == system, (index, model.text(16, 24, 50), system)
                else:
                    assert emitted == [True] and model.cpu.mem_read(model.base+0x52, 1) == b'\x01'
                assert returns
                checked.append(True)
        m.startup_observer = observe
        try:
            m.startup(reset=True, production_controls=True, through_boot=True)
        finally:
            for hook in hooks: m.cpu.hook_del(hook)
        assert checked and m.cpu.mem_read(0x7C00, 4) == b'BOOT'
        print(f'POST ROM policy {kind}/{index}: whole-range independent readback, read-only renderer -> BOOT PASS', flush=True)


def roms():
    for addresses in ((), (0xC800,), tuple(range(0xC800, 0xE000, 0x80))):
        m = setup.production_post_model()
        setup.schema2_fixture(m, types=0, flags=0x0B, order=(2, 0, 0))
        for index, segment in enumerate(addresses):
            m.cpu.mem_write(segment*16, bytes(legacy.rom(index)))
        emitted = []
        # Observe actual selected card entry, after its renderer has emitted.
        entries = {segment*16+3 for segment in addresses}
        def emitted_record(cpu, address, size, unused):
            if address not in entries: return
            count = cpu.mem_read(m.base+0x52, 1)[0]
            if count > len(emitted):
                row = 18 + min(count-1, 3)
                emitted.append((m.text(row, 3, 5), m.text(row, 16, 40).rstrip()))
        hook = m.cpu.hook_add(UC_HOOK_CODE, emitted_record, None, 0xC8000, 0xDFFFF)
        def observe(model, name):
            if name == 'option_rom_discovery':
                model.chipset.update({7: 8, 0x19: 0, 0x0F: 0, 0x10: 0, 0x15: 0, 0x16: 0x40})
                model.cpu.reg_write(x.UC_X86_REG_CR0, 0x10)
            if name != 'post_debug_summary': return
            assert model.cpu.mem_read(model.base+0x52, 1)[0] == len(addresses)
            assert tuple(item[0] for item in emitted) == tuple(f'{segment:04X}h' for segment in addresses)
            for segment, record in zip(addresses, emitted):
                assert record[1] == ('Not shadowed, Not cached' if segment >= 0xDC00 else 'Not shadowed, Cached'), (segment, record)
            for index, segment in enumerate(addresses[-4:]):
                assert model.text(18+index, 3, 5) == f'{segment:04X}h'
            assert model.text(17, 24, 2).strip() == str(len(addresses)) if addresses else model.text(17, 24, 12) == 'Not detected'
            assert model.text(22, 0, 80) == ' '*80
            assert model.text(24, 3, 10) == 'Del: Setup'
            assert model.text(15, 3, 8) == 'VGA BIOS'
            assert model.text(16, 3, 11) == 'System BIOS'
        m.startup_observer = observe
        m.startup(reset=True, production_controls=True, through_boot=True)
        m.cpu.hook_del(hook)
        assert tuple(struct.unpack('<'+str(len(addresses))+'H', m.cpu.mem_read(0x600, len(addresses)*2))) == (1,)*len(addresses)
        assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
    print('POST ROMs: zero/one/48 add-in records progressively emitted, scrolling, callbacks -> BOOT PASS', flush=True)


def rom_exclusions():
    for kind in ('valid', 'signature', 'zero', 'checksum', 'extent', 'covered'):
        m = setup.production_post_model()
        setup.schema2_fixture(m, types=0, flags=0x0B, order=(2, 0, 0))
        first = legacy.rom(0, 64 if kind == 'covered' else 4)
        if kind == 'signature': first[0] = 0
        if kind == 'zero': first[2] = 0
        if kind == 'checksum': first[-1] ^= 1
        if kind == 'extent': first[2] = 193
        if kind == 'covered':
            first[2048:4096] = legacy.rom(2)
            first[-1] = 0
            first[-1] = -sum(first) & 255
        m.cpu.mem_write(0xC8000, bytes(first))
        m.cpu.mem_write(0xD8000, bytes(legacy.rom(1)))
        emitted, hooks = [], []
        def entry(cpu, address, size, unused):
            if address not in (0xC8003, 0xC8803, 0xD8003): return
            count = cpu.mem_read(m.base+0x52, 1)[0]
            row = 18+count-1
            emitted.append((m.text(row, 3, 5), m.text(row, 16, 50).rstrip()))
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE, entry, None, 0xC8000, 0xDFFFF))
        def observe(model, owner):
            if owner == 'option_rom_discovery':
                model.chipset.update({7: 8, 0x19: 0, 0x0F: 0x20, 0x10: 0,
                                      0x15: 0x40, 0x16: 0})
                model.cpu.reg_write(x.UC_X86_REG_CR0, 0x10)
            if owner == 'post_debug_summary':
                expected = ([('C800h', 'Partly shadowed, Partly cached' if kind == 'covered' else 'Shadowed, Cached')]
                            if kind in ('valid', 'covered') else [])
                expected.append(('D800h', 'Not shadowed, Cached'))
                assert emitted == expected, (kind, emitted, expected)
                assert model.cpu.mem_read(model.base+0x52, 1) == bytes((len(expected),))
                assert model.text(24, 3, 10) == 'Del: Setup'
        m.startup_observer = observe
        try:
            m.startup(reset=True, production_controls=True, through_boot=True)
        finally:
            for hook in hooks: m.cpu.hook_del(hook)
        assert m.cpu.mem_read(0x600, 6) == struct.pack('<3H', int(kind in ('valid', 'covered')), 1, 0)
        assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
        print(f'POST ROM exclusion {kind}: selected extent/state, excluded records, later callback -> BOOT PASS', flush=True)


def recovery_flow():
    chipset = importlib.import_module('test-chipset')
    for stage in (None, 'early', 'visible', 'final', 'persistent'):
        m = setup.production_post_model()
        setup.schema2_fixture(m, types=0, flags=0x0A, order=(2, 0, 0))
        setup.nondefault_extensions(m)
        hits, hooks = chipset.ram_faults(m, [] if stage is None else
                                        ['visible', 'visible'] if stage == 'persistent' else [stage])
        warnings = []
        def warning(cpu, address, size, unused):
            text = bytes(cpu.mem_read(0xF0000+cpu.reg_read(x.UC_X86_REG_SI), 96)).split(b'\0', 1)[0]
            if b'RAM test' not in text: return
            col, row = bytes(cpu.mem_read(0x450, 2))
            lines = []
            for part in text.split(b'\r\n'):
                if part:
                    assert row in (22, 23), (stage, part, col, row)
                    lines.append((row, col, part.decode('ascii')))
                col, row = 0, row+1
            hardware = bytes(cpu.mem_read(0xB8000, 22*160))
            hint = bytes(cpu.mem_read(0xB8000+24*160, 160))
            sp, ss = cpu.reg_read(x.UC_X86_REG_SP), cpu.reg_read(x.UC_X86_REG_SS)
            target = 0xF0000+int.from_bytes(cpu.mem_read(ss*16+sp, 2), 'little')
            consumed = []
            def printed(cpu, address, size, unused):
                if consumed: return
                consumed.append(True)
                for line_row, line_col, line in lines:
                    assert m.text(line_row, line_col, len(line)) == line
                assert bytes(cpu.mem_read(0xB8000, 22*160)) == hardware
                assert bytes(cpu.mem_read(0xB8000+24*160, 160)) == hint
                warnings.append(' '.join(line.strip() for _, _, line in lines))
            hooks.append(cpu.hook_add(UC_HOOK_CODE, printed, None, target, target))
        point = 0xF0000+rtc.symbol('print_string')
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE, warning, None, point, point))
        try:
            m.startup(reset=True, production_controls=True, halt=stage == 'persistent',
                      through_boot=stage != 'persistent')
        finally:
            for hook in hooks: m.cpu.hook_del(hook)
        if stage is None:
            assert not warnings and not hits and not getattr(m, 'restarts', 0)
        else:
            assert hits and warnings and m.restarts == 1
            expected = {'early': 'POST RAM test failed; chipset defaults restored',
                        'visible': 'RAM test failed; retrying defaults',
                        'final': 'RAM test after L2 setup failed; retrying defaults',
                        'persistent': 'RAM test failed; retrying defaults'}[stage]
            assert any(expected in item for item in warnings), (stage, warnings)
        if stage == 'persistent':
            assert m.posts[-1] == 0xE7 and 'int19' not in m.startup_hops
        else:
            assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
            if stage is not None: assert m.text(13, 54, 13) == 'RAM recovered'
        print(f'POST recovery {stage}: actual warning rows/preserved hardware, retry -> terminal PASS', flush=True)


def skip_final_validation():
    chipset = importlib.import_module('test-chipset')
    for failed in (False, True):
        m = setup.production_post_model()
        setup.schema2_fixture(m, types=0, flags=0x0B, order=(2, 0, 0))
        hits, hooks = chipset.ram_faults(m, ['final'] if failed else [])
        scans, skipped = [], []
        def escape(cpu, address, size, unused):
            if not scans:
                scans.append(True)
                m.pending.append(1)
        point = 0xF0000+rtc.symbol('.keyboard')
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE, escape, None, point, point))
        def observe(model, owner):
            if owner == 'chipset_late_cache' and not skipped:
                assert model.text(5, 34, 7) == 'Skipped'
                skipped.append(True)
        m.startup_observer = observe
        try:
            m.startup(reset=True, production_controls=True, through_boot=True)
        finally:
            for hook in hooks: m.cpu.hook_del(hook)
        assert skipped and m.cpu.mem_read(0x7C00, 4) == b'BOOT'
        assert hits == ([('final', 0x10000)] if failed else [])
        assert getattr(m, 'restarts', 0) == int(failed)
        assert ('RAM test after L2 setup failed; retrying defaults' in m.console) == failed
        print(f'POST skipped RAM/final failure={failed}: real patterned decision/recovery -> BOOT PASS', flush=True)


def warning_flow(causes=('clock', 'settings', 'clock+settings', 'floppy', 'floppy-pair', 'keyboard', 'rom', 'rom-pair',
                        'keyboard+clock', 'keyboard+settings', 'recovery+clock', 'recovery+settings',
                        'keyboard+recovery', 'clock+ram', 'clock+ram-fatal', 'floppy+ram', 'floppy+ram-fatal')):
    for cause in causes:
        for error in (False, True):
            m = setup.production_post_model(peripherals=True)
            setup.schema2_fixture(m, types=0x44 if cause == 'floppy-pair' else 0x40 if cause.startswith('floppy') else 0,
                                  flags=0x0B if cause == 'clock+ram-fatal' else 0x03, order=(2, 0, 0))
            if error and (cause.startswith('clock') or cause.endswith('+clock')): m.cmos[8] = 0
            if error and (cause in ('settings', 'clock+settings') or cause.endswith('+settings')): m.cmos[0x38] ^= 0xFF
            if error and cause.startswith('floppy') and cause != 'floppy-pair': m.fdc_timeout = 0
            if error and cause == 'floppy-pair': m.track_zero = [True, True]
            if error and cause.startswith('keyboard'): m.device_present = False
            if error and 'recovery' in cause:
                m.cmos[0x36], m.cmos[0x69] = 0xDA, 0xD2  # Carried notice and actual recovery profile.
            if cause in ('rom', 'rom-pair'):
                for index, address in enumerate((0xC8000, 0xD8000) if cause == 'rom-pair' else (0xC8000,)):
                    image = legacy.rom(index)
                    if error: image[-1] ^= 1
                    m.cpu.mem_write(address, bytes(image))
            hooks, warnings, notice, waiting_screen = [], [], [0, 0], []
            late_ram = cause.endswith(('+ram', '+ram-fatal'))
            fatal = error and cause.endswith('+ram-fatal')
            if late_ram:
                chipset = importlib.import_module('test-chipset')
                hits, fault_hooks = chipset.ram_faults(m, ['final']*(2 if fatal else 1) if error else [])
                hooks.extend(fault_hooks)
            def message_entry(cpu, address, size, unused):
                hardware = bytes(cpu.mem_read(0xB8000, 22*160))
                hint = bytes(cpu.mem_read(0xB8000+24*160, 160))
                sp, ss = cpu.reg_read(x.UC_X86_REG_SP), cpu.reg_read(x.UC_X86_REG_SS)
                target = 0xF0000+int.from_bytes(cpu.mem_read(ss*16+sp, 2), 'little')
                consumed = []
                def returned(cpu, address, size, unused):
                    if consumed: return
                    consumed.append(True)
                    assert bytes(cpu.mem_read(0xB8000, 22*160)) == hardware
                    assert bytes(cpu.mem_read(0xB8000+24*160, 160)) == hint
                    assert bytes(cpu.mem_read(0xB8000+22*160, 320)) == b' \x07'*160
                    assert bytes(cpu.mem_read(0x450, 2)) == bytes((3, 22))
                hooks.append(cpu.hook_add(UC_HOOK_CODE, returned, None, target, target))
            point = 0xF0000+rtc.symbol('post_message_cursor')
            hooks.append(m.cpu.hook_add(UC_HOOK_CODE, message_entry, None, point, point))
            def print_entry(cpu, address, size, unused):
                text = bytes(cpu.mem_read(0xF0000+cpu.reg_read(x.UC_X86_REG_SI), 96)).split(b'\0', 1)[0]
                if not text.lstrip(b'\r\n').startswith((b'WARNING:', b'Floppy ', b'Expansion ROM invalid;', b'Enter/D:', b'Press any key to continue', b' POST RAM test', b' RAM test')): return
                col, row = bytes(cpu.mem_read(0x450, 2))
                lines = []
                for part in text.split(b'\r\n'):
                    if part:
                        assert row in (22, 23), (cause, error, part, col, row)
                        lines.append((row, col, part.decode('ascii')))
                    col, row = 0, row+1
                hardware = bytes(cpu.mem_read(0xB8000, 22*160))
                hint = bytes(cpu.mem_read(0xB8000+24*160, 160))
                sp, ss = cpu.reg_read(x.UC_X86_REG_SP), cpu.reg_read(x.UC_X86_REG_SS)
                target = 0xF0000+int.from_bytes(cpu.mem_read(ss*16+sp, 2), 'little')
                consumed = []
                def returned(cpu, address, size, unused):
                    if consumed: return
                    consumed.append(True)
                    for line_row, line_col, line in lines:
                        assert m.text(line_row, line_col, len(line)) == line
                        assert m.text(line_row, line_col, 80-line_col) == line.ljust(80-line_col), (cause, line_row, m.text(line_row, 0, 80))
                    assert bytes(cpu.mem_read(0xB8000, 22*160)) == hardware
                    assert bytes(cpu.mem_read(0xB8000+24*160, 160)) == hint
                    warnings.append(text.decode('ascii'))
                    waiting_screen[:] = [bytes(cpu.mem_read(0xB8000, 4000))]
                hooks.append(cpu.hook_add(UC_HOOK_CODE, returned, None, target, target))
            point = 0xF0000+rtc.symbol('print_string')
            hooks.append(m.cpu.hook_add(UC_HOOK_CODE, print_entry, None, point, point))
            def observe(model, owner):
                if owner == 'post_notice_wait':
                    notice[0] += 1
                    assert waiting_screen and bytes(model.cpu.mem_read(0xB8000, 4000)) == waiting_screen[0]
            def acknowledge(model, address):
                if notice[0] != notice[1] and model.cpu.mem_read(address, 1) == b'\xf4':
                    assert bytes(model.cpu.mem_read(0xB8000, 4000)) == waiting_screen[0]
                    notice[1] = notice[0]
                    model.pending.append(28)
            m.startup_observer, m.event_observer = observe, acknowledge
            try:
                m.startup(reset=True, production_controls=True, halt=fatal, through_boot=not fatal)
            finally:
                for hook in hooks: m.cpu.hook_del(hook)
            expected = {'clock': 'CMOS date/time not set', 'settings': 'CMOS settings invalid', 'clock+settings': 'CMOS settings invalid',
                        'floppy': 'Floppy A seek error', 'floppy-pair': 'Floppy A seek error',
                        'keyboard': 'Keyboard not detected', 'rom': 'ROM', 'rom-pair': 'ROM',
                        'keyboard+clock': 'Keyboard not detected', 'keyboard+settings': 'Keyboard not detected',
                        'recovery+clock': 'POST RAM test failed', 'recovery+settings': 'POST RAM test failed',
                        'keyboard+recovery': 'POST RAM test failed',
                        'clock+ram': 'RAM test after L2 setup failed', 'clock+ram-fatal': 'RAM test after L2 setup failed',
                        'floppy+ram': 'RAM test after L2 setup failed', 'floppy+ram-fatal': 'RAM test after L2 setup failed'}[cause]
            assert any(expected in line for line in warnings) == error, (cause, error, warnings)
            if cause.endswith(('+clock', '+settings')) and cause.startswith(('keyboard', 'recovery')) and error:
                later = 'CMOS date/time not set' if cause.endswith('+clock') else 'CMOS settings invalid'
                assert any(later in line for line in warnings), (cause, warnings)
                if cause.endswith('+clock'): assert m.cmos[8] == 1  # Date-domain BL survives cursor reset/defaults.
            if cause == 'keyboard+recovery' and error:
                assert any('Keyboard not detected' in line for line in warnings)
            if late_ram:
                assert len(hits) == (2 if fatal else int(error))
                assert getattr(m, 'restarts', 0) == int(error)
                preceding = 'CMOS date/time not set' if cause.startswith('clock') else 'Floppy A seek error'
                assert any(preceding in line for line in warnings) == error
            if cause == 'clock+settings' and error:
                assert any('CMOS settings invalid; date/time not set' in line for line in warnings)
            if cause == 'floppy-pair' and error:
                assert sum('seek error' in line for line in warnings) == 2
                assert any('Floppy B seek error' in line for line in warnings)
            if cause == 'rom-pair' and error:
                assert sum('Expansion ROM invalid' in line for line in warnings) == 2
            if not error: assert not warnings and not notice[0], (cause, warnings, notice)
            if fatal:
                assert m.posts[-1] == 0xE7 and 'int19' not in m.startup_hops
                print(f'POST warning {cause}/error=True: actual message rows, hardware/hint preserved -> E7 PASS', flush=True)
                continue
            assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
            token = {'clock': 'Clock', 'settings': 'CMOS', 'clock+settings': 'Clock', 'floppy': 'Floppy', 'floppy-pair': 'Floppy',
                     'keyboard': 'Keyboard', 'rom': 'ROM', 'rom-pair': 'ROM',
                     'keyboard+clock': 'Keyboard', 'keyboard+settings': 'Keyboard',
                     'recovery+clock': 'RAM recovered', 'recovery+settings': 'RAM recovered',
                     'keyboard+recovery': 'RAM recovered',
                     'clock+ram': 'RAM recovered', 'clock+ram-fatal': 'RAM recovered',
                     'floppy+ram': 'RAM recovered', 'floppy+ram-fatal': 'RAM recovered'}[cause]
            # Explicit defaults acceptance repairs the invalid base record and
            # clears its warning. Other unresolved causes reach the summary.
            if cause not in ('settings', 'clock+settings'):
                assert (token in m.text(13, 3, 77)) == error, (cause, error, m.text(13, 3, 77))
            print(f'POST warning {cause}/error={error}: actual message rows, hardware/hint preserved -> BOOT PASS', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case', action='append', choices=('display', 'flow', 'configuration', 'input', 'roms', 'rom-states', 'rom-exclusions', 'recovery', 'warnings'))
    args = parser.parse_args()
    checks = {'display': display, 'flow': flow, 'configuration': configuration_flow, 'input': inputs,
              'roms': roms, 'rom-states': rom_states, 'rom-exclusions': rom_exclusions, 'recovery': recovery_flow, 'warnings': warning_flow}
    for case in args.case or checks: checks[case]()
