"""Bounded PIO negotiation and UMC timing checks through the compiled owners."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from m919.tools.ide_completeness_proof import Machine, x


class PIO(Machine):
    def __init__(self, image, kinds=('ata',)*4, *, requests=0, clock=0,
                 revision=0x0E, cycles=(240,)*4, legacy=None, failures=None,
                 controller=1, usable=1, bdf=0x91, device_id=0x673A1060, chs=False,
                 iordy=(True,)*4, advanced=(3,)*4, cycles_iordy=(120,)*4, valid=(True,)*4, device_count=4, generic=False, legacy_valid=False,
                 observe_pending=False):
        self.config = {0x80009100: device_id, 0x80009008: revision, 0x80009104: 1}
        self.config.update({0x80009140+n: int.from_bytes(bytes((0x55+n,))*4, 'little') for n in (0, 4, 8, 12)})
        self.legacy_valid=legacy_valid
        self.generic=generic
        self.iordy,self.advanced,self.cycles_iordy,self.valid=iordy,advanced,cycles_iordy,valid
        self.transfer_widths=[]
        self.events, self.device_modes = [], [0]*4
        self.accepted = [False]*4
        self.required_modes, self.untouched_timing = {}, {}
        self.observe_pending=observe_pending
        self.pending_baselines,self.pending_observations={},[]
        self.cycles, self.legacy, self.failures = cycles, legacy, failures or {}
        self.pending = [0]*4
        super().__init__(image, kinds, controller=controller, usable=usable, chs=chs, device_count=device_count)
        self.cpu.mem_write(self.base+0x1034, struct.pack('<H', bdf))
        if isinstance(requests,int):low,high=requests,0
        else:
            low=sum((v&3)<<(2*p) for p,v in enumerate(requests))
            high=sum((v>>2)<<p for p,v in enumerate(requests))
        if not generic:
            self.cpu.mem_write(self.base+0x60+20,bytes((low,clock)))
            self.cpu.mem_write(self.base+0x60+23,bytes((high,)))
        self.state.update(S_PIO_BLOCKED=0x1CA, S_PIO_REQUEST=0x1CB, S_PIO_LIMIT=0x1CC, S_PIO_MODE=0x1CE)

    def identify(self, position):
        data = bytearray(super().identify(position))
        for word, value in ((51, (self.legacy[position] if self.legacy is not None else 0) << 8),
                            (49,(0 if self.chs else 0x200)|(0x800 if self.iordy[position] else 0)),
                            (53,0 if (self.legacy is not None and not self.legacy_valid) or not self.valid[position] else 2),
                            (64,self.advanced[position]),(67,self.cycles[position]),(68,self.cycles_iordy[position])):
            struct.pack_into('<H', data, word*2, value)
        return bytes(data)

    def byte(self, offset):
        return self.config.get(0x80009100+(offset & ~3), 0) >> ((offset & 3)*8) & 255

    def timing(self, position):
        shift = 4 if position%2==0 else 0
        return ((self.byte(0x43) >> (6-position*2)) & 3,
                *((self.byte(base+(position >> 1)) >> shift) & 15 for base in (0x44, 0x48, 0x4C, 0x46, 0x4A, 0x4E)))

    def incoming(self, cpu, port, size, data):
        if 0xCFC <= port <= 0xCFF:
            return self.config.get(self.pci & ~3, 0) >> ((port-0xCFC)*8) & ((1 << (size*8))-1)
        task = self.task(port)
        if task is not None:
            _, pos, offset = task
            phase = self.phase[pos]
            if offset==0 and phase=='read':self.transfer_widths.append(('in',pos,size))
            if offset in (7, 8) and phase.startswith('mode-'):
                if self.observe_pending and phase=='mode-wait' and self.pending[pos]:
                    baseline=self.pending_baselines[pos]
                    assert not self.accepted[pos] and self.get('S_PIO_MODE',position=pos)==0
                    if not self.generic:assert baseline==expected(0)
                    assert (dict(self.config) if self.generic else self.timing(pos))==baseline
                    self.pending_observations.append(dict(position=pos,effective=0,host_unchanged=True,
                                                          accepted=False,polls_left=self.pending[pos]))
                if phase == 'mode-wait':
                    if self.pending[pos]:
                        self.pending[pos] -= 1
                        return 0x80
                    self.phase[pos] = 'idle'
                    self.accepted[pos] = True
                    self.events.append(('accepted', pos, self.device_modes[pos]))
                    return 0 if self.kinds[pos] == 'packet' else 0x40
                return {'mode-abort': 0x41, 'mode-busy': 0x80, 'mode-pending': 0x48}[phase]
            if offset == 1 and phase == 'mode-abort':
                return 4
            value = super().incoming(cpu, port, size, data)
            return value & ~0x40 if offset in (7, 8) and self.kinds[pos] == 'packet' else value
        return super().incoming(cpu, port, size, data)

    def outgoing(self, cpu, port, size, value, data):
        if 0xCFC <= port <= 0xCFF:
            address = self.pci & ~3
            shift, mask = (port-0xCFC)*8, (1 << (size*8))-1
            before = bytes(self.byte(n) for n in range(0x43, 0x50))
            self.config[address] = (self.config.get(address, 0) & ~(mask << shift)) | value << shift
            for peer, timing in self.untouched_timing.items():
                assert self.timing(peer) == timing, ('unrelated channel timing', peer)
            after = bytes(self.byte(n) for n in range(0x43, 0x50))
            self.events.append(('pci', (address & 255)+(port-0xCFC), value, size, before, after))
            return
        task = self.task(port)
        if task is not None:
            channel, pos, offset = task
            if offset==0 and self.phase[pos]=='write':self.transfer_widths.append(('out',pos,size))
            if offset == 8 and value & 4:
                self.events.append(('reset', channel, self.timing(channel*2), self.timing(channel*2+1)))
                for peer in (channel*2, channel*2+1):
                    self.device_modes[peer] = 0
                    self.accepted[peer] = False
            if offset == 7 and value in (0x91, 0xC6, 0x20, 0xC4, 0x30, 0xC5, 0xA0) and pos in self.required_modes:
                mode = self.required_modes[pos]
                assert self.accepted[pos], ('command before accepted negotiation', pos, value)
                assert self.device_modes[pos] == mode and (self.generic or self.timing(pos) == expected(mode))
            if offset == 7 and value == 0xEF:
                self.accepted[pos] = False
                if self.observe_pending:
                    self.pending_baselines[pos]=dict(self.config) if self.generic else self.timing(pos)
                assert self.regs[pos][1] == 3
                mode = self.regs[pos][2] & 7
                self.commands.append(('command', pos, value))
                self.events.append(('features', pos, mode))
                outcome = self.failures.get(pos)
                if outcome:
                    self.phase[pos] = 'mode-'+outcome
                else:
                    self.device_modes[pos], self.phase[pos], self.pending[pos] = mode, 'mode-wait', 2
                return
        return super().outgoing(cpu, port, size, value, data)


TRIPLES = ((3,6,11),(2,5,8),(1,4,5),(0,3,2),(0,3,0))


def expected(mode):
    a, b, c = TRIPLES[mode]
    return a, b, b, b, c, c, c


def modes(m):
    return [m.get('S_PIO_MODE', position=p) for p in range(4)]


def negotiated(m,wanted):
    """Bind decoded limits, emitted commands, device acceptance and publication."""
    for pos,want in enumerate(wanted):
        assert m.get('S_PIO_LIMIT',position=pos)==want,(pos,want,m.get('S_PIO_LIMIT',position=pos))
        assert ('features',pos,want) in m.events and ('accepted',pos,want) in m.events
        assert m.accepted[pos] and m.device_modes[pos]==m.get('S_PIO_MODE',position=pos)==want
    return dict(limits=[m.get('S_PIO_LIMIT',position=p) for p in range(len(wanted))],
                feature_modes=[list(row[1:]) for row in m.events if row[0]=='features'],
                accepted=m.accepted[:len(wanted)],device_modes=m.device_modes[:len(wanted)],
                effective=[m.get('S_PIO_MODE',position=p) for p in range(len(wanted))])


def assert_post_modes(m):
    m.call('post_debug_summary')
    for pos in range(4):
        if not (m.get('S_PRESENT',position=pos) or m.get('S_ATAPI',position=pos)):continue
        text=bytes(m.cpu.mem_read(0xB8000+(9+pos)*160,160))[::2]
        assert ('PIO'+str(m.get('S_PIO_MODE',position=pos))).encode() in text,(pos,text)


def qualification_cases(image):
    rows = []
    for options in ({}, {'requests': (1,)*4}, {'clock': 1}, {'revision': 12}, {'usable': 0}, {'controller': 0}, {'bdf': 0xFFFF}, {'device_id': 0x673B1060}):
        m = PIO(image, **options)
        original = bytes(m.byte(n) for n in range(0x43, 0x50))
        m.call('ata_detect_primary')
        allowed = not any(name in options for name in ('usable','controller','bdf','device_id'))
        want = [4]*4 if allowed and 'requests' not in options else [0]*4
        assert modes(m) == want, (options, modes(m))
        commands = [row for row in m.events if row[0] == 'features']
        assert bool(commands) == allowed, (options, commands)
        if allowed:
            assert all(m.timing(pos) == expected(want[pos]) for pos in range(4))
        else:
            assert bytes(m.byte(n) for n in range(0x43, 0x50)) == original
        if not allowed:
            m.public(0x80,0)
            assert modes(m)==[0]*4 and not any(row[0]=='features' and row[2]>0 for row in m.events)
            assert bytes(m.byte(n) for n in range(0x43,0x50))==original
        assert_post_modes(m)
        rows.append(dict(options=options, modes=want,effective_POST=True,
                         rejected_public_reset_safe=not allowed,all_revisions=allowed))
    return rows


def capability_cases(image):
    rows=[]
    cases=[({},4),({'cycles_iordy':(180,)*4},3),({'cycles_iordy':(181,)*4},2),
           ({'cycles_iordy':(121,)*4},3),({'cycles_iordy':(119,)*4},4),
           ({'cycles_iordy':(0,)*4},2),({'cycles_iordy':(65535,)*4},2),
           ({'iordy':(False,)*4},2),({'advanced':(0,)*4},2),
           ({'advanced':(1,)*4},3),({'advanced':(2,)*4},4),
           ({'advanced':(2,)*4,'cycles_iordy':(180,)*4},2),
           ({'valid':(False,)*4},0)]
    for options,want in cases:
        m=PIO(image,**options);m.call('ata_detect_primary')
        assert modes(m)==[want]*4,(options,modes(m))
        rows.append(dict(options=options,**negotiated(m,[want]*4)))
    for cycles,want in ((0,0),(65535,0),(384,0),(383,1),(241,1),(240,2),(120,2)):
        m=PIO(image,cycles=(cycles,)*4,iordy=(False,)*4);m.call('ata_detect_primary')
        assert modes(m)==[want]*4,(cycles,modes(m))
        rows.append(dict(without_IORDY_cycle_ns=cycles,**negotiated(m,[want]*4)))
    for invalid_cycle in (0,65535):
        m=PIO(image,legacy=(0,1,2,3),legacy_valid=True,cycles=(invalid_cycle,)*4,iordy=(False,)*4)
        m.call('ata_detect_primary');assert modes(m)==[0,1,2,0]
        rows.append(dict(valid67_fallback_legacy=True,cycle=invalid_cycle,**negotiated(m,[0,1,2,0])))
    m=PIO(image,legacy=(0,1,2,3));m.call('ata_detect_primary')
    assert modes(m)==[0,1,2,0]
    rows.append(dict(legacy=[0,1,2,3],**negotiated(m,[0,1,2,0])))
    return rows


def timing_cases(image):
    rows = []
    for revision,mode in ((revision,mode) for revision in (0x0E,0x0C) for mode in range(5)):
        m = PIO(image, requests=(mode+1,)*4,observe_pending=True,revision=revision)
        original = {offset: m.byte(offset) for offset in (0x40, 0x41, 0x42)}
        m.call('ata_detect_primary')
        assert modes(m) == [mode]*4
        assert m.device_modes == [mode]*4
        assert all(m.timing(pos) == expected(mode) for pos in range(4)), [m.timing(pos) for pos in range(4)]
        assert {offset: m.byte(offset) for offset in original} == original
        assert {row['position'] for row in m.pending_observations}==set(range(4))
        m.required_modes=dict(enumerate([mode]*4))
        for pos in range(4):
            accepted = m.events.index(('accepted', pos, mode))
            records = [row for row in m.events[accepted+1:] if row[0] == 'pci'][:7]
            writes = [row[1] for row in records]
            half = pos >> 1
            assert writes == [0x43, 0x44+half, 0x48+half, 0x4C+half, 0x46+half, 0x4A+half, 0x4E+half], writes
            before = bytearray(records[0][4])
            a, b, c = TRIPLES[mode]
            before[0] = (before[0] & ~(3 << (6-pos*2))) | a << (6-pos*2)
            for offset, value in ((0x44, b), (0x48, b), (0x4C, b), (0x46, c), (0x4A, c), (0x4E, c)):
                at, shift = offset+half-0x43, 4 if pos%2==0 else 0
                before[at] = (before[at] & ~(15 << shift)) | value << shift
            assert records[-1][5] == before, (pos, records[-1][5], before)
        assert all(m.accepted)
        assert not m.public(0x80,0x42,lba=17)
        assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(0,17)
        rows.append(dict(revision=revision,mode=mode, positions=4, full_register_recipe=True,accepted=m.accepted,
                         effective=modes(m),pending_observations=m.pending_observations,public_payload=True))
    return rows


def completion_cases(image):
    rows = []
    for outcome in ('abort', 'busy', 'pending'):
        m = PIO(image, failures={0: outcome})
        m.call('ata_detect_primary', count=20000000)
        assert m.get('S_PRESENT') == 1 and m.get('S_CAPACITY', 4) == 16*65536
        assert m.get('S_POLICY_INDEX') == 0 and m.get('S_PIO_REQUEST') == 0
        model = b'SAME MODEL PREFIX 0'.ljust(40)+b'\0'
        assert bytes(m.cpu.mem_read(m.base+m.state['S_MODEL'], 41)) == model
        assert m.cpu.mem_read(0x475, 1) == bytes((4 if outcome == 'abort' else 3,))
        assert m.timing(0) == expected(0)
        if outcome == 'abort':
            assert modes(m) == [0,4,4,4]
            assert m.get('S_PIO_BLOCKED') == 0
            assert not m.public(0x80, 0x42, lba=17)
            assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(0, 17)
            written = bytes((n*13+7) & 255 for n in range(512))
            m.cpu.mem_write(0x21000, written)
            assert not m.public(0x80, 0x43, lba=19) and bytes(m.written[0]) == written
        else:
            assert m.get('S_PIO_BLOCKED') == 1 and m.get('S_PRESENT', position=1) == 0
            assert not any(row[:2] == ('command', 1) for row in m.commands)
            before = list(m.commands)
            assert m.public(0x80, 0x42) and m.public(0x80, 0x43)
            assert m.commands == before
            assert not m.public(0x81, 0x42, lba=17)
            assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(2, 17)
            assert not m.public(0x82, 0x42, lba=17)
            assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(3, 17)
        assert bytes(m.cpu.mem_read(m.base+m.state['S_MODEL'], 41)) == model
        assert_post_modes(m)
        rows.append(dict(outcome=outcome, effective=modes(m),effective_POST=True, identity_retained=True,
                         model_and_numbering_retained=True, abort_io_completed=outcome == 'abort'))
    return rows


def pending_packet_case(image):
    from unicorn import UC_HOOK_CODE
    m = PIO(image, ('packet', 'ata', 'packet', 'ata'), failures={0: 'busy'})
    m.call('ata_detect_primary', count=20000000)
    assert m.get('S_ATAPI') == 1 and m.get('S_PIO_BLOCKED') == 1
    model = b'SAME MODEL PREFIX 0'.ljust(40)+b'\0'
    assert bytes(m.cpu.mem_read(m.base+m.state['S_MODEL'], 41)) == model
    assert m.get('S_PACKET_BYTES') == 12 and m.get('S_PACKET_CD') == 1
    assert m.get('S_POLICY_INDEX') == 0 and m.get('S_PIO_REQUEST') == 0
    assert m.cpu.mem_read(0x475, 1) == b'\x01'
    start, terminal = len(m.commands), []
    def handoff(cpu, address, size, data):
        terminal.append(address)
        cpu.emu_stop()
    hook = m.cpu.hook_add(UC_HOOK_CODE, handoff, None, 0x7C00, 0x7C00)
    try:
        for name, value in (('CS', 0xF000), ('FS', m.base >> 4), ('SS', 0), ('SP', 0x7000)):
            m.cpu.reg_write(getattr(x, 'UC_X86_REG_'+name), value)
        m.cpu.emu_start(0xF0000+m.listing.symbol('cd_boot'), 0, count=3000000)
    finally:
        m.cpu.hook_del(hook)
    assert terminal == [0x7C00] and bytes(m.cpu.mem_read(0x7C00, 4)) == b'CDOK'
    assert all(row[1] >= 2 for row in m.commands[start:] if row[0] in ('command', 'packet'))
    assert bytes(m.cpu.mem_read(m.base+m.state['S_MODEL'], 41)) == model
    assert m.cpu.mem_read(0x475, 1) == b'\x01'
    assert not m.public(0x80, 0x42, lba=17)
    assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(3, 17)
    return dict(blocked_packet_identity_retained=True, no_replacement_commands=True, other_channel_boots=True)


def reset_cases(image):
    rows = []
    for kinds in (('ata',)*4, ('ata', 'packet', 'ata', 'packet')):
        m = PIO(image, kinds, cycles_iordy=(120,180,180,120), chs=True)
        m.call('ata_detect_primary')
        assert modes(m) == [4,3,3,4]
        for channel in (0, 1):
            m.required_modes.update({p: mode for p, mode in enumerate((4,3,3,4)) if p//2 == channel})
            m.untouched_timing = {p: m.timing(p) for p in range(4) if p//2 != channel}
            start = len(m.events)
            assert not m.public(0x80+(channel*2 if kinds[1] == 'ata' else channel), 0)
            reset = next(row for row in m.events[start:] if row[0] == 'reset')
            assert reset[1] == channel and reset[2:] == (expected(0), expected(0)), reset
            assert modes(m) == m.device_modes == [4,3,3,4]
            drive, pos = (0x81+channel*2, channel*2+1) if kinds[1] == 'ata' else (0x80+channel, channel*2)
            for count, command in ((1, 0x20), (3, 0xC4)):
                assert not m.public(drive, 0x42, lba=41, count=count)
                assert ('command', pos, command) in m.commands
                assert bytes(m.cpu.mem_read(0x21000, count*512)) == m.payload(pos, 41, count)
        if kinds[1] == 'packet':
            m.images[1] = bytes(len(m.images[1]))
            terminal = []
            from unicorn import UC_HOOK_CODE
            def handoff(cpu, address, size, data):
                terminal.append(address)
                cpu.emu_stop()
            hook = m.cpu.hook_add(UC_HOOK_CODE, handoff, None, 0x7C00, 0x7C00)
            try:
                m.cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
                m.cpu.reg_write(x.UC_X86_REG_FS, m.base >> 4)
                m.cpu.reg_write(x.UC_X86_REG_SS, 0)
                m.cpu.reg_write(x.UC_X86_REG_SP, 0x7000)
                m.cpu.emu_start(0xF0000+m.listing.symbol('cd_boot'), 0, count=3000000)
            finally:
                m.cpu.hook_del(hook)
            assert terminal == [0x7C00]
            assert bytes(m.cpu.mem_read(0x7C00, 4)) == b'CDOK'
        rows.append(dict(kinds=kinds, restored=modes(m), ordinary_multiple_packet=True,
                         restore_before_commands=True, unrelated_host_timing_preserved=True))
    m = PIO(image, failures={0: 'busy'})
    m.call('ata_detect_primary', count=20000000)
    m.failures.clear()
    m.required_modes={0:4,2:4,3:4}
    assert not m.public(0x80, 0)
    assert m.get('S_PIO_BLOCKED') == 0 and m.get('S_PRESENT') == 1
    assert m.accepted[0] and m.device_modes[0]==m.get('S_PIO_MODE')==4
    assert modes(m)==m.device_modes==[4,0,4,4] and all(m.accepted[p] for p in (0,2,3))
    assert not m.public(0x80, 0x42, lba=17)
    assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(0,17)
    rows.append(dict(blocked_channel_reset_reopens=True,accepted=m.accepted,device_modes=m.device_modes,
                     effective=modes(m),required_modes=m.required_modes,acceptance_before_data=True,payload=True))
    return rows


def policy_cases(image):
    from unicorn import UC_HOOK_CODE,UC_HOOK_MEM_WRITE
    class Screen(PIO):
        def __init__(self,*args,**kwargs):
            super().__init__(*args,**kwargs)
            self.save_boundary=None;self.failed_save_resumed=False
            at=self.base+self.state['U_CHIP_SCREEN']
            assert self.state['U_CHIP']+self.state['CHIP_SIZE']==self.state['U_CHIP_SCREEN']
            def entry(cpu,address,size,data):
                assert cpu.reg_read(x.UC_X86_REG_SI)==self.state['U_CHIP']
                # Valid submenu plus adjacent popup state must survive either save result.
                self.put('U_CHIP_SCREEN',5);self.put('U_CHIP_VALUE',0xA6)
                self.save_boundary=bytes(cpu.mem_read(at,2))
            def adjacent_write(cpu,access,address,size,value,data):
                if self.save_boundary is not None:
                    raise AssertionError(('packed save wrote adjacent Setup state',hex(address),size,value))
            self.cpu.hook_add(UC_HOOK_CODE,entry,None,0xF0000+self.listing.symbol('chipset_packed_save'),0xF0000+self.listing.symbol('chipset_packed_save'))
            self.cpu.hook_add(UC_HOOK_MEM_WRITE,adjacent_write,None,at,at+1)
        def interrupt(self, cpu, number, data):
            if number==0x16 and cpu.reg_read(x.UC_X86_REG_AH)==0 and self.save_boundary is not None:
                assert bytes(cpu.mem_read(self.base+self.state['U_CHIP_SCREEN'],2))==self.save_boundary
                assert self.failed_write==0x71 and self.cmos[0x38]==0 and self.cmos[0x71]==0
                self.failed_save_resumed=True;self.save_boundary=None
            if (number == 0x16 and cpu.reg_read(x.UC_X86_REG_AH) == 0 and self.keys and
                    self.get('U_PAGE') == 1 and self.get('U_FIELD') == 11 and self.keys[0] == 0x4800):
                labels = [bytes(cpu.mem_read(0xB8000+row*160+26*2, 10))[::2].strip()
                          for row in range(10,16)]
                assert labels == [b'0',b'1',b'2',b'3',b'4',b'Auto'], labels
                self.popup_seen = True
            return super().interrupt(cpu, number, data)
    rows = []
    for action in ('cancel', 'save', 'failed-save'):
        m = Screen(image, requests=0, clock=0)
        m.cpu.mem_write(m.base+0x60, bytes.fromhex('A0010070900000A255070F6E010F01FCA9870F0100000000'))
        m.cpu.mem_write(m.base+0x60+21,b'\x01') # Opaque old selector remains saved, without affecting PIO.
        original = bytes(m.cpu.mem_read(m.base+0x60, 24))
        for policy in range(4):
            m.cpu.mem_write(m.base+0xA01+policy*12, b'\x30')
        devices = bytes(m.cpu.mem_read(m.base+0xA00, 51))
        ports = bytes(m.cpu.mem_read(m.base+m.state['C_PORTS'], 8))
        keys = [0x5000, 9, 0x5000, 0x5000]
        for policy in range(4):
            keys += [13]+[0x5000]*11
            keys += [13,0x4800,0x4800,13] if policy==2 else [0x4D00]*(0,3,4,5)[policy]
            keys += [27]+([0x5000] if policy < 3 else [])
        keys += [27]
        keys += [27, ord('y')] if action == 'cancel' else [0x4400, ord('y')]
        if action=='failed-save':
            m.failed_write=0x71
            keys += [27,27,27,ord('y')]
        m.keys = keys
        m.call('setup_main', count=20000000)
        assert not m.keys and not m.io and m.popup_seen
        assert b'IDE Timing Clock' not in image.read_bytes()
        assert bytes(m.cpu.mem_read(m.base+0x60, 24)) == original
        draft = bytes(m.cpu.mem_read(m.base+m.state['U_CHIP'], 24))
        assert draft[:20] == original[:20] and draft[20:22] == b'\x4c\x01' and draft[23]==12, draft.hex()
        if action == 'cancel':
            assert not m.writes and not m.reset
        elif action=='failed-save':
            assert not m.reset and m.failed_save_resumed and (0x71,ord('W')) in m.writes
            assert (0x38,ord('B')) not in m.writes
        else:
            assert m.reset and m.cmos[0x33:0x36] == bytes.fromhex('3402ca')
            assert m.save_boundary==b'\x05\xa6'
            assert bytes(m.cpu.mem_read(m.base+m.state['U_CHIP_SCREEN'],2))==m.save_boundary
            masks = bytes.fromhex('F0010170900301FFFF070F7F010F01FCFFFF0F01FF01030F')
            bits = [(v >> b) & 1 for v, mask in zip(draft, masks) for b in range(8) if mask >> b & 1]
            packed = bytearray(b'W\0'+sum(v << n for n, v in enumerate(bits)).to_bytes(13, 'little'))
            packed[1] = -sum(packed) & 255
            assert m.cmos[0x71:0x80] == packed
            restored = PIO(image)
            restored.cmos[:] = m.cmos
            restored.call('settings_load')
            assert bytes(restored.cpu.mem_read(m.base+0x60, 24)) == draft
            assert bytes(restored.cpu.mem_read(m.base+0xA00, 51)) == devices
            assert bytes(restored.cpu.mem_read(m.base+m.state['C_PORTS'], 8)) == ports
            restored.call('ata_detect_primary')
            assert modes(restored) == [4,2,3,4]
            restored.call('post_debug_summary')
            for pos, mode in enumerate(modes(restored)):
                text = bytes(restored.cpu.mem_read(0xB8000+(9+pos)*160, 160))[::2]
                assert ('PIO'+str(mode)).encode() in text, text
                assert not restored.public(0x80+pos, 0x42, lba=17)
                assert bytes(restored.cpu.mem_read(0x21000, 512)) == restored.payload(pos, 17)
        if action=='save':
            assert len(bits)==92
            old=draft[:23]+b'\0'
            def pack(chip):
                bits=[(v>>b)&1 for v,mask in zip(chip,masks) for b in range(8) if mask>>b&1]
                raw=bytearray(b'W\0'+sum(v<<n for n,v in enumerate(bits)).to_bytes(13,'little'))
                raw[1]=-sum(raw)&255
                return raw
            old_record=pack(old)
            assert old_record[2:13]==packed[2:13],'Old88-bit prefix moved'
            for invalid in (None,6,7):
                for pos in ((0,) if invalid is None else range(4)):
                    chip=bytearray(old)
                    if invalid is not None:
                        chip[20]=(chip[20]&~(3<<(2*pos)))|((invalid&3)<<(2*pos))
                        chip[23]|=1<<pos
                    fresh=PIO(image);fresh.cmos[:]=m.cmos;fresh.cmos[0x71:0x80]=pack(chip)
                    fresh.writes.clear();fresh.call('settings_load')
                    assert not fresh.writes
                    actual=bytes(fresh.cpu.mem_read(fresh.base+0x60,24))
                    assert actual==(bytes(chip) if invalid is None else b'\0\1\0\x40'+bytes(20)),(invalid,pos,actual.hex())
                    assert bytes(fresh.cpu.mem_read(fresh.base+0xA00,51))==devices
                    assert bytes(fresh.cpu.mem_read(fresh.base+fresh.state['C_PORTS'],8))==ports
                    if invalid is None:
                        fresh.call('ata_detect_primary');assert modes(fresh)==[4,2,4,0]
                    else:assert fresh.get('C_VALID')==0
            rows.append(dict(old88_bit_prefix=True,old_zero_high_bits=True,invalid6_7_all_positions_rejected=True,unrelated_records_retained=True))
        rows.append(dict(action=action, four_requests=[0,3,4,5], opaque_byte21_preserved=True, real_popup=True,
                         packed_save_adjacent_state_untouched=action!='cancel',
                         failed_save_resumes_Setup=m.failed_save_resumed))
    # Changing a former mode4 request to0/1 must clear its appended high bit.
    for steps,request in ((2,1),(3,2)):
        m=Screen(image,requests=(5,)*4)
        m.keys=[0x5000,9,0x5000,0x5000,13]+[0x5000]*11+[0x4D00]*steps+[0x4400,ord('y')]
        m.call('setup_main',count=12000000);assert m.reset and not m.keys
        fresh=PIO(image);fresh.cmos[:]=m.cmos;fresh.call('settings_load')
        assert fresh.cpu.mem_read(fresh.base+0x60+23,1)==b'\x0e'
        assert fresh.cpu.mem_read(fresh.base+0x60+20,1)==bytes((0x54|request,))
        fresh.call('ata_detect_primary');assert modes(fresh)==[request-1,4,4,4]
        rows.append(dict(mode4_to_request=request,high_bit_cleared=True,real_UI_save_reload=True))
    return rows


def legacy_policy_case(image):
    m = PIO(image,requests=(5,)*4)
    before = bytes(m.cmos)
    m.call('chipset_record_save', SI=m.state['C_CHIP'])
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert m.cmos[0x33:0x36] == bytes(3) and m.cmos[0x69] == 0x57
    assert bytes(m.cpu.mem_read(m.base+0x60+20, 4)) == bytes(4)
    assert m.cmos[0x40:0x69] == before[0x40:0x69]
    m.writes.clear()
    m.call('settings_load')
    assert not m.writes and bytes(m.cpu.mem_read(m.base+0x60+20, 4)) == bytes(4)
    return dict(legacy_standalone_keeps_format=True, new_fields_zero=True, unrelated_owners_retained=True)


def run(image):
    return dict(qualification=qualification_cases(image), capability=capability_cases(image),
                timing=timing_cases(image), completion=completion_cases(image), packet_pending=pending_packet_case(image), reset=reset_cases(image),
                policy=policy_cases(image), legacy_policy=legacy_policy_case(image))


def limit_cases(image):
    from shared.tools.rom import build
    port=Path(__file__).resolve().parents[1]
    rows=[]
    for maximum in (0,2,3,4):
        variant=image
        if maximum!=4:
            directory=port/'build/tests/pipeline-pio'/f'cap{maximum}'/'image'
            variant=Path(build(port,str(directory),(f'BOARD_ATA_PIO_MAX={maximum}',))['path'])
        for request in (0,1,3,4,5):
            m=PIO(variant,requests=(request,)*4)
            m.call('ata_detect_primary')
            want=min(maximum,4 if request==0 else request-1)
            assert modes(m)==m.device_modes==[want]*4,(maximum,request,modes(m))
            assert not m.public(0x80,0)
            assert modes(m)==m.device_modes==[want]*4
            assert_post_modes(m)
            rows.append(dict(port_max=maximum,request=request,effective=want,reset_restored=True,effective_POST=True))
    m=PIO(image,requests=(5,)*4,cycles_iordy=(180,120,180,120))
    m.call('ata_detect_primary');m.required_modes=dict(enumerate((3,4,3,4)))
    assert negotiated(m,[3,4,3,4])
    assert not m.public(0x80,0)
    assert negotiated(m,[3,4,3,4])
    assert not m.public(0x80,0x42,lba=17)
    assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(0,17)
    rows.append(dict(explicit_request=4,device_limits=[3,4,3,4],reset_restored=True,payload=True,
                     **negotiated(m,[3,4,3,4])))
    return rows


def generic_limit_cases(image,port):
    """Compile the primary-only ceiling contrast inside its owning port."""
    assert port=='pb430'
    from shared.tools.rom import build
    from pb430.tools.build import selected_vga,validate
    port=Path(__file__).resolve().parents[2]/'pb430'
    directory=port/'build/tests/pipeline-pio/cap3/image'
    variant=Path(build(port,str(directory),('PB430_VGA60','BOARD_ATA_PIO_MAX=3'))['path'])
    raw=variant.read_bytes();variant.write_bytes(selected_vga()+raw[32768:])
    integrity=validate(variant)
    rows=[]
    for maximum,path in ((4,image),(3,variant)):
        m=PIO(path,('ata','ata',None,None),device_count=2,generic=True)
        config=dict(m.config);m.call('ata_detect_primary');m.required_modes={0:maximum,1:maximum}
        assert [m.get('S_PIO_LIMIT',position=p) for p in (0,1)]==[4,4]
        for reset in (False,True):
            if reset:assert not m.public(0x80,0)
            assert all(m.accepted[p] and m.device_modes[p]==m.get('S_PIO_MODE',position=p)==maximum for p in (0,1))
        assert not m.public(0x80,0x42,lba=17)
        assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(0,17) and m.config==config
        rows.append(dict(port='pb430',port_max=maximum,device_limits=[4,4],accepted=[maximum]*2,effective=[maximum]*2,
                         image_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                         compiled_variant=integrity if maximum==3 else None,
                         reset_restored=True,public_payload=True,host_unchanged=True))
    return rows


def inventory_cases(image):
    rows=[]
    for kinds,enabled in (((None,)*4,(1,)*4),(('ata',None,None,None),(1,)*4),
                          ((None,'ata',None,'ata'),(1,)*4),(('ata',)*4,(1,)*4),
                          (('ata','packet','ata','ata'),(0,1,1,1))):
        m=PIO(image,kinds,cycles_iordy=(120,180,180,120))
        m.put('C_HDD',enabled[0]);m.put('C_SLAVE',enabled[1]);m.cpu.mem_write(m.base+0xA31,bytes(enabled[2:]))
        m.call('ata_detect_primary')
        published=[]
        for pos,kind in enumerate(kinds):
            if kind is None or not enabled[pos]:continue
            assert m.get('S_POLICY_INDEX',position=pos)==pos
            assert m.get('S_PIO_MODE',position=pos)==(4,3,3,4)[pos]
            model=bytes(m.cpu.mem_read(m.base+pos*512+m.state['S_MODEL'],41))
            assert model==('SAME MODEL PREFIX '+str(pos)).ljust(40).encode()+b'\0'
            if kind=='ata' and enabled[pos]:published.append(pos)
        assert m.cpu.mem_read(0x475,1)==bytes((len(published),))
        for n,pos in enumerate(published):
            assert not m.public(0x80+n,0x42,lba=17)
            assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(pos,17)
        rows.append(dict(kinds=kinds,enabled=enabled,published=published,physical_modes=modes(m)))
    return rows


def width_cases(image):
    rows=[]
    for width in (0,1):
        m=PIO(image,requests=(5,)*4)
        m.cpu.mem_write(m.base+0x60+13,bytes((15 if width else 0,)))
        m.call('ata_detect_primary');assert modes(m)==[4]*4
        assert m.device_modes==[4]*4 and all(m.accepted)
        assert all(m.timing(p)==expected(4) for p in range(4))
        m.required_modes=dict(enumerate([4]*4))
        for count in (1,3):
            for write in (False,True):
                payload=bytes((i*13+count)&255 for i in range(count*512))
                if write:m.cpu.mem_write(0x21000,payload)
                m.io.clear();m.transfer_widths.clear()
                assert not m.public(0x80,0x43 if write else 0x42,lba=41,count=count)
                assert (bytes(m.written[0])==payload if write else bytes(m.cpu.mem_read(0x21000,count*512))==m.payload(0,41,count))
                transfers=m.transfer_widths
                assert transfers and {row[2] for row in transfers}=={4 if width else 2},transfers[:5]
                assert all(m.timing(p)==expected(4) for p in range(4))
                rows.append(dict(PIO=4,width=32 if width else 16,count=count,write=write,payload=True,
                                 accepted=m.accepted,device_modes=m.device_modes,effective=modes(m),
                                 host_tuples=[m.timing(p) for p in range(4)],acceptance_before_data=True))
    return rows


def precommand_cases(image,port):
    """An old command error is idle; an unfinished phase still blocks the channel."""
    from unicorn import UC_HOOK_CODE
    class PreviousCommand(PIO):
        def __init__(self, image, outcome, **options):
            self.old_status={}
            self.outcome=outcome
            self.inject=True
            self.optional_aborts=[]
            super().__init__(image,('ata','packet',None,None),**options)
            def entry(cpu,address,size,data):
                position=((cpu.reg_read(x.UC_X86_REG_FS)<<4)-self.base)//512
                if self.inject and position==0 and outcome in ('busy','drq'):
                    self.old_status[position]=0x80 if outcome=='busy' else 0x48
                elif self.inject and self.kinds[position]=='packet':
                    self.old_status[position]=0x41
            address=0xF0000+self.listing.symbol('ide_pio_restore')
            self.cpu.hook_add(UC_HOOK_CODE,entry,None,address,address)
        def incoming(self,cpu,port,size,data):
            task=self.task(port)
            if task is not None:
                _,position,offset=task
                if position in self.old_status:
                    if offset in (7,8):return self.old_status[position]
                    if offset==1:return 4
            return super().incoming(cpu,port,size,data)
        def outgoing(self,cpu,port,size,value,data):
            task=self.task(port)
            if task is not None:
                channel,position,offset=task
                if offset==8 and value&4:
                    for peer in (channel*2,channel*2+1):self.old_status.pop(peer,None)
                if offset==7:
                    self.old_status.pop(position,None) # A new command clears the old ERR.
                    if value==0xC6 and self.kinds[position]=='ata':
                        self.commands.append(('command',position,value))
                        self.optional_aborts.append(position)
                        self.old_status[position]=0x41
                        self.phase[position]='idle'
                        return
            return super().outgoing(cpu,port,size,value,data)
    rows=[]
    for outcome in ('old-error','abort','busy','drq'):
        m=PreviousCommand(image,outcome,device_count=4 if port=='m919' else 2,generic=port!='m919',
                          failures={0:'abort'} if outcome=='abort' else None)
        original=dict(m.config)
        m.call('ata_detect_primary',count=20000000)
        assert m.optional_aborts and m.get('S_PRESENT')==1
        if outcome in ('busy','drq'):
            assert m.get('S_PIO_BLOCKED')==1 and m.get('S_PIO_MODE')==0
            assert not any(event[:2]==('features',0) for event in m.events)
            assert not m.accepted[0] and (m.generic or m.timing(0)==expected(0))
            before=list(m.commands)
            assert m.public(0x80,0x42,lba=17) and m.commands==before
        else:
            wanted=0 if outcome=='abort' else 4
            assert m.get('S_PIO_MODE')==wanted and m.get('S_PIO_BLOCKED')==0
            assert ('features',0,4) in m.events
            assert m.get('S_ATAPI',position=1)==1 and m.get('S_PIO_MODE',position=1)==4
            assert m.accepted[1] and ('accepted',1,4) in m.events
            if wanted:assert m.accepted[0] and m.device_modes[0]==4
            else:assert not m.accepted[0] and (m.generic or m.timing(0)==expected(0))
            assert not m.public(0x80,0x42,lba=17)
            assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(0,17)
        m.inject=False
        m.failures.clear()
        assert not m.public(0x80,0)
        assert m.get('S_PIO_BLOCKED')==0 and m.get('S_PIO_MODE')==m.device_modes[0]==4 and m.accepted[0]
        assert not m.public(0x80,0x42,lba=19)
        assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(0,19)
        if m.generic:assert m.config==original
        rows.append(dict(port=port,outcome=outcome,optional_C6_aborted=True,
                         packet_previous_ERR_accepted=outcome in ('old-error','abort'),
                         real_EF_ABRT_safe=outcome=='abort',pending_no_replacement=outcome in ('busy','drq'),
                         public_reset_PIO4_and_payload=True,generic_host_unchanged=m.generic))
    return rows


def shared_port_cases(image,port='m919',gaps_only=False):
    rows=[]
    paths={port:image}
    for port,path in paths.items():
        count=4 if port=='m919' else 2
        scenarios=[] if gaps_only else [((None,)*count,(120,)*4),(('ata',)+(None,)*(count-1),(120,)*4),(('ata',)*count,(120,)*4)]
        if port!='m919':scenarios.extend([((None,'ata'),(120,180,120,120)),(('ata','ata'),(180,120,120,120))])
        for kinds,cycles in scenarios:
            m=PIO(path,kinds+(None,)*(4-count),device_count=count,generic=port!='m919',cycles_iordy=cycles)
            config=dict(m.config)
            m.call('ata_detect_primary')
            published=[p for p in range(count) if kinds[p]=='ata']
            wanted={p:3 if cycles[p]==180 else 4 for p in published}
            m.required_modes=wanted
            assert m.cpu.mem_read(0x475,1)==bytes((len(published),)),(port,kinds)
            for p in published:
                assert m.get('S_PIO_MODE',position=p)==m.device_modes[p]==wanted[p],(port,p,modes(m),m.events)
                assert m.accepted[p] and ('accepted',p,wanted[p]) in m.events
                if port=='m919':assert m.get('S_POLICY_INDEX',position=p)==p
                else:assert m.get('S_ATA_DEVICE',position=p)==p*0x10
                assert m.get('S_CAPACITY',4,position=p)==(16+p)*65536
                assert bytes(m.cpu.mem_read(m.base+p*512+m.state['S_MODEL'],41))==('SAME MODEL PREFIX '+str(p)).ljust(40).encode()+b'\0'
            if port!='m919':assert m.config==config,'Generic host timing changed'
            assert_post_modes(m)
            for drive,p in enumerate(published):
                assert not m.public(0x80+drive,0)
                assert all(m.accepted[n] and m.get('S_PIO_MODE',position=n)==m.device_modes[n]==wanted[n] for n in published)
                assert not m.public(0x80+drive,0x42,lba=17)
                assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(p,17)
            rows.append(dict(port=port,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),kinds=kinds,
                             compiled_entries={name:hex(m.listing.symbol(name)) for name in ('ata_detect_primary','ide_pio_identify','ide_pio_restore','ata_reset','int13')},
                             accepted=m.device_modes[:count],effective=[m.get('S_PIO_MODE',position=p) for p in range(count)],
                             published=published,models_capacities_physical_selectors=True,compact_public_numbering=True,
                             unequal_peer_modes=len(set(wanted.values()))>1,
                             public_reset_read=True,actual_POST_PIO=True,generic_host_unchanged=port!='m919'))
    return rows


def generic_guard_cases(image,port):
    """Primary-only generic guards, through actual disk and packet entry points."""
    assert port in ('pb430','mp386','presario-800')
    from shared.tools.ram_proof import constants
    from unicorn import UC_HOOK_CODE
    cd=constants(Path(__file__).resolve().parents[2]/'shared/src/firmware/cdboot.inc')
    def machine():
        m=PIO(image,('ata','packet',None,None),device_count=2,generic=True,
              cycles_iordy=(180,120,120,120),observe_pending=port=='pb430')
        m.state.update(cd)
        return m
    def metadata(m):
        return dict(count=m.cpu.mem_read(0x475,1)[0],records=[dict(
            model=bytes(m.cpu.mem_read(m.base+p*512+m.state['S_MODEL'],41)).hex(),
            capacity=m.get('S_CAPACITY',4,position=p),present=m.get('S_PRESENT',position=p),
            packet=m.get('S_ATAPI',position=p),packet_bytes=m.get('S_PACKET_BYTES',position=p),
            packet_CD=m.get('S_PACKET_CD',position=p)) for p in (0,1)])
    def packet_boot(m):
        terminal=[]
        def handoff(cpu,address,size,data):terminal.append(address);cpu.emu_stop()
        hook=m.cpu.hook_add(UC_HOOK_CODE,handoff,None,0x7C00,0x7C00)
        try:
            for name,value in (('CS',0xF000),('FS',m.base>>4),('SS',0),('SP',0x7000)):
                m.cpu.reg_write(getattr(x,'UC_X86_REG_'+name),value)
            m.cpu.emu_start(0xF0000+m.listing.symbol('cd_boot'),0,count=3000000)
        finally:m.cpu.hook_del(hook)
        assert terminal==[0x7C00] and bytes(m.cpu.mem_read(0x7C00,4))==b'CDOK'
    def blocked_entries(m,before):
        commands=list(m.commands)
        assert m.public(0x80,0x42,lba=17) and m.public(0x80,0x43,lba=19)
        assert m.get('S_STATUS')==0x80
        m.put('CD_DEVICE',0x10)
        m.call('cd_packet_command')
        assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1 and m.get('CD_STATUS')==0x80
        assert m.commands==commands,'Pending primary received a replacement command, including A0'
        assert metadata(m)==before,'Guard changed model/capacity/count/packet metadata'
    rows=[]
    if port=='pb430':
        m=machine();m.failures[0]='abort';m.call('ata_detect_primary',count=20000000)
        before=metadata(m)
        assert before['count']==1 and before['records'][0]['present']==1 and before['records'][1]['packet']==1
        assert m.get('S_PIO_BLOCKED')==0 and m.get('S_PIO_MODE')==0 and m.get('S_PIO_MODE',position=1)==4
        assert not m.public(0x80,0x42,lba=17)
        assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(0,17)
        packet_boot(m);assert metadata(m)==before
        rows.append(dict(port=port,outcome='ABRT',metadata=before,ATA_payload=True,packet_payload=True,
                         effective=[m.get('S_PIO_MODE',position=p) for p in (0,1)],blocked=False))
    for outcome in (('busy','pending') if port=='pb430' else ('injected-pending',)):
        m=machine();m.call('ata_detect_primary');before=metadata(m);config=dict(m.config)
        assert before['count']==1 and before['records'][0]['present']==1 and before['records'][1]['packet']==1
        if outcome=='injected-pending':
            # Producer is proved on PB430; these ports exercise their compiled generic entry branch.
            m.put('S_PIO_BLOCKED',1)
        else:
            m.failures[0]=outcome
            start=len(m.events)
            m.call('int13',iret=True,AX=0,DX=0x80,count=20000000)
            assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1
            assert m.cpu.reg_read(x.UC_X86_REG_AH)==0x80
            assert ('features',0,3) in m.events[start:]
            assert m.phase[0]=='mode-'+outcome and not m.accepted[0]
        assert m.get('S_PIO_BLOCKED')==1
        blocked_entries(m,before)
        m.failures.clear();m.required_modes={0:3,1:4}
        assert not m.public(0x80,0)
        assert m.get('S_PIO_BLOCKED')==0 and m.device_modes[:2]==[3,4]
        assert [m.get('S_PIO_MODE',position=p) for p in (0,1)]==[3,4]
        assert all(m.accepted[p] for p in (0,1))
        if port=='pb430':assert {row['position'] for row in m.pending_observations}=={0,1}
        assert not m.public(0x80,0x42,lba=17)
        assert bytes(m.cpu.mem_read(0x21000,512))==m.payload(0,17)
        if port=='pb430':packet_boot(m)
        assert metadata(m)==before and m.config==config
        rows.append(dict(port=port,outcome=outcome,metadata=before,public_ATA_read_write_rejected=True,
                         actual_packet_entry_rejected=True,no_replacement_command_or_A0=True,
                         reset_reopened=True,accepted_and_effective=[3,4],reset_ATA_payload=True,
                         reset_packet_payload=port=='pb430',generic_host_unchanged=True,
                         acceptance_before_data=True,pending_observations=m.pending_observations))
    for row in rows:
        row['image_sha256']=hashlib.sha256(image.read_bytes()).hexdigest()
        row['compiled_entries']={name:hex(m.listing.symbol(name)) for name in ('ide_pio_guard','ide_pio_cd_guard','ata_reset','int13','cd_packet_command')}
    return rows


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image',type=Path)
    parser.add_argument('--case',action='append',choices=('qualification','capability','limits','generic-limits','timing','completion','packet-pending','reset','inventory','policy','legacy-policy','width','shared-ports','shared-port-gaps','generic-guards','precommand'))
    parser.add_argument('--port',choices=('m919','pb430','mp386','presario-800'),default='m919')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();args.image=args.image.resolve()
    checks={'qualification':qualification_cases,'capability':capability_cases,'limits':limit_cases,
            'timing':timing_cases,'completion':completion_cases,'packet-pending':pending_packet_case,
            'reset':reset_cases,'inventory':inventory_cases,'policy':policy_cases,'legacy-policy':legacy_policy_case,
            'width':width_cases,'shared-ports':lambda p:shared_port_cases(p,args.port),
            'shared-port-gaps':lambda p:shared_port_cases(p,args.port,gaps_only=True),
            'generic-guards':lambda p:generic_guard_cases(p,args.port)}
    checks['generic-limits']=lambda p:generic_limit_cases(p,args.port)
    checks['precommand']=lambda p:precommand_cases(p,args.port)
    result={'image_sha256':hashlib.sha256(args.image.read_bytes()).hexdigest()}
    selected=args.case or [name for name in checks if name!='shared-port-gaps' and (name!='generic-guards' or args.port!='m919')
                          and (name!='generic-limits' or args.port=='pb430')]
    for name in selected:
        result[name]=checks[name](args.image)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(result,indent=2)+'\n')
        print(name,'PASS',flush=True)
