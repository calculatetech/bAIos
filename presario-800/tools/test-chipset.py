"""Exercise real chipset policy, CMOS, UI and RAM checks; capture real 86Box VGA."""
import argparse
import importlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import zlib

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_HOOK_INTR, UC_MEM_WRITE
from unicorn import x86_const as x

setup = importlib.import_module('test-setup')
ROOT = setup.ROOT
BUILD = setup.rtc.BUILD
NORMAL = bytes.fromhex('96160000883830000031285555555555aa00000000030003')
RECOVERY = bytes.fromhex('a6160000883830000031685555555555aa00000000030003')

def saved_policy(model):
    if model.cmos[0x69] == 0xD2:
        return RECOVERY
    if model.cmos[0x69] not in (0xC1, 0xC2):
        return NORMAL
    policy = bytearray(model.cmos[0x6B:0x80]+model.cmos[0x33:0x36])
    if model.cmos[0x69] == 0xC1:
        policy[10] |= 0xA0
        policy[23] |= 2
    return bytes(policy)

C, U, SIZE = 0x60, 0x260, 24


class Chipset(setup.Setup):
    def __init__(self, segment=0x9FC0):
        super().__init__(segment=segment)
        self.cpu.mem_map(0x200000, 6 * 1024 * 1024)
        self.chipset.update({4: 0x56, 6: 4, 7: 0xC8, 0xC: 0xA8, 0x24: 0x90})
        self.reg_writes = []
        self.a20 = 0
        self.fast = None
        self.warm = False
        self.dma_masks = []

    def interrupt(self,cpu,vector,unused):
        if vector==0x10 and cpu.reg_read(x.UC_X86_REG_AH)==2:
            cpu.mem_write(0x450,struct.pack('<H',cpu.reg_read(x.UC_X86_REG_DX)))
        if vector==0x10 and cpu.reg_read(x.UC_X86_REG_AH)==0x0E:
            col,row=bytes(cpu.mem_read(0x450,2))
            char=cpu.reg_read(x.UC_X86_REG_AL)
            if char==13: col=0
            elif char==10: row+=1
            else:
                cpu.mem_write(0xB8000+(row*80+col)*2,bytes((char,7)))
                col+=1
            if col==80: col=0;row+=1
            if row>=25:
                cpu.mem_write(0xB8000,bytes(cpu.mem_read(0xB8000+160,24*160)))
                cpu.mem_write(0xB8000+24*160,b' \x07'*80)
                row=24
            cpu.mem_write(0x450,bytes((col,row)))
        return super().interrupt(cpu,vector,unused)

    def port_in(self, cpu, port, size, unused):
        if getattr(self, 'starting', False):
            if port == 0x71 and not self.delayed:
                assert cpu.reg_read(x.UC_X86_REG_CX) == 0, 'stackless CMOS settle loop did not finish'
                self.delayed = True
        if getattr(self, 'starting', False) and port in (0x3BA, 0x3DA):
            return 0  # Opaque VGA status while production POST blanks video.
        if port == 0x92:
            return self.a20
        if port == 0x64 and self.warm:
            return super().port_in(cpu, port, size, unused) | 4
        return super().port_in(cpu, port, size, unused)

    def port_out(self, cpu, port, size, value, unused):
        if port == 0x71 and getattr(self, 'starting', False) and not self.delayed:
            assert cpu.reg_read(x.UC_X86_REG_CX) == 0, 'stackless CMOS settle loop did not finish'
            self.delayed = True
        if port in (0x0D, 0xDA):
            self.dma_masks.append(port)
        elif getattr(self, 'starting', False) and port in (0x3B8, 0x3D8, 0x3C0):
            pass  # Opaque VGA blanking ports.
        elif port == 0xED:
            self.reg_writes.append((self.chipset_index, value))
            self.chipset[self.chipset_index] = value
        elif port == 0x92:
            assert not value & 1
            self.a20 = value
        elif port in (0xF4, 0xF5):
            self.fast = port == 0xF5
        else:
            super().port_out(cpu, port, size, value, unused)

    def record(self, draft=False):
        return bytes(self.cpu.mem_read(self.base + (U if draft else C), SIZE))

    def draft(self, data):
        self.cpu.mem_write(self.base + U, bytes(data))

    def startup(self, reset=False, before_notice=False, entry=None, through_visible=False,
                halt=False, before_restart=False, through_gate=False, expected_record=None,
                production_controls=False, through_boot=False, stop_at_notice=False, boot_failure=False):
        # Continue the real entry; only retained video/peripheral mechanics are opaque.
        self.starting = True
        if (reset or entry == 'chipset_late_cache') and not getattr(self, 'reset_ram', False):
            self.cpu.mem_map(0x800000, 24 * 1024 * 1024)
            self.reset_ram = True
        self.cpu.hook_del(self.code_hook)
        terminal = ('post_notice_wait' if stop_at_notice else 'boot_retry' if boot_failure else 'boot_sector' if through_boot else '.controlled_restart' if before_restart else 'hard_halt' if halt else
                    'chipset_post_recovery_notice' if before_notice else
                    'chipset_late_cache' if through_gate else
                    'post_clock_alert' if through_visible else 'chipset_visible_ram_test')
        traced = ('init_memory', 'chipset_memory_prepare', 'memory_interleave_options',
                  'chipset_interleave_policy', 'chipset_ram_test', 'shadow_system_bios',
                  'settings_load', 'chipset_apply', 'publish_memory_cmos',
                  'chipset_post_recovery_notice', 'chipset_visible_ram_test',
                  'controlled_defaults_restart', '.controlled_restart', 'post_clock_alert', 'setup_post_gate',
                  * (('post_numlock_apply', 'post_keyboard_presence', 'init_keyboard',
                      'arm_keyboard_runtime', 'init_floppy', 'post_floppy_seek', 'ata_detect_primary', 'int19', 'int18',
                      'init_external_cache', * (('init_peripherals',) if getattr(self, 'publish_peripherals', False) else ()),
                      'post_notice_wait', 'setup_main', 'chipset_late_cache', 'option_rom_discovery', 'post_debug_summary')
                     if production_controls else ()), terminal)
        opaque = ('validate_vga_image', 'init_pic_pit', 'init_rtc', 'init_superio',
                  'init_at_prerequisites', 'init_keyboard', 'arm_keyboard_runtime',
                  'post_numlock_apply', 'post_keyboard_presence',
                  'init_peripherals', 'init_floppy', 'post_floppy_seek', 'ata_detect_primary',
                  'init_mouse', 'init_fpu', 'post_success_tone')
        if production_controls:
            opaque = tuple(n for n in opaque if n not in ('init_keyboard', 'arm_keyboard_runtime',
                                                          'post_numlock_apply', 'post_keyboard_presence',
                                                          'init_floppy', 'post_floppy_seek', 'ata_detect_primary', 'init_fpu'))
        if getattr(self, 'publish_peripherals', False):
            opaque = tuple(n for n in opaque if n != 'init_peripherals')
        native_owners = getattr(self, 'startup_native_owners', ())
        opaque = tuple(n for n in opaque if n not in native_owners)
        traced += native_owners
        hops, hooks, alert_hook = [], [], [None]
        if production_controls:
            # Hook actual HLT sites and the FDC IRQ poll, not every RAM-test instruction.
            rom = bytes(self.cpu.mem_read(0xF0000, 65536))
            events = [0xF0000+i for i, byte in enumerate(rom) if byte == 0xF4]
            events.append(0xF0000+setup.rtc.symbol('fdc_wait_irq')+5)  # Poll after STI enables IRQ6.
            for address in events:
                hooks.append(self.cpu.hook_add(UC_HOOK_CODE, self.code, None, address, address))
        def observe(cpu, address, size, unused):
            name = entries[address]
            if name == '.controlled_restart':
                self.restarts = getattr(self, 'restarts', 0) + 1
                if alert_hook[0] is not None:
                    self.cpu.hook_del(alert_hook[0])
                    hooks.remove(alert_hook[0])
                    alert_hook[0] = None
            if name in traced:
                hops.append(name)
                if name not in ('controlled_defaults_restart', '.controlled_restart', 'post_clock_alert', 'hard_halt', 'boot_sector', 'int19', 'int18', 'halt_forever', 'post_debug_summary', 'option_rom_discovery', 'boot_retry') and 'init_memory' in hops:
                    assert self.chipset[0x19] == 0, (name, 'L2 enabled before Setup')
                if name == 'chipset_memory_prepare':
                    assert self.dma_masks[-2:] == [0x0D, 0xDA]
                if name == 'shadow_system_bios':
                    assert bytes(cpu.mem_read(0x9FC00, 1)) == b'\x01'
                    assert bytes(cpu.mem_read(0x9FC60, SIZE)) == bytes(SIZE), 'EBDA must be rebuilt'
                if getattr(self, 'startup_observer', None):
                    self.startup_observer(self, name)
                if name == terminal and (entry != terminal or getattr(self, 'restarts', 0)):
                    cpu.emu_stop()
                elif name == 'post_clock_alert':
                    self.code(cpu, address, size, unused)
            elif name in opaque or name == 'vga':
                sp = cpu.reg_read(x.UC_X86_REG_SP)
                ip = int.from_bytes(cpu.mem_read(sp, 2), 'little')
                if name == 'vga':
                    cpu.mem_write(0x42, b'\x00\xc0')
                    cpu.reg_write(x.UC_X86_REG_CS, int.from_bytes(cpu.mem_read(sp+2, 2), 'little'))
                    sp += 2
                cpu.reg_write(x.UC_X86_REG_SP, sp+2)
                cpu.reg_write(x.UC_X86_REG_IP, ip)
                cpu.reg_write(x.UC_X86_REG_EFLAGS, cpu.reg_read(x.UC_X86_REG_EFLAGS) & ~1)
        entries = {(0x7C00 if name == 'boot_sector' else 0xF0000+setup.rtc.symbol(name)): name for name in (*traced, *opaque)}
        entries[0xC0003] = 'vga'
        for address in entries:
            hooks.append(self.cpu.hook_add(UC_HOOK_CODE, observe, None, address, address))
        start = 0xF0000+setup.rtc.symbol(entry) if entry else 0xFFFF0 if reset else self.warm_entry
        self.cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
        if not entry:
            self.cpu.reg_write(x.UC_X86_REG_CR0, 0x60000010)
        else:
            self.cpu.reg_write(x.UC_X86_REG_DS, 0)
            self.cpu.reg_write(x.UC_X86_REG_ES, 0)
            self.cpu.reg_write(x.UC_X86_REG_FS, self.segment)
            self.cpu.reg_write(x.UC_X86_REG_SS, 0)
            self.cpu.reg_write(x.UC_X86_REG_SP, 0x7000)
        self.cpu.reg_write(x.UC_X86_REG_EFLAGS, 2)
        if entry == 'post_clock_alert':
            # Real keyboard/RTC stimulus for the warning; other mechanics stay opaque.
            alert_hook[0] = self.cpu.hook_add(UC_HOOK_CODE, self.code)
            hooks.append(alert_hook[0])
        try:
            self.cpu.emu_start(start, 0xFFFFFF, count=100000000)
            assert hops[-1:] == [terminal], hops[-64:]
            self.startup_hops = hops
            if halt or before_restart or stop_at_notice or boot_failure:
                return
            sequence = list(traced[:6])
            assert any(hops[i:i+6] == sequence for i in range(len(hops)-5)), hops
            tail = ['settings_load', *(['post_numlock_apply', 'post_keyboard_presence'] if production_controls else []),
                    'chipset_apply', 'publish_memory_cmos', 'chipset_post_recovery_notice']
            if not before_notice:
                tail.append('chipset_visible_ram_test')
                if through_visible and not through_gate:
                    tail.append(terminal)
            # Early Setup or an acknowledged keyboard notice may interpose
            # before chipset application. Their real hops remain in the trace.
            post_tail = [name for name in hops if name not in ('setup_main', 'post_notice_wait')]
            assert any(post_tail[i:i+len(tail)] == tail for i in range(len(post_tail)-len(tail)+1)), hops
            if through_gate:
                assert hops[-2:] == ['setup_post_gate', 'chipset_late_cache']
                assert bytes(self.cpu.mem_read(0x49E, 1)) == b'\x02', 'actual final Setup gate did not close'
            if through_boot:
                assert hops[-1] == 'boot_sector' and hops[-2] in ('int19', 'int18'), hops
                assert self.cpu.reg_read(x.UC_X86_REG_DL) == 0x80
            expected = saved_policy(self) if expected_record is None else expected_record
            assert self.record() == expected
            exposed = bytes(self.cpu.mem_read(self.base+0xD0, 2))
            assert bytes(self.cmos[0x17:0x19]) == bytes(self.cmos[0x30:0x32]) == exposed
        finally:
            for hook in hooks:
                self.cpu.hook_del(hook)
            self.starting = False
            self.code_hook = self.cpu.hook_add(UC_HOOK_CODE, self.code)


def profiles():
    enter = [0x50]*4 + [28, 28]  # Real Setup navigation to the RAM group.
    def choice(current, selected):
        return [28] + [0x48]*current + [0x50]*selected + [28]
    def stored(m):
        return bytes(m.cmos[0x6B:0x80]+m.cmos[0x33:0x36])
    # Independent values from the supplied profile table, not the ROM lookup.
    table = ((0x04, 0x12, 0x12, 0x16), (0x16, 0x16, 0x16, 0x26))
    choices_seen, help_seen = set(), set()
    for mode in (0, 1):
        for clock in (0, 1):
            for speed in (0, 1, 2):
                m = Chipset()
                def observe(model):
                    if model.cpu.mem_read(model.base+0x278, 1) != b'\x01':
                        return
                    draft = model.record(True)
                    draft_mode, draft_speed, draft_clock = draft[10] >> 6, (draft[10] >> 4)&3, (draft[23] >> 1)&1
                    if draft_mode < 2:
                        assert draft[0]&0x3F == table[draft_mode][draft_clock*2 + (draft_speed != 1)], 'profile metadata and raw draft diverged before Save'
                    field = model.cpu.mem_read(model.base+0xF7, 1)[0]
                    if field < 3:
                        choices_seen.add((field, model.text((5,6,7)[field],49,28).strip()))
                        help_seen.add(model.text(18,25,24).strip())
                m.observer = observe
                m.open(enter + choice(1,clock) + [0x3B,1,0x50] +
                       choice(2,speed) + [0x3B,1,0x50] + choice(0,mode) + [0x3B,1,0x44,28])
                low = table[mode][clock*2 + (speed != 1)]
                expected = bytearray(NORMAL)
                expected[0] = 0x80 | low
                expected[10] = 8 | (speed << 4) | (mode << 6)
                expected[23] = 1 | (clock << 1)
                assert m.warm and m.cmos[0x69] == 0xC2
                assert stored(m) == expected and not (low & 1), (mode,clock,speed,stored(m).hex())
                assert (sum(expected)+m.cmos[0x6A]+0xC2)&255 == 0
                m.startup()
                assert m.record() == expected and m.chipset[1] == expected[0]
                assert m.chipset[4] == 0x16 and m.chipset[0x19] == 0 and m.fast
                assert m.chipset[0x24] & 0x0C == 8, 'metadata leaked into XCTL'
    assert choices_seen >= {(0,'25 MHz'),(0,'33 MHz'),(1,'Unknown'),(1,'60 ns'),(1,'70 ns'),
                            (2,'Normal'),(2,'Compatibility')}, choices_seen
    assert help_seen >= {'Timing Profile Clock','DRAM Speed','Memory Timing'}, help_seen
    print('Profiles: all 12 identities / Unknown alias via Setup popup/F1 -> verified C2 save -> warm POST -> exact hardware tuple and unrelated controls: PASS', flush=True)

    m = Chipset()
    m.observer = observe
    m.open(enter + [0x50]*2 + choice(0,2) + [0x3B,1,0x44,28])
    expected = bytearray(NORMAL)
    expected[10] = 0xA8
    assert stored(m) == expected and (2,'Manual') in choices_seen
    m.startup()
    assert m.record() == expected and m.chipset[1] == 0x96
    print('Profiles: explicit Manual popup selection preserves raw tuple through verified save and POST: PASS', flush=True)

    # Each raw control must independently select Manual before Save.
    for field, raw in ((3,0x56),(4,0x86),(5,0x92),(6,0x95)):
        m = Chipset()
        expected = bytearray(NORMAL)
        expected[0], expected[10] = raw, 0xA8
        seen = []
        def isolated_edit(model):
            if (model.cpu.mem_read(model.base+0x278,1) == b'\x01' and
                    model.record(True)[0] == raw):
                assert model.record(True) == expected, (field,model.record(True).hex())
                seen.append(True)
        m.observer = isolated_edit
        m.open(enter + [0x50]*2 + choice(0,2) + [0x50]*(field-2) + [0x4B,0x44,28])
        assert seen and m.cmos[0x69] == 0xC2 and stored(m) == expected
        m.startup()
        assert m.record() == expected and m.chipset[1] == raw
    print('Profiles: isolated cycle-start/precharge/RCD/CAS edits -> immediate Manual -> verified C2 save -> exact warm hardware tuple: PASS', flush=True)

    # Select the 2T-write code through the actual popup, then keep it through L2.
    m = Chipset()
    expected = bytearray(NORMAL)
    expected[0], expected[10] = 0x97, 0xA8
    seen = set()
    def write_width(model):
        if model.text(8,26,9) == 'CAS Width':
            assert model.text(15,26,7) == '  2T/2T'
            assert model.text(15,40,5) == '3T/2T'
            seen.add('popup')
        if model.text(13,49,13) == '2T/2T | 3T/2T':
            assert model.record(True) == expected
            seen.add('selected')
    m.observer = write_width
    m.open(enter + [0x50]*2 + choice(0,2) + [0x50]*4 + choice(2,3) + [0x44,28])
    assert seen == {'popup','selected'} and m.cmos[0x69] == 0xC2 and stored(m) == expected
    m.startup()
    assert m.record() == expected and m.chipset[1] == 0x97
    m.call('chipset_late_cache',flags=2)
    assert m.record() == expected and m.chipset[1] == 0x97
    print('Profiles: CAS11 popup 2T/2T | 3T/2T -> Manual -> verified save -> warm hardware 97h -> late cache preserves 2T write: PASS', flush=True)

    # Manual preserves raw timings while metadata changes, and Auto restores a tuple.
    m = Chipset()
    m.open([0x43,28] + enter + [0x50]*2 + choice(0,2) + [0x50,0x4B] + [0x50]*3 + [0x4B] +
           [0x48]*6 + [0x4B,0x50,0x4B,0x44,28])
    expected = bytearray(NORMAL)
    expected[0], expected[10], expected[23] = 0x55, 0x98, 1
    assert stored(m) == expected, stored(m).hex()
    m.startup()
    assert m.record() == expected and m.chipset[1] == 0x55
    # 25/60 Manual -> Auto, retaining cycle start and all unrelated data.
    m.warm = False
    m.open(enter + [0x50]*2 + [0x4D,0x44,28])
    expected[0], expected[10] = 0x44, 0x18
    assert stored(m) == expected
    m.startup()
    assert m.record() == expected and m.chipset[1] == 0x44
    print('Profiles: F9 then raw edit selects Manual; Manual metadata preserves raw; Auto applies tuple retaining cycle start through F10/POST: PASS', flush=True)

    for fast in (0,1):
        legacy = bytearray(NORMAL)
        legacy[0], legacy[10], legacy[23] = 0x54, 0x0A, fast
        m = Chipset()
        m.cmos[0x69], m.cmos[0x6A] = 0xC1, -(0xC1+sum(legacy))&255
        m.cmos[0x6B:0x80], m.cmos[0x33:0x36] = legacy[:21], legacy[21:]
        before = bytes(m.cmos)
        migrated = bytearray(legacy)
        migrated[10] |= 0xA0
        migrated[23] |= 2
        m.startup()
        assert m.record() == migrated and m.chipset[1] == 0x54 and m.fast == bool(fast)
        assert bytes(m.cmos[0x69:]) == before[0x69:] and bytes(m.cmos[0x33:0x36]) == before[0x33:0x36]
        m.warm = False
        m.open([0x44,28])
        assert m.cmos[0x69] == 0xC2 and stored(m) == migrated
        m.startup()
        assert m.record() == migrated and m.fast == bool(fast)
    print('Profiles: custom C1 -> Manual/70/33 in RAM, CMOS unchanged; verified C2 migration keeps raw timings and CPU bit0: PASS', flush=True)
    # Full startup rejects reserved selectors, C1 reserved bits, and both automatic lies.
    for signature,index,value in ((0xC1,10,0x28),(0xC1,23,3),(0xC2,10,0xE8),
                                  (0xC2,10,0x38),(0xC2,23,7),(0xC2,0,0x94),
                                  (0xC2,10,0x68)):
        m = Chipset()
        bad = bytearray(NORMAL)
        bad[index] = value
        m.cmos[0x69],m.cmos[0x6A] = signature,-(signature+sum(bad))&255
        m.cmos[0x6B:0x80],m.cmos[0x33:0x36] = bad[:21],bad[21:]
        before = bytes(m.cmos)
        # Execute warm POST through rebuild/apply, before the ordinary CMOS warning.
        m.startup(expected_record=NORMAL)
        assert m.record() == NORMAL and m.chipset[1] == 0x96, (signature,index,value)
        assert bytes(m.cmos[0x69:]) == before[0x69:] and bytes(m.cmos[0x33:0x36]) == before[0x33:0x36]
        m.call('chipset_apply',flags=2)
        assert m.chipset[1] == 0x96 and m.chipset[0x24]&0x0C == 8
    print('Profiles: checksum-valid reserved/legacy-mask/Auto-Compatibility inconsistency rejected before hardware apply: PASS', flush=True)

    # A checksum fault must reject a custom policy through the actual startup.
    for corrupt in (False,True):
        m = Chipset()
        policy = bytearray(NORMAL)
        policy[0], policy[10] = 0x54, 0xA8
        m.draft(policy)
        m.call('chipset_settings_save')
        assert m.cmos[0x69] == 0xC2
        if corrupt:
            m.cmos[0x6A] ^= 1
        before = bytes(m.cmos)
        expected = NORMAL if corrupt else policy
        m.startup(expected_record=expected)
        assert m.record() == expected and m.chipset[1] == (0x96 if corrupt else 0x54)
        assert bytes(m.cmos[0x69:]) == before[0x69:] and bytes(m.cmos[0x33:0x36]) == before[0x33:0x36]
    print('Profiles: same custom C2 with valid/corrupt checksum -> actual startup -> custom54h or NORMAL96h hardware; saved bytes unchanged: PASS', flush=True)

    # Real comparison failure commits D2, which survives unsaved F9/F10/discard.
    for commit in ('discard','Auto','Manual'):
        m, _ = recovery_model()
        hit, hooks = ram_faults(m,['early'])
        m.cpu.reg_write(x.UC_X86_REG_DX,7168)
        m.startup(entry='chipset_ram_test')
        for hook in hooks: m.cpu.hook_del(hook)
        assert hit and m.cmos[0x69] == 0xD2 and m.record() == RECOVERY and m.chipset[1] == 0xA6
        saved = stored(m)
        m.warm = False
        if commit == 'discard':
            m.open([0x43,28,0x44,1,1,28])
            assert not m.warm and m.cmos[0x69] == 0xD2 and stored(m) == saved
            m.startup(reset=True)
            assert m.record() == RECOVERY and m.chipset[1] == 0xA6 and m.cmos[0x69] == 0xD2
        else:
            script = [0x43,28] + (enter+[0x50]*2+choice(0,2)+[0x50,0x4B] if commit == 'Manual' else []) + [0x44,28]
            m.open(script)
            assert m.cmos[0x69] == 0xC2
            expected = bytearray(NORMAL)
            if commit == 'Manual': expected[0],expected[10] = 0x56,0xA8
            assert stored(m) == expected
            m.startup()
            assert m.record() == expected and m.chipset[1] == expected[0]
    print('Profiles: actual RAM failure D2 -> Setup F9/cancel F10/discard -> next reset retains A6; verified Auto/Manual saves replace D2 with C2: PASS', flush=True)

    class FailedRecoverySave(Chipset):
        def port_in(self, cpu, port, size, unused):
            value = super().port_in(cpu, port, size, unused)
            if port == 0x71 and self.index == 0x6A and getattr(self, 'fail_save', False):
                return value ^ 1  # Existing RTC verification-mismatch stimulus.
            return value
    m = FailedRecoverySave()
    hit, hooks = ram_faults(m,['early'])
    m.cpu.reg_write(x.UC_X86_REG_DX,7168)
    m.startup(entry='chipset_ram_test')
    for hook in hooks: m.cpu.hook_del(hook)
    assert hit and m.cmos[0x69] == 0xD2
    m.draft(NORMAL)
    m.writes.clear()
    m.fail_save = True
    m.call('chipset_settings_save')
    assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1 and m.cmos[0x69] == 0xD2
    assert all(value == 0xD2 for index,value in m.writes if index == 0x69)
    m.fail_save = False
    m.startup(reset=True)
    assert m.cmos[0x69] == 0xD2 and m.record() == RECOVERY and m.chipset[1] == 0xA6
    print('Profiles: actual failure D2 -> RTC save verification mismatch -> D2 marker retained throughout -> next POST Compatibility/A6: PASS', flush=True)

    class FailedCompleteSave(Chipset):
        def port_in(self, cpu, port, size, unused):
            value = super().port_in(cpu, port, size, unused)
            if (port == 0x71 and self.index == 0x3E and getattr(self, 'fail_save', False)
                    and (0x38, 66) in self.writes):
                return value ^ 255  # Existing base-settings verification mismatch.
            return value
    for recovering in (False, True):
        for manual in (False, True):
            m = FailedCompleteSave()
            if recovering:
                hit, hooks = ram_faults(m, ['early'])
                m.cpu.reg_write(x.UC_X86_REG_DX, 7168)
                m.startup(entry='chipset_ram_test')
                for hook in hooks: m.cpu.hook_del(hook)
                assert hit and m.cmos[0x69] == 0xD2
            else:
                m.draft(NORMAL)
                m.call('chipset_settings_save')
                m.startup()
            active = RECOVERY if recovering else NORMAL
            attempted = bytearray(NORMAL)
            if manual: attempted[0], attempted[10] = 0x56, 0xA8
            seen = []
            def failed_save_observer(model):
                if 'CMOS verification failed.' in model.text(19, 23, 46):
                    assert not model.warm and model.record() == active
                    assert model.cmos[0x69] == (0xD2 if recovering else 0xC2)
                    assert stored(model) == attempted
                    assert model.text(20, 49, 8) == '3E 02 FD'
                    seen.append(True)
                    model.observer = None
                    model.script = ([1, 1, 1, 28] if manual else [1, 28])  # Field/sidebar discard.
            m.warm = False
            m.writes.clear()
            m.fail_save = True
            m.observer = failed_save_observer
            m.open([0x43, 28] + (enter + [0x50]*2 + choice(0,2) + [0x50,0x4B] if manual else []) + [0x44, 28])
            assert seen and not m.warm
            m.fail_save = False
            m.startup(reset=True)
            expected = RECOVERY if recovering else attempted
            assert m.record() == expected and m.chipset[1] == expected[0]
            assert m.cmos[0x69] == (0xD2 if recovering else 0xC2)
    print('Profiles: real F10 base verification failure -> visible error -> discard -> reset; D2 retains A6, ordinary C2 stays ordinary: PASS', flush=True)

    # CAS01 display must remain the actual VL82C481 table, without raw correction.
    for l2,hspd in ((False,False),(True,False),(False,True),(True,True)):
        m = Chipset()
        policy = bytearray(NORMAL)
        policy[0],policy[10] = 0x95,0xAA if hspd else 0xA9
        policy[9] = 0x31 if l2 else 0x30
        m.draft(policy)
        m.call('chipset_settings_save')
        m.call('settings_load')
        seen=[]
        def cas(model):
            if model.text(8,26,9) == 'CAS Width':
                assert model.text(13,26,7) == '1.5T/1T'
                assert model.text(13,40,5) == '2T/1T'
                assert 'L2/HSPD uses right widths.' in model.text(20,25,53) or not model.text(18,25,9) == 'CAS Width'
                seen.append(True)
        m.observer=cas
        m.open(enter+[0x50]*6+[28,0x3B,1,28,0x44,28])
        assert seen and stored(m) == policy
        m.startup()
        assert m.chipset[1] == 0x95 and m.record() == policy
        m.call('chipset_late_cache',flags=2)
        assert m.chipset[1] == 0x95 and m.record() == policy
        assert bool(m.chipset[0x24]&0x40) == hspd
    print('Profiles: CAS01 1.5/1 -> 2/1 for L2-only/HSPD-only; popup/help, saved raw and late cache do not add CAS clocks: PASS', flush=True)


def profile_locks():
    enter = [0x50]*4 + [28,28]
    locked = (3,4,5,6,7)
    for mode, raw, metadata in ((0,0x96,0x28),(1,0xA6,0x68),(3,0x95,0xE8),(2,0x96,0xA8)):
        m = Chipset()
        expected = bytearray(NORMAL)
        expected[0], expected[10] = raw, metadata
        seen, changed, pages = set(), set(), set()
        def observe(model):
            if model.cpu.mem_read(model.base+0x278,1) != b'\x01': return
            field = model.cpu.mem_read(model.base+0xF7,1)[0]
            draft = model.record(True)
            if mode == 2:
                if field not in locked: return
                seen.add(field)
                assert draft[10]&0xC0 == 0x80
                if draft != expected: changed.add(field)
            else:
                if field < 2 or draft[10]>>6 != mode: return
                assert field not in locked, (mode,field)
                assert draft == expected, (mode,field,draft.hex())
                if model.text(8,26,12) == 'SELECT VALUE' or model.text(18,25,13) == 'Memory Timing': return
                page = 0 if field < 8 else 1
                pages.add(page)
                for row in ((10,11,12,13,14) if page == 0 else ()):
                    assert model.cpu.mem_read(0xB8000+row*160+49*2+1,1) == b'\x08', (mode,page,row)
                if page == 1:
                    for row in (5,6,7,11):
                        assert model.cpu.mem_read(0xB8000+row*160+49*2+1,1) != b'\x08', (mode,page,row)
                seen.add(field)
        m.observer = observe
        script = enter+[0x50]*2+[28]+[0x50]*mode+[28]
        if mode == 2:
            current = 2
            for field in locked:
                script += [0x50]*(field-current)+[0x4B,0x4D]
                current = field
        else:
            script += [0x3B,1]+[0x50]*6+[0x48,0x48,0x51,0x49]
        m.open(script+[0x44,28])
        if mode == 2: assert seen == changed == set(locked)
        else: assert seen >= {2,8,9,10,11,12,13} and pages == {0,1}
        assert m.warm and m.cmos[0x69] == 0xC2
        assert bytes(m.cmos[0x6B:0x80]+m.cmos[0x33:0x36]) == expected
        m.startup()
        assert m.record() == expected and m.chipset[1] == raw
        m.call('chipset_late_cache',flags=2)
        assert m.chipset[1] == raw
    print('Presets: access timings gray08/unselectable, refresh selectable; Manual edits; F10/reset/late-cache retains tuples: PASS',flush=True)

    # Refresh edits through both arrows and popups retain every profile and persist.
    for mode,raw,metadata in ((0,0x96,0x28),(1,0xA6,0x68),(3,0x95,0xE8),(2,0x96,0xA8)):
        m = Chipset()
        expected = bytearray(NORMAL)
        expected[0],expected[10],expected[2] = raw,metadata,0x07
        expected[1] = 0x06  # RAS Timeout enabled, other RAM configuration unchanged.
        script = enter+[0x50]*2+[28]+[0x50]*mode+[28,0x51,0x4D,0x50,28,0x50,28,0x50,0x4D,0x50,0x50,28,0x48,28,0x44,28]
        m.open(script)
        assert m.warm and m.cmos[0x69] == 0xC2
        assert bytes(m.cmos[0x6B:0x80]+m.cmos[0x33:0x36]) == expected
        m.startup()
        assert m.record() == expected and m.chipset[1] == raw
        m.call('chipset_late_cache',flags=2)
        assert m.record() == expected and m.chipset[1] == raw
        assert m.chipset[4]&0x17 == 0x06 and m.chipset[5]&0xEF == 0x07
    print('Refresh and RAS Timeout edit with arrows/popup, retain all four modes, survive F10/reset/late-cache: PASS',flush=True)

    m = Chipset()
    modes = []
    def mode_arrows(model):
        if model.cpu.mem_read(model.base+0x278,1) != b'\x01': return
        if model.cpu.mem_read(model.base+0xF7,1) != b'\x02': return
        mode = model.record(True)[10]>>6
        if not modes or modes[-1] != mode: modes.append(mode)
    m.observer = mode_arrows
    m.open(enter+[0x50]*2+[0x4B]+[0x4D]*4+[0x44,28])
    assert modes[-5:] == [3,0,1,2,3], modes
    expected = bytearray(NORMAL)
    expected[0],expected[10] = 0x95,0xE8
    m.startup()
    assert m.record() == expected
    print('Timing arrows follow Fast/Normal/Compatibility/Manual, wrap correctly and retain stable CMOS meanings: PASS',flush=True)

    for clock in (0,1):
        for speed in (0,1,2):
            m = Chipset()
            seen = []
            def popup(model):
                if model.text(8,26,12) == 'SELECT VALUE' and model.cpu.mem_read(model.base+0xF7,1) == b'\x02':
                    available = (clock,speed) != (0,1)
                    labels = ('Fast','Normal','Compatibility','Manual') if available else ('Normal','Compatibility','Manual','')
                    assert tuple(model.text(row,26,13).strip() for row in range(10,14)) == labels
                    seen.append(True)
            m.observer = popup
            available = (clock,speed) != (0,1)
            script = enter+[28]+[0x48]+[0x50]*clock+[28,0x50,28]+[0x48]*2+[0x50]*speed+[28,0x50,28]
            script += ([0x50]*3+[28] if available else [1])+[0x44,28]
            m.open(script)
            assert seen and m.cmos[0x69] == 0xC2
            expected = bytearray(NORMAL)
            normal = (0x04,0x12,0x12,0x16)[clock*2+(speed != 1)]
            expected[0] = 0x80 | (normal-1 if available else normal)
            expected[10] = 8 | (speed<<4) | (0xC0 if available else 0)
            expected[23] = 1 | (clock<<1)
            m.startup()
            assert m.record() == expected and m.chipset[1] == expected[0]
            m.call('chipset_late_cache',flags=2)
            assert m.chipset[1] == expected[0]
    print('Fast popup offered wherever Normal non-L2 CAS can be matched with L2; 25MHz/60ns excluded: PASS',flush=True)

    for field in (0,1):
        m = Chipset()
        fast = bytearray(NORMAL)
        fast[0],fast[10] = 0x95,0xE8
        m.draft(fast)
        m.call('chipset_settings_save')
        m.startup()
        m.warm = False
        m.open(enter+[0x50]*field+[0x4B,0x44,28])
        expected = bytearray(NORMAL)
        expected[0],expected[10] = 0x91,0xE8
        if field == 0: expected[23] = 1
        else: expected[10] = 0xD8
        m.startup()
        assert m.record() == expected and m.chipset[1] == 0x91
    # Changing both inputs to 25MHz/60ns leaves Fast because L2 cannot reach 1T.
    m = Chipset()
    fast = bytearray(NORMAL)
    fast[0],fast[10] = 0x95,0xE8
    m.draft(fast)
    m.call('chipset_settings_save')
    m.startup()
    m.warm = False
    m.open(enter+[0x4B,0x50,0x4B,0x44,28])
    expected = bytearray(NORMAL)
    expected[0],expected[10],expected[23] = 0x84,0x18,1
    m.startup()
    assert m.record() == expected and m.chipset[1] == 0x84
    for clock,speed in ((0,1),(0,2),(1,1)):
        m = Chipset()
        bad = bytearray(NORMAL)
        bad[0],bad[10],bad[23] = 0x95,0xC8|(speed<<4),1|(clock<<1)
        m.cmos[0x69],m.cmos[0x6A] = 0xC2,-(0xC2+sum(bad))&255
        m.cmos[0x6B:0x80],m.cmos[0x33:0x36] = bad[:21],bad[21:]
        m.startup(expected_record=NORMAL)
        assert m.record() == NORMAL and m.chipset[1] == 0x96
    print('Fast retained for eligible clock/speed changes, Normal at 25MHz/60ns; unsupported or incoherent Fast records rejected at startup: PASS',flush=True)


def cmos_and_policy():
    for segment in (0x9FC0, 0x8FC0):
        m = Chipset(segment)
        baseline = m.record()
        assert baseline.hex() == NORMAL.hex()
        if segment==0x9FC0:  # Early map policy runs before EBDA relocation.
            m.cpu.reg_write(x.UC_X86_REG_AX,5)
            m.call('chipset_interleave_policy')
            assert m.cpu.reg_read(x.UC_X86_REG_CL)==0x16
        assert baseline[4]&8 and baseline[9]&1, 'Both caches requested enabled'
        assert baseline[0]&0x3F==0x16 and baseline[10]&8
        m.draft(baseline)
        m.call('chipset_settings_save')
        assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
        assert m.cmos[0x69] == 0xC2
        original = bytes(m.cmos)
        m.call('chipset_settings_load')
        assert m.record() == baseline and bytes(m.cmos) == original
        custom = bytearray(baseline)
        custom[0] = 0x54
        custom[1] = 0x12  # No interleave,24mA MA/RAMW, page mode.
        custom[2], custom[3] = 0xA7, 0x99
        custom[4], custom[5], custom[6] = 0xAF, 0x96, 0x7B
        custom[7], custom[8], custom[10], custom[23] = 0xAD, 2, 0x0A, 0
        custom[10] = (custom[10] & 0x3F) | 0x80
        m.draft(custom)
        m.call('chipset_settings_save')
        assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
        m.call('chipset_settings_load')
        assert m.record() == custom
        m.chipset[8], m.chipset[9] = 0x40, 0xB0
        m.call('chipset_apply', flags=2)
        assert m.chipset[1] == 0x54
        assert m.chipset[4] == 0x52, 'interleave mapping is not a late register toggle'
        assert m.chipset[6] == 0x9D and m.chipset[0xC] == 0xAA
        assert m.chipset[7] == 0xEF and m.chipset[0x24] == 0xD8
        assert (m.chipset[5], m.chipset[8], m.chipset[9], m.chipset[0xB]) == (0xB7, 0xD6, 0xFB, 0xAD)
        assert tuple(m.chipset[r] for r in range(0x20, 0x24)) == (0, 0, 0, 0)
        assert m.chipset[0x19] == 0, 'L2 must stay off before POST summary'
        assert not m.fast and not m.cpu.reg_read(x.UC_X86_REG_CR0) & 0x60000000
        assert all(m.chipset[i] == custom[11+i-0x13] for i in range(0x13, 0x19))
        m.call('chipset_late_cache', flags=2)
        assert tuple(m.chipset[r] for r in (1, 4, 5, 6, 7, 8, 9, 0xB, 0xC, 0x19, 0x24)) == (0x54, 0x52, 0xB7, 0x9D, 0xEF, 0xD6, 0xFB, 0xAD, 0xAA, 0, 0xD8)
        assert tuple(m.chipset[r] for r in range(0x13, 0x19)) == (0x55, 0x55, 0x55, 0x55, 0x55, 0xAA)
        assert not m.fast and not m.cpu.reg_read(x.UC_X86_REG_CR0) & 0x60000000
        m.cmos[0x6A] ^= 1
        m.call('chipset_settings_load')
        assert m.record() == baseline
        # Independently validate every persisted selector against its UI domain.
        invalid = [(0, 0xC0), (2, 0x0C), (8, 3), (10, 3), (17, 0x80)]
        invalid += [(byte, baseline[byte] | (3 << shift))
                    for byte in range(11,17) for shift in (0,2,4,6)]
        invalid += [(1,0x08),(2,0x10),(3,0x04),(4,0x40),(5,0x40),(6,0x80),
                    (8,0x04),(9,0x21),(9,0x80),(10,0x30),(19,0x80),(22,0x10),(23,4)]
        for index, value in invalid:
            bad = bytearray(baseline)
            bad[index] = value
            m.draft(bad)
            m.call('chipset_settings_save')
            assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1, (index, value)
            # Bypass save: a checksum-valid corrupt selector must fail at load too.
            m.cmos[0x69], m.cmos[0x6A] = 0xC2, -(0xC2+sum(bad)) & 255
            m.cmos[0x6B:0x80], m.cmos[0x33:0x36] = bad[:21], bad[21:]
            saved = bytes(m.cmos)
            m.call('chipset_settings_load')
            assert m.record() == baseline and bytes(m.cmos) == saved, (index, value)
        m.cmos[0x6B:0x80], m.cmos[0x33:0x36] = custom[:21], custom[21:]
        m.cmos[0x69], m.cmos[0x6A] = 0xC0, -(0xC0+sum(custom)) & 255
        saved = bytes(m.cmos)
        m.call('chipset_settings_load')
        assert m.record() == baseline and bytes(m.cmos) == saved, 'Wrong signature must load defaults without writes'
        m.draft(baseline)
        m.call('chipset_settings_save')
        # An interrupted POST must retain saved policy and all devices.
        devices = bytes(m.cmos[0x38:0x69])
        m.cmos[0x36] = 0xA5
        m.call('chipset_memory_prepare', flags=2)
        assert m.cmos[0x69] == 0xC2 and m.cmos[0x36] == 0
        assert m.record() == baseline
        assert bytes(m.cmos[0x38:0x69]) == devices
    print('CMOS, selector validation, register masks, early L2-off and recovery: PASS', flush=True)
    for strap in (0, 0x40):
        m = Chipset()
        m.chipset[0x24] = 0x90 | strap
        m.call('chipset_memory_prepare', flags=2)
        assert m.cmos[0x37] == 0xA0 | strap
        m.warm = True
        m.chipset[0x24] ^= 0x40
        m.cmos[0x36] = 0xA5
        m.call('chipset_memory_prepare', flags=2)
        assert m.chipset[0x24] & 0x40 == strap
        assert m.cmos[0x37] == 0xA0 | strap
    print('Power-on HSPD strap survives warm override and recovery: PASS', flush=True)
    for turbo in (0, 0x10):
        for speed in (0, 1):
            m = Chipset()
            policy = bytearray(m.record())
            policy[2], policy[23] = 0xA7, speed | 2
            m.draft(policy)
            m.call('chipset_settings_save')
            m.chipset[5] = turbo
            m.cpu.reg_write(x.UC_X86_REG_SI, 1)
            m.call('chipset_memory_prepare', flags=2)
            assert m.chipset[5] == 0xA7 | turbo
    print('Early NTBREF uses refresh byte independently of CPU speed and retains TURBO: PASS', flush=True)
    for marker in (0,0xA5,0x1A,0x5A,0xDA):
        m=Chipset()
        custom=bytearray(m.record())
        custom[0]=0x56
        custom[10] = (custom[10] & 0x3F) | 0x80
        m.draft(custom)
        m.call('chipset_settings_save')
        m.cmos[0x36]=marker
        m.call('chipset_memory_prepare',flags=2)
        assert m.record()==custom and m.chipset[1]==0x56
        assert m.cmos[0x69]==0xC2
        assert m.cmos[0x36]==(0xDA if marker in (0x5A,0xDA) else 0)
        m.call('chipset_apply',flags=2)
        assert m.chipset[1]==0x56
    print('Power-off/reset during POST retains custom timings: PASS',flush=True)
    for marker in (0, 0xA5, 0x1A):
        m = Chipset()
        custom = bytearray(m.record())
        custom[0] = 0x56
        custom[10] = (custom[10] & 0x3F) | 0x80
        m.draft(custom)
        m.call('chipset_settings_save')
        assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
        devices = bytes(m.cmos[0x38:0x69])
        m.cmos[0x36] = marker
        m.startup(reset=True, through_visible=True, expected_record=custom)
        assert m.record() == custom and m.chipset[1] == 0x56
        assert m.cmos[0x69] == 0xC2 and m.cmos[0x36] == 0
        assert bytes(m.cmos[0x38:0x69]) == devices
        screen = bytes(m.cpu.mem_read(0xB8000, 80 * 50 * 2))[::2]
        assert b'POST RAM test failed' not in screen
        assert b'RAM test failed' not in screen
        assert not getattr(m, 'restarts', 0)
    print('Ordinary/reset-vector startup after interrupted POST keeps custom C2, hardware, devices and no RAM-failure notice: PASS', flush=True)
    m=Chipset()
    m.cpu.mem_write(m.base+0x78,struct.pack('<H',3072))
    policy=bytearray(m.record())
    policy[17:19]=bytes((2,1)) #64KiB ISA subregion at1MiB.
    m.cpu.mem_write(m.base+C,bytes(policy))
    m.call('chipset_apply',flags=2)
    assert bytes(m.cpu.mem_read(m.base+0xD0,2))==b'\0\0'
    m.cpu.reg_write(x.UC_X86_REG_DI,C)
    m.call('chipset_defaults')
    m.call('chipset_apply',flags=2)
    assert bytes(m.cpu.mem_read(m.base+0xD0,2))==struct.pack('<H',3072)
    print('Defaults restore physical RAM reports after ISA holes: PASS',flush=True)
    for enabled in (False, True):
        m=Chipset()
        policy=bytearray(m.record())
        policy[1]=0x96 if enabled else 0x16
        policy[9]=0x31 if enabled else 0x30
        policy[4]=0x88 if enabled else 0x80
        m.draft(policy)
        m.call('chipset_settings_save')
        m.call('chipset_settings_load')
        m.cpu.reg_write(x.UC_X86_REG_AX,5)
        m.call('chipset_interleave_policy')
        assert m.cpu.reg_read(x.UC_X86_REG_CL)==(0xB6 if enabled else 0x16)
        m.call('chipset_apply',flags=2)
        assert m.chipset[0x19]==0 and m.record()[9]==(0x31 if enabled else 0x30)
        assert bool(m.chipset[7]&8)==enabled
        assert m.cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000==(0 if enabled else 0x60000000)
        m.warm=True
        m.startup()
        assert m.chipset[0x19]==0 and m.record()==policy
        assert m.chipset[4]==0x16, 'No eligible pair on this retained single-bank layout'
    # Optional C/D/E shadows must copy each selected segment before DRAM reads.
    for enabled in (False, True):
        m=Chipset()
        policy=bytearray(m.record())
        policy[17:21]=bytes((4,1,6,2))
        policy[21:23]=bytes((0xFF,0x0F)) if enabled else bytes((0,0))
        m.cpu.mem_write(m.base+C,bytes(policy))
        m.cpu.mem_write(0xC0000,b'ROM!'*(0x30000//4))
        copies=[]
        def copy(cpu,access,address,size,value,unused):
            if enabled:
                segment=(address-0xC0000)//0x4000
                assert (m.chipset[0xF+segment//4] >> (2*(segment%4))) & 3 == 1
                assert value.to_bytes(size,'little') == (b'ROM!'*2)[address%4:address%4+size]
                copies.append(segment)
        hook=m.cpu.hook_add(UC_HOOK_MEM_WRITE,copy,None,0xC0000,0xEFFFF)
        m.call('chipset_apply',flags=2)
        m.cpu.hook_del(hook)
        m.call('chipset_late_cache',flags=2)
        assert tuple(m.chipset[r] for r in (0x20,0x21,0x22,0x23))==(4,1,6,2)
        assert tuple(m.chipset[r] for r in (0xF,0x10,0x11))==((0xAA,0xAA,0xAA) if enabled else (0,0,0))
        assert set(copies)==(set(range(12)) if enabled else set())
        assert bytes(m.cpu.mem_read(0xC0000,0x30000))==b'ROM!'*(0x30000//4)
    print('Saved interleave/L2 contrasts, late controls, ISA mapping and shadow copy ordering: PASS',flush=True)


def ui():
    # Real IRQ1 and INT16 input, rather than setting setup state.
    enter = [0x50] * 4 + [28]
    m = Chipset()
    # Enforce the native column contracts on every compiled label/value/help.
    rom=bytes(m.cpu.mem_read(0xF0000,65536))
    m.cpu.mem_write(m.base+0x278,b'\x01')
    m.cpu.mem_write(m.base+0xF7,b'\x00')
    m.call('chipset_ui_descriptor')
    descriptor=m.cpu.reg_read(x.UC_X86_REG_SI)
    def text_at(pointer):
        return rom[pointer:].split(b'\0',1)[0]
    for field in range(103):
        label,byte,shift,mask,count,values,h1,h2,reserved=struct.unpack_from('<HBBBHHHHB',rom,descriptor+14*field)
        assert len(text_at(label))<=24, text_at(label)
        assert len(text_at(h1))<=53 and len(text_at(h2))<=53
        if values in (0, 1):
            assert count == (256 if values == 0 else 64)
            # Numeric text is checked through both real UI consumers by test-modular-setup.py.
        else:
            for choice in struct.unpack_from('<'+'H'*count,rom,values):
                assert len(text_at(choice))<=28, text_at(choice)
    observed = set()
    cas_seen = []
    def observe(model):
        if model.cpu.mem_read(model.base + 0xF5, 1) == b'\x05':
            screen = model.cpu.mem_read(model.base + 0x278, 1)[0]
            observed.add(screen)
            if screen == 1:
                if model.text(8,26,9) == 'CAS Width':
                    cas_seen.append(True)
                    assert model.text(10,26,11) == 'L2 Disabled'
                    assert model.text(10,37,3) == ' | '
                    assert model.text(10,40,10) == 'L2 Enabled'
                    assert model.text(14,26,7) == '  2T/1T'
                    assert model.text(14,40,5) == '3T/1T'
                elif model.cpu.mem_read(model.base+0xF7,1)==b'\x06':
                    assert model.text(13,49,13) == '2T/1T | 3T/1T'
                elif model.text(3,62,14).strip() == 'Page 1  / 1':
                    raise AssertionError('RAM page count is not 2')
    m.observer = observe
    before = bytes(m.cmos)
    # Memory: change start, inspect popup/help, enable interleave; then discard.
    manual = [0x50]*2+[28,0x50,0x50,28]  # Normal -> Manual in display order.
    m.open(enter + [28] + manual + [0x50] + [0x4B] + [0x50]*3 + [28,0x3B,1,28] + [0x50]*5 + [0x4B, 1, 1, 1, 28])
    assert observed >= {0, 1}
    assert cas_seen
    assert m.record(True)[0] == 0x56 and m.record(True)[1] == 0x96
    assert bytes(m.cmos) == before
    # Every category and every field can be reached and is inside the columns.
    counts = (17,34,5,29,5,13)
    layouts = (
        [(0,[5,6,7,10,11,12,13,14]),(8,[5,6,7,10,11,12,13,16,17])],
        [(0,[5,8,9,10,11,12,13,14,15,16]),
         (10,[5,6,7,8,11,12,13,14,17,18,19,20]),(22,[5,6,7,8,11,12,13,14,17,18,19,20])],
        [(0,[5,8,11,12,13])],
        [(0,[5,6,7,8,9,10,11,14,15]),(9,[5,6,7,8,9,10,11,12,13,14]),(19,[5,6,7,8,9,10,11,12,13,14])],
        [(0,[5,6,7,8,9])],
        [(0,[5,8,9,10,11,14,15,16,17]),(9,[5,6,7,8])],
    )
    total = 0
    for category, count in enumerate(counts):
        m = Chipset()
        seen = set()
        def fields(model):
            if model.text(8,26,12) == 'SELECT VALUE': return
            if model.cpu.mem_read(model.base+0x278, 1)[0] == category+1:
                field = model.cpu.mem_read(model.base+0xF7, 1)[0]
                seen.add(field)
                page = max(i for i,(start,rows) in enumerate(layouts[category]) if field>=start)
                start,rows = layouts[category][page]
                row = rows[field-start]
                assert model.text(row,24,24).strip(), (category,field,row)
                assert model.text(row,49,28).strip(), (category,field,row)
                assert model.text(3,62,14).strip() == f'Page {page+1}  / {len(layouts[category])}'
                attrs=bytes(model.cpu.mem_read(0xB8000+row*160+48*2+1,60))[::2]
                assert attrs == bytes([0x1F])*30, (category,field,attrs)
                assert model.text(9,2,7) == 'Chipset' and model.text(10,2,4) == 'Exit'
                if category == 2:
                    for clock_row in (8,11,13):
                        assert model.text(clock_row,49,9) == 'TCLK2 /  '
                        assert model.text(clock_row,58,1).isdigit()
        m.observer = fields
        prepare = manual+[0x48]*2 if category == 0 else []
        m.open(enter + [0x50]*category + [28] + prepare + [0x50]*(count-1) + [1,1,1,28])
        assert seen == set(range(count)), (category, seen)
        total += count
    assert total == 103
    # Native page keys change the related block without changing settings.
    m=Chipset()
    pages=set()
    before=bytes(m.cmos)
    def cache_pages(model):
        if model.cpu.mem_read(model.base+0x278,1) == b'\x02':
            pages.add(model.text(3,62,14).strip())
    m.observer=cache_pages
    m.open(enter+[0x50,28,0x51,0x51,0x51,0x51,0x49,0x49,0x49,0x49,1,1,1,28])
    assert pages == {f'Page {i}  / 3' for i in range(1,4)}
    assert bytes(m.cmos)==before
    # Large enum has real paged selection, cancellation and field-specific F1.
    m = Chipset()
    popup_pages=set()
    help_titles=set()
    def popup(model):
        popup_pages.add(model.text(8,62,14).strip())
        help_titles.add(model.text(18,25,16))
    m.observer=popup
    m.open(enter + [0x50]*3 + [28] + [0x50]*8 + [28]+[0x49]*2+[0x51]*23+[0x3B,1,28,1,1,1,28])
    assert m.record(True)[7] == 255
    assert popup_pages >= {f'Page {i:<2} / 22' for i in range(1,23)}
    assert 'Fast ISA Address' in help_titles
    # F10's deliberate reset must not look like an unfinished unstable POST.
    m=Chipset()
    m.cmos[0x36]=0xA5
    m.open(enter+[28]+manual+[0x50]+[0x4B,0x44,28])
    assert m.cmos[0x69]==0xC2 and m.cmos[0x36]==0xA5
    m.warm=True
    m.call('chipset_memory_prepare',flags=2)
    assert m.record()[0]==0x56 and m.cmos[0x69]==0xC2
    assert m.cmos[0x36]==0
    # F9/F10 restores the safe policy even when a valid faster record exists.
    m=Chipset()
    safe=m.record()
    fast=bytearray(safe)
    fast[0],fast[1],fast[10]=0x54,0x96,0
    fast[10] = (fast[10] & 0x3F) | 0x80
    m.draft(fast)
    m.call('chipset_settings_save')
    m.open(enter+[0x43,28,0x44,28])
    m.startup()
    assert m.record()==safe and m.chipset[1]==0x96 and m.chipset[0x24]&8
    # F9 is a draft reset; later timing edits must survive F10 and startup.
    m=Chipset()
    m.open([0x43,28]+enter+[28]+manual+[0x50]+[0x4B]*2+[0x50]+[0x4B]*1+
           [0x50]+[0x4B]*1+[0x50]+[0x4B]*2+[0x44,28])
    assert m.warm and m.record(True)[0]==0
    saved=bytes(m.cmos)
    m.startup()
    m.call('publish_disk_cmos',flags=2)
    assert m.record()[0]==0 and m.chipset[1]==0 and m.cmos[0x69]==0xC2
    assert m.chipset[1]==0 and m.record()[0]==0
    assert bytes(m.cmos[0x69:])==saved[0x69:]
    assert bytes(m.cmos[0x33:0x36])==saved[0x33:0x36]
    for marker in (0,0xA5,0x1A,0x5A,0xDA):
        m.cmos[0x36]=marker
        m.console=''
        m.call('chipset_post_recovery_notice')
        pending=marker in (0x5A,0xDA)
        assert ('POST RAM test failed; chipset defaults restored' in m.console)==pending
        assert m.cmos[0x36]==(0x1A if pending else marker)
        once=m.console
        m.call('chipset_post_recovery_notice')
        assert m.console==once, 'Notice must be displayed once without keyboard input'
    # Real POST polling/IRQ1 Ctrl+Alt+Del, before/after Setup entry closes.
    for state in (1,2):
        m=Chipset()
        custom=bytearray(m.record())
        custom[0]=0x56
        custom[10] = (custom[10] & 0x3F) | 0x80
        m.draft(custom)
        m.call('chipset_settings_save')
        saved=bytes(m.cmos[0x69:])
        m.cmos[0x36]=0xA5
        m.cpu.mem_write(0x49E,bytes([state]))
        m.pending=[0x1D,0x38,0xE0,0x53]
        for scan in range(4):
            if not m.warm:
                m.call('post_keyboard_wait')
        assert m.warm and m.cmos[0x36]==0xA5
        assert bytes(m.cmos[0x69:])==saved
        m.startup()
        assert m.record()==custom and m.cmos[0x69]==0xC2
        assert m.cmos[0x36]==0
        assert m.chipset[1] == 0x56 and 'POST RAM test failed' not in m.console
    print('Ctrl+Alt+Del in open/closed POST preserves saved timings: PASS',flush=True)
    print('All103 fields, native navigation, popups, F1, paging and discard: PASS', flush=True)


def recovery_model():
    m = Chipset()
    policy = bytearray(m.record())
    policy[0], policy[1], policy[2] = 0x54, 0x96, 0xA7
    policy[10] |= 0x80
    policy[17:19] = bytes((4, 1))  # Valid ISA hole limits active memory to 2MiB.
    m.draft(policy)
    m.call('chipset_settings_save')
    m.call('settings_load')
    m.call('chipset_apply', flags=2)
    m.call('publish_memory_cmos', flags=2)
    m.chipset[2], m.chipset[3], m.chipset[4] = 0xCC, 0x88, 0x36
    m.cpu.mem_write(m.base+0x78, struct.pack('<H', 7168))
    m.cmos[0x36], m.cmos[0x37] = 0, 0xA0
    m.writes.clear()
    return m, policy


def ram_faults(m, stages):
    pending, hit, hooks = list(stages), [], []
    stage = [None]
    for name, owner in (('early', 'chipset_ram_test'), ('visible', 'chipset_visible_ram_test'),
                        ('final', 'chipset_runtime_ram_check')):
        address = 0xF0000+setup.rtc.symbol(owner)
        hooks.append(m.cpu.hook_add(UC_HOOK_CODE,
            lambda cpu, addr, size, _, name=name: stage.__setitem__(0, name), None, address, address))
    def corrupt(cpu, access, address, size, value, unused):
        if not pending or pending[0] != stage[0]:
            return
        point = {'early': 0x9FFFC, 'visible': 0x1FFFFC, 'final': 0x10000}[stage[0]]
        if address != point:
            return
        ip = cpu.reg_read(x.UC_X86_REG_IP)
        opcode = bytes(cpu.mem_read(0xF0000+ip, 4))
        if stage[0] != 'visible' and opcode[:3] not in (b'\x67\x66\x39', b'\x67\x66\x3b', b'\x67\x66\x8b'):
            return
        if stage[0] == 'final' and (opcode != b'\x67\x66\x8b\x07' or
                bytes(cpu.mem_read(address, 4)) not in (b'\xaa\x55\xaa\x55', b'\x55\xaa\x55\xaa')):
            return
        if stage[0] == 'visible' and (opcode[-1:] != b'\xaf' or
                cpu.reg_read(x.UC_X86_REG_EAX) not in (0x55AA55AA, 0xAA55AA55, 0)):
            return
        hit.append((pending.pop(0), address))
        cpu.mem_write(address, bytes(4))
    for point in (0x9FFFC, 0x1FFFFC, 0x10000):
        hooks.append(m.cpu.hook_add(UC_HOOK_MEM_READ, corrupt, None, point, point+3))
    return hit, hooks


def ram_pause():
    m = Chipset()
    m.cpu.mem_write(m.base+0xD0, struct.pack('<H', 64))
    m.cpu.mem_write(0x451, b'\x02')
    m.cpu.mem_write(0x100000, b'R'*65536)
    original = bytes(m.cpu.mem_read(0x100000, 65536))
    saved = bytes(m.cmos)
    events = (0x1D, 0x45, 0xE1, 0x9D, 0xC5, 0x9E, 0xFA, 0x1E)
    walkers = []
    m.cpu.hook_del(m.code_hook)
    def service(cpu, address, size, unused):
        if bytes(cpu.mem_read(address, 1)) == b'\xf4':
            assert not cpu.reg_read(x.UC_X86_REG_CR0) & 1
            assert bytes(cpu.mem_read(0x4A6, 2)) == b'\x01\x01'
            walkers.append(cpu.reg_read(x.UC_X86_REG_EDI))
            assert len(set(walkers)) == 1, 'RAM walker advanced during Pause'
            assert len(walkers) <= len(events)
            m.pending.append(events[len(walkers)-1])
        m.code(cpu, address, size, unused)
    m.cpu.hook_add(UC_HOOK_CODE, service)
    m.pending.append(0xE1)
    m.call('chipset_visible_ram_test', count=50000000)
    assert len(walkers) == 8 and walkers[0] == 0x10400
    assert bytes(m.cpu.mem_read(0x100000, 65536)) == original
    assert bytes(m.cmos[0x10:]) == saved[0x10:]
    assert bytes(m.cpu.mem_read(0x4A6, 2)) == b'\0\0'
    print('Protected RAM Pause: first1KiB yield, frozen walker, consumed resume, retained data/CMOS PASS', flush=True)


def ram_bursts():
    listing=(BUILD/'baios-presario800-system.lst').read_text().splitlines()
    compares={int(match[1],16) for line in listing if 'repe scasd' in line and
              (match:=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line))}
    assert compares
    patterns=(0x55AA55AA,0xAA55AA55,0)
    cases=[('pass',None,None)]+[('fault',pattern,position) for pattern in patterns for position in (0,512,1020)]+[('alias',bit,None) for bit in range(2,10)]+[(key,region,None) for key in ('escape','delete') for region in (0,0x100000)]
    for kind,selector,position in cases:
        extended=kind in ('escape','delete') and selector==0x100000
        input_floor=0x100400 if extended else 0x10400
        m=Chipset();m.cpu.hook_del(m.code_hook)
        m.cpu.mem_write(m.base+0xD0,struct.pack('<H',64 if extended else 0))
        m.cpu.mem_write(m.base+0x78,bytes(2))
        m.cpu.mem_write(m.base+0x51,bytes((int(kind in ('escape','delete')),)))
        data=bytes((i*7+3)&255 for i in range(0x9FC00-0x10000))
        if kind=='alias':data=b'\x11'*1024+data[1024:]
        m.cpu.mem_write(0x10000,data)
        high=bytes((i*11+5)&255 for i in range(65536))
        if extended:m.cpu.mem_write(0x100000,high)
        m.cpu.mem_write(0x500,b'G'*0x300);m.cpu.mem_write(0xC00,b'H'*(0x6000-0xC00))
        low=bytes(m.cpu.mem_read(0,0x6000));state=bytes(m.cpu.mem_read(m.base,1024));saved=bytes(m.cmos)
        injected=[];services=[];terminal=[];writes=dict.fromkeys(patterns,0);reads=dict.fromkeys(patterns,0)
        coverage=bytearray(len(data)//4);low_stack=[0x7000]
        external=([1] if kind=='escape' else [0xE0,0x53]) if kind in ('escape','delete') else []
        if external:
            def irq(cpu,address,size,unused):
                if external and services and services[-1]>=input_floor:
                    m.pending.append(external.pop(0))
                    setup.rtc.Clock.interrupt(m,cpu,9,None)
            address=0xF0000+setup.rtc.symbol('post_keyboard_wait')
            m.cpu.hook_add(UC_HOOK_CODE,irq,None,address,address)
        def memory(cpu,access,address,size,value,unused):
            if access==UC_MEM_WRITE:
                if address<0x10000:
                    assert 0x800<=address and address+size<=0xC00 or 0x6000<=address and address+size<=0x7000 or 0x400<=address and address+size<=0x500, ('unowned low write',hex(address),size)
                    if 0x6000<=address<0x7000:low_stack[0]=min(low_stack[0],address)
                if kind=='alias' and 0x10000<=address<0x10400:
                    cpu.mem_write(address^(1<<selector),value.to_bytes(size,'little'))
                if kind=='pass' and 0x10000<=address<0x9FC00 and value in patterns:
                    writes[value]+=1;coverage[(address-0x10000)//4]|={patterns[0]:1,patterns[1]:2,0:4}[value]
            elif 0x10000<=address<0x9FC00 and cpu.reg_read(x.UC_X86_REG_IP) in compares:
                pattern=cpu.reg_read(x.UC_X86_REG_EAX)
                if kind=='pass':reads[pattern]+=1
                if kind=='fault' and not injected and address==0x10000+position and pattern==selector:
                    cpu.mem_write(address,bytes(v^255 for v in cpu.mem_read(address,size)));injected.append(address)
        m.cpu.hook_add(UC_HOOK_MEM_READ|UC_HOOK_MEM_WRITE,memory)
        keyboard=setup.rtc.symbol('chipset_visible_ram_test')
        start=next(i for i,line in enumerate(listing) if re.search(r'\bchipset_visible_ram_test:\s*$',line))
        row=next(i for i in range(start,len(listing)) if re.search(r'\.keyboard:\s*$',listing[i]))
        service_address=next(int(match[1],16) for line in listing[row+1:] if (match:=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line)))
        def service(cpu,address,size,unused):
            assert cpu.mem_read(0x10000,1024)==data[:1024], 'block not restored before IRQ service'
            if extended:assert cpu.mem_read(0x100000,1024)==high[:1024], 'extended block not restored before IRQ service'
            services.append(cpu.reg_read(x.UC_X86_REG_EDI))
        m.cpu.hook_add(UC_HOOK_CODE,service,None,0xF0000+service_address,0xF0000+service_address)
        for name in ('controlled_defaults_restart','hard_halt'):
            address=0xF0000+setup.rtc.symbol(name)
            m.cpu.hook_add(UC_HOOK_CODE,lambda cpu,a,n,u,name=name:(terminal.append(name),cpu.emu_stop()),None,address,address)
        for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_DS,0),(x.UC_X86_REG_ES,0),(x.UC_X86_REG_FS,m.segment),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x6FFE),(x.UC_X86_REG_EFLAGS,2)):
            m.cpu.reg_write(reg,value)
        m.cpu.mem_write(0x6FFE,b'\xff\xff')
        m.cpu.emu_start(0xF0000+keyboard,0xFFFFF,count=50000000)
        assert m.cpu.mem_read(0x10000,len(data))==data, (kind,selector,position,'restoration')
        if extended:assert m.cpu.mem_read(0x100000,len(high))==high, (kind,'extended restoration')
        assert m.cpu.mem_read(0,0x400)==low[:0x400]
        assert m.cpu.mem_read(0x500,0x300)==low[0x500:0x800]
        assert m.cpu.mem_read(0xC00,0x5400)==low[0xC00:0x6000]
        assert low_stack[0]>=0x6000
        if kind in ('fault','alias'):
            assert terminal==['controlled_defaults_restart'],(kind,selector,terminal)
            assert m.cmos[0x69]==0xD2 and m.cmos[0x36]==0x1A
            if kind=='fault':assert injected
        else:
            assert not terminal and bytes(m.cmos)==saved
            assert services[0]==0x10400
            if kind=='pass':
                assert coverage==bytes((7,))*len(coverage)
                assert writes==reads==dict.fromkeys(patterns,len(data)//4)
            else:
                assert services[-1]==input_floor, (kind,selector,services)
                assert [at for at in services if at>0x100000]==([0x100400] if extended else []), (kind,selector,services)
                if not extended:assert services==[0x10400], (kind,services)
                assert m.cpu.mem_read(m.base+0x50,1)==b'\2'
                assert m.cpu.mem_read(m.base+0xF4,1)==bytes((kind=='delete',))
        after=bytearray(m.cpu.mem_read(m.base,1024))
        for offset in (0x50,0xF4):after[offset]=state[offset]
        assert after==state, (kind,'live EBDA changed')
        assert m.a20==0 and m.speaker==0xA0
    ram_pause()
    print('Burst RAM: every constant at every dword, first/middle/last mismatches, tied low address bits, restored service/exit/restart, low/stack guards, first1KiB conventional/extended Escape/Delete and conventional Pause PASS',flush=True)


def ram_test():
    ram_pause()
    # Disabled L2 skips the SRAM owner; the final RAM owner must gate NMIs itself.
    for control in (0xA0, 0xAC):
        m = Chipset()
        m.speaker = control
        m.chipset[0x19] = 0  # Actual startup leaves L2 off before this late entry.
        m.cpu.mem_write(m.base+0xD0, struct.pack('<H', 3072))
        m.cpu.mem_write(m.base+C+9, b'\x30')
        protected = []
        def parity_gate(cpu, access, address, size, value, unused):
            if cpu.reg_read(x.UC_X86_REG_CR0) & 1:
                assert m.speaker & 0x0C == 0x0C, 'NMI reporting enabled with real-mode IVT in PE'
                protected.append(address)
        hook = m.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, parity_gate, None, 0x10000, 0x4FFFFF)
        m.call('chipset_late_cache', flags=2)
        m.cpu.hook_del(hook)
        assert protected and m.chipset[0x19] == 0
        assert m.speaker == control and not m.cpu.reg_read(x.UC_X86_REG_CR0) & 1
        assert m.cpu.reg_read(x.UC_X86_REG_DS) == m.cpu.reg_read(x.UC_X86_REG_ES) == 0
    print('L2-disabled final RAM protected accesses mask NMI and restore parity/channel control: PASS', flush=True)
    owners = {'early': 'chipset_ram_test', 'visible': 'chipset_visible_ram_test',
              'final': 'chipset_late_cache'}
    notices = {'early': 'POST RAM test failed; chipset defaults restored',
               'visible': 'RAM test failed; retrying defaults',
               'final': 'RAM test after L2 setup failed; retrying defaults'}
    # Passing selected policy never commits recovery, and visible RAM remains intact.
    m, policy = recovery_model()
    m.cpu.mem_write(0x20000, b'KEEP')
    m.startup(through_visible=True)
    assert m.record() == policy and m.chipset[4] == 0x36
    assert not getattr(m, 'restarts', 0) and (0x69, 0) not in m.writes
    assert bytes(m.cpu.mem_read(0x20000, 4)) == b'KEEP'
    assert m.text(5, 3, 8) == 'RAM Test'
    assert m.text(5, 24, 5) == '2048 ' and m.text(5, 34, 6) == 'Passed'
    print('Passing selected interleave/timing/ISA policy and visible free-RAM preservation: PASS', flush=True)

    # The passing visible owner must preserve all live firmware state and RAM.
    m = Chipset()
    m.cpu.hook_del(m.code_hook)
    m.cpu.mem_write(m.base+0xD0, struct.pack('<H', 3072))
    m.cpu.mem_write(m.base+0x78, struct.pack('<H', 3072))
    m.cpu.mem_write(0x450, b'\0\0')
    sentinels = (0x10000, 0x80000, 0x100000, 0x3FFFFC)
    for address in sentinels:
        m.cpu.mem_write(address, b'KEEP')
    protected = bytes(m.cpu.mem_read(m.base, 1024))
    m.chipset[1], m.cmos[0x69], m.cmos[0x36], m.speaker = 0x96, 0xC2, 0, 0xA4
    seen = []
    def progress(cpu, access, address, size, value, unused):
        value = m.text(0, 11, 5)
        if value.isdigit() and (not seen or value != seen[-1]):
            seen.append(value)
    for point in (0x20000, 0x80000, 0x1FFFFC, 0x2FFFFC, 0x3FFFFC):
        m.cpu.hook_add(UC_HOOK_MEM_READ, progress, None, point, point+3)
    m.call('chipset_visible_ram_test', flags=2, count=50000000)
    assert list(map(int, seen)) == [128, 512, 1984, 3008, 4032], seen
    assert m.text(0, 0, 19) == ' RAM test: 04096 KB'
    assert m.text(1, 0, 21).startswith(' POST RAM test passed')
    assert all(bytes(m.cpu.mem_read(address, 4)) == b'KEEP' for address in sentinels)
    assert bytes(m.cpu.mem_read(m.base, 1024)) == protected
    assert m.a20 == 0 and m.speaker == 0xA4
    assert m.cmos[0x69] == 0xC2 and m.cmos[0x36] == 0
    print('Passing visible RAM ordered progress, all sentinels/full EBDA, A20 and port61 preservation: PASS', flush=True)

    for first, second in ((owner, None) for owner in owners):
        m, _ = recovery_model()
        hit, hooks = ram_faults(m, [first])
        m.cpu.mem_write(m.base+0xD4, struct.pack('<H', 0x1532))
        m.cpu.reg_write(x.UC_X86_REG_EBP, 0x15320000)
        if first == 'early':
            m.cpu.reg_write(x.UC_X86_REG_DX, 7168)
        m.startup(entry=owners[first], through_visible=True, through_gate=first == 'final')
        assert len(hit) == 1 and getattr(m, 'restarts', 0) == 1, (first, hit, m.startup_hops)
        assert bytes(m.cpu.mem_read(m.base+0xD4, 2)) == struct.pack('<H', 0x1532)
        assert m.writes.count((0x69, 0xD2)) == m.writes.count((0x36, 0x5A)) == 1
        assert m.writes.index((0x69, 0xD2)) < m.writes.index((0x36, 0x5A))
        assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0x1A
        assert m.chipset[4] == 0x16 and m.record() == RECOVERY and m.chipset[1] == 0xA6
        assert m.chipset[2] == 0xCC and m.chipset[3] == 0x88
        assert m.chipset[0x19] == 0 and m.cpu.mem_read(m.base+0x3A, 1) == b'\0'
        assert m.a20 == 0
        assert bytes(m.cmos[0x17:0x19]) == bytes(m.cmos[0x30:0x32]) == struct.pack('<H', 7168)
        assert m.cpu.mem_read(m.base+0xD0, 2) == struct.pack('<H', 7168)
        assert m.console.count(notices[first]) == 1
        assert m.text(5, 3, 8) == 'RAM Test'
        assert m.text(5, 24, 5) == '8192 ' and m.text(5, 34, 6) == 'Passed'
        assert 'Press any key' not in m.console
        for hook in hooks: m.cpu.hook_del(hook)
        m.startup(reset=True, through_visible=True)
        assert m.cmos[0x69] == 0xD2 and m.cmos[0x36] == 0
        assert m.record() == RECOVERY and m.chipset[1] == 0xA6
        assert m.console.count(notices[first]) == 1
    print('Actual early/visible/final comparisons -> ordered commit -> ROM restart -> sequential map/rebuild/apply/publication/pass: PASS', flush=True)

    for first, second in (('early', 'early'), ('visible', 'early'), ('visible', 'visible'), ('early', 'visible'),
                          ('final', 'visible'), ('visible', 'final'), ('final', 'final')):
        m, _ = recovery_model()
        hit, hooks = ram_faults(m, [first, second])
        m.cpu.reg_write(x.UC_X86_REG_DX, 7168)
        m.startup(entry=owners[first], halt=True)
        assert [item[0] for item in hit] == [first, second], (first, second, hit)
        assert m.posts[-1:] == [0xE7] and m.restarts == 1
        assert m.writes.count((0x69, 0xD2)) == m.writes.count((0x36, 0x5A)) == 1
        assert m.cmos[0x36] == (0x5A if second == 'early' and first == 'early' else 0x1A)
        for hook in hooks: m.cpu.hook_del(hook)
    print('Persistent and cross-owner failure retains one retry before/after notice; second failure E7 with no second commit: PASS', flush=True)

    for owner in owners:
        # Stop an actual comparison failure after its commit, then ordinary reset.
        m, _ = recovery_model()
        hit, hooks = ram_faults(m, [owner])
        m.cpu.reg_write(x.UC_X86_REG_DX, 7168)
        m.startup(entry=owners[owner], before_restart=True)
        assert hit and m.cmos[0x36] == (0x5A if owner == 'early' else 0x1A)
        for hook in hooks: m.cpu.hook_del(hook)
        m.startup(reset=True, before_notice=True)
        expected = 0xDA if owner == 'early' else 0
        assert m.cmos[0x36] == expected
        assert m.record() == RECOVERY and m.chipset[1] == 0xA6
        m.startup(reset=True, before_notice=True)
        assert m.cmos[0x36] == expected
        assert m.record() == RECOVERY and m.chipset[1] == 0xA6
        count = m.console.count(notices['early'])
        m.startup(reset=True)
        assert m.console.count(notices['early']) == count + (owner == 'early')
        assert m.record() == RECOVERY and m.chipset[1] == 0xA6
        m.startup(reset=True)
        assert m.cmos[0x36] == 0 and m.console.count(notices['early']) == count + (owner == 'early')
        assert m.record() == RECOVERY and m.chipset[1] == 0xA6
    print('Actual committed failure interrupted before/after notice; repeated ordinary startup carries/acknowledges/clears once: PASS', flush=True)


def production_controls():
    # Compose a new saved control with independent nondefault timing/cache policy.
    for accept in (False, True):
        saved = setup.production_post_model()
        setup.schema2_fixture(saved, types=0, flags=0x0B, order=(2, 0, 0))
        policy = setup.nondefault_extensions(saved)
        before = bytes(saved.cmos)
        saved.open([0x50, 0x50, 15]+[0x50]*5+[0x4D] +
                   ([0x44, 28] if accept else [0x44, 1, 1, 1, 28]))
        assert saved.warm == accept
        if not accept: assert bytes(saved.cmos) == before
        assert bytes(saved.cmos[0x33:0x36]+saved.cmos[0x40:0x80]) == before[0x33:0x36]+before[0x40:0x80]
        for cold in (False, True):
            post = setup.production_post_model()
            post.cmos[:] = saved.cmos
            if accept:
                post.cpu.mem_write(0xC8000,bytes(importlib.import_module('test-legacy-boot').rom(0)))
            timings = []
            def before_cache(m, name):
                if name == 'chipset_late_cache':
                    assert m.chipset[1] == 0x54 and m.chipset[4] == 0x14 and m.chipset[0x19] == 0
                    timings.append(True)
            post.startup_observer = before_cache
            post.startup(reset=cold, production_controls=True, through_boot=True)
            assert timings and post.record() == policy and post.chipset[1] == 0x54
            assert post.cpu.mem_read(post.base+0x17F, 1) == b'\x01'
            assert bool(post.cpu.mem_read(0x417, 1)[0] & 0x20) == (not accept)
            setup.settle_boot_leds(post)
            assert post.led_values and bool(post.led_values[-1] & 2) == (not accept)
            assert post.cpu.mem_read(0x49F, 1) == b'\0'
            hops = post.startup_hops
            assert hops.index('post_numlock_apply') < hops.index('post_keyboard_presence') < hops.index('chipset_apply')
            assert hops.index('setup_post_gate') < hops.index('chipset_late_cache') < hops.index('int19')
            if accept:
                assert post.cpu.mem_read(0x600,2)==b'\x01\0' and post.cpu.mem_read(0x182,2)==b'\0\xC8'
                assert hops.index('chipset_apply') < hops.index('chipset_late_cache') < hops.index('option_rom_discovery') < hops.index('post_debug_summary') < hops.index('int19')
                assert post.cpu.mem_read(0x7C00,4)==b'BOOT' and post.chipset[4]==0x14
                assert post.cpu.reg_read(x.UC_X86_REG_CR0)&0x60000000==0
                assert post.chipset[0x19]==0 and post.text(4,20,12)=='Not detected'
            assert post.cpu.mem_read(post.base+0x7A, 1)[0] in (0x14, 0x15, 0x16), 'late SRAM probe did not run'
            assert not getattr(post, 'restarts', 0)
    # No Errors retains the mandatory comparison, recovery commit, one retry and E7.
    for persistent in (False, True):
        post = setup.production_post_model()
        setup.schema2_fixture(post, types=0, flags=0x0A, order=(2, 0, 0))
        setup.nondefault_extensions(post)
        hit, hooks = ram_faults(post, ['visible']*(2 if persistent else 1))
        try:
            post.startup(reset=True, production_controls=True, halt=persistent, through_boot=not persistent)
            assert [stage for stage, _ in hit] == ['visible']*(2 if persistent else 1)
            assert post.restarts == 1 and post.cmos[0x69] == 0xD2 and post.record() == RECOVERY
            assert post.writes.count((0x69, 0xD2)) == post.writes.count((0x36, 0x5A)) == 1
            assert post.writes.index((0x69, 0xD2)) < post.writes.index((0x36, 0x5A))
            assert post.cpu.mem_read(post.base+0x17F, 1) == b'\x01'
            assert post.startup_hops.count('post_numlock_apply') == post.startup_hops.count('post_keyboard_presence') == 2
            assert 'RAM test failed; retrying defaults' in post.console
            if persistent:
                assert post.posts[-1] == 0xE7 and 'int19' not in post.startup_hops
            else:
                assert post.cpu.mem_read(0x7C00, 4) == b'BOOT'
                assert post.text(13, 54, 13) == 'RAM recovered'
                assert post.cpu.mem_read(0x484, 3) == b'\x18\x10\0'
                assert post.startup_hops.index('chipset_late_cache') < post.startup_hops.index('post_debug_summary') < post.startup_hops.index('int19')
                assert post.startup_hops.index('controlled_defaults_restart') < post.startup_hops.index('chipset_late_cache')
        finally:
            for hook in hooks: post.cpu.hook_del(hook)
    print('Saved controls plus nondefault timing/cache, cold/warm POST, mandatory No Errors RAM retry/fatal and late L2: PASS', flush=True)


def integrity():
    system=(BUILD/'baios-presario800-system.rom').read_bytes()
    name = 'baios-presario800-vga141-bus07.bin' if (BUILD/'baios-presario800-vga141-bus07.bin').exists() else 'baios-presario800.bin'
    physical=(BUILD/name).read_bytes()
    retained=bytearray((ROOT/'reference/COMPAQ_PROLINEA_MT_05-02-94.BIN').read_bytes()[:65536])
    if 'bus07' in name or name == 'baios-presario800.bin':
        retained[:32768]=(ROOT/'reference/baios-presario800-vga141-bus07.bin').read_bytes()[:32768]
        if physical[0x08E7] == 0x1C:
            retained[0x08E7] = 0x1C
            retained[32767] = -sum(retained[:32767])&255
    assert len(system)==65536 and sum(system)&255==0
    assert len(physical)==131072 and physical[:65536]==retained and physical[65536:]==system
    assert system[0xFFF0:0xFFF5]==b'\xea\0\0\0\xf0'
    print('ROM size/checksum, physical layout, retained bytes and reset target: PASS',flush=True)


def emulator(preview=False, only=None, vga141=False, bus07=False, vga_clock=None):
    floppy=importlib.import_module('floppy-matrix')
    work=(BUILD if bus07 or BUILD != ROOT/'build' else ROOT/('build/review/vga141' if vga141 else 'build'))/'review/chipset'
    if vga_clock == 50: work = work/'vga50'
    work.mkdir(parents=True,exist_ok=True)
    roms=work/'roms'
    source=ROOT/'reference/86box'
    for relative in ('machines/d824','video/cirruslogic'):
        (roms/relative).mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source/'video/cirruslogic/5428.bin',roms/'video/cirruslogic/5428.bin')
    wrapper=roms/'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
    physical_path=BUILD/'baios-presario800-vga141-bus07.bin' if bus07 else ROOT/('build/review/vga141/baios-presario800-vga141.bin' if vga141 else 'build/baios-presario800.bin')
    if vga_clock: physical_path = BUILD/f'baios-presario800-vga{vga_clock}.bin'
    physical=physical_path.read_bytes()
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    exe=shutil.which('86Box.exe') or str(Path(os.environ['LOCALAPPDATA'])/'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe')
    screens=[('standard',0,None,'STANDARD'),('standard24',0,None,'STANDARD'),('categories',0,None,None),('categories-disabled',0,None,None),('memory',1,0,None),('ram-config',1,11,None),
             ('cache',2,0,None),('cache-abc',2,10,None),('cache-def',2,22,None),
             ('clock',3,0,None),('isa-bus',4,0,None),('isa-region1',4,9,None),('isa-region2',4,19,None),
             ('dma',5,0,None),('shadow-cd',6,0,None),('shadow-e',6,9,None)]
    screens += [('fast-profile',1,2,None),('cas-popup',1,6,'POPUP'),('cas-help',1,6,'HELP'),
                ('profile-popup',1,2,'POPUP'),('profile-help',1,2,'HELP'),
                ('profile-clock-help',1,0,'HELP'),('dram-speed-help',1,1,'HELP'),
                ('interleave-popup',1,11,'POPUP'),('fast-isa-popup',4,8,'POPUP'),('post-ram',0,None,'POST_RAM'),
                ('ram-timing-help',1,4,'HELP'),('refresh-help',1,10,'HELP'),('ras-timeout-help',1,12,'HELP'),
                ('l2-write-help',2,2,'HELP'),('cache-policy-help',2,10,'HELP'),
                ('clock-help',3,4,'HELP'),('shadow-help',6,1,'HELP'),('isa-divider-popup',3,4,'POPUP'),
                ('isa-waits-popup',4,6,'POPUP'),('isa-waits-help',4,6,'HELP'),
                ('post-summary',0,None,'SUMMARY'),('post-summary-long',0,None,'SUMMARY'),('post-ui',0,None,'POST_UI'),
                ('post-ram-error',0,None,'RAM_ERROR')]
    preview_label = only[0] if only else 'categories'
    theme_names = ('default','award-blue','award-gray','ami-purple','ami-teal',
                   'ami-classic','amber','black-white','high-contrast')
    screens += [('theme-'+name,0,None,'STANDARD') for name in theme_names]
    screens += [('theme-gray-cache',2,10,None),('theme-gray-cas',1,6,'POPUP'),
                ('theme-gray-help',1,6,'HELP'),('theme-ami-classic-help',1,6,'HELP'),
                ('theme-amber-help',1,6,'HELP')]
    for label,screen,field,mode in screens:
        if only and label not in only: continue
        if preview and label!=preview_label: continue
        vm=work/('preview' if preview else label)
        vm.mkdir(exist_ok=True)
        for n in ('nvr','disk'):
            (vm/n).mkdir(exist_ok=True)
        disk=vm/'disk/scratch.img'
        if not disk.exists():
            with disk.open('xb') as out: out.truncate(64*1024*1024)
        # config owns only this disposable VM; a repeat recreates its CMOS.
        if (vm/'nvr/d824.nvr').exists():
            # config's native mkdir expects a new nvr directory.
            (vm/'nvr/d824.nvr').unlink()
            (vm/'nvr').rmdir()
        else:
            (vm/'nvr').rmdir()
        setup_preview = preview and mode != 'SUMMARY'
        floppy.config(vm,disk,4 if setup_preview else 0,0,vm/'a.img',vm/'b.img',
                      boot=0 if setup_preview else 2,seek=setup_preview)
        with (vm/'86box.cfg').open('a') as cfg:
            cfg.write('\n[Cirrus Logic GD5428 (ISA) (On-Board)]\nmemory = 1024\n')
        if label == 'standard24':
            nvr=vm/'nvr/d824.nvr'
            cmos=bytearray(nvr.read_bytes())
            record=bytearray((66,56,3,0x93,1,0,2,0))
            record[5]=-(sum(record)+cmos[0x10])&255
            cmos[0x38:0x40]=record
            nvr.write_bytes(cmos)
        if label in ('categories','categories-disabled','fast-profile','cas-popup','cas-help','ram-timing-help','refresh-help','theme-gray-cas','theme-gray-help','theme-ami-classic-help','theme-amber-help'):
            nvr=vm/'nvr/d824.nvr'
            cmos=bytearray(nvr.read_bytes())
            policy=bytearray(NORMAL)
            policy[9]=0x30 if label=='categories-disabled' else 0x31
            if label == 'fast-profile': policy[0],policy[10] = 0x95,0xE8
            elif label in ('cas-popup','cas-help','ram-timing-help','refresh-help','theme-gray-cas','theme-gray-help','theme-ami-classic-help','theme-amber-help'): policy[10] = 0xA8
            cmos[0x69],cmos[0x6A]=0xC2,-(0xC2+sum(policy))&255
            cmos[0x6B:0x80],cmos[0x33:0x36]=policy[:21],policy[21:]
            nvr.write_bytes(cmos)
        system=vm/'test.rom'
        defines=['-DEMULATOR_TEST','-DEMULATOR_CHIPSET_TEST',f'-DEMULATOR_CHIPSET_SCREEN={screen}']
        if mode == 'SUMMARY' or label.startswith('theme-'):
            defines[0] = '-DEMULATOR_POST_SUMMARY_TEST'
        defines += ['-DVGA_BIOS_141']
        if label.startswith('theme-'):
            if label.startswith('theme-gray-'): theme = 2
            elif label.endswith('-help'): theme = theme_names.index(label[6:-5])
            else: theme = theme_names.index(label[6:])
            defines += [f'-DEMULATOR_CHIPSET_THEME={theme}']
        if label in ('categories','categories-disabled'):
            defines += [f'-DEMULATOR_CHIPSET_L2_REQUEST={0 if label=="categories-disabled" else 1}']
        if field is not None: defines += [f'-DEMULATOR_CHIPSET_FIELD={field}']
        if mode: defines += [f'-DEMULATOR_CHIPSET_{mode}']
        if label == 'post-summary-long': defines += ['-DEMULATOR_CHIPSET_SUMMARY_LONG']
        if label == 'standard24': defines += ['-DEMULATOR_CHIPSET_CLOCK24']
        if preview: defines += ['-DEMULATOR_CHIPSET_PREVIEW']
        subprocess.run([nasm,'-f','bin',*defines,'-I',str(ROOT/'src')+'/',
                        '-o',str(system),str(ROOT/'src/bios.asm')],check=True)
        data=bytearray(system.read_bytes())
        assert len(data)==65536
        data[-1]=-sum(data[:-1])&255
        wrapper.write_bytes(physical[:65536]+data)
        args=[exe,'-P',str(vm),'-R',str(roms),'-L',str(vm/'86box.log'),'-N']
        if preview:
            # Explicitly requested visible emulator; it remains open for review.
            proc=subprocess.Popen(args)
            (work/'preview.pid').write_text(str(proc.pid))
            print('86Box visual review opened: '+str(vm),flush=True)
            return
        result=floppy.run_hidden(args,timeout=90)
        assert result.returncode==0x67,(label,hex(result.returncode))
        with disk.open('rb') as inp:
            inp.seek(63*512)
            width,height=struct.unpack('<HH',inp.read(4))
            assert width in (640,720) and height==400
            inp.seek(64*512)
            pixels=inp.read(width*height*4)
        rows=bytearray()
        for row in range(height):
            rows.append(0)
            for col in range(width):
                offset=(row*width+col)*4
                rows.extend(pixels[offset:offset+3][::-1])
        def chunk(kind,data):
            return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data))
        png=b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>IIBBBBB',width,height,8,2,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')
        (work/(label+'.png')).write_bytes(png)
        print('86Box real VGA / '+label+('' if mode in ('SUMMARY', 'POST_UI') else ' / L2 off')+': PASS',flush=True)
    figures=''.join(f'<figure id="{label}"><figcaption>{label}</figcaption>'
                    f'<img src="{label}.png" width="720" height="400" alt="{label}"></figure>'
                    for label,screen,field,mode in screens if (work/(label+'.png')).exists())
    (work/'review.html').write_text('<!doctype html><meta charset="utf-8">'
                                 '<title>86Box chipset review</title>'
                                 '<h1>86Box chipset review</h1>'+figures,encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case',action='append',choices=('profiles','profile-locks','policy','ui','ram','ram-bursts','controls','integrity'))
    parser.add_argument('--86box',dest='emulator',action='store_true')
    parser.add_argument('--screen',action='append')
    parser.add_argument('--preview',action='store_true')
    parser.add_argument('--vga141',action='store_true')
    parser.add_argument('--vga-bus07',action='store_true')
    parser.add_argument('--vga-clock',type=int,choices=(50,60))
    args=parser.parse_args()
    cases={'profiles':profiles,'profile-locks':profile_locks,'policy':cmos_and_policy,'ui':ui,'ram':ram_test,'ram-bursts':ram_bursts,'controls':production_controls,'integrity':integrity}
    for case in args.case or cases:
        cases[case]()
    if args.emulator or args.preview:
        emulator(args.preview,args.screen,args.vga141,args.vga_bus07,args.vga_clock)


if __name__=='__main__':
    main()
