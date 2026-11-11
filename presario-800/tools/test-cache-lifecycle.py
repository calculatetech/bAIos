"""Run real POST and Setup/reset with independent direct SRAM decoding."""
import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.ram_proof import constants

setup = importlib.import_module('test-setup')
chipset = importlib.import_module('test-chipset')
cache = importlib.import_module('test-external-cache')
SAVE = [0x44, 28]
STATE = constants(PORT.parent/'shared/src/pc/state.inc')


def direct_cache_memory(m):
    d = m.cache_device
    def direct(cpu, access, address, size, value, unused):
        d.external_cache = m.chipset.get(0x19, 0)
        if d.external_cache&7 != 7 or 0xA0000 <= address < 0x100000:
            return
        d.ramtmg, d.miscset, d.xctl = (m.chipset[r] for r in (1, 7, 0x24))
        if m.cache_phase:
            m.cache_traffic['write' if access == 17 else 'read'] += size
            if access == 17:
                m.cache_seeds.add(value ^ address)
        d.memory(cpu, access, address, size, value, unused)
    return direct


def watch_direct_cache(m, direct):
    """Follow the real controller mode, including discovery before data_test."""
    hooks = []
    # A newly added read hook misses reads already translated in the current
    # Unicorn block. Keep reads watched; dynamic writes remain observable.
    m.cpu.hook_add(UC_HOOK_MEM_READ, direct)
    def changed(cpu, port, size, value, unused):
        if port != 0xED or m.chipset_index != 0x19:
            return
        # The previously installed board port_out delegate owns this write.
        current = m.chipset.get(0x19, 0)
        m.cache_device.external_cache = current
        if current&7 == 7 and not hooks:
            hooks.append(m.cpu.hook_add(UC_HOOK_MEM_WRITE, direct))
        elif current&7 != 7 and hooks:
            for hook in hooks:m.cpu.hook_del(hook)
            hooks.clear()
    changed(m.cpu, 0xED, 1, m.chipset.get(0x19, 0), None)
    m.cpu.hook_add(UC_HOOK_INSN, changed, None, 1, 0, x.UC_X86_INS_OUT)


def machine(l1=1, l2=1, capacity=128*1024, broken=False, ram=8):
    m = setup.production_post_model(kinds=('ata', 'absent'), peripherals=True)
    setup.schema2_fixture(m, types=0x42, flags=0x09, order=(2, 0, 0))
    m.call('settings_load')
    read=lambda off,size:bytes(m.cpu.mem_read(m.base+off,size))
    write=lambda off,data:m.cpu.mem_write(m.base+off,data)
    chipset.draft_from_active(read,write,m.call)
    write(STATE['U_POST_DELAY'],b'\0')
    m.call('settings_save')
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1
    m.call('settings_load')
    assert read(STATE['C_POST_DELAY'],1)==b'\0'
    m.target_cpu(0x0430)
    m.cpu.reg_write(x.UC_X86_REG_EDX, 0x0430)
    assert ram in (4, 8)
    m.chipset[2] = 0x8C if ram == 4 else 0x8D
    def floating(cpu, access, address, size, value, unused):
        cpu.mem_write(address, b'\xFF'*size)
    m.cpu.hook_add(UC_HOOK_MEM_READ, floating, begin=ram*1024*1024, end=0x1FFFFFF)
    raw = bytearray(chipset.NORMAL)
    raw[4] = (raw[4]&~8) | (8 if l1 else 0)
    raw[9] = (raw[9]&~1) | l2
    # Reapply the original legacy chipset input after saving the base delay.
    m.cmos[0x69] = 0xC2; m.cmos[0x6A] = -(0xC2+sum(raw))&255
    m.cmos[0x6B:0x80], m.cmos[0x33:0x36] = raw[:21], raw[21:]
    d = cache.Cache(capacity, broken=broken)
    m.cache_device = d
    m.cache_phase = False
    m.cache_traffic = dict(read=0, write=0)
    m.cache_seeds = set()
    m.startup_native_owners = ('warm_reset', 'settings_save')
    begin = 0xF0000+cache.symbol('.data_test')
    end = 0xF0000+cache.symbol('.data_done')
    def phase(cpu, address, size, unused):
        m.cache_phase = address == begin
    m.cpu.hook_add(UC_HOOK_CODE, phase, begin=begin, end=begin)
    m.cpu.hook_add(UC_HOOK_CODE, phase, begin=end, end=end)
    watch_direct_cache(m, direct_cache_memory(m))
    return m


def hook_window_check():
    """Compare actual x86 OUT transitions with the original always-watch seam."""
    import struct
    def exercise(gated, broken):
        m = object.__new__(chipset.Chipset)
        m.cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        m.cpu.mem_map(0, 0x200000)
        m.chipset = {1:0x96, 7:0x80, 0x24:0xD0, 0x19:0}
        m.chipset_index = 0; m.reg_writes = []; m.starting = False
        m.cache_device = cache.Cache(128*1024, broken=broken)
        m.cache_phase = False; m.cache_traffic = dict(read=0, write=0); m.cache_seeds = set()
        calls = [0]; observations = []; expected = []; phases = {}; points = set(); code = bytearray()
        def mode(value):
            code.extend(bytes((0xB0,0x19,0xE6,0xEC,0xB0,value,0xE6,0xED)))
        def access(address, value):
            code.extend(b'\x67\x66\xC7\x05'+struct.pack('<II',address,value))
            code.extend(b'\x67\x66\xA1'+struct.pack('<I',address))
            points.add(0x90000+len(code))
            expected.append(value ^ int(broken and address == 0x100200))
            code.append(0x90)
        for value in range(16):access(0x3000,value)
        for ordinal, value in enumerate((7, 0x87)):
            mode(value)
            phases[0x90000+len(code)] = False
            access(0x10000,0x10203040+ordinal) # Actual discovery, before data phase.
            phases[0x90000+len(code)] = True
            for pattern in (0x55AA55AA,0xAA55AA55):access(0x100200,pattern)
            mode(0)
            for value in range(16):access(0x3000,value)
        def observe(cpu,address,size,unused):
            if address in phases:m.cache_phase = phases[address]
            if address in points:observations.append(cpu.reg_read(x.UC_X86_REG_EAX))
        original = direct_cache_memory(m)
        def counted(*args):
            calls[0] += 1
            return original(*args)
        m.cpu.hook_add(UC_HOOK_INSN,m.port_out,None,1,0,x.UC_X86_INS_OUT)
        if gated:watch_direct_cache(m,counted)
        else:m.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE,counted)
        m.cpu.hook_add(UC_HOOK_CODE,observe)
        m.cpu.mem_write(0x90000,bytes(code))
        m.cpu.reg_write(x.UC_X86_REG_CS,0x9000)
        m.cpu.emu_start(0x90000,0x90000+len(code),count=1000)
        assert m.cpu.reg_read(x.UC_X86_REG_IP) == len(code)
        assert m.cache_traffic == dict(read=16,write=16), (gated,m.cache_traffic,calls,m.reg_writes)
        assert m.cache_device.direct_reads == 6
        assert observations == expected
        assert m.cache_seeds == {0x55AA55AA^0x100200,0xAA55AA55^0x100200}
        assert m.reg_writes == [(0x19,7),(0x19,0),(0x19,0x87),(0x19,0)]
        return (observations,bytes(m.cache_device.sram),dict(m.chipset),m.reg_writes,
                m.cache_traffic,m.cache_seeds,m.cache_device.external_cache,
                bytes(m.cpu.mem_read(0x3000,4))),calls[0]
    results=[]
    for broken in (False, True):
        reference, always = exercise(False, broken)
        actual, gated = exercise(True, broken)
        assert actual == reference
        assert gated == 60 and always == 108, (gated,always)
        results.append(dict(broken=broken,always_callbacks=always,gated_callbacks=gated,
                            full_SRAM_registers_reads_counters_seeds_and_memory_equal=True))
    return dict(id='hook-window',status='pass',actual_OUT_entry_exit_reentry=True,
                discovery_before_data_phase=True,results=results)


def active(m):
    return (not bool(m.cpu.reg_read(x.UC_X86_REG_CR0)&0x40000000),
            0 < m.chipset.get(0x19, 0)&7 < 7)


def boot(m, *, cold=False, script=None, escape=True, expected_record=None):
    if not cold:
        setup.settle_boot_leds(m)
        m.warm = False
        m.scans([0x1D, 0x38, 0xE0, 0x53])
        assert m.warm
    events = []
    requested = False
    def observe(mm, name):
        nonlocal requested
        events.append(name)
        if script is not None and not requested and name == 'chipset_apply':
            requested = True
            mm.pending.extend((0xE0, 0x53))
        if name == 'setup_main':
            mm.script = list(script)
        if name == 'settings_save' and getattr(mm, 'reject_save', False):
            mm.reject_armed = True
        if name == 'warm_reset' and getattr(mm, 'reject_save', False):
            raise AssertionError(('rejected Save reached reset',mm.reject_armed,mm.rejected_reads))
        if name == 'post_notice_wait':
            assert script is not None and requested and events.count(name) == 1, (
                'unexpected POST notice', events[-16:], mm.console[-400:],
                bytes(mm.cmos[0x38:0x40]).hex())
    m.startup_observer = observe
    skipped = []
    def skip(cpu, address, size, unused):
        if escape and not skipped:
            skipped.append(True)
            m.pending.append(1)
    point = 0xF0000+cache.symbol('.keyboard')
    hook = m.cpu.hook_add(UC_HOOK_CODE, skip, begin=point, end=point)
    try:
        m.startup(reset=cold, production_controls=True, through_boot=True, expected_record=expected_record)
    except AssertionError:
        pc = (m.cpu.reg_read(x.UC_X86_REG_CS)<<4)+m.cpu.reg_read(x.UC_X86_REG_IP)
        print('Presario terminal PC', hex(pc), 'bytes', bytes(m.cpu.mem_read(pc, 8)).hex(),
              'boot reads', m.boot_reads, flush=True)
        raise
    finally:
        m.cpu.hook_del(hook)
    m.startup_observer = None
    assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
    assert events.index('setup_post_gate') < events.index('chipset_late_cache') < events.index('int19')
    assert ('setup_main' in events) == (script is not None)
    print('Presario cache POST', active(m), 'cold' if cold else 'warm', 'BOOT PASS', flush=True)
    return dict(active=list(active(m)), owners=events, terminal='signed boot sector',
                traffic=dict(m.cache_traffic), seeds=sorted(m.cache_seeds))


def edit(field):
    # Chipset > Cache, then the independent L1 or L2 control.
    return [0x50]*4+[28, 0x50, 28]+[0x50]*field+[0x4D]


def run(stage="all"):
    if stage == 'hook-window':
        return [hook_window_check()]
    def cases(name, values):
        return values if stage in ("all", name) else ()
    evidence = {f'S{i}': [] for i in range(1, 11)}
    def record(ids, value):
        for identity in ids:
            evidence[identity].append(value)
    for l1, l2 in cases("cold", ((0, 0), (0, 1), (1, 0), (1, 1))):
        m = machine(l1, l2)
        row = boot(m, cold=True)
        assert active(m) == (bool(l1), bool(l2)), row
        if l2:
            assert m.cache_seeds == {0x55AA55AA, 0xAA55AA55}
            assert m.cache_traffic['read'] == m.cache_traffic['write'] == 2*m.cache_device.capacity
        record(('S1', 'S7'), row)

    if stage == "transitions":
        m = machine()
        boot(m, cold=True)
    for field, expected in cases("transitions", ((0, (0, 1)), (1, (0, 0)), (1, (0, 1)), (0, (1, 1)))):
        row = boot(m, script=edit(field)+SAVE)
        assert active(m) == tuple(map(bool, expected)), row
        record(('S2',), row)
        row = boot(m, script=SAVE)
        assert active(m) == tuple(map(bool, expected))
        record(('S3',), row)
        row = boot(m)
        assert active(m) == tuple(map(bool, expected))
        record(('S3',), row)

    for name, script in cases("ui", (
        ('discard', edit(0)+[1, 1, 1, 28]),
        ('cancel-save', edit(0)+[0x44, 1, 1, 1, 1, 28]),
        ('defaults-discard', [0x43, 28, 1, 28]),
        ('defaults-save', [0x43, 28]+SAVE))):
        m = machine(0, 0)
        boot(m, cold=True)
        row = boot(m, script=script)
        expected = (1, 1) if name == 'defaults-save' else (0, 0)
        assert active(m) == tuple(map(bool, expected)), row
        record(('S4',), dict(operation=name, **row))

    if stage in ("all", "rejection"):
        m = machine(0, 0)
        boot(m, cold=True)
        old = m.record()
        m.reject_save = True; m.reject_armed = False; m.rejected_reads = 0
        def reject(index, value):
            if index == 0x3E and m.reject_armed:
                m.rejected_reads += 1
                return value ^ 255
            return value
        def error(mm):
            if 'CMOS verification failed.' in mm.text(19, 23, 46):
                mm.observer = None
                mm.script = [1, 1, 1, 28]
        m.rtc_read_filter = reject
        m.observer = error
        rejected = boot(m, script=edit(0)+SAVE, expected_record=old)
        assert m.rejected_reads and 'warm_reset' not in rejected['owners']
        m.reject_save = False; m.rtc_read_filter = None
        # The failed base commit selects recovery defaults; explicitly choose L2 off.
        resumed = boot(m, script=edit(1)+SAVE)
        assert active(m) == (True, False), resumed
        record(('S5',), dict(rejected=rejected, resumed=resumed, rejected_reads=m.rejected_reads,
                            recovery_selection='External Cache Off, then Save'))

    for capacity, broken in cases("discovery", ((0, False), (98304, False), (131072, True))):
        m = machine(capacity=capacity, broken=broken)
        row = boot(m, cold=True)
        assert not active(m)[1], row
        assert m.cpu.mem_read(m.base+0x7A, 1) == bytes((0x16 if not capacity else 0x14,))
        record(('S6',), row)
        if broken:
            m.cache_device.broken = False
            retry = boot(m)
            assert active(m)[1]
            record(('S9',), dict(failed=row, retry=retry))

    for escape in cases("skip", (False, True)):
        m = machine()
        row = boot(m, cold=True, escape=escape)
        assert active(m) == (True, True)
        record(('S8',), dict(escape=escape, **row))
    budget = []
    for ram in cases('budget', (4, 8)):
        m = machine(ram=ram)
        row = boot(m, cold=True)
        installed = int.from_bytes(m.cpu.mem_read(m.base+0x78, 2), 'little')
        assert installed == ram*1024-1024, (ram, installed, m.chipset[2])
        budget.append(row['traffic'])
        record(('S7',), dict(ram=ram, **row))
    if budget:
        assert budget[0] == budget[1]
    # No new write-back support is inferred from the shared phase vocabulary.
    if stage == 'all':
        record(('S10',), dict(policy='existing controller policy preserved', new_modes=False,
                         evidence=evidence['S1']+evidence['S2']))
        subprocess.run([sys.executable, '-B', str(PORT/'tools/test-external-cache.py')], check=True)
    return [dict(id=k, status='pass', evidence=v) for k, v in evidence.items() if v]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument("--stage", choices=sorted(("all", "cold", "transitions", "ui", "rejection", "discovery", "skip", "budget", "hook-window")), default="all")
    args = parser.parse_args()
    rows = run(args.stage)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(port='presario-800', scenarios=rows), indent=2)+'\n')
