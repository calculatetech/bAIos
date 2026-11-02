"""Composed cache startup, Setup/reset and bounded external-SRAM evidence."""
import argparse
import binascii
import json
from pathlib import Path

from unicorn import x86_const as x
from cache_proof import POSTHardware, DRAM, composed, guest, dma
from geometry_proof import Listing, invoke
from shared.tools.ram_proof import constants

PORT = Path(__file__).resolve().parents[1]
SAVE = [0x44, 28]


def policy(l1=1, l2=1, wb=False, fast=True):
    raw = bytearray(24)
    raw[0] = 0xF0
    raw[1:4] = bytes((l1, 1-l2, 0x40 if wb else 0))
    raw[12] = int(fast)
    return bytes(raw)


class Hardware(POSTHardware):
    def __init__(self, pattern_fault=None, **options):
        super().__init__(**options)
        self.pattern_fault = pattern_fault
        self.pattern_error = None
        self.test_phase = None
        self.traffic = dict(data_read=0, data_write=0, witness_read=0, witness_write=0)
        self.patterns = set()
        self.data_fetch_locations = set()
        self.witness_addresses = set()
        self.reject_save = False
        self.reject_armed = False
        self.rejected_reads = 0

    def rtc_read(self, index, value):
        if self.reject_armed and index == 0x3E:
            self.rejected_reads += 1
            return value ^ 255
        return value

    def prepare(self, u):
        super().prepare(u)
        listing = Listing(PORT/'build/hardware-tests/geometry/baios-m919.lst')
        self.phase_points = {}
        for label, phase in (('.patterns', 'data'), ('.witnesses', 'witness'),
                             ('.copyback', None), ('.address_failed', 'failure'),
                             ('.tag_failed', 'failure'), ('.finish', None)):
            offset = listing.symbol(label, 'cache_run')
            for base in (0xF0000, 0xFFFF0000):
                self.phase_points[base+offset] = phase
        self.boot_wait = 0xF0000+listing.symbol('.wait', 'boot_retry')
        self.reset_entry = 0xF0000+listing.symbol('warm_reset')

    def outgoing(self, u, port, size, value):
        if port == 0x80 and value == 0xFF:
            self.ports[port] = value
            return
        super().outgoing(u, port, size, value)

    def observe(self, u, address, size):
        if getattr(self, 'reset_on_idle', False) and address < 0x8000 and bytes(u.mem_read(address, 1)) == b'\xF4':
            self.reset_on_idle = False
            self.queue.extend((0x1D, 0x38, 0xE0, 0x53))
        if self.reject_save and getattr(self, 'points', {}).get(address) == 'settings_save':
            self.reject_armed = True
        if address in self.phase_points:
            self.test_phase = self.phase_points[address]
        if self.test_phase == 'data':
            assert 0xF0000 <= address < 0x100000, hex(address)
            assert self.registers[0x55] == 0xC0
            self.data_fetch_locations.add('uncached-shadow')
        if address == self.reset_entry:
            self.keyboard_reset_seen = True
        super().observe(u, address, size)
        if self.continuing and address == self.boot_wait:
            self.stop = 'boot_retry'
            u.emu_stop()

    def read(self, address, size):
        result = super().read(address, size)
        if self.test_phase in ('data', 'witness'):
            assert self.machine.reg_read(x.UC_X86_REG_CR0)&0x40000000
            self.traffic[self.test_phase+'_read'] += size
        if self.test_phase == 'data' and address == 0x100000+self.capacity-4:
            seed = self.machine.reg_read(x.UC_X86_REG_EDX)
            if seed == self.pattern_fault:
                value = int.from_bytes(result, 'little') ^ 0x02000000
                self.pattern_error = (address, address ^ seed, value)
                return value.to_bytes(size, 'little')
        if self.test_phase == 'failure' and self.pattern_error and address == self.pattern_error[0]:
            return self.pattern_error[2].to_bytes(size, 'little')
        return result

    def write(self, address, size, value):
        if self.test_phase in ('data', 'witness'):
            self.traffic[self.test_phase+'_write'] += size
            if self.test_phase == 'data':
                self.patterns.add(value ^ address)
            else:
                assert self.cacheable(address), hex(address)
                assert address % self.capacity == 0, hex(address)
                self.witness_addresses.add(address)
        super().write(address, size, value)


def boot(*, memory=None, chip=None, ram=8, kib=64, **options):
    row, fixture = composed(kib=kib, ram=ram, chip=chip or policy(), memory=memory,
                            hardware=Hardware, **options)
    if row['terminal'] == 'boot_retry':
        assert row['post_visits'].index('setup_post_gate') < row['post_visits'].index('cache_enable')
        assert row['enable_attempts'] == 1
    return row, fixture


def reboot(fixture, dirty=False):
    d = fixture[1]
    d.reset_requests.clear()
    d.keyboard_reset_seen = False
    if dirty:
        d.reset_on_idle = True
    else:
        d.queue.extend((0x1D, 0x38, 0xE0, 0x53))
    guest(fixture, 'cache-keyboard-reset',
          ('mov dword [dword 0x20000],0xC0DEFACE\n' if dirty else '')+'sti\nhlt', reset=True)
    assert d.keyboard_reset_seen
    if dirty:
        assert DRAM.read(d, 0x20000, 4) == bytes.fromhex('CE FA DE C0')
    row, result = boot(memory=d)
    if dirty:
        assert DRAM.read(d, 0x20000, 4) == bytes.fromhex('CE FA DE C0')
    return row, result


def seed(memory, raw):
    from cache_proof import post_module
    cmos = bytearray(post_module().nvram(types=0x40)[:128])
    cmos[0x69] = 0x57; cmos[0x6B:0x80] = raw[:21]; cmos[0x33:0x36] = raw[21:]
    cmos[0x6A] = (-0x57-sum(raw))&255
    memory.saved_cmos = bytes(cmos)
    return memory


def run(stage="all"):
    def cases(name, values):
        return values if stage in ("all", name) else ()
    evidence = {f'S{i}': [] for i in range(1, 11)}
    def record(ids, detail):
        for identity in ids:
            evidence[identity].append(detail)

    if stage == 'shadow':
        for kib, wb in ((64, False), (512, False), (512, True)):
            row, f = boot(kib=kib, ram=16, chip=policy(wb=wb))
            d = f[1]
            assert row['terminal'] == 'boot_retry' and row['enabled'], row
            assert d.l2_wb() == wb
            assert d.patterns == {0x55AA55AA, 0xAA55AA55}
            assert d.traffic['data_read'] == d.traffic['data_write'] == 2*d.capacity
            assert d.traffic['witness_read'] == d.traffic['witness_write'] == 16
            assert d.data_fetch_locations == {'uncached-shadow'}
            record(('S7',), dict(kib=kib, wb=wb, traffic=d.traffic,
                                code_fetch=sorted(d.data_fetch_locations), terminal=row['terminal']))
        for pattern_seed in (0x55AA55AA, 0xAA55AA55):
            d = seed(Hardware(kib=64, ram=8, pattern_fault=pattern_seed), policy(wb=True))
            row, _ = boot(memory=d)
            assert row['terminal'] == 'reset' and not row['enabled'], row
            actual = row['cache_failure']
            assert (actual['address'], actual['expected'], actual['observed']) == d.pattern_error, actual
            record(('S9',), dict(seed=f'{pattern_seed:08X}', mismatch=actual,
                                terminal=row['terminal']))

    if stage in ('all', 'retired'):
        _, f = boot(chip=policy(l1=0))
        u, d, listing, state, *_ = f
        state = dict(state, **constants(PORT/'src/hardware/board-definition.inc'))
        base = u.reg_read(x.UC_X86_REG_FS)<<4
        # Historical 45af656^ cache_validation_identity: all fourteen key bytes.
        key = bytes((0xA5, d.read(base+state['HW_CACHE_MAP'],1)[0],
                     d.read(base+state['HW_HB52'],1)[0], d.read(base+state['HW_HB53'],1)[0]&0x3F,
                     d.read(base+state['HW_HB61'],1)[0]&0x30, d.registers[8]))
        signature=d.read(base+state['S_CPU_SIGNATURE'],2)
        image=bytes(u.mem_read(0xF0000,0x10000))
        invoke(f,'cpu_detect_name')
        key += signature + u.reg_read(x.UC_X86_REG_SI).to_bytes(2,'little')
        key += binascii.crc32(image).to_bytes(4,'little')
        for present, checksum_ok, partial in ((False, True, False), (True, True, False),
                                              (True, True, True), (True, False, False)):
            raw = policy(l1=0)[:10] + (key if present else bytes(14))
            if partial:raw=raw[:21]+bytes((0x34,0x02,0x11))
            memory = seed(Hardware(kib=64,ram=8),raw)
            cmos = bytearray(memory.saved_cmos);cmos[0x69]=0x56;cmos[0x6A]=(-0x56-sum(raw))&255
            if not checksum_ok:cmos[0x6A]^=1
            memory.saved_cmos=bytes(cmos)
            row, result = boot(memory=memory)
            if not checksum_ok:
                assert row['terminal']=='reset' and not row['enabled'],row
                record(('S6',),dict(retired_checksum_rejected=True,terminal=row['terminal']))
                continue
            assert row['terminal']=='boot_retry' and not row['l1'] and row['enabled'],row
            assert 'cache_qualify' in row['post_visits']
            assert memory.patterns=={0x55AA55AA,0xAA55AA55}
            assert memory.traffic['data_read']==memory.traffic['data_write']==2*memory.capacity
            assert memory.traffic['witness_read']==memory.traffic['witness_write']==16
            actual = memory.read((result[0].reg_read(x.UC_X86_REG_FS)<<4)+state['C_CHIP'],10)
            assert actual==raw[:10],(actual.hex(),raw[:10].hex())
            record(('S3','S7'),dict(retired_certificate=present,partial_marker=partial,key=raw[10:].hex(),saved_choices=actual.hex(),traffic=dict(memory.traffic),terminal=row['terminal']))

    for l1, l2 in cases("cold", ((0, 0), (0, 1), (1, 0), (1, 1))):
        row, f = boot(chip=policy(l1, l2))
        assert row['terminal'] == 'boot_retry' and row['l1'] == bool(l1) and row['enabled'] == bool(l2), row
        d = f[1]
        assert ('cache_qualify' in row['post_visits']) == bool(l2)
        if l2:
            assert d.patterns == {0x55AA55AA, 0xAA55AA55}, d.patterns
            assert d.traffic['data_read'] == d.traffic['data_write'] == 2*d.capacity, d.traffic
            assert d.traffic['witness_write'] <= 16 and d.traffic['witness_read'] <= 16, d.traffic
        record(('S1', 'S7'), dict(tuple=[l1, l2], terminal=row['terminal'], traffic=d.traffic))

    if stage in ("all", "transitions"):
        row, f = boot()
    for field, l1, l2 in cases("transitions", ((0, 0, 1), (1, 0, 0), (1, 0, 1), (0, 1, 1))):
        # Chipset > Cache: independent internal/external cache controls.
        keys = [0x50]*4+[28, 28]+[0x50]*field+[0x4D]+SAVE
        changed, g = boot(memory=f[1], keys=keys)
        assert changed['terminal'] == 'reset' and not g[1].keys
        current, f = boot(memory=g[1])
        assert (current['l1'], current['enabled']) == (bool(l1), bool(l2)), current
        unchanged, g = boot(memory=f[1], keys=SAVE)
        assert unchanged['terminal'] == 'reset'
        current, f = boot(memory=g[1])
        reset, f = reboot(f)
        assert (reset['l1'], reset['enabled']) == (bool(l1), bool(l2)), reset
        assert ('cache_qualify' in reset['post_visits']) == bool(l2)
        record(('S2', 'S3'), dict(saved=[l1, l2], unchanged_and_keyboard_reset=True, terminal=reset['terminal']))

    for name, keys, expected in cases("ui", (
        ('discard', [0x50]*4+[28, 28, 0x4D, 1, 1, 1, 28], (0, 0)),
        ('cancel-save', [0x50]*4+[28, 28, 0x4D, 0x44, 1, 1, 1, 1, 28], (0, 0)),
        ('defaults-discard', [0x43, 28, 1, 28], (0, 0)),
        ('defaults-save', [0x43, 28]+SAVE, (1, 1)))):
        _, f = boot(chip=policy(0, 0, wb=False))
        edited, g = boot(memory=f[1], keys=keys)
        if edited['terminal'] == 'reset':
            current, f = boot(memory=g[1])
        else:
            current, f = reboot(g)
        assert (current['l1'], current['enabled']) == tuple(map(bool, expected))
        record(('S4',), dict(operation=name, terminal=current['terminal']))

    if stage in ('all', 'rejection'):
        _, f = boot()
        f[1].reject_save = True
        keys = [0x50]*4+[28, 28, 0x4D]+SAVE+[1, 1, 1, 28]
        rejected, g = boot(memory=f[1], keys=keys)
        assert rejected['terminal'] == 'boot_retry' and not g[1].reset_requests and g[1].rejected_reads
        g[1].reject_save = g[1].reject_armed = False
        resumed, f = reboot(g)
        assert not resumed['l1'] and resumed['enabled'], resumed
        record(('S5',), dict(rejected_reads=g[1].rejected_reads, later_keyboard_reset=resumed['terminal'], l1=False))

    for options in cases("discovery", (dict(kind='absent'), dict(kind='stored'), dict(alias=5), dict(fault=0x2B6A))):
        row, f = boot(**options)
        assert not row['enabled'], row
        assert row['terminal'] == 'reset', row
        safe, _ = boot(memory=f[1])
        assert safe['terminal'] == 'boot_retry' and not safe['enabled']
        record(('S6',), dict(hardware=options, terminal=row['terminal'], flags=row['flags']))

    for pattern_seed in cases("failure", (0x55AA55AA, 0xAA55AA55)):
        d = seed(Hardware(kib=64, ram=8, pattern_fault=pattern_seed), policy())
        failed, f = boot(memory=d)
        assert failed['terminal'] == 'reset' and not failed['enabled'], failed
        actual = failed['cache_failure']
        assert (actual['address'], actual['expected'], actual['observed']) == d.pattern_error, actual
        safe, g = boot(memory=d)
        assert safe['terminal'] == 'boot_retry' and not safe['enabled']
        d.pattern_fault = None; d.pattern_error = None
        retry, f = boot(memory=d, keys=[0x50]*4+[28, 28, 0x50, 0x4D]+SAVE)
        assert retry['terminal'] == 'reset'
        healed, f = boot(memory=d)
        assert healed['enabled'] and 'cache_qualify' in healed['post_visits']
        record(('S9',), dict(seed=f'{pattern_seed:08X}', mismatch=actual, safe_boot=True, saved_retry=True))

    for fast in cases("skip", (False, True)):
        d = seed(Hardware(kib=64, ram=4), policy(fast=fast))
        d.ram_escape = fast
        row, f = boot(memory=d)
        assert row['enabled'] and f[1].traffic['data_read'] == 2*f[1].capacity
        record(('S8',), dict(fast=fast, escaped=row['ram_escaped'], terminal=row['terminal']))

    traffic_by_mode = {}
    for ram, wb in (((8, False), (16, False), (8, True), (16, True)) if stage in ('all','modes','witnesses') else ()):
        row, f = boot(ram=ram, chip=policy(wb=wb))
        assert row['enabled'] and f[1].l2_wb() == wb
        traffic = dict(f[1].traffic)
        device=f[1]
        limit=min(ram*0x100000,device.capacity*(256 if device.registers[0x51]&1 else 128))
        highest=max(a for a in range(0x100000+device.capacity,limit,device.capacity))
        expected={0x100000,0x100000+device.capacity,highest}
        assert device.witness_addresses==expected,(device.witness_addresses,expected)
        assert len({device.index(a) for a in expected})==1
        assert len({device.tag(a,device.capacity) for a in expected})==len(expected)
        if wb in traffic_by_mode:
            assert traffic == traffic_by_mode[wb], (ram, wb, traffic)
        traffic_by_mode[wb] = traffic
        detail = dict(ram=ram, wb=wb, witnesses=sorted(f[1].witness_addresses), traffic=traffic)
        record(('S7', 'S10'), detail)
        if wb and ram == 8 and stage != 'witnesses':
            resumed, f = reboot(f, dirty=True)
            assert resumed['enabled']
            record(('S10',), dict(dirty_keyboard_reset=True, terminal=resumed['terminal']))
    if stage in ('all', 'modes'):
        for kib, banks in ((512, 1), (512, 2), (1024, 2)):
            row, f = boot(kib=kib, banks=banks, ram=16, chip=policy(wb=True))
            assert row['enabled'] and f[1].traffic['data_read'] == 2*kib*1024
            record(('S6', 'S10'), dict(kib=kib, banks=banks, terminal=row['terminal'],
                                     traffic=dict(f[1].traffic)))
        record(('S10',), dict(dma=dma(l2_wb=True)))
    return [dict(id=k, status='pass', evidence=v) for k, v in evidence.items() if v]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument("--stage", choices=sorted(("all", "cold", "transitions", "ui", "rejection", "discovery", "failure", "skip", "modes", "retired", "witnesses", "shadow")), default="all")
    args = parser.parse_args()
    rows = run(args.stage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(port='m919', scenarios=rows), indent=2)+'\n')
