"""Execute uncached RAM testing and failed-trial recovery in the assembled PB430 ROM."""
import importlib
import json
import struct
from pathlib import Path
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

timing = importlib.import_module('test-timing-setup')
PORT = Path(__file__).resolve().parents[1]
IMAGE = PORT / 'build/baios-pb430.bin'


def machine(fast_boot=1):
    chip = bytearray(timing.DEFAULT)
    chip[6] = fast_boot
    chip[14] = 1
    m = timing.model(IMAGE, chip)
    m.cpu.mem_write(m.base + 0x78, struct.pack('<H', 15360))
    m.cpu.mem_write(m.base + 0x51, b'\x04')  # P_PHASE: existing POST row.
    m.cpu.mem_write(0x49E, b'\x01')          # Presario POST key handling stays open.
    m.cpu.mem_write(m.base+0x1006,b'\0')
    m.registers[4] &= 0xFE
    m.cpu.reg_write(x.UC_X86_REG_CR0,0x60000010)
    m.call('chipset_timing_trial_begin')
    m.call('chipset_memory_policy')
    return m


def until(m, name, stop):
    target = 0xF0000 + m.listing.symbol(stop)
    reached = []
    def observe(mm, address):
        if address == target:
            reached.append(True)
            mm.cpu.emu_stop()
    m.code_observer = observe
    try:
        m.call(name)
    except AssertionError:
        assert reached, (name, stop, m.posts)
    else:
        raise AssertionError(('Did not reach stop', name, stop))
    m.code_observer = None


def run():
    rows = []
    # Observe one continuous production POST, including the summary and RTC work.
    chip = bytearray(timing.DEFAULT)
    chip[6] = chip[14] = 1
    for interrupted in (False, True):
        m = timing.model(IMAGE, chip)
        names = ('post_debug_summary', 'rtc_sync_ticks', 'chipset_timing_trial_finish')
        addresses = {0xF0000 + m.listing.symbol(name): name for name in names}
        seen = []
        finish_return = []
        def progress(mm, address):
            if address in addresses:
                name = addresses[address]
                # RTC synchronization also runs earlier in POST.
                if name == 'rtc_sync_ticks' and not seen:
                    return
                assert mm.cmos[0x36] == 0xAB, (name, mm.cmos[0x36])
                seen.append(name)
                if name == 'chipset_timing_trial_finish':
                    sp = mm.cpu.reg_read(x.UC_X86_REG_SS)*16 + mm.cpu.reg_read(x.UC_X86_REG_SP)
                    finish_return.append(0xF0000 + int.from_bytes(mm.cpu.mem_read(sp, 2), 'little'))
            if finish_return and address == finish_return[0]:
                assert mm.cmos[0x36] == 0
                seen.append('finished')
        m.code_observer = progress
        m.stop_address = (0xF0000 + m.listing.symbol('post_debug_summary') if interrupted
                          else 0xF0000 + m.listing.symbol('.wait', 'boot_retry'))
        m.cold_boot()
        assert m.registers[0xB] == 0 and m.registers[0x16] == 3
        if interrupted:
            assert seen == ['post_debug_summary'] and m.cmos[0x36] == 0xAB
            m.code_observer = None
            m.stop_address = 0xF0000 + m.listing.symbol('setup_post_gate')
            m.cold_boot()
            assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x1A
            assert bytes(m.cpu.mem_read(m.base+0x60, 24)) == timing.DEFAULT[:2] + b'\0' + timing.DEFAULT[3:]
            m.open([1, 28])
            assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x1A
        else:
            assert seen == list(names) + ['finished'], seen
            assert m.cmos[0x36] == 0 and m.posts[-1] == 0xE4
        rows.append({'production_summary_trial_and_hard_reset': interrupted})
    print('PASS production summary/RTC finish and interrupted-summary recovery', flush=True)

    # Fail only the selected-timing DRAM read; firmware owns every retry stage.
    m = timing.model(IMAGE, chip)
    patterned = [False]
    failed = []
    restarted = []
    def write_pattern(cpu, access, address, size, value, unused):
        if m.cmos[0x36] == 0xAB and value == 0x55AA55AA:
            patterned[0] = True
    def read_fault(cpu, access, address, size, value, unused):
        if patterned[0] and not failed and m.cmos[0x36] == 0xAB:
            cpu.mem_write(address, b'\0\0\0\0')
            failed.append(True)
    restart = 0xF0000 + m.listing.symbol('controlled_defaults_restart')
    def recovery(mm, address):
        if address == restart:
            assert failed and mm.cmos[0x69] == 0xD2 and mm.cmos[0x36] == 0x1A
            restarted.append(True)
    m.cpu.hook_add(UC_HOOK_MEM_WRITE, write_pattern, begin=0x10000, end=0x10003)
    m.cpu.hook_add(UC_HOOK_MEM_READ, read_fault, begin=0x10000, end=0x10003)
    m.code_observer = recovery
    m.stop_address = 0xF0000 + m.listing.symbol('setup_post_gate')
    m.cold_boot()
    assert failed and restarted == [True] and m.reset_count == 1
    assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x1A
    assert bytes(m.cpu.mem_read(m.base+0x60, 24)) == timing.DEFAULT[:2] + b'\0' + timing.DEFAULT[3:]
    assert m.registers[0xB] == 0x15 and m.registers[0x16] == 0 and not m.registers[4]&1
    m.open([1, 28])
    assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x1A
    rows.append({'production_dram_fault_reset_safe_retry_and_setup': True})
    print('PASS production DRAM fault, controlled reset, safe retry and Setup', flush=True)

    # Fail late base-record verification after the valid chipset draft was saved.
    class SaveMismatch(timing.ACC):
        def port_in(self, cpu, port, size, unused):
            value = super().port_in(cpu, port, size, unused)
            if port == 0x71 and self.index == 0x3E and (0x38, 66) in self.writes:
                return value ^ 255
            return value
    m = timing.model(IMAGE, cls=SaveMismatch)
    m.cmos[0x69] = 0xD2
    m.cmos[0x36] = 0x1A
    errors = []
    def save_error(mm):
        if 'CMOS verification failed.' in mm.text(19, 23, 46):
            assert mm.cmos[0x69] == 0xD2 and mm.cmos[0x36] == 0x1A
            assert (0x69, 0xC2) in mm.writes and (0x38, 66) in mm.writes
            assert not mm.reset_count
            errors.append(True)
            mm.observer = None
            mm.script = [1, 28]
    m.observer = save_error
    m.open([0x44, 28])
    assert errors and not m.reset_count and m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x1A
    rows.append({'valid_ui_save_failed_verification_preserves_recovery': True})
    print('PASS valid Setup save with failed CMOS verification keeps recovery', flush=True)

    m = machine()
    before = bytes((i * 7 + 3) & 255 for i in range(0x800))
    m.cpu.mem_write(0x10000, before)
    reads, writes = [], []
    def block(cpu, access, address, size, value, unused):
        assert m.registers[0xB] == 0 and m.registers[0x16] == 3 and not m.registers[4]&1
        assert m.cmos[0x36] == 0xAB and cpu.reg_read(x.UC_X86_REG_CR0) & 0x40000000
        (reads if access == 16 else writes).append(address)
    m.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, block, begin=0x10000, end=0x107FF)
    conflicts = []
    m.cpu.hook_add(UC_HOOK_MEM_READ, lambda c,a,p,s,v,u: conflicts.append(p), begin=0x110000, end=0x1107FF)
    high_writes = []
    m.cpu.hook_add(UC_HOOK_MEM_WRITE, lambda c,a,p,s,v,u: high_writes.append(p), begin=0x100000, end=0xFFFFFF)
    m.call('chipset_visible_ram_test')
    assert reads and writes and not conflicts
    assert not high_writes and m.cpu.mem_read(0x10000, 0x800) == before
    assert m.text(5, 24, 5) == '16384'
    assert m.cmos[0x36] == 0xAB and m.cmos[0x37] == 0xA7
    m.call('chipset_timing_trial_finish')
    assert m.cmos[0x36] == 0 and m.cmos[0x37] == 0xA7
    rows.append({'fast_boot_selected_timings_l2_off_data_restored': True})
    print('PASS selected timings, L2 disabled, Fast Boot and successful trial', flush=True)

    # A direct DRAM read fault must still reach the existing retry.
    m = machine()
    m.cpu.mem_write(0x10000, before)
    patterned = [False]
    def pattern(cpu, access, address, size, value, unused):
        if value == 0x55AA55AA: patterned[0] = True
    def fault(cpu, access, address, size, value, unused):
        if patterned[0] and address == 0x10000:
            cpu.mem_write(address, b'\0\0\0\0')
    m.cpu.hook_add(UC_HOOK_MEM_WRITE, pattern, begin=0x10000, end=0x10003)
    m.cpu.hook_add(UC_HOOK_MEM_READ, fault, begin=0x10000, end=0x10003)
    until(m, 'chipset_visible_ram_test', 'controlled_defaults_restart')
    assert patterned[0] and m.cpu.mem_read(0x10000, 0x800) == before
    assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x1A and m.cmos[0x37] == 0
    assert m.registers[0xB] == 0x15 and m.registers[0x16] == 0
    m.call('settings_load')
    assert m.cpu.mem_read(m.base + 0x62, 1) == b'\0'
    m.call('chipset_timing_trial_begin')
    assert m.cmos[0x36] == 0x1A
    until(m, 'chipset_visible_ram_test', 'hard_halt')
    assert m.posts[-1] == 0xE7
    rows.append({'direct_read_fault_restores_data_and_timings_retries_once': True})
    print('PASS RAM fault recovery and second-failure guard', flush=True)

    # Normal reset consumes an unfinished trial before any memory/cache setup.
    m = machine()
    timing.restore(m)
    start = m.listing.symbol('.write_timing_reset_ready', 'startup')
    end = m.listing.symbol('.ras_reset_ready', 'startup')
    m.cpu.emu_start(0xF0000 + start, 0xF0000 + end, count=10000)
    assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x5A
    assert m.cpu.reg_read(x.UC_X86_REG_ESP) == 0x23456789
    m.call('settings_load')
    assert m.cpu.mem_read(m.base + 0x60, 24) == timing.DEFAULT[:2] + b'\0' + timing.DEFAULT[3:]
    m.call('chipset_post_recovery_notice')
    assert m.cmos[0x36] == 0x1A
    m.call('chipset_timing_trial_finish')
    assert m.cmos[0x36] == 0x1A
    # A complete verified save clears the retry guard; an invalid draft does not.
    m.cpu.mem_write(m.base + 0x260, timing.DEFAULT)
    m.cpu.mem_write(m.base + 0x26E, b'\xff')
    m.call('settings_save')
    assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1 and m.cmos[0x36] == 0x1A
    m.cpu.mem_write(m.base + 0x260, timing.DEFAULT)
    m.call('settings_save')
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1 and m.cmos[0x36] == 0
    rows.append({'hard_reset_pending_trial_safe_defaults_and_save_guard': True})
    print('PASS pending trial recovery and verified-save guard', flush=True)

    # L2 is off, so two MiB no longer needs a third MiB for eviction reads.
    m = machine(fast_boot=0)
    m.cpu.mem_write(m.base + 0xD0, struct.pack('<H', 1024))
    reads_above = []
    m.cpu.hook_add(UC_HOOK_MEM_READ, lambda c,a,p,s,v,u: reads_above.append(p), begin=0x100000, end=0x3FFFFF)
    m.call('chipset_visible_ram_test')
    assert reads_above and max(reads_above) < 0x200000
    rows.append({'full_test_two_mib_no_conflict_window': True})
    print('PASS uncached full test and detected-memory bounds', flush=True)

    for keys, setup in (([1], False), ([0xE0, 0x53], True)):
        m = machine()
        m.call('post_ui_begin')
        m.pending.extend(keys)
        m.call('chipset_visible_ram_test')
        assert m.cpu.mem_read(m.base + 0x50, 1) == b'\2'
        assert m.cpu.mem_read(0x41A, 2) == m.cpu.mem_read(0x41C, 2)
        assert m.cpu.mem_read(m.base + 0xF4, 1) == bytes((int(setup),))
        assert m.text(24, 3, 32).strip() == 'Del: Setup    Esc: Skip RAM test'
        if setup:
            until(m, 'post_early_setup', 'setup_main')
    m = machine()
    m.pending.extend([0x1D, 0x38, 0xE0, 0x53])
    try:
        m.call('chipset_visible_ram_test')
    except AssertionError:
        assert m.reset_pending and m.posts[-1] == 0x93, m.posts
    else:
        raise AssertionError('Ctrl+Alt+Del did not reset during the RAM test')
    assert m.cmos[0x36] == 0 and m.cmos[0x37] == 0 and m.cmos[0x69] == 0xC2
    m = machine()
    m.cpu.reg_write(x.UC_X86_REG_FS, 0x1234)
    untouched = bytes(m.cpu.mem_read(0x12340, 0x400))
    m.irq_scans([0x1D, 0x38, 0xE0, 0x53])
    assert m.reset_pending and m.cmos[0x36] == 0 and m.cmos[0x37] == 0
    assert m.cpu.mem_read(0x12340, 0x400) == untouched
    rows.append({'late_escape_delete_and_deliberate_reset': True})
    print('PASS Esc, Presario DEL-to-Setup and Ctrl+Alt+Del during testing', flush=True)

    m = machine()
    m.continue_reset = True
    m.stop_address = 0xF0000 + m.listing.symbol('setup_post_gate')
    m.cold_boot()
    assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x1A
    assert m.cpu.mem_read(m.base + 0x62, 1) == b'\0'
    m.open([1, 28])
    assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x1A
    rows.append({'hard_reset_reaches_and_opens_existing_setup': True})
    print('PASS full hard reset and Setup access after unfinished trial', flush=True)
    return rows


if __name__ == '__main__':
    rows = run()
    output = PORT / 'build/diagnostics/timing-recovery-checks.json'
    output.write_text(json.dumps(rows, indent=2) + '\n')
    print(f'{len(rows)} timing recovery groups passed')
