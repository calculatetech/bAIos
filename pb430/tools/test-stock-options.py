"""Exercise stock options through real Setup/reset owners and independent devices."""
import importlib
import json
import struct
import sys
from pathlib import Path
from unicorn import x86_const as x, UC_HOOK_CODE

timing = importlib.import_module('test-timing-setup')
cache = importlib.import_module('test-cache-transitions')
from core_proof import ACC
from scenarios import ports_record
from shared.tools.peripheral_proof import UART

PORT = Path(__file__).resolve().parents[1]
IMAGE = Path(sys.argv[1]) if len(sys.argv) > 1 else PORT / 'build/baios-pb430.bin'
SELECTORS = (0x17, 0x10, 0x15, 0x11, 0x12, 0x17, 0x13, 0x14)
PAIRS = ((0x338, 0x238), (0x3E8, 0x2E8), (0x2E8, 0x3E8), (0x220, 0x228))
SAVE = [0x44, 28]
DISCARD_CHIP = [1, 1, 1, 28]
ISA_MENU = [0x50]*4 + [28] + [0x50]*4 + [28]
PAIR_MENU = [0x50]*3 + [28, 0x50, 0x50]


def machine(selector=0, pair=1, flags=0, refresh=None):
    chip = bytearray(timing.DEFAULT)
    chip[6] = 1
    if refresh is not None:
        chip[7], chip[14] = refresh, 2
    chip[22] = selector << 4 | flags
    m = timing.model(IMAGE, chip)
    ports_record(m.cmos, (3, 4, pair, 2, 0, 1, 1, 1))
    m.call('settings_load')
    m.continue_reset = True
    m.stop_address = 0xF0000 + m.listing.symbol('.wait', 'boot_retry')
    idle = [0]
    def input_wait(cpu, address, size, unused):
        idle[0] = idle[0]+1 if not m.starting and not m.script and not m.pending else 0
        assert idle[0] < 100, ('exhausted Setup input', hex(address),
                               bytes(cpu.mem_read(0xB8000,4000))[::2].decode('cp437'))
    address = 0xF0000+m.listing.symbol('.input','setup_main')
    m.cpu.hook_add(UC_HOOK_CODE,input_wait,begin=address,end=address)
    return m


def selected(m, selector):
    assert m.cpu.mem_read(m.base+0x76, 1)[0] >> 4 == selector
    assert m.registers[6] == 0xA0 | SELECTORS[selector], (selector, hex(m.registers[6]))
    assert m.posts[-1] == 0xE4


def isa_change(selector, current=0):
    order = (7, 6, 0, 4, 3, 2, 1)
    selector = 0 if selector == 5 else selector
    current = 0 if current == 5 else current
    return [0x4D] * ((order.index(selector) - order.index(current)) % len(order))


def isa_choices():
    rows = []
    for selector in (0, 1, 2, 3, 4, 6, 7):
        print(f'CHECK ISA selector {selector}', flush=True)
        m = machine()
        visits = []
        names = ('chipset_late_cache', 'chipset_isa_policy', 'option_rom_discovery')
        points = {0xF0000+m.listing.symbol(n): n for n in names}
        def trace(mm, address):
            if mm.starting and address in points:
                visits.append(points[address])
        m.code_observer = trace
        m.open(ISA_MENU + isa_change(selector) + SAVE)
        selected(m, selector)
        assert visits == list(names), visits
        assert m.cmos[0x34] >> 4 == selector
        m.irq_scans([0x1D, 0x38, 0xE0, 0x53])
        assert m.reset_pending and m.registers[6] == 0xB7
        m.complete_reset()
        selected(m, selector)
        rows.append({'isa_selector': selector, 'save_and_warm_reset': True})
    print('PASS all ISA choices through menu, Save and warm reset', flush=True)
    return rows


def isa_labels():
    rows = []
    for jumper, default, register in ((5, '/4 (Default)', 0xB7), (4, '/3 (Default)', 0x33)):
        expected = ['/2', '/3', '/4', '/5', '/6', '/8', '/10']
        order = (7, 6, 0, 4, 3, 2, 1) if jumper == 5 else (7, 0, 5, 4, 3, 2, 1)
        expected[2 if jumper == 5 else 1] = default
        for selector in range(8):
            m = machine(selector, flags=0x0F)
            m.jumper = jumper
            m.registers[6] = register
            m.cpu.mem_write(m.base+0x260, bytes(m.cpu.mem_read(m.base+0x60, 24)))
            m.cpu.mem_write(m.base+0x278, b'\x05')
            m.cpu.mem_write(m.base+0xF7, b'\x00')
            m.call('chipset_ui_parameters')
            alias = 5 if jumper == 5 else 6
            choice = order.index(0 if selector == alias else selector)
            assert m.cpu.mem_read(m.base+0x279, 1) == bytes((choice,))
            assert m.cpu.reg_read(x.UC_X86_REG_CX) == 7
            table = m.cpu.reg_read(x.UC_X86_REG_SI)
            labels = []
            for index in range(7):
                address = int.from_bytes(m.cpu.mem_read(0xF0000+table+index*2, 2), 'little')
                labels.append(bytes(m.cpu.mem_read(0xF0000+address, 20)).split(b'\0')[0].decode())
            assert labels == expected, (jumper, labels)
            divisors = [int(label[1:].split()[0]) for label in labels]
            assert divisors == sorted(set(divisors)) and len(divisors) == 7
            m.call('chipset_ui_commit')
            assert m.cpu.mem_read(m.base+0x276, 1)[0] == selector << 4 | 0x0F
            m.call('chipset_isa_policy')
            assert m.registers[6] == (register if not selector else register & 0xE0 | SELECTORS[selector])
            m.cpu.reg_write(x.UC_X86_REG_AX, 0x4D00)
            m.call('chipset_ui_change')
            assert m.cpu.mem_read(m.base+0x276, 1)[0] == order[(choice+1)%7] << 4 | 0x0F
        rows.append({'jumper': jumper, 'labels': expected, 'selectors_unchanged': True})
    print('PASS ISA final divisors, resolved defaults and unchanged selectors', flush=True)
    return rows


def isa_menus():
    rows = []
    for jumper, alias, register in ((5, 5, 0xB7), (4, 6, 0x33)):
        expected = ['/2', '/3', '/4', '/5', '/6', '/8', '/10']
        expected[2 if jumper == 5 else 1] += ' (Default)'
        m = machine(alias)
        m.jumper = jumper
        m.registers[6] = register
        captured = []
        tail = [28] + SAVE
        def capture(mm):
            if mm.script == tail and not mm.pending and not captured:
                screen = bytes(mm.cpu.mem_read(0xB8000, 4000))[::2].decode('cp437')
                labels = [screen[row*80+26:row*80+46].strip() for row in range(25)]
                labels = [label for label in labels if label in expected]
                assert labels == expected, labels
                captured.extend(labels)
        m.observer = capture
        m.open(ISA_MENU + [28] + tail)
        assert captured and m.cmos[0x34] >> 4 == alias
        assert m.registers[6] == register
        m.irq_scans([0x1D, 0x38, 0xE0, 0x53])
        assert m.reset_pending
        m.complete_reset()
        assert m.cmos[0x34] >> 4 == alias and m.registers[6] == register
        rows.append({'jumper': jumper, 'popup': captured, 'saved_alias': alias,
                     'save_and_warm_reset': True})
    print('PASS unique rendered ISA menus and both saved aliases through Save/reset', flush=True)
    return rows


def refresh_menus():
    rows = []
    expected = ['15 us (Normal)', '30 us', '60 us', '120 us (Slow)']
    for saved in range(4):
        print(f'CHECK refresh code {saved}', flush=True)
        m = machine(refresh=saved)
        captured = []
        tail = [28] + SAVE
        def capture(mm):
            if mm.script == tail and not mm.pending and not captured:
                screen = bytes(mm.cpu.mem_read(0xB8000, 4000))[::2].decode('cp437')
                labels = [screen[row*80+26:row*80+46].strip() for row in range(25)]
                labels = [label for label in labels if label in expected]
                assert labels == expected, labels
                captured.extend(labels)
        m.observer = capture
        menu = [0x50]*4 + [28] + [0x50]*3 + [28]
        m.open(menu + [28] + tail)
        assert captured and m.cmos[0x72] == saved, (saved, captured, m.cmos[0x72])
        assert m.cpu.mem_read(m.base+0x67, 1) == bytes((saved,))
        assert m.registers[5] & 3 == (0, 3, 1, 2)[saved]
        m.irq_scans([0x1D, 0x38, 0xE0, 0x53])
        assert m.reset_pending
        m.complete_reset()
        assert m.cmos[0x72] == saved and m.registers[5] & 3 == (0, 3, 1, 2)[saved]
        rows.append({'refresh_code': saved, 'popup': captured, 'unchanged_save_and_cad': True})
    print('PASS sorted refresh popups and all saved codes through Save/reset', flush=True)
    return rows


def persistence():
    rows = []
    for action in ('discard', 'defaults-discard', 'defaults-save'):
        print(f'CHECK persistence {action}', flush=True)
        m = machine(6, 2)
        m.open(SAVE.copy())
        cache.prepare_ui(m)
        before = bytes(m.cmos)
        registers = bytes(m.registers)
        resets = m.reset_count
        seen = []
        keys = ISA_MENU + isa_change(7, 6)
        if action.startswith('defaults'):
            keys += [0x43, 28]
        tail = SAVE if action == 'defaults-save' else DISCARD_CHIP
        def draft(mm):
            if mm.script == tail and not mm.pending and not seen:
                expected = 0 if action.startswith('defaults') else 7
                assert mm.cpu.mem_read(mm.base+0x276, 1)[0] >> 4 == expected
                assert mm.cpu.mem_read(mm.base+0x1F0, 1)[0] == (1 if action.startswith('defaults') else 2)
                assert bytes(mm.cmos) == before and bytes(mm.registers) == registers
                seen.append(True)
        m.observer = draft
        m.open(keys + tail)
        assert seen
        if action == 'defaults-save':
            selected(m, 0)
            assert m.cmos[0x62] == 1 and m.reset_count == resets+1
        else:
            assert bytes(m.cmos) == before and bytes(m.registers) == registers
            assert m.reset_count == resets
        loaded = ACC(IMAGE, m.cmos)
        assert loaded.cpu.mem_read(loaded.base+0x76, 1)[0] >> 4 == (0 if action == 'defaults-save' else 6)
        rows.append({'persistence': action, 'draft_and_reload': True})
    for profile in (0, 1, 2):
        print(f'CHECK profile {profile}', flush=True)
        m = machine(6, flags=0x0F)
        # Normal -> selected profile through the existing RAM profile descriptor.
        m.open([0x50]*4 + [28, 0x50, 28] + [0x4D]*profile + SAVE)
        selected(m, 6)
        assert m.cmos[0x34] == 0x6F
        rows.append({'profile': profile, 'divider_and_low_flags_preserved': True})
    for kind in ('extended', 'legacy', 'checksum'):
        chip = bytearray(timing.DEFAULT if kind != 'legacy' else bytes((0,1,1,1,1,0,0,0,0))+bytes(15))
        n = timing.record(chip)
        if kind == 'checksum':
            n[0x34] = 0x60
        m = ACC(IMAGE, n)
        assert m.cpu.mem_read(m.base+0x76, 1)[0] >> 4 == 0
        assert bytes(m.cmos) == bytes(n[:128])
        rows.append({'old_record': kind, 'stock_no_cmos_write': True})
    print('PASS Discard, Defaults, profiles and saved-record compatibility', flush=True)
    return rows


def serial_pairs():
    rows = []
    for pair, expected in enumerate(PAIRS):
        print(f'CHECK COM pair {pair}', flush=True)
        m = machine()
        delta = [0x4B] if pair == 0 else [0x4D]*(pair-1)
        m.open(PAIR_MENU + delta + SAVE)
        assert m.cmos[0x62] == pair
        assert struct.unpack('<4H', m.cpu.mem_read(0x400, 8)) == (*expected, 0, 0)
        assert tuple((m.registers[i]&0xFE)<<2 for i in (0xDC,0xDD)) == expected
        assert m.irq_sources() == {3:3, 4:2}
        for unit in (0, 1):
            payload = 0x41+unit
            received, _ = m.public(0x14,0x0200,dx=unit)
            assert received & 255 == 0xA6
            ax, _ = m.public(0x14, 0x0100 | payload, dx=unit)
            assert ax == 0x6000 | payload and m.devices_uart[unit].tx == [payload]
        cache.prepare_ui(m)
        before = bytes(m.cmos)
        m.open(PAIR_MENU + [0x4D, 1, 1, 28])
        assert bytes(m.cmos) == before
        rows.append({'pair': pair, 'bases': expected, 'both_int14_and_reopen_discard': True})
    # Preferred COM1 repeats before the later ISA COM2 candidate.
    m = machine()
    ports_record(m.cmos, (1,4,1,2,0,1,1,1))
    m.call('settings_load')
    m.extra_uarts[0x2F8] = UART()
    m.open(PAIR_MENU + [0x4D] + SAVE)
    assert struct.unpack('<4H', m.cpu.mem_read(0x400, 8)) == (0x3F8,0x3E8,0x2F8,0)
    assert (struct.unpack('<H',m.cpu.mem_read(0x410,2))[0] >> 9)&7 == 3
    received, _ = m.public(0x14,0x0200,dx=2)
    assert received & 255 == 0xA6
    ax, _ = m.public(0x14, 0x015A, dx=2)
    assert ax == 0x605A and m.extra_uarts[0x2F8].tx == [0x5A]
    rows.append({'alternate_pair_duplicate_prefix_later_uart': True})
    print('PASS all COM pairs, both INT14 owners and later ISA discovery', flush=True)
    return rows


def cache_and_reset():
    rows = []
    m = cache.machine()
    chronology = []
    policy = {'late': False, 'start': None}
    owners = ('startup','cache_stock_reset','chipset_late_cache',
              'chipset_isa_policy','option_rom_discovery')
    addresses = {0xF0000+m.listing.symbol(name):name for name in owners}
    def clock_order(cpu, address, size, unused):
        name = addresses[address]
        if name == 'startup':
            policy.update(late=False, start=None)
        elif name in ('cache_stock_reset','chipset_late_cache','chipset_isa_policy'):
            assert m.registers[6]&0x1F == 0x17, (name,hex(m.registers[6]))
            if name == 'chipset_late_cache':
                policy['late'] = True
            elif name == 'chipset_isa_policy':
                assert policy['late']
                policy['start'] = len(m.acc_writes)
        else:
            assert policy['late'] and policy['start'] is not None
            selector = cpu.mem_read(m.base+0x76,1)[0] >> 4
            writes = [(index,value) for index,value in m.acc_writes[policy['start']:] if index == 6]
            assert writes == ([(6,0xA0|SELECTORS[selector])] if selector else []), writes
            assert m.registers[6] == 0xA0|SELECTORS[selector]
        chronology.append({'owner':name,'register06':m.registers[6]})
    for address in addresses:
        m.cpu.hook_add(UC_HOOK_CODE,clock_order,begin=address,end=address)
    cache.prepare_ui(m)
    m.open(ISA_MENU + isa_change(6) + SAVE)
    selected(m, 6)
    for script, cold in ((cache.edit(1)+SAVE, True), (SAVE.copy(), False), (None, False)):
        rows.append(cache.transition(m, script, cold, 1, 1))
        selected(m, 6)
    # Cold POST follows the same complete hardware probe, not a direct policy call.
    m.cold_boot()
    selected(m, 6)
    m.cmos[0x69] = 0
    m.cold_boot()
    selected(m, 0)
    assert sum(event['owner']=='option_rom_discovery' for event in chronology) == 6
    rows.append({'cold_and_cleared_chipset_record': True, 'clock_owner_chronology':chronology})
    for shutdown in (5, 0x0A):
        m = machine(6)
        m.registers[6] = 0xB3
        m.cmos[0x0F] = shutdown
        m.cpu.mem_write(0x467, struct.pack('<HH', 0, 0x9000))
        m.stop_address = 0x90000
        before = bytes(m.registers)
        m.reset_pending = True
        m.complete_reset(count=100000)
        assert bytes(m.registers) == before and m.posts == [shutdown]
        rows.append({'service_resume_preserves_isa': shutdown})
    for upper in (0, 0x20, 0xA0, 0xE0):
        m = machine(6)
        m.registers[6] = upper | 0x13
        timing.restore(m)
        assert m.registers[6] == upper | 0x17
        before = bytes(m.cpu.mem_read(m.base+0x76,1))
        m.call('chipset_isa_policy')
        assert m.registers[6] == upper | 0x13
        assert bytes(m.cpu.mem_read(m.base+0x76,1)) == before
        rows.append({'restore_and_apply_preserve_upper': upper})
    print('PASS changed cache, unchanged reset, cold/default and service paths', flush=True)
    return rows


def disk_at_selected_clock():
    class Disk(ACC):
        def __init__(self):
            self.disk = None
            self.word = 0
            self.read_clocks = []
            self.sector = b'BOOT' + bytes(506) + b'\x55\xAA'
            chip = bytearray(timing.DEFAULT)
            chip[6] = 1
            super().__init__(IMAGE, timing.record(chip))
            self.jumper = 5
            self.disk = importlib.import_module('test-legacy-disk').Pair(('ata', 'absent'))
            self.disk.cpu = self.cpu
        def port_in(self, cpu, port, size, unused):
            if self.disk is not None and (0x1F0 <= port <= 0x1F7 or port == 0x3F6):
                if port == 0x1F0 and self.disk.ata.get(0x1F7) == 0x20:
                    value = struct.unpack_from('<H', self.sector, self.word*2)[0]
                    self.word += 1
                    return value
                return self.disk.port_in(cpu,port,size,unused)
            return super().port_in(cpu,port,size,unused)
        def port_out(self, cpu, port, size, value, unused):
            if self.disk is not None and (0x1F0 <= port <= 0x1F7 or port == 0x3F6):
                if port == 0x1F7 and value == 0x20:
                    self.word = 0
                    self.read_clocks.append(self.registers[6])
                return self.disk.port_out(cpu,port,size,value,unused)
            return super().port_out(cpu,port,size,value,unused)
    m = Disk()
    m.continue_reset = True
    m.stop_address = 0x7C00
    m.open(ISA_MENU + isa_change(6) + SAVE)
    assert m.cpu.reg_read(x.UC_X86_REG_CS) == 0 and m.cpu.reg_read(x.UC_X86_REG_IP) == 0x7C00
    assert bytes(m.cpu.mem_read(0x7C00,512)) == m.sector
    ax, flags = m.public(0x13,0x0201,dx=0x80,cx=1,bx=0x7E00)
    assert ax == 1 and not flags&1
    assert bytes(m.cpu.mem_read(0x7E00,512)) == m.sector
    assert m.read_clocks == [0xB3,0xB3], m.read_clocks
    print('PASS signed ATA boot and public INT13 at selected divider', flush=True)
    return [{'signed_boot_and_public_int13_register06': m.read_clocks}]


def screens():
    rows = []
    for selector, pair, menu, tail, expected in (
            (0,1,ISA_MENU,DISCARD_CHIP,'ISA Clock Divider'),
            (0,1,ISA_MENU+[0x3B],[1]+DISCARD_CHIP,'Clear CMOS if startup fails.'),
            (0,1,PAIR_MENU,[1,1,28],'COM3 / IRQ4'),
            (6,1,ISA_MENU,DISCARD_CHIP,'/3'),
            (0,2,PAIR_MENU,[1,1,28],'2E8h / 3E8h')):
        m = machine(selector,pair)
        captured = []
        def capture(mm):
            if mm.script == tail and not mm.pending and not captured:
                screen = bytes(mm.cpu.mem_read(0xB8000,4000))[::2].decode('cp437')
                lines = [screen[row*80:(row+1)*80] for row in range(25)]
                assert any(expected in line for line in lines), lines
                if 'bAIos Setup > Devices' in screen:
                    assert 'Floppy Controller' not in screen
                    assert 'PS/2 Mouse' in screen
                captured.extend(lines)
        m.observer = capture
        m.open(menu+tail)
        assert captured
        rows.append({'screen': expected, 'lines': captured})
    return rows


def run():
    rows = isa_labels() + isa_menus() + refresh_menus() + isa_choices() + persistence() + serial_pairs() + cache_and_reset() + disk_at_selected_clock() + screens()
    output = PORT / 'build/tests/results/stock-options.json'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(rows, indent=2)+'\n')
    print(f'PASS {len(rows)} stock option cases', flush=True)


if __name__ == '__main__':
    run()
