"""Compose CLOCKCHK, actual SMM and actual RTC firmware; electrical clocks are seams."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

import smm_activation_proof as smm
from smm_activation_proof import Board, HB, SB, ROOT, PORT, x
from shared.tools.ram_proof import Listing, constants
from shared.tools.rom import build, verify

spec = importlib.util.spec_from_file_location('wake_check', PORT / 'tools/test-wake-check.py')
wake = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wake)
OUT = PORT / 'build/tests/clock-check'


class ClockBoard(Board):
    def __init__(self, *, clock_wake=False, pending_on_smi=False, **kwargs):
        self.rtc_in = self.rtc_out = None
        self.clock_wake = clock_wake
        self.clock_edges = 0
        self.pending_on_smi = pending_on_smi
        self.port61 = 0xA7
        self.caller = None
        self.trial_writes = []
        super().__init__(**kwargs)
        self.clock_offset = self.listing.symbol('board_clock_saved') - self.listing.symbol('board_smm_image')

    def inp(self, u, port, size, user):
        if self.rtc_in and port in (0x21, 0xA1, 0xA0, 0x71, 0x84):
            return self.rtc_in(u, port, size, user)
        if port == 0x61:
            return self.port61
        return super().inp(u, port, size, user)

    def out(self, u, port, size, value, user):
        if self.rtc_out and port in (0x21, 0xA1, 0xA0, 0x20, 0x70, 0x71):
            if port == 0x70:
                self.nmi = value
            return self.rtc_out(u, port, size, value, user)
        if port == 0x61:
            self.port61 = value
        if self.smm:
            if port == 0x61:
                self.trial_writes.append((0x61, value))
            elif 0xCFC <= port <= 0xCFF and self.cf8 & ~255 == SB:
                self.trial_writes.append(((self.cf8 & 0xFC) + port - 0xCFC, value))
        request = (self.smm and port == 0xCFC and self.cf8 == SB | 0xA4
                   and value & 0x9C == 0x14 and not self.conf[SB][0xA4] & 0x10)
        super().out(u, port, size, value, user)
        if request:
            assert self.conf[SB][0xA0] & 3 == 2
            assert self.conf[SB][0x56] & 3 == 3
            assert self.conf[SB][0x80] & 0xC0 == 0xC0
            assert self.conf[SB][0x91] & 1 and not self.port61 & 3
            self.clock_edges += 1
            if self.clock_wake:
                self.clock_latch()
                self.conf[SB][0xA2] |= 0x10

    def write(self, u, access, address, size, value, user):
        scratch = self.sm_base + 0x8000 + self.clock_offset
        if self.smm and scratch <= address and address + size <= scratch + 8:
            return
        super().write(u, access, address, size, value, user)

    def enter(self):
        super().enter()
        if self.rtc_in and self.pending_on_smi:
            self.clock_latch()

    def step(self, u, address, size, user):
        if self.rtc_in and address == self.address('board_smm_command'):
            self.caller = {name: u.reg_read(reg) for name, reg in smm.REGS.items()}
        if self.rtc_in and address == self.address('board_clock_command') + 3:
            assert self.caller is not None
            for name, value in self.caller.items():
                if name not in ('EAX', 'EFLAGS', 'EIP', 'ESP'):
                    assert u.reg_read(smm.REGS[name]) == value, ('caller', name)
            assert u.reg_read(x.UC_X86_REG_ESP) == self.caller['ESP'] + 2
            assert u.reg_read(x.UC_X86_REG_EAX) & 0xFFFF0000 == self.caller['EAX'] & 0xFFFF0000
            assert u.reg_read(x.UC_X86_REG_EFLAGS) & ~1 == self.caller['EFLAGS'] & ~1
        super().step(u, address, size, user)


def main():
    build(PORT, 'build/tests/clock-check')
    smm.ROM = OUT / 'baios-m919.bin'
    rom = smm.ROM.read_bytes()
    assert len(rom) == 131072 and all(sum(rom[a:a+65536]) & 255 == 0 for a in (0, 65536))
    listing = Listing(smm.ROM.with_suffix('.lst'))
    window = listing.symbol('.window', 'board_clock_smm_entry')
    assert listing.symbol('.window_end', 'board_clock_smm_entry') - window == 18
    assert rom[window:window+18] == b'\x90' * 18
    config = json.loads((PORT / 'port.json').read_text())['platform']
    geometry = json.loads((PORT / 'port.json').read_text())['rom']
    invalid = bytearray(rom)
    invalid[geometry['reset_vector_offset']+1] ^= 1
    checksum = geometry['checksum_offset']
    invalid[checksum] = 0
    invalid[checksum] = (-sum(invalid)) & 255
    invalid_path = OUT / 'invalid-reset.bin'
    invalid_path.write_bytes(invalid)
    try:
        try:
            verify(PORT, invalid_path.resolve())
        except ValueError as error:
            assert 'reset target' in str(error), str(error)
        else:
            raise AssertionError('wrong reset target accepted with valid checksums')
    finally:
        invalid_path.unlink()
    image = PORT / 'build/diagnostics/CLOCKCHK.COM'
    image.parent.mkdir(parents=True, exist_ok=True)
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA']) / 'bin/NASM/nasm.exe')
    common = [nasm, '-w+error', '-f', 'bin', f'-DSMM_STATUS={smm.STATUS}',
              f'-DSTATE_KIB={config["state_kib"]}', f'-DNMI_POLICY={config["rtc_nmi_mask"]}']
    source = str(PORT / 'diagnostics/wake-check.asm')
    subprocess.run(common + ['-DCLOCK_TRIAL', '-o', str(image), source], check=True)
    subprocess.run(common + ['-o', str(OUT / 'WAKECHK.COM'), source], check=True)
    # The RTC-only diagnostic uses the SMM signature after the ROM header.
    assert hashlib.sha256((OUT / 'WAKECHK.COM').read_bytes()).hexdigest() == '6bc232a327baf707bf803de8b2d95fe468738f739049543183f2c98fb219a7c2'
    symbols = {key: listing.symbol(key) for key in ('RTC_INTERRUPT_LABEL', 'int70')}
    cases = [('wake-in-window', {'clock_wake': True}, 'C0'),
             ('Am5x86-wake', {'family': 'Am5x86', 'clock_wake': True}, 'C0'),
             ('Intel-DX2-wake', {'signature': 0x430, 'clock_wake': True}, 'C0'),
             ('BF-wake', {'bridge': 0x888A1060, 'clock_wake': True}, 'C0'),
             ('continued-before-alarm', {}, 'C6'),
             ('full-on-bit-already-set', {'a4': 0x11, 'clock_wake': True}, 'C0'),
             ('preserve-high-clock-fields', {'a4': 0x61, 'clock_wake': True}, 'C0'),
             ('PCI-half', {'a4': 0, 'clock_wake': True}, 'C0'),
             ('PCI-two-thirds', {'a4': 2, 'clock_wake': True}, 'C0'),
             ('PCI-encoding-3-preserved', {'a4': 3, 'clock_wake': True}, 'C0'),
             ('ISA-restored', {'sb56': 0xB1, 'clock_wake': True}, 'C0'),
             ('keyboard-restored', {'sb56': 0xB6, 'clock_wake': True}, 'C0'),
             ('RTC-owner-busy', {'rtc_b': 0x22}, 'C2'),
             ('pending-before-entry', {'pending': 1}, 'C2'),
             ('expired-after-arm', {'expire_after_arm': True}, 'C2'),
             ('expired-on-SMI', {'pending_on_smi': True}, 'C2'),
             ('protected', {'protected': True}, 'CX'),
             ('IF-clear', {'interrupts': False}, 'C2'),
             ('old-ROM-private-header', {'clock_header': False}, 'C1'),
             ('not-ready', {'status': 3}, 'C1'),
             ('wrong-host-live', {'wrong_host': True}, 'C1'),
             ('wrong-CPU-live', {'wrong_cpu': True}, 'C1'),
             ('wrong-bridge-live', {'wrong_bridge': True}, 'C1'),
             ('wrong-mode-live', {'wrong_mode': True}, 'C1'),
             ('no-SMI-delivery', {'no_smi': True}, 'C7'),
             ('no-alarm', {'no_alarm': True}, 'C4'),
             ('pending-at-cancel', {'clock_wake': True, 'pending_cancel': True}, 'C0'),
             ('undrained-at-cancel', {'clock_wake': True, 'pending_cancel': True, 'stuck_drain': True}, 'C5'),
             ('selector-policy', {'clock_wake': True, 'pic_selector': 0x0B}, 'C0')]
    rows = []
    for name, opts, expected in cases:
        opts = dict(opts)
        b = ClockBoard(clock_wake=opts.pop('clock_wake', False), pending_on_smi=opts.pop('pending_on_smi', False),
                       family=opts.pop('family', 'Intel486'), bridge=opts.pop('bridge', 0x886A1060),
                       signature=opts.pop('signature', None))
        assert b.startup() == 1
        b.conf[HB][0x50] = 0x85
        b.conf[SB][0xA0], b.conf[SB][0xA8] = 0x81, 0x42
        b.conf[SB][0xA4] = opts.pop('a4', 1)
        b.conf[SB][0x56] = opts.pop('sb56', 0xB2)
        b.conf[SB][0x80], b.conf[SB][0x91], b.conf[SB][0x92] = 0xD5, 0x6C, 0xA9
        if opts.pop('wrong_host', False):
            b.conf[HB][0] ^= 1
        if opts.pop('wrong_cpu', False):
            b.vendor = b'Unknown CPU!'
        if opts.pop('wrong_bridge', False):
            b.conf[SB][0] ^= 1
        if opts.pop('wrong_mode', False):
            b.conf[SB][0x76] |= 0x10
        b.deliver = not opts.pop('no_smi', False)
        if opts.pop('clock_header', True) is False:
            b.u.mem_write(0xE0008, b'OTHERROM')
        before = {offset: b.conf[SB][offset] for offset in (0xA0, 0xA4, 0xA8, 0x56, 0x80, 0x91, 0x92)}
        cf8 = b.cf8
        b.events.clear()
        b.trial_writes.clear()
        row = wake.check(image.read_bytes(), rom, symbols, smm.STATUS, config['state_kib'],
                         config['rtc_nmi_mask'], name, board=b, expected=expected, **opts)
        assert {offset: b.conf[SB][offset] for offset in before} == before
        assert b.conf[HB][0x50] == 0x85 and b.cf8 == cf8 and b.port61 == 0xA7
        requested = expected in ('C0', 'C6', 'C4', 'C5')
        assert b.clock_edges == int(requested), (name, b.clock_edges)
        if requested:
            clock_byte = (before[0xA4] & 0x73) | 4
            assert all(value & 3 == before[0xA4] & 3 for register,value in b.trial_writes if register==0xA4)
            entry = next(i for i, event in enumerate(b.events) if event == ('pci', SB, 0xA4, clock_byte))
            entry += 2
            release = b.events[entry+1:entry+8]
            assert release == [('pci', SB, 0x80, before[0x80]&0x3F),
                ('pci', SB, 0xA0, (before[0xA0]|0x34)&0xFC), ('pci', SB, 0xA3, 0xA0),
                ('pci', SB, 0xA3, 0x80), ('pci', SB, 0x56, before[0x56]),
                ('pci', SB, 0xA4, before[0xA4]&0xEF), ('pci', SB, 0xA4, before[0xA4]|0x10)], (name, release)
            assert b.trial_writes == [(0xA2,0),(0xA3,0xE0),(0xA3,0x80),
                (0x91,before[0x91]|1),(0x61,0xA4),(0x80,(before[0x80]&0x3F)|0xC0),
                (0xA0,((before[0xA0]|0x34)&0xFC)|2),(0x56,(before[0x56]&0xFC)|3),
                (0xA4,clock_byte),(0xA4,clock_byte&0xEF),(0xA4,clock_byte|0x10),
                (0x80,before[0x80]&0x3F),(0xA0,(before[0xA0]|0x34)&0xFC),
                (0xA3,0xA0),(0xA3,0x80),(0x56,before[0x56]),
                (0xA4,before[0xA4]&0xEF),(0xA4,before[0xA4]|0x10),
                (0xA4,before[0xA4]),(0x80,before[0x80]),(0x91,before[0x91]),(0x61,0xA7),
                (0xA0,before[0xA0]|0x34)], (name,b.trial_writes)
        row.update(boundaries=['B20','B21','B22','B23','B24'], clock_edges=b.clock_edges)
        rows.append(row)
    for name, args in [('wrong-source', dict(software=False, command=2)),
                       ('wrong-cookie', dict(cookie=smm.REPLY, command=2)),
                       ('unknown-command', dict(command=7))]:
        b = ClockBoard()
        assert b.startup() == 1
        before = bytes(b.conf[SB])
        b.direct_smi(**args)
        assert b.clock_edges == 0 and bytes(b.conf[SB][0xA4:0xA8]) == before[0xA4:0xA8]
        rows.append(dict(name=name, boundaries=['B20','B24'], clock_edges=0))
    result = dict(cases=rows, image=dict(size=len(rom), SUM32=f'{sum(rom):08X}', sha256=hashlib.sha256(rom).hexdigest()),
                  diagnostic=dict(size=image.stat().st_size, SUM32=f'{sum(image.read_bytes()):08X}'),
                  electrical_StopGrant_validation=False)
    result['integrity'] = dict(valid_image='pass', checksum_preserving_wrong_reset='rejected', boundaries=['B25'])
    result['source_sha256'] = {str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
        for path in (Path(__file__), PORT/'diagnostics/wake-check.asm', PORT/'src/hardware/smm.inc',
                     PORT/'src/hardware/clock-trial.inc', PORT/'src/hardware/board-core.inc',
                     PORT/'tools/test-wake-check.py', PORT/'tools/smm_activation_proof.py')}
    (OUT / 'result.json').write_text(json.dumps(result, indent=2)+'\n')
    print(f'CLOCKCHK: {len(rows)} composed checks PASS; ROM SUM32 {sum(rom):08X}')


if __name__ == '__main__':
    main()
