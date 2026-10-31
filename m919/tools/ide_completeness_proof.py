"""Execute the shared four-position ATA owners against independent devices."""
import argparse
import json
from pathlib import Path
import re
import struct
import sys
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_CODE, UC_HOOK_MEM_READ
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.tools.ram_proof import Listing, constants
from shared.tools.cd_fixture import disc


class Machine:
    base = 0x80000

    def __init__(self, image, kinds=('ata',)*4, enabled=(1,)*4, controller=1, usable=1, chs=False, device_count=4):
        self.listing = Listing(image.with_suffix('.lst'))
        self.state = constants(ROOT/'shared/src/pc/state.inc')
        self.state.update(constants(ROOT/'shared/src/setup/layout.inc'))
        for name, off in re.findall(r'%define\s+(\w+)\s+STATE_BASE\s*\+\s*(\d+)',
                                    (ROOT/'shared/src/pc/state.inc').read_text()):
            self.state[name] = self.state['STATE_BASE']+int(off)
        self.device_count=device_count
        if device_count==4:self.state.update(C_IDE=0xA00, U_IDE=0xA40, IDE_SETTINGS_SIZE=51)
        self.cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        self.cpu.mem_map(0, 0x200000)
        raw=image.read_bytes()
        self.cpu.mem_write(0x100000-len(raw),raw)
        self.cpu.mem_write(0x40E, struct.pack('<H', self.base >> 4))
        self.cpu.mem_write(0x413, struct.pack('<H', 640))
        self.kinds, self.enabled = kinds, enabled
        self.chs, self.geometry = chs, [(7, 29)]*4
        self.regs = [bytearray(8) for _ in kinds]
        self.selected = [0, 2]
        self.phase, self.data, self.cursor = ['idle']*4, [b'']*4, [0]*4
        self.multiple, self.cdb, self.images = [0]*4, [None]*4, [disc(media=0) for _ in kinds]
        self.written = [bytearray() for _ in kinds]
        self.commands, self.io, self.eois, self.writes, self.keys, self.views = [], [], [], [], [], []
        self.cmos, self.index, self.pci = bytearray(128), 0, 0
        self.cmos[0x0D] = 0x80
        self.ports = {0xA1: 255, 0x21: 255}
        self.reset = False
        self.failed_write = None
        self.notifications = []
        self.cpu.hook_add(UC_HOOK_INSN, self.incoming, None, 1, 0, x.UC_X86_INS_IN)
        self.cpu.hook_add(UC_HOOK_INSN, self.outgoing, None, 1, 0, x.UC_X86_INS_OUT)
        self.cpu.hook_add(UC_HOOK_INTR, self.interrupt)
        for vector, owner in ((0x13, 'int13'), (0x15, 'int15'), (0x1A, 'pci_int1a'),
                              (0x76, 'int76'), (0x77, 'int77')):
            try:entry=self.listing.symbol(owner)
            except StopIteration:continue
            self.cpu.mem_write(vector*4, struct.pack('<HH',entry,0xF000))
        # The external timer wait is not under test; each call still executes.
        self.cpu.mem_write(0xF0000+self.listing.symbol('kbc_delay_2ms'), b'\xc3')
        self.call('settings_load')
        self.put('C_IDE', controller)
        for name in ('C_HDD', 'C_SLAVE'):
            self.put(name, enabled[('C_HDD', 'C_SLAVE').index(name)])
        if device_count==4:self.cpu.mem_write(self.base+0xA31,bytes(enabled[2:]))
        self.cpu.mem_write(self.base+0x1034, b'\x90\x00')
        self.cpu.mem_write(self.base+0x1039, bytes((usable,)))
        self.io.clear()

    def put(self, name, value, size=1, position=0):
        self.cpu.mem_write(self.base+position*512+self.state[name], value.to_bytes(size, 'little'))

    def get(self, name, size=1, position=0):
        return int.from_bytes(self.cpu.mem_read(self.base+position*512+self.state[name], size), 'little')

    def call(self, owner, *, iret=False, halt=False, count=2000000, **registers):
        context = dict(CS=0xF000, FS=self.base >> 4, SS=0, SP=0x7000, EFLAGS=0x202)
        context.update(registers)
        for name, value in context.items():
            self.cpu.reg_write(getattr(x, 'UC_X86_REG_'+name), value)
        frame = struct.pack('<HHH', 0x8000, 0xF000, 0x202) if iret else b'\x00\x80'
        self.cpu.mem_write(0x7000, frame)
        self.cpu.emu_start(0xF0000+self.listing.symbol(owner), 0xF8000, count=count)
        terminal = self.listing.symbol('hard_halt')+2 if halt else 0x8000
        assert self.reset or self.cpu.reg_read(x.UC_X86_REG_IP) == terminal, (owner, hex(self.cpu.reg_read(x.UC_X86_REG_IP)))

    def public(self, drive, ah=2, *, lba=0, count=1):
        registers = dict(AX=ah << 8 | (0 if ah >= 0x41 else count), DX=drive, BX=0x1000, ES=0x2000, DS=0, SI=0x500, CX=1)
        if ah == 0x41:
            registers['BX'] = 0x55AA
        if ah in (0x42, 0x43):
            self.cpu.mem_write(0x500, struct.pack('<BBHHHQ', 16, 0, count, 0x1000, 0x2000, lba))
        if ah == 0x48:
            self.cpu.mem_write(0x500, struct.pack('<H', 26)+bytes(28))
        self.call('int13', iret=True, **registers)
        return bool(self.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1)

    @staticmethod
    def payload(position, lba, count=1):
        return bytes((position*43 + lba*17 + n*7) & 255 for n in range(count*512))

    def identify(self, position):
        result = bytearray(512)
        packet = self.kinds[position] == 'packet'
        for word, value in ((0, 0x8580 if packet else 0x40), (1, 1024), (3, 7 if self.chs else 16), (6, 29 if self.chs else 63),
                            (47, 0x8008), (49, 0 if self.chs else 0x200), (60, 0), (61, 16+position)):
            struct.pack_into('<H', result, word*2, value)
        model = ('SAME MODEL PREFIX '+str(position)).ljust(40).encode()
        result[54:94] = b''.join(model[i:i+2][::-1] for i in range(0, 40, 2))
        return bytes(result)

    def task(self, port):
        if 0x1F0 <= port <= 0x1F7 or port == 0x3F6:
            return 0, self.selected[0], 8 if port == 0x3F6 else port-0x1F0
        if 0x170 <= port <= 0x177 or port == 0x376:
            return 1, self.selected[1], 8 if port == 0x376 else port-0x170
        return None

    def incoming(self, cpu, port, size, _):
        if port == 0x71:
            return self.cmos[self.index & 127]
        if 0xCFC <= port <= 0xCFF:
            return 1 if self.pci & 252 == 4 else 0
        task = self.task(port)
        if task is None:
            return self.ports.get(port, 0)
        _, pos, offset = task
        self.io.append(('in', port, pos))
        if self.kinds[pos] is None:
            return 0
        phase = self.phase[pos]
        if offset in (7, 8):
            return 0x48 if phase in ('identify', 'read', 'write', 'cdb', 'reply') else 0x40
        if offset == 0:
            if phase in ('identify', 'read'):
                assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            value = int.from_bytes(self.data[pos][self.cursor[pos]:self.cursor[pos]+size], 'little')
            self.cursor[pos] += size
            if self.cursor[pos] == len(self.data[pos]):
                self.phase[pos] = 'packet-done' if phase == 'reply' else 'idle'
            return value
        if self.cdb[pos] is not None:
            if offset == 2:
                return 1 if phase == 'cdb' else 2 if phase == 'reply' else 3
            if offset in (4, 5):
                return len(self.data[pos]) >> (8*(offset-4)) & 255
        if offset in (4, 5) and self.kinds[pos] == 'packet' and phase == 'idle':
            return (0x14, 0xEB)[offset-4]
        return self.regs[pos][offset]

    def outgoing(self, cpu, port, size, value, _):
        if port == 0x70:
            self.index = value
        elif port == 0x71:
            if self.index & 127 != self.failed_write:
                self.cmos[self.index & 127] = value
            self.writes.append((self.index & 127, value))
        elif port == 0xCF8:
            self.pci = value
        elif port == 0x64 and value == 0xFE:
            self.reset = True
            cpu.emu_stop()
        elif port in (0x20, 0xA0):
            self.eois.append((port, value))
        self.ports[port] = value
        task = self.task(port)
        if task is None:
            return
        channel, pos, offset = task
        self.io.append(('out', port, pos))
        if offset == 6:
            pos = channel*2 + ((value >> 4) & 1)
            self.selected[channel] = pos
            self.cdb[pos] = None
            self.regs[pos][6] = value
        elif offset == 8:
            if value & 4:
                for peer in (channel*2, channel*2+1):
                    self.multiple[peer], self.phase[peer], self.cdb[peer] = 0, 'idle', None
                    self.geometry[peer] = None
                self.commands.append(('reset', channel))
        elif offset == 0 and self.phase[pos] == 'write':
            assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            self.written[pos].extend(value.to_bytes(size, 'little'))
            if len(self.written[pos]) == self.regs[pos][2]*512:
                self.phase[pos] = 'idle'
        elif offset == 0 and self.phase[pos] == 'cdb':
            self.cdb[pos].extend(value.to_bytes(size, 'little'))
            if len(self.cdb[pos]) == 12:
                cdb = self.cdb[pos]
                command = cdb[0]
                self.commands.append(('packet', pos, command))
                reply = b''
                if command == 0x25:
                    reply = struct.pack('>II', len(self.images[pos])//2048-1, 2048)
                elif command == 0x28:
                    lba = int.from_bytes(cdb[2:6], 'big')
                    reply = self.images[pos][lba*2048:(lba+1)*2048]
                elif command == 3:
                    reply = bytes(18)
                else:
                    assert command == 0, command
                self.data[pos], self.cursor[pos] = reply, 0
                self.phase[pos] = 'reply' if reply else 'packet-done'
        elif offset == 7:
            self.commands.append(('command', pos, value))
            if value in (0xEC, 0xA1):
                self.data[pos], self.cursor[pos], self.phase[pos] = self.identify(pos), 0, 'identify'
            elif value in (0x20, 0xC4):
                r = self.regs[pos]
                if r[6] & 0x40:
                    lba = r[3] | r[4] << 8 | r[5] << 16 | (r[6] & 15) << 24
                else:
                    assert self.geometry[pos] is not None, 'CHS transfer before device geometry was restored'
                    heads, sectors = self.geometry[pos]
                    lba = ((r[4] | r[5] << 8)*heads+(r[6] & 15))*sectors+r[3]-1
                self.commands.append(('read', pos, lba))
                self.data[pos], self.cursor[pos], self.phase[pos] = self.payload(pos, lba, r[2]), 0, 'read'
            elif value == 0xC6:
                self.multiple[pos] = self.regs[pos][2]
            elif value in (0x30, 0xC5):
                self.written[pos], self.phase[pos] = bytearray(), 'write'
            elif value == 0xA0:
                self.cdb[pos], self.phase[pos], self.data[pos], self.cursor[pos] = bytearray(), 'cdb', b'', 0
            elif value == 0x91:
                self.geometry[pos] = ((self.regs[pos][6] & 15)+1, self.regs[pos][2])
            else:
                assert value == 8, hex(value)
        elif offset < 8:
            self.regs[pos][offset] = value

    def interrupt(self, cpu, number, _):
        if number == 0x10:
            return
        if number == 0x16:
            if cpu.reg_read(x.UC_X86_REG_AH) == 1:
                flags = cpu.reg_read(x.UC_X86_REG_EFLAGS)
                cpu.reg_write(x.UC_X86_REG_EFLAGS, flags & ~0x40 if self.keys else flags | 0x40)
                return
            assert self.keys, 'Setup exhausted its external keyboard input'
            self.views.append((self.get('U_PAGE'), self.get('U_IDE_DEVICE'), self.get('U_FIELD')))
            cpu.reg_write(x.UC_X86_REG_AX, self.keys.pop(0))
            return
        if number == 0x15:
            self.notifications.append(cpu.reg_read(x.UC_X86_REG_AX))
        sp = cpu.reg_read(x.UC_X86_REG_SP)-6
        cpu.mem_write((cpu.reg_read(x.UC_X86_REG_SS) << 4)+sp,
                      struct.pack('<HHH', cpu.reg_read(x.UC_X86_REG_IP), cpu.reg_read(x.UC_X86_REG_CS),
                                  cpu.reg_read(x.UC_X86_REG_EFLAGS) & 65535))
        cpu.reg_write(x.UC_X86_REG_SP, sp)
        cpu.reg_write(x.UC_X86_REG_EFLAGS, cpu.reg_read(x.UC_X86_REG_EFLAGS) & ~0x300)
        ip, cs = struct.unpack('<HH', bytes(cpu.mem_read(number*4, 4)))
        cpu.reg_write(x.UC_X86_REG_CS, cs)
        cpu.reg_write(x.UC_X86_REG_IP, ip)


def inventory(image):
    rows = []
    cases = [(None,)*4] + [tuple('ata' if n == pos else None for n in range(4)) for pos in range(4)]
    cases += [('ata',)*4, ('packet', 'ata', 'packet', 'ata'), ('ata', None, 'ata', 'ata')]
    for kinds in cases:
        enabled = (0, 1, 1, 1) if kinds == ('ata', None, 'ata', 'ata') else (1,)*4
        m = Machine(image, kinds, enabled)
        for policy in range(4):
            m.cpu.mem_write(m.base+0xA01+policy*12+1, bytes((policy, policy+1, 0)))
        m.cpu.mem_write(m.base+0x60+13, b'\x05')
        sentinels = {0xB0: b'KBC!', 0x27E: bytes(range(80)), 0x1000: b'PCI!', 0x1220: b'TAG!', 0x1800: b'RAM!'}
        for offset, value in sentinels.items():
            m.cpu.mem_write(m.base+offset, value)
        m.call('ata_detect_primary')
        detected = [p for p, kind in enumerate(kinds) if kind is not None]
        order = detected + [p for p, kind in enumerate(kinds) if kind is None]
        assert [m.get('S_POLICY_INDEX', position=p) for p in range(4)] == list(range(4))
        for pos in range(4):
            policy=pos
            assert bytes(m.cpu.mem_read(m.base+pos*512+m.state['S_IDE'], 12)) == bytes(m.cpu.mem_read(m.base+0xA01+policy*12, 12))
            assert m.get('S_PIO32', position=pos) == (5 >> policy & 1)
        assert (m.get('C_HDD'), m.get('C_SLAVE')) == enabled[:2]
        for pos in detected:
            if not enabled[pos]:continue
            assert bytes(m.cpu.mem_read(m.base+pos*512+m.state['S_MODEL'], 40)).decode().strip() == 'SAME MODEL PREFIX '+str(pos)
        ata = [p for p in detected if kinds[p] == 'ata' and enabled[p]]
        assert m.cpu.mem_read(0x475, 1) == bytes((len(ata),))
        for n, pos in enumerate(ata):
            assert not m.public(0x80+n), (kinds, pos)
            assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(pos, 0)
            assert not m.public(0x80+n, 0x42, lba=17)
            assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(pos, 17)
            payload = bytes((n*19+i) & 255 for i in range(512))
            m.cpu.mem_write(0x21000, payload)
            assert not m.public(0x80+n, 3) and bytes(m.written[pos]) == payload
            assert not m.public(0x80+n, 0x43, lba=17) and bytes(m.written[pos]) == payload
            assert m.cpu.mem_read(0x502, 2) == b'\x01\0'
            assert m.regs[pos][3:6] == b'\x11\0\0'
            assert not m.public(0x80+n, 8)
            policy = pos
            assert m.cpu.reg_read(x.UC_X86_REG_DH) == (15 if policy == 1 else 31)
            assert m.cpu.reg_read(x.UC_X86_REG_CL) & 63 == 63
            assert m.cpu.reg_read(x.UC_X86_REG_DL) == len(ata)
            assert not m.public(0x80+n, 0x48)
            assert struct.unpack('<Q', bytes(m.cpu.mem_read(0x510, 8)))[0] == (16+pos)*65536
        for n, pos in enumerate(ata[:2]):
            pointer = 0x104 if n == 0 else 0x118
            assert bytes(m.cpu.mem_read(pointer, 4)) == struct.pack('<HH', m.state['S_FDPT'], (m.base >> 4)+pos*32)
        assert m.cmos[0x12] == (0xFF if len(ata) >= 2 else 0xF0 if ata else 0)
        start = len(m.io)
        for ah in (0x42, 0x43):
            payload = bytes(m.cpu.mem_read(0x21000, 512))
            m.cpu.reg_write(x.UC_X86_REG_EDI, 0x13572468)
            m.cpu.reg_write(x.UC_X86_REG_EBP, 0x24681357)
            assert m.public(0x80+len(ata), ah)
            assert m.cpu.reg_read(x.UC_X86_REG_AH) == (1 if ata else 0x80)
            assert len(m.io) == start and bytes(m.cpu.mem_read(0x21000, 512)) == payload
            assert m.cpu.reg_read(x.UC_X86_REG_EDI) == 0x13572468 and m.cpu.reg_read(x.UC_X86_REG_EBP) == 0x24681357
            assert m.cpu.reg_read(x.UC_X86_REG_ES) == 0x2000 and m.cpu.reg_read(x.UC_X86_REG_DS) == 0
            assert m.cpu.reg_read(x.UC_X86_REG_FS) == m.base >> 4
            assert m.cpu.mem_read(0x502, 2) == b'\0\0'
        if ata:
            assert m.cpu.mem_read(0x502, 2) == b'\0\0'
            m.call('int13', iret=True, AX=0x0201, DX=0x80+len(ata)-1, BX=0, ES=m.base >> 4, CX=1)
            assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1 and len(m.io) == start
        for offset, value in sentinels.items():
            assert bytes(m.cpu.mem_read(m.base+offset, len(value))) == value, hex(offset)
        rows.append(dict(kinds=kinds, enabled=enabled, ata_positions=ata, unique_policies=True))
    for controller, usable in ((0, 1), (1, 0)):
        m = Machine(image, controller=controller, usable=usable)
        m.call('ata_detect_primary')
        assert not m.io and m.cpu.mem_read(0x475, 1) == b'\0'
        rows.append(dict(controller=controller, usable=usable, taskfile_accesses=0))
    return rows


def reset_and_bpb(image):
    m = Machine(image, chs=True)
    m.call('ata_detect_primary')
    for channel in (0, 1):
        before = list(m.multiple)
        command_start = len(m.commands)
        assert not m.public(0x80+channel*2, 0)
        assert m.multiple == before == [8]*4
        restored = {row[1] for row in m.commands[command_start:] if row[0] == 'command'}
        assert restored == {channel*2, channel*2+1}
        assert all(m.geometry[pos] == (7, 29) for pos in range(4))
        m.eois.clear()
        delivered = []
        def pending(cpu, address, size, _):
            if not delivered and m.get('S_COUNT', position=channel*2+1) == 3 and cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200:
                delivered.append(channel)
                m.interrupt(cpu, 0x76+channel, None)
        at = 0xF0000+m.listing.symbol('.loop', 'ata_wait_drq')
        hook = m.cpu.hook_add(UC_HOOK_CODE, pending, None, at, at)
        try:
            assert not m.public(0x81+channel*2, 0x42, lba=41)
            assert m.commands[-1] == ('read', channel*2+1, 41)
            assert ('command', channel*2+1, 0x20) in m.commands[command_start:]
            assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(channel*2+1, 41)
            assert not m.public(0x81+channel*2, 0x42, lba=99, count=3)
        finally:
            m.cpu.hook_del(hook)
        assert delivered == [channel] and m.eois == [(0xA0, 0x66+channel), (0x20, 0x62)]
        assert m.notifications[-1] == 0x9100 and m.cpu.mem_read(0x48E, 1) == b'\xff'
        assert ('command', channel*2+1, 0xC4) in m.commands
        assert bytes(m.cpu.mem_read(0x21000, 1536)) == m.payload(channel*2+1, 99, 3)
    # A boot BPB may override only80h; later Auto geometry remains independent.
    m = Machine(image)
    m.call('ata_detect_primary')
    bpb = bytearray(512)
    bpb[0] = 0xEB
    for offset, value in ((11, 512), (14, 1), (24, 17), (26, 4), (510, 0xAA55)):
        struct.pack_into('<H', bpb, offset, value)
    m.cpu.mem_write(0x7C00, bytes(bpb))
    m.put('B_DRIVE', 0x80)
    assert not m.public(0x80, 8)
    assert m.cpu.reg_read(x.UC_X86_REG_DH) == 3 and m.cpu.reg_read(x.UC_X86_REG_CL) & 63 == 17
    m.call('int13', iret=True, AX=0x0201, DX=0x0380, CX=0x0102, BX=0x1000, ES=0x2000)
    assert m.commands[-1] == ('read', 0, 120)
    assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(0, 120)
    assert not m.public(0x83, 8)
    assert m.cpu.reg_read(x.UC_X86_REG_DH) == 31 and m.cpu.reg_read(x.UC_X86_REG_CL) & 63 == 63
    assert not m.public(0x83)
    assert m.commands[-1] == ('read', 3, 0)
    assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(3, 0)
    m.call('int13', iret=True, AX=0x0201, DX=0x0383, CX=0x0102, BX=0x1000, ES=0x2000)
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert m.commands[-1] == ('read', 3, 2206)
    assert bytes(m.cpu.mem_read(0x21000, 512)) == m.payload(3, 2206)
    m.put('S_GEOMETRY', 0x1306, 2, position=3)
    assert not m.public(0x83, 8)
    assert m.cpu.reg_read(x.UC_X86_REG_DH) == 5 and m.cpu.reg_read(x.UC_X86_REG_CL) & 63 == 19
    m.put('S_GEOMETRY', 0x1306, 2)
    assert not m.public(0x80, 8)
    assert m.cpu.reg_read(x.UC_X86_REG_DH) == 5 and m.cpu.reg_read(x.UC_X86_REG_CL) & 63 == 19
    for vector, value in ((0x76, 0x66), (0x77, 0x67)):
        m.eois.clear()
        m.call('int76' if vector == 0x76 else 'int77', iret=True)
        assert m.eois == [(0xA0, value), (0x20, 0x62)]
    return dict(channel_reset_peers_restored=True, later_disk_bpb_isolated=True, irq14_irq15=True)


def cd_positions(image):
    rows = []
    for pos in (2, 3):
        kinds = ['packet', 'ata', 'ata', 'ata']
        kinds[pos] = 'packet'
        m = Machine(image, tuple(kinds))
        m.images[0] = bytes(64*2048)  # Earlier packet provider has no boot descriptor.
        m.call('ata_detect_primary')
        assert not m.public(0x80, 0) and not m.public(0x81, 0)
        reached = []
        def terminal(cpu, where, size, _):
            reached.append(where)
            cpu.emu_stop()
        hook = m.cpu.hook_add(UC_HOOK_CODE, terminal, None, 0x7C00, 0x7C00)
        try:
            try:
                m.call('cd_boot')
            except AssertionError:
                assert reached == [0x7C00]
        finally:
            m.cpu.hook_del(hook)
        assert reached == [0x7C00] and bytes(m.cpu.mem_read(0x7C00, 4)) == b'CDOK'
        assert ('packet', 0, 0x28) in m.commands and ('packet', pos, 0x28) in m.commands
        rows.append(dict(boot_position=pos, earlier_nonbootable_skipped=True, exact_boot_payload=True))
    return rows


def setup_navigation(image):
    rows = []
    for discovered, controller, usable in ((False, 1, 1), (False, 0, 1), (False, 1, 0), (True, 1, 1)):
        m = Machine(image, controller=controller, usable=usable)
        if discovered:
            m.call('ata_detect_primary')
        active = bytes(m.cpu.mem_read(m.base+0xA00, 51))
        io = len(m.io)
        m.keys = [0x5000, 9, 0x5000, 0x5000]  # Drives page, first device.
        for n in range(4):
            m.keys += [13, 0x4D00, 27]
            if n < 3:
                m.keys += [0x5000]
        m.keys += [27, 27, ord('y')]
        m.call('setup_main', count=8000000)
        assert all((1, n, 0) in m.views for n in range(4)), m.views
        assert bytes(m.cpu.mem_read(m.base+0xA00, 51)) == active and len(m.io) == io
        assert not any(index >= 0x33 for index, _ in m.writes), m.writes
        rows.append(dict(discovered=discovered, controller=controller, four_forms=True, cancel_preserves_active=True))
    # Actual early Setup save/restart; absent and disabled controller needs no probe.
    for controller in (0, 1):
        m = Machine(image, ('ata', None, 'ata', 'ata'), controller=controller)
        m.keys = [0x5000, 9, 0x5000, 0x5000]
        for n in range(4):
            m.keys += [13, 0x4D00, 27]
            if n < 3:
                m.keys += [0x5000]
        m.keys += [0x4400, ord('y')]
        m.call('setup_main', count=8000000)
        assert m.reset and not m.io and not m.keys
        restarted = Machine(image, m.kinds)
        restarted.cmos[:] = m.cmos
        restarted.call('settings_load')
        assert restarted.get('C_IDE') == controller
        assert restarted.get('C_HDD') == restarted.get('C_SLAVE') == 0
        assert bytes(restarted.cpu.mem_read(m.base+0xA31, 2)) == b'\0\0'
        restarted.call('ata_detect_primary')
        assert restarted.cpu.mem_read(0x475, 1) == b'\0'
        assert [restarted.get('S_POLICY_INDEX', position=p) for p in (0, 2, 3, 1)] == [0, 2, 3, 1]
        if not controller:
            assert not restarted.io
        rows.append(dict(controller=controller, early_setup_save_restart=True, disabled_mapping_retained=True))
    return rows


def setup_presentation(image):
    class Screen(Machine):
        def interrupt(self, cpu, number, data):
            if number == 0x16 and cpu.reg_read(x.UC_X86_REG_AH) == 0 and self.keys:
                field = self.get('U_FIELD')
                if self.get('U_PAGE') == 1 and 2 <= field <= 5:
                    if self.keys[0] == 0x3B00:
                        self.help_pending = True
                        for policy in range(4):
                            at = 0xB8000+(8+policy)*160+49*2
                            text = bytes(cpu.mem_read(at, 8))
                            assert text[::2] == b'Auto'
                            assert text[1::2] == bytes((0x1F if policy+2 == field else 7,))*4
                    elif self.keys[0] == 27 and getattr(self, 'help_pending', False):
                        self.help_pending = False
                        title = bytes(cpu.mem_read(0xB8000+18*160+25*2, 40))[::2]
                        assert title.startswith(('Primary IDE Master','Primary IDE Slave','Secondary IDE Master','Secondary IDE Slave')[field-2].encode()), title
                        body = bytes(cpu.mem_read(0xB8000+19*160+25*2, 90))[::2]
                        assert body.startswith(b'Auto detects hard disks and CD drives'), body
            return super().interrupt(cpu, number, data)
    m = Screen(image)
    m.keys = [0x5000, 9, 0x5000, 0x5000]
    for policy in range(4):
        m.keys += [0x3B00, 27]+([0x5000] if policy < 3 else [])
    m.keys += [27, 27, ord('y')]
    m.call('setup_main', count=5000000)
    assert not m.keys and not m.writes
    return dict(four_readable_values=True, four_correct_help_topics=True)


def setup_full_policies(image):
    rows = []
    auto = bytes(4)+struct.pack('<HBBHH', 1024, 16, 63, 0xFFFF, 1024)
    records = []
    keys = [0x5000, 9, 0x5000, 0x5000]
    for policy in range(4):
        keys += [13, 0x5000, 0x5000]
        numbers = (120+policy, 4+policy, 17+policy, 128+policy, 119+policy)
        for field, value in enumerate(numbers):
            keys += [13]+list(str(value).encode())+[13]
            if field < 4:
                keys += [0x5000]
        keys += [0x5000]+[0x4D00]*(policy+1)
        keys += [0x5000]+[0x4D00]*(policy+2)
        keys += [0x5000]+[0x4D00]*(policy & 1)
        keys += [0x5000, 0x4D00, 27]
        if policy < 3:
            keys += [0x5000]
        records.append(bytes((48, (2, 3, 1, 0)[policy], policy+2, policy & 1))+
                       struct.pack('<HBBHH', *numbers))
    expected = b'\x01'+b''.join(records)+b'\x01\x01'
    for action in ('cancel', 'save'):
        m = Machine(image, ('ata', None, 'ata', 'ata'))
        for policy in range(4):
            m.cpu.mem_write(m.base+0xA01+policy*12, b'\x30'+auto[1:])
        original = bytes(m.cpu.mem_read(m.base+0xA00, 51))
        m.keys = keys+([27, 27, ord('y')] if action == 'cancel' else [0x4400, ord('y')])
        m.call('setup_main', count=20000000)
        assert not m.keys and not m.io
        assert bytes(m.cpu.mem_read(m.base+0xA00, 51)) == original
        assert bytes(m.cpu.mem_read(m.base+0xA40, 51)) == expected
        assert m.get('U_CHIP') == m.get('C_CHIP')
        if action == 'cancel':
            assert not m.reset and not m.writes
        else:
            assert m.reset
            restored = Machine(image, m.kinds)
            restored.cmos[:] = m.cmos
            restored.call('settings_load')
            assert bytes(restored.cpu.mem_read(m.base+0xA00, 51)) == expected
            assert bytes(restored.cpu.mem_read(m.base+0x60+13, 1)) == b'\x0f'
            restored.call('ata_detect_primary')
            for drive, position in ((0x80, 0), (0x81, 2), (0x82, 3)):
                assert not restored.public(drive)
                assert bytes(restored.cpu.mem_read(0x21000, 512)) == restored.payload(position, 0)
            assert not restored.public(0x82, 0x42, lba=17)
            assert bytes(restored.cpu.mem_read(0x21000, 512)) == restored.payload(3, 17)
        rows.append(dict(action=action, four_distinct_full_forms=True, saved_boot_disk_payloads=action == 'save'))
    return rows


def persistence(image):
    """Independent CMOS grammar through the real settings owners."""
    m = Machine(image)
    s, base = m.state, m.base
    rows = []

    def write(name, data, offset=0):
        m.cpu.mem_write(base+s[name]+offset, bytes(data))

    def read(name, size):
        return bytes(m.cpu.mem_read(base+s[name], size))

    def checked(raw, checksum):
        result = bytearray(raw)
        result[checksum] = 0
        result[checksum] = -sum(result) & 255
        return result

    def load():
        before = bytes(m.cmos)
        m.writes.clear()
        m.call('settings_load')
        assert bytes(m.cmos) == before and not m.writes, 'Load wrote CMOS'

    records = [bytes((48, i, i+2, i & 1))+
               struct.pack('<HBBHH', 513+i*111, 2+i, 17+i, 0xFFFA-i, 500+i) for i in range(4)]
    extra = bytes((0, 1))
    ports = bytes((1, 2, 1, 3, 2, 1, 0, 1))
    chip = bytes.fromhex('A0010070900000A255070F6E010F01FCA9870F0100000000')
    masks = bytes.fromhex('F0010170900301FFFF070F7F010F01FCFFFF0F01FF01030F')

    def packed_ide(policies):
        flags = sum((r[2] | r[3] << 4 | ((0, 0)+tuple(extra))[i] << 5) << (i*6)
                    for i, r in enumerate(policies))
        payload = (bytes((1,))+bytes(r[0] | r[1] << 6 for r in policies)+
                   flags.to_bytes(3, 'little')+b''.join(r[4:] for r in policies))
        return checked(b'ID\x02\0'+payload, 3)

    widths = (3, 3, 1, 2, 2, 1, 1, 1)
    port_bits = sum(v << sum(widths[:i]) for i, v in enumerate(ports))
    packed_ports = checked(b'P\x02\0'+port_bits.to_bytes(2, 'little'), 2)
    chip_bits = [(v >> bit) & 1 for v, mask in zip(chip, masks) for bit in range(8) if mask >> bit & 1]
    assert len(chip_bits) == 92
    packed_chip = checked(b'W\0'+sum(v << i for i, v in enumerate(chip_bits)).to_bytes(13, 'little'), 1)
    m.call('ide_defaults', DI=s['U_IDE'])
    for i, record in enumerate(records):
        write('U_IDE', record, 1+i*12)
    write('U_IDE', extra, 49)
    write('U_PORTS', ports)
    write('U_CHIP', chip)
    for name, value in (('U_TYPES', 0x40), ('U_HDD', 1), ('U_SLAVE', 0), ('U_SEEK', 1),
                        ('U_NUMLOCK', 1), ('U_SWAP', 0), ('U_HALT', 2), ('U_CLOCK24', 0),
                        ('U_THEME', 0), ('U_BOOT', 3), ('U_BOOT_SECOND', 1),
                        ('U_BOOT_THIRD', 2), ('U_BOOT_FOURTH', 0)):
        m.put(name, value)
    m.call('settings_save')
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert m.cmos[0x33:0x36] == bytes.fromhex('3402CA')
    assert m.cmos[0x40:0x6C] == packed_ide(records)
    assert m.cmos[0x6C:0x71] == packed_ports and m.cmos[0x71:0x80] == packed_chip
    golden = bytes(m.cmos)
    publication = list(m.writes)
    assert publication[0] == (0x38, 0) and publication[-1] == (0x38, ord('B'))
    marker_at = publication.index((0x33, 0x34))
    assert marker_at < next(i for i, (address, _) in enumerate(publication) if 0x40 <= address <= 0x7F)
    for address, tag in ((0x40, ord('I')), (0x6C, ord('P')), (0x71, ord('W'))):
        assert publication.index((address, tag)) < len(publication)-1
    rows.append(dict(case='format and owner publication', marker_before_overlap=True, base_signature_last=True))
    active = bytes((1,))+b''.join(records)+extra
    auto = bytes(4)+struct.pack('<HBBHH', 1024, 16, 63, 0xFFFF, 1024)
    defaults = {'C_IDE': b'\x01'+auto*4+b'\x01\x01',
                'C_PORTS': bytes((1, 2, 1, 2, 0, 1, 0, 1)),
                'C_CHIP': b'\0\x01\0\x40'+bytes(20)}
    load()
    assert read('C_IDE', 51) == active and read('C_PORTS', 8) == ports
    assert read('C_CHIP', 24) == chip and m.get('C_VALID') == 1
    assert (m.get('C_HDD'), m.get('C_SLAVE')) == (1, 0)
    rows.append(dict(case='four full policies', independent_bytes=True, no_write_load=True))
    fresh = Machine(image)
    fresh.cmos[:] = golden
    fresh.call('settings_load')
    assert bytes(fresh.cpu.mem_read(base+s['C_IDE'], 51)) == active
    assert bytes(fresh.cpu.mem_read(base+s['C_PORTS'], 8)) == ports
    assert bytes(fresh.cpu.mem_read(base+s['C_CHIP'], 24)) == chip
    fresh.writes.clear()
    fresh.call('chipset_record_save', SI=s['C_CHIP'])
    assert not fresh.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert fresh.cmos == golden and all(0x71 <= address <= 0x7F for address, _ in fresh.writes)
    rows.append(dict(case='fresh packed load and standalone save', full_records=True, unrelated_owners_retained=True))
    for policy, bad_record in ((2, bytes((15,))+records[2][1:]),
                               (3, records[3][:6]+b'\0'+records[3][7:])):
        policies = list(records)
        policies[policy] = bad_record
        m.cmos[:] = golden
        m.cmos[0x40:0x6C] = packed_ide(policies)
        load()
        assert m.get('C_VALID') == 0 and read('C_IDE', 51) == defaults['C_IDE']
        assert read('C_PORTS', 8) == ports and read('C_CHIP', 24) == chip
        rows.append(dict(case='checksummed semantic invalid policy', policy=policy+1, owner_defaults=True))
    m.cmos[:] = golden
    m.cmos[0x6E] ^= 1
    m.failed_write = 0x6E
    m.writes.clear()
    m.call('settings_save')
    assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert m.cmos[0x38] == 0 and m.cmos[0x6C] == 0
    assert (0x38, ord('B')) not in m.writes
    m.failed_write = None
    rows.append(dict(case='packed readback failure', failed_owner_unpublished=True, base_unpublished=True))
    m.cmos[:] = golden
    m.cmos[0x35] ^= 1
    load()
    assert m.get('C_VALID') == 0 and read('C_IDE', 51) != active
    for owner, value in defaults.items():
        assert read(owner, len(value)) == value, owner
    rows.append(dict(case='invalid global format', rejected=True, no_write_load=True))
    for checksum, owner in ((0x43, 'C_IDE'), (0x6E, 'C_PORTS'), (0x72, 'C_CHIP')):
        m.cmos[:] = golden
        m.cmos[checksum] ^= 1
        load()
        assert m.get('C_VALID') == 0
        assert read(owner, len(defaults[owner])) == defaults[owner], owner
        if owner != 'C_IDE':
            assert read('C_IDE', 51) == active
        if owner != 'C_PORTS':
            assert read('C_PORTS', 8) == ports
        if owner != 'C_CHIP':
            assert read('C_CHIP', 24) == chip
        rows.append(dict(case='bad checksum', owner=owner, unrelated_records_retained=True))
    for address, bit, checksum, start, end, owner in (
        (0x49, 0x20, 0x43, 0x40, 0x6C, 'C_IDE'),
        (0x70, 0x80, 0x6E, 0x6C, 0x71, 'C_PORTS'),
        (0x7F, 0x80, 0x72, 0x71, 0x80, 'C_CHIP')):
        m.cmos[:] = golden
        m.cmos[address] |= bit
        m.cmos[checksum] = 0
        m.cmos[checksum] = -sum(m.cmos[start:end]) & 255
        load()
        assert m.get('C_VALID') == 0, owner
        assert read(owner, len(defaults[owner])) == defaults[owner], owner
        rows.append(dict(case='checksummed reserved bit', owner=owner, rejected=True))
    legacy = bytearray(golden)
    legacy[0x33:0x36] = bytes(3)
    legacy[0x40:0x80] = bytes(64)
    legacy[0x40:0x5D] = checked(b'ID\x01\0'+bytes((1,))+b''.join(records[:2]), 3)
    legacy[0x5D:0x69] = checked(b'P1\x01'+ports+b'\0', 11)
    old_chip = bytearray(chip)
    old_chip[13] = 3
    legacy[0x69] = 0x57
    legacy[0x6A] = -(0x57+sum(old_chip)) & 255
    for i, value in enumerate(old_chip):
        legacy[0x6B+i if i < 21 else 0x33+i-21] = value
    m.cmos[:] = legacy
    load()
    assert read('C_IDE', 51) == bytes((1,))+b''.join(records[:2])+auto*2+b'\x01\x01'
    assert read('C_PORTS', 8) == ports and read('C_CHIP', 24) == old_chip
    assert (m.get('C_HDD'), m.get('C_SLAVE')) == (1, 0)
    rows.append(dict(case='legacy schema', first_two_retained=True, extra_auto=True, no_write_load=True))
    m.cmos[0x69] = 0xD2
    load()
    assert read('C_CHIP', 3)[1:] == b'\x00\x01'
    prior = bytes(m.cmos)
    m.call('chipset_record_save', SI=s['C_CHIP'])
    assert not m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
    assert m.cmos[0x33:0x36] == bytes(3) and m.cmos[0x69] == 0x57
    assert m.cmos[0x40:0x69] == prior[0x40:0x69]
    rows.append(dict(case='legacy recovery', standalone_save_keeps_format=True))
    for source, recovery in ((legacy, 0x69), (golden, 0x71)):
        m.cmos[:] = source
        m.cmos[recovery] = 0xD2
        m.cmos[0x3B] = golden[0x3B] ^ 1
        m.failed_write = 0x3B
        m.call('settings_save')
        assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
        assert m.cmos[0x33:0x36] == bytes.fromhex('3402CA') and m.cmos[0x71] == 0xD2
        assert m.cmos[0x40:0x6C] == packed_ide(records) and m.cmos[0x6C:0x71] == packed_ports
        fresh.cmos[:] = m.cmos
        fresh.call('settings_load')
        assert bytes(fresh.cpu.mem_read(base+s['C_CHIP']+1, 2)) == b'\x00\x01'
        assert fresh.get('C_VALID') == 0
        m.failed_write = None
        rows.append(dict(case='failed base save retains recovery', source_tag=recovery, destination_tag=0x71))
    modified = list(records)
    modified[3] = modified[3][:8]+struct.pack('<H', 0xD212)+modified[3][10:]
    m.cmos[:] = golden
    m.cmos[0x40:0x6C] = packed_ide(modified)
    assert m.cmos[0x69] == 0xD2
    load()
    assert read('C_CHIP', 24) == chip
    assert read('C_IDE', 51) == bytes((1,))+b''.join(modified)+extra
    rows.append(dict(case='geometry D2 at old tag', no_false_recovery=True))
    prior = bytes(m.cmos)
    m.writes.clear()
    m.call('settings_recovery_publish')
    assert m.writes == [(0x71, 0xD2)] and m.cmos[0x40:0x71] == prior[0x40:0x71]
    load()
    assert read('C_CHIP', 3)[1:] == b'\x00\x01'
    assert read('C_IDE', 51) == bytes((1,))+b''.join(modified)+extra and read('C_PORTS', 8) == ports
    rows.append(dict(case='packed recovery', tag=0x71, device_records_retained=True))
    # Continue the production RAM failure through its hardware reset request,
    # then consume its exact CMOS in a fresh machine's normal settings loader.
    from shared.tools.ram_proof import run as ram_run
    layout = json.loads((ROOT/'m919/port.json').read_text())['rom']
    for source, tag in ((legacy, 0x69), (golden, 0x71)):
        prior = bytearray(source)
        prior[0x36] = 0
        outcome = ram_run(image, layout, m.state, fault=(0x10000, 'middle'), coverage=False,
                          cmos_seed=prior, through_restart=True)
        restarted = Machine(image)
        restarted.cmos[:] = bytes.fromhex(outcome['cmos_after'])
        restarted.call('settings_load')
        assert restarted.cmos[tag] == 0xD2
        assert restarted.cmos[0x40:tag] == prior[0x40:tag]
        assert bytes(restarted.cpu.mem_read(base+s['C_CHIP']+1, 2)) == b'\x00\x01'
        rows.append(dict(case='visible RAM failure reset reload', tag=tag, device_records_retained=True,
                         terminal=outcome['terminal'], safe_caches=True))

        for owner in ('cache_recovery', 'chipset_post_ram_cache', 'chipset_late_cache'):
            for recovering in ((False, True) if owner != 'cache_recovery' else (False,)):
                probe = Machine(image)
                probe.cmos[:] = source
                probe.cmos[0x36] = 0x1A
                if recovering:
                    probe.cmos[tag] = 0xD2
                probe.call('settings_load')
                probe.call('chipset_safe_defaults', DI=s['C_CHIP'])
                before = bytes(probe.cmos)
                probe.keys = [13]
                probe.put('S_EXTENDED_KIB', 65, 2)
                probe.put('S_EXTENDED_KIB32', 65, 4)
                tone_start = 0xF0000+probe.listing.symbol('post_tone')
                tone_end = 0xF0000+probe.listing.symbol('post_notice_wait')
                pattern = probe.listing.symbol('.pattern', 'chipset_runtime_ram_check')
                faults = []

                def timer(cpu, address, size, _):
                    if tone_start <= address < tone_end and bytes(cpu.mem_read(address, 1)) == b'\xf4':
                        ticks = int.from_bytes(cpu.mem_read(0x46C, 2), 'little')
                        cpu.mem_write(0x46C, struct.pack('<H', (ticks+32) & 65535))
                        cpu.reg_write(x.UC_X86_REG_IP, cpu.reg_read(x.UC_X86_REG_IP)+1)

                def bad_ram(cpu, access, address, size, value, _):
                    if (owner == 'chipset_post_ram_cache' and address == 0x10000 and not faults and
                            pattern <= cpu.reg_read(x.UC_X86_REG_EIP) < pattern+22):
                        value = int.from_bytes(cpu.mem_read(address, 4), 'little') ^ 1
                        cpu.mem_write(address, struct.pack('<I', value))
                        faults.append(address)

                probe.cpu.hook_add(UC_HOOK_CODE, timer)
                probe.cpu.hook_add(UC_HOOK_MEM_READ, bad_ram)
                terminal_halt = owner == 'chipset_post_ram_cache' and recovering
                probe.call(owner, DS=0xF000, halt=terminal_halt, count=1000000)
                assert probe.cmos[0x40:tag] == before[0x40:tag]
                if owner == 'chipset_late_cache':
                    assert not probe.reset and probe.cmos[tag] == before[tag]
                    assert probe.cmos[0x36] == (0x1A if recovering else 0)
                else:
                    assert probe.cmos[tag] == 0xD2
                    if terminal_halt:
                        assert not probe.reset and probe.ports[0x80] == 0xE7
                    else:
                        assert probe.reset and probe.cmos[0x36] == 0x1A
                        restarted.cmos[:] = probe.cmos
                        restarted.call('settings_load')
                        assert bytes(restarted.cpu.mem_read(base+s['C_CHIP']+1, 2)) == b'\x00\x01'
                assert bool(faults) == (owner == 'chipset_post_ram_cache')
                rows.append(dict(case=owner, tag=tag, prior_recovery=recovering,
                                 other_owners_retained=True, reset=probe.reset, terminal_halt=terminal_halt))
    return rows


def physical_policy_cases(image,baseline=None):
    """Compose real discovery, fixed Setup forms and saved physical policies."""
    from pio_proof import PIO
    import hashlib
    labels=(b'Primary IDE Master',b'Primary IDE Slave',b'Secondary IDE Master',b'Secondary IDE Slave')
    rows=[]
    class Screen(PIO):
        def interrupt(self,cpu,number,data):
            if number==0x16 and cpu.reg_read(x.UC_X86_REG_AH)==0 and self.keys and self.get('U_PAGE')==1:
                screen=bytes(cpu.mem_read(0xB8000,4000))[::2]
                device=self.get('U_IDE_DEVICE');field=self.get('U_FIELD')
                if device<4:
                    assert screen[3*80+23:3*80+23+len(labels[device])]==labels[device]
                else:
                    for p,label in enumerate(labels):assert screen[(8+p)*80+24:(8+p)*80+24+len(label)]==label
                    if self.keys[0]==27 and b'Auto detects hard disks' in screen:
                        label=labels[field-2]
                        assert screen[18*80+25:18*80+25+len(label)]==label
            return super().interrupt(cpu,number,data)
    if baseline:
        old=PIO(baseline,(None,None,'ata',None),requests=(1,2,4,5));old.call('ata_detect_primary')
        got=[old.get('S_POLICY_INDEX',position=p) for p in range(4)]
        assert got!=list(range(4)) and old.get('S_PIO_REQUEST',position=2)!=4
        rows.append(dict(baseline_sha256=hashlib.sha256(baseline.read_bytes()).hexdigest(),baseline_rejected=True,mapping=got,secondary_request=old.get('S_PIO_REQUEST',position=2)))
    scenarios=[('empty',(None,)*4,(1,)*4),('secondary-only',(None,None,'ata',None),(1,)*4),
               ('holes-packet',(None,'packet','ata',None),(1,)*4),
               ('disabled-slot',('ata','packet','ata','ata'),(0,1,1,1)),
               ('full',('ata',)*4,(1,)*4)]
    requests=(1,2,4,5)
    for name,kinds,enabled in scenarios:
        m=Screen(image,kinds,requests=requests)
        m.put('C_HDD',enabled[0]);m.put('C_SLAVE',enabled[1]);m.cpu.mem_write(m.base+0xA31,bytes(enabled[2:]))
        for p in range(4):m.cpu.mem_write(m.base+0xA01+p*12,bytes((0,p,p+2,0))+bytes(8))
        m.cpu.mem_write(m.base+m.state['C_CHIP']+13,b'\x0A')
        m.call('ata_detect_primary')
        assert [m.get('S_POLICY_INDEX',position=p) for p in range(4)]==list(range(4))
        before=bytes(m.cpu.mem_read(m.base+0xA00,51));chip=bytes(m.cpu.mem_read(m.base+m.state['C_CHIP'],24))
        ports=bytes(m.cpu.mem_read(m.base+m.state['C_PORTS'],8));io=len(m.io)
        for p in range(4):
            assert bytes(m.cpu.mem_read(m.base+p*512+m.state['S_IDE'],12))==before[1+p*12:13+p*12]
            assert m.get('S_ENABLED',position=p)==enabled[p]
            assert m.get('S_PIO_REQUEST',position=p)==requests[p]
            assert m.get('S_PIO32',position=p)==(0xA>>p&1)
        # Edit the physical Secondary Master's EDD choice through its real form.
        m.keys=[0x5000,9]+[0x5000]*4+[0x3B00,27,13]+[0x5000]*4+[0x4D00,0x4400,ord('y')]
        m.call('setup_main',count=10000000)
        assert not m.keys and m.reset and len(m.io)==io,'Setup performed device I/O'
        expected=bytearray(before);expected[1+2*12+3]=1
        assert bytes(m.cpu.mem_read(m.base+0xA40,51))==expected
        fresh=PIO(image,kinds,requests=0);fresh.cmos[:]=m.cmos;fresh.writes.clear();fresh.call('settings_load')
        assert not fresh.writes and bytes(fresh.cpu.mem_read(fresh.base+0xA00,51))==expected
        assert bytes(fresh.cpu.mem_read(fresh.base+fresh.state['C_PORTS'],8))==ports
        assert bytes(fresh.cpu.mem_read(fresh.base+fresh.state['C_CHIP'],24))==chip
        fresh.call('ata_detect_primary')
        assert [fresh.get('S_POLICY_INDEX',position=p) for p in range(4)]==list(range(4))
        published=[]
        for p,kind in enumerate(kinds):
            assert bytes(fresh.cpu.mem_read(fresh.base+p*512+fresh.state['S_IDE'],12))==expected[1+p*12:13+p*12]
            assert fresh.get('S_PIO_REQUEST',position=p)==requests[p]
            assert fresh.get('S_PIO32',position=p)==(0xA>>p&1)
            assert fresh.get('S_ENABLED',position=p)==enabled[p]
            want=requests[p]-1 if kind is not None and enabled[p] else 0
            assert fresh.get('S_PIO_MODE',position=p)==want,(name,p,want,fresh.get('S_PIO_MODE',position=p))
            if kind=='ata' and enabled[p]:published.append(p)
        assert fresh.cpu.mem_read(0x475,1)==bytes((len(published),))
        for ordinal,p in enumerate(published):
            assert not fresh.public(0x80+ordinal)
            assert bytes(fresh.cpu.mem_read(0x21000,512))==fresh.payload(p,0)
        rows.append(dict(case=name,kinds=kinds,enabled=enabled,fixed_mapping=True,overview_submenu_help=True,
                         actual_edit_save_reload=True,Setup_no_ATA_IO=True,physical_requests=requests,
                         public_ATA_positions=published,payloads_match=True,other_records_unchanged=True))
    # Early Setup remains a pure policy editor without discovering attached devices.
    early=Screen(image,(None,None,'ata',None));io=len(early.io)
    early.keys=[0x5000,9]+[0x5000]*4+[13,0x4D00,27,27,27,ord('y')]
    early.call('setup_main',count=5000000)
    assert not early.keys and len(early.io)==io and not early.writes
    rows.append(dict(early_Setup_no_ATA_IO=True,physical_secondary_form=True,cancel_preserves_active=True))
    return rows


def run(image):
    return dict(inventory=inventory(image), reset=reset_and_bpb(image), cd=cd_positions(image),
                setup=setup_navigation(image), presentation=setup_presentation(image),
                full_setup=setup_full_policies(image), persistence=persistence(image), physical_policy=physical_policy_cases(image))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', type=Path)
    parser.add_argument('--case',choices=('physical-policy',))
    parser.add_argument('--baseline',type=Path)
    args = parser.parse_args()
    result = {'physical_policy':physical_policy_cases(args.image,args.baseline)} if args.case else run(args.image)
    output = args.image.parent.parent/'ide-completeness.json'
    output.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
