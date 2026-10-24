"""Exercise saved IDE policies, native setup, and actual ROM transfer owners."""
import importlib
import struct
from unicorn import x86_const as x

setup = importlib.import_module('test-setup')
legacy = importlib.import_module('test-legacy-disk')
rtc = setup.rtc
DEFAULT = bytes.fromhex('01000000000004103fffff0004000000000004103fffff0004')
# Independent numeric oracle, Phoenix1989 pp64..66; all entries use17 sectors.
PRESETS = [
    (306,4,128,305), (615,4,300,615), (615,6,300,615), (940,8,512,940),
    (940,6,512,940), (615,4,65535,615), (462,8,256,511), (733,5,65535,733),
    (900,15,65535,901), (820,3,65535,820), (855,5,65535,855), (855,7,65535,855),
    (306,8,128,319), (733,7,65535,733), None, (612,4,0,663), (977,5,300,977),
    (977,7,65535,977), (1024,7,512,1023), (733,5,300,732), (733,7,300,732),
    (733,5,300,733), (306,4,0,336), (1024,7,65535,1024), (615,4,0,615),
    (1024,4,65535,1024), (1024,5,65535,1024), (1024,8,65535,1024),
    (512,8,256,512), (615,2,615,615), (989,5,0,989), (1020,15,65535,1024),
    None, None, (1024,9,1024,1024), (1024,5,512,1024), (830,10,65535,830),
    (823,10,256,824), (615,4,128,664), (615,8,128,664), (917,15,65535,918),
    (1023,15,65535,1024), (823,10,512,823), (820,6,65535,820), None,
    (925,9,65535,925), (699,7,256,700)]
TYPE_MENU = [0x50, 28, 0x50, 0x50, 28, 0x50, 28]


def record(kind=0, translation=0, block=0, edd_off=0, cylinders=1024,
           heads=16, sectors=63, precomp=65535, landing=1024):
    return struct.pack('<BBBBHBBHH', kind, translation, block, edd_off,
                       cylinders, heads, sectors, precomp, landing)


def saved(model, payload=DEFAULT):
    model.cmos[0x40:0x5D] = b'ID\x01' + bytes((-(ord('I') + ord('D') + 1 + sum(payload)) & 255,)) + payload


class Disk(legacy.Pair):
    def __init__(self, kinds=('ata', 'absent')):
        super().__init__(kinds)
        self.negotiated = [0, 0]
        self.phase_words = 0
        self.transfer_words = 0
        self.taskfiles = []
        self.reject_multiple = False
        self.disk_words = {}
        self.command_lba = 0
        self.fail_after_words = None
        self.superio = 0xDC
        for data in self.payloads:
            struct.pack_into('<H', data, 2, 1024)
            struct.pack_into('<H', data, 94, 0x8010)

    def port_in(self, cpu, port, size, unused):
        if port == 0x3F1:
            return self.superio
        command = self.ata.get(0x1F7)
        if command == 0xC6 and port in (0x1F7, 0x3F6) and self.reject_multiple:
            return 0x51
        if command in (0xC4, 0xC5) and port in (0x1F7, 0x3F6):
            if self.fail_after_words is not None and self.transfer_words >= self.fail_after_words:
                return 0x51
            return 0x58 if self.transfer_words < self.ata[0x1F2] * 256 else 0x50
        if command in (0x20, 0xC4) and port == 0x1F0:
            assert size == 2 and not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            key = self.unit, self.command_lba * 256 + self.transfer_words
            value = self.disk_words.get(key, (key[1] + 0xA001 + self.unit) & 65535)
            self.transfer_words += 1
            return value
        return super().port_in(cpu, port, size, unused)

    def port_out(self, cpu, port, size, value, unused):
        if port == 0x3F1:
            self.superio = value
        if port == 0x3F6 and value & 4:
            self.negotiated[:] = [0, 0]
        if port == 0x1F0 and self.ata.get(0x1F7) in (0x30, 0xC5):
            assert size == 2 and not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
            self.disk_words[self.unit, self.command_lba * 256 + self.transfer_words] = value
            self.transfer_words += 1
        if port == 0x1F7:
            if value == 0xC6 and not self.reject_multiple:
                assert self.kinds[self.unit] == 'ata'
                count = self.ata.get(0x1F2, 0)
                assert count <= self.payloads[self.unit][94] and count >= 2
                self.negotiated[self.unit] = count
            if value in (0x20, 0x30, 0xC4, 0xC5):
                if value in (0xC4, 0xC5):
                    assert self.negotiated[self.unit] >= 2, 'multiple command without negotiation'
                self.transfer_words = 0
                head = self.ata.get(0x1F6, 0)
                s, lo, hi = (self.ata.get(p, 0) for p in (0x1F3, 0x1F4, 0x1F5))
                if head & 0x40:
                    self.command_lba = s | lo << 8 | hi << 16 | (head & 15) << 24
                else:
                    base = 0x9FC00 + self.unit * 512
                    h, n = self.cpu.mem_read(base + 0xF2, 2)
                    self.command_lba = (((lo | hi << 8) * h + (head & 15)) * n + s - 1)
                self.taskfiles.append((self.unit, value, self.command_lba, self.ata.get(0x1F2)))
        super().port_out(cpu, port, size, value, unused)


def detect(model, payload=DEFAULT, hdd=1, slave=1):
    model.cmos[0x10] = 0x42
    model.cmos[0x38:0x40] = bytes((66, 56, 1, hdd, 0, -(66 + 56 + 1 + hdd + 0x42) & 255,
                                   0x5A, 0x5A if slave else 0xA5))
    if payload is not None:
        saved(model, payload)
    model.cmos[0x2E:0x30] = sum(model.cmos[0x10:0x2E]).to_bytes(2, 'big')
    model.post_call('settings_load')
    model.post_call('ata_detect_primary')


def detect_saved(model, cmos):
    model.cmos[:] = cmos
    model.post_call('settings_load')
    model.post_call('ata_detect_primary')


def publication(model, enabled):
    units = [unit for unit, on in enumerate(enabled) if on]
    assert model.cpu.mem_read(0x475, 1)[0] == len(units)
    assert model.cmos[0x12] == (0xFF if len(units) == 2 else 0xF0 if units else 0)
    for unit, on in enumerate(enabled):
        base = 0x9FC00 + unit * 512
        assert model.cpu.mem_read(base + 0x20, 1)[0] == on
        assert all(enabled[position] for position, _ in model.selected_commands)
        if not on:
            assert bytes(model.cpu.mem_read(base + 0xE0, 16)) == bytes(16)
            assert bytes(model.cpu.mem_read(base + 0x2E, 4)) == bytes(4)
    for logical, vector in enumerate((0x104, 0x118)):
        expected = struct.pack('<HH', 0xE0, 0x9FC0 + units[logical] * 0x20) if logical < len(units) else bytes(4)
        assert bytes(model.cpu.mem_read(vector, 4)) == expected
        assert model.cmos[0x19 + logical] == (47 if logical < len(units) else 0)
        if logical >= len(units):
            assert model.cmos[0x1B + logical * 9:0x24 + logical * 9] == bytes(9)
        for function in (8, 2):
            if logical < len(units):
                assert not model.disk(function, dx=0x80 + logical)[0]
            else:
                # The generic helper assumes a valid logical-to-physical status owner.
                model.setup(ah=function, cx=1, dx=0x80 + logical, flags=0x202)
                model.cpu.reg_write(x.UC_X86_REG_AL, 1)
                model.cpu.reg_write(x.UC_X86_REG_ES, 0x2000)
                model.cpu.reg_write(x.UC_X86_REG_BX, 0x1000)
                model.cpu.mem_write(0x90000, b'\xcd\x13\x90')
                previous = len(model.selected_commands)
                model.cpu.emu_start(0x90000, 0x90002, count=4000000)
                assert model.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1
                assert len(model.selected_commands) == previous


def settings():
    model = setup.Setup()
    expected = DEFAULT
    assert bytes(model.cpu.mem_read(model.base + 0x190, 25)) == expected
    model.open(setup.DRIVE_EDIT + [0x44, 28])
    assert model.warm
    assert sum(model.cmos[0x40:0x5D]) & 255 == 0
    model.call('settings_load')
    assert bytes(model.cpu.mem_read(model.base + 0x190, 25)) == expected
    print('S28/S29 saved IDE extension: default, save and reload PASS', flush=True)

    # Independent semantic-invalid fixtures have correct checksum bytes.
    for offset, value in ((0, 2), (1, 15), (2, 4), (3, 9), (4, 2)):
        payload = bytearray(DEFAULT)
        payload[offset] = value
        saved(model, payload)
        before = bytes(model.cmos)
        model.call('settings_load')
        assert model.cpu.mem_read(model.base + 0x174, 1) == b'\x00'
        assert bytes(model.cpu.mem_read(model.base + 0x190, 25)) == DEFAULT
        assert bytes(model.cmos) == before
    for master, slave in ((0, 1), (1, 0), (0, 0), (1, 1)):
        model = setup.Setup()
        setup.settings_fixture(model, hdd=master)
        model.cmos[0x3F] = 0x5A if slave else 0xA5
        model.call('settings_load')
        model.open([0x44, 28])
        assert model.warm and model.cmos[0x3A] == 5
        assert model.cmos[0x3B] == 0x13 | (0 if master else 0x20) | (0 if slave else 0x40)
        assert model.cmos[0x3E:0x40] == b'\x02\0'
        disk = Disk(('ata', 'ata'))
        detect_saved(disk, model.cmos)
        publication(disk, (master, slave))
    disk = Disk(('ata', 'ata'))
    detect(disk, payload=b'\x00' + DEFAULT[1:])
    assert not disk.selected_commands and disk.cpu.mem_read(0x475, 1) == b'\x00'
    assert disk.superio == 0xDC
    publication(disk, (0, 0))
    detect(disk)
    assert disk.superio == 0xDD and disk.cpu.mem_read(0x475, 1) == b'\x02'
    print('S28/S29/S30 legacy Disabled migration, invalid-record rejection and controller gate PASS', flush=True)
    for defect in ('absent', 'checksum', 'schema', 'second-cylinder', 'second-heads', 'second-sectors'):
        for choice in ('defaults', 'setup'):
            restart = defect != 'absent' and choice == 'defaults'
            model = importlib.import_module('test-chipset').Chipset() if restart else setup.Setup()
            payload = bytearray(b'\x01' + record() + record(48))
            if defect.startswith('second-'):
                offset, value = {'second-cylinder': (17, 0), 'second-heads': (19, 17),
                                 'second-sectors': (20, 64)}[defect]
                payload[offset] = value
                if defect == 'second-cylinder':
                    payload[offset + 1] = 0
            if defect != 'absent':
                saved(model, payload)
                if defect == 'checksum':
                    model.cmos[0x43] ^= 1
                if defect == 'schema':
                    model.cmos[0x42] = 2
                    model.cmos[0x43] = -(sum(model.cmos[0x40:0x43]) + sum(payload)) & 255
            before = bytes(model.cmos)
            model.call('settings_load')
            assert model.cpu.mem_read(model.base + 0x174, 1)[0] == (defect == 'absent')
            model.script = [28] if choice == 'defaults' else [0xE0, 0x53]
            if restart:
                model.startup(entry='post_clock_alert')
                assert model.restarts == 1
            else:
                model.call('post_clock_alert')
            assert ('CMOS settings invalid.' in model.console) == (defect != 'absent')
            if defect == 'absent':
                assert not model.writes and bytes(model.cmos) == before
            elif choice == 'defaults':
                assert model.cpu.mem_read(model.base + 0x174, 1) == b'\x01'
                assert bytes(model.cmos[0x44:0x5D]) == DEFAULT
            else:
                assert not model.writes and bytes(model.cmos[0x10:]) == before[0x10:]
                assert model.cpu.mem_read(model.base + 0xF4, 1) == b'\x01'
    print('B19 signed checksum/schema/second User ranges trigger actual warning/recovery; absent extension stays valid PASS', flush=True)


def transfer():
    for block in (0, 1, 2, 5, 8):
        for function in (2, 3, 0x42, 0x43):
            for count in (16, 19):
                model = Disk()
                detect(model, b'\x01' + record(block=block) + record())
                model.commands.clear()
                payload = struct.pack('<H', 0x1357) * (count * 256)
                model.cpu.mem_write(0x21000, payload)
                if function >= 0x42:
                    model.cpu.mem_write(0x25A5A, struct.pack('<BBHHHQ', 16, 0, count, 0x1000, 0x2000, 8))
                result = model.disk(function, al=count if function < 0x40 else 0, cx=9)
                assert not result[0], (block, function, count, result, model.commands)
                multiple = block in (0, 2, 5)
                assert (0xC4 if function in (2, 0x42) else 0xC5) in model.commands if multiple else 0xC6 not in model.commands
                data = bytes(model.cpu.mem_read(0x21000, count * 512))
                expected = b''.join(struct.pack('<H', (8 * 256 + i + 0xA001) & 65535)
                                    for i in range(count * 256))
                if function in (2, 0x42):
                    assert data == expected
                else:
                    assert all(model.disk_words[0, 8 * 256 + i] == 0x1357 for i in range(count * 256))
                assert model.cpu.mem_read(0x9FC24, 1)[0] == count
                if function >= 0x42:
                    assert struct.unpack('<H', model.cpu.mem_read(0x25A5C, 2))[0] == count
    for reject, capability in ((True, 0x8010), (False, 0), (False, 0x8003)):
        model = Disk()
        model.reject_multiple = reject
        struct.pack_into('<H', model.payloads[0], 94, capability)
        detect(model)
        assert not model.disk(2, al=19)[0]
        assert 0xC4 not in model.commands and model.commands.count(0x20) == 19
    model = Disk(('ata', 'ata'))
    detect(model, b'\x01' + record(block=3) + record(block=5))
    for unit, value in enumerate((0x1357, 0x2468)):
        model.cpu.mem_write(0x21000, struct.pack('<H', value) * (19 * 256))
        assert not model.disk(3, al=19, dx=0x80 + unit)[0]
    for function in (2, 0x42):
        for reset, read in ((0x80, 0x81), (0x81, 0x80)):
            assert not model.disk(0, dx=reset)[0]
            assert model.negotiated == [0, 0]
            for external in (False, True):
                if external:
                    model.negotiated[:] = [0, 0]  # Sequential external-driver reset seam.
                if function == 0x42:
                    model.cpu.mem_write(0x25A5A, struct.pack('<BBHHHQ', 16, 0, 19, 0x1000, 0x2000, 0))
                assert not model.disk(function, al=19 if function == 2 else 0, dx=read)[0]
                assert model.negotiated[read - 0x80] == (4 if read == 0x80 else 16)
                value = 0x1357 if read == 0x80 else 0x2468
                assert bytes(model.cpu.mem_read(0x21000, 19 * 512)) == struct.pack('<H', value) * (19 * 256)
            for unit, value in enumerate((0x1357, 0x2468)):
                assert not model.disk(2, al=19, dx=0x80 + unit)[0]
                assert bytes(model.cpu.mem_read(0x21000, 19 * 512)) == struct.pack('<H', value) * (19 * 256)
    print('S33/S34/S35 CHS+EDD R/W, partial blocks, capability fallback and sibling/external reset PASS', flush=True)
    for function in (2, 3, 0x42, 0x43):
        model = Disk()
        count = 128 if function < 0x40 else 127  # Existing EDD request limit.
        struct.pack_into('<H', model.payloads[0], 94, 0x8080)
        detect(model, b'\x01' + record(block=8) + record())
        # Keep the64KiB buffer separate from the caller's stack and DAP.
        model.cpu.mem_write(0x3FFFF, b'\xA5' + bytes(65536) + b'\x5A')
        model.cpu.mem_write(0x25A5A, struct.pack('<BBHHHQ', 16, 0, count, 0, 0x4000, 8))
        assert not model.disk(function, al=count if function < 0x40 else 0, cx=9, bx=0, es=0x4000)[0]
        assert model.cpu.mem_read(0x3FFFF, 1) == b'\xA5' and model.cpu.mem_read(0x50000, 1) == b'\x5A'
        assert model.cpu.mem_read(0x9FC24, 1) == bytes((count,))
    for function in (2, 3, 0x42, 0x43):
        model = Disk()
        detect(model, b'\x01' + record(block=3) + record())  #4-sector blocks.
        model.fail_after_words = 5 * 256
        model.cpu.mem_write(0x25A5A, struct.pack('<BBHHHQ', 16, 0, 9, 0x1000, 0x2000, 8))
        assert model.disk(function, al=9 if function < 0x40 else 0)[0]
        assert model.cpu.mem_read(0x9FC24, 1) == b'\x04'
        if function >= 0x40:
            assert model.cpu.mem_read(0x25A5C, 2) == b'\x04\x00'
        assert not any(cmd in (0x20, 0x30) for _, cmd, _, _ in model.taskfiles), 'partial transfer replayed'
    print('S33 maximum128-sector block,64KiB guards and partial-error counts/no replay PASS', flush=True)


def geometry():
    for mode, heads, sectors in ((0, 4, 17), (1, 4, 17), (2, 4, 17), (3, 32, 63)):
        model = Disk()
        detect(model, b'\x01' + record(48, mode, cylinders=120, heads=4, sectors=17) + record())
        # Explicit mapping defeats the accepted first-logical-disk BPB override.
        bpb = bytearray(512)
        bpb[0] = 0xEB
        struct.pack_into('<H', bpb, 11, 512)
        struct.pack_into('<H', bpb, 14, 1)
        struct.pack_into('<HH', bpb, 24, 63, 255)
        bpb[510:] = b'\x55\xAA'
        model.cpu.mem_write(0x7C00, bytes(bpb))
        assert not model.disk(8)[0]
        actual_heads = model.cpu.reg_read(x.UC_X86_REG_DH) + 1
        actual_sectors = model.cpu.reg_read(x.UC_X86_REG_CL) & 63
        assert (actual_heads, actual_sectors) == (heads, sectors)
        assert model.cpu.mem_read(0x9FCE5, 2) == b'\xff\xff'
        assert not model.disk(2, al=2, cx=0x0102, dx=0x180)[0]
        assert model.taskfiles[-1][2] == ((1 * actual_heads + 1) * actual_sectors + 1)
    model = Disk()
    struct.pack_into('<H', model.payloads[0], 98, 0)
    struct.pack_into('<H', model.payloads[0], 2, 128)
    detect(model, b'\x01' + record(translation=1) + record())
    assert not model.disk(2, al=2, cx=0x0307, dx=0x280)[0]
    assert model.taskfiles[-1][2] == (3 * 16 + 2) * 63 + 6
    assert not model.ata[0x1F6] & 0x40
    # Auto alone keeps the accepted BPB, while explicit translation defeats it.
    for mode in (0, 1, 2, 3):
        model = Disk()
        detect(model, b'\x01' + record(translation=mode) + record())
        model.cpu.mem_write(0x7C00, bytes(bpb))
        assert not model.disk(8)[0]
        assert (model.cpu.reg_read(x.UC_X86_REG_DH) + 1, model.cpu.reg_read(x.UC_X86_REG_CL) & 63) == (
            (255, 63) if mode == 0 else (16, 63) if mode in (1, 2) else (32, 63))
    # Exercise halving beyond1024 cylinders and each capacity threshold boundary.
    cases = [(2, 4096 * 16 * 63, 4096, 64), (2, 65535 * 16 * 63, 65535, 128)]
    cases += [(3, capacity, 1024, heads) for capacity, heads in (
        (0x1F8000, 32), (0x1F8001, 64), (0x3F0000, 64), (0x3F0001, 128),
        (0x7E0000, 128), (0x7E0001, 255), (0x10000001, 255))]
    for mode, capacity, native_cylinders, heads in cases:
        model = Disk()
        struct.pack_into('<H', model.payloads[0], 2, native_cylinders)
        struct.pack_into('<I', model.payloads[0], 120, capacity)
        detect(model, b'\x01' + record(translation=mode) + record())
        assert not model.disk(8)[0]
        cx = model.cpu.reg_read(x.UC_X86_REG_CX)
        cylinders = ((cx >> 8) | ((cx & 0xC0) << 2)) + 1
        assert model.cpu.reg_read(x.UC_X86_REG_DH) + 1 == heads and cx & 63 == 63
        bounded = min(capacity, 0x10000000)
        assert cylinders * heads * 63 <= bounded
        table = bytes(model.cpu.mem_read(0x9FCE0, 16))
        assert struct.unpack_from('<H', table)[0] == min(bounded // (heads * 63), 1024)
        assert table[2] == heads and table[14] == 63
        assert struct.unpack_from('<H', table)[0] * heads * 63 <= bounded
        model.cpu.mem_write(0x25A5A, b'\x1E\x00' + bytes(28))
        assert not model.disk(0x48)[0]
        params = bytes(model.cpu.mem_read(0x25A5A, 26))
        assert struct.unpack_from('<Q', params, 16)[0] == bounded
        assert struct.unpack_from('<III', params, 4) == (bounded // (heads * 63), heads, 63)
    for off_unit in (0, 1):
        model = Disk(('ata', 'ata'))
        policies = [record(), record()]
        policies[off_unit] = record(edd_off=1)
        detect(model, b'\x01' + b''.join(policies))
        for unit in (0, 1):
            for function in (0x41, 0x42, 0x43, 0x44, 0x47, 0x48):
                model.cpu.mem_write(0x25A5A, struct.pack('<BBHHHQ', 16, 0, 1, 0x1000, 0x2000, 0)
                                    if function != 0x48 else b'\x1E\x00' + bytes(28))
                previous = len(model.taskfiles)
                if function == 0x41 and unit != off_unit:
                    model.setup(ah=function, dx=0x80 + unit, flags=0x202)
                    model.cpu.reg_write(x.UC_X86_REG_BX, 0x55AA)
                    model.cpu.mem_write(0x90000, b'\xcd\x13\x90')
                    model.cpu.emu_start(0x90000, 0x90002, count=4000000)
                    result = (bool(model.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 1),
                              model.cpu.reg_read(x.UC_X86_REG_AX), model.cpu.mem_read(0x474, 1)[0])
                    assert model.cpu.reg_read(x.UC_X86_REG_BX) == 0xAA55
                    assert model.cpu.reg_read(x.UC_X86_REG_CX) == 1
                else:
                    result = model.disk(function, al=0 if function == 0x43 else 1,
                                        dx=0x80 + unit, bx=0x55AA if function == 0x41 else 0x1000)
                assert result[0] == (unit == off_unit), (unit, off_unit, function, result)
                if unit == off_unit:
                    assert result[2] == 1 and len(model.taskfiles) == previous
            payload = struct.pack('<H', 0x7511 + unit) * 256
            model.cpu.mem_write(0x21000, payload)
            assert not model.disk(3, dx=0x80 + unit)[0]
            model.cpu.mem_write(0x21000, bytes(512))
            assert not model.disk(2, dx=0x80 + unit)[0]
            assert bytes(model.cpu.mem_read(0x21000, 512)) == payload
            assert not model.disk(8, dx=0x80 + unit)[0]
            assert model.cpu.reg_read(x.UC_X86_REG_DL) == 2
    model = Disk(('packet', 'ata'))
    detect(model, b'\x01' + record(48, 2, 5, cylinders=120, heads=4, sectors=17) + record())
    assert model.cpu.mem_read(0x475, 1) == b'\x01'
    assert all(unit == 1 for unit, cmd in model.selected_commands if cmd == 0xC6)
    class OldDisk(Disk):
        def port_in(self, cpu, port, size, unused):
            if self.unit == 0 and self.ata.get(0x1F7) == 0xEC and port in (0x1F7, 0x3F6):
                return 0x51  # Ready old ATA device rejects IDENTIFY.
            return super().port_in(cpu, port, size, unused)
    for kind, present in ((0, 0), (48, 1)):
        model = OldDisk()
        detect(model, b'\x01' + record(kind, cylinders=120, heads=4, sectors=17) + record())
        assert model.cpu.mem_read(0x475, 1) == bytes((present,))
        if present:
            assert (0, 0x91) in model.selected_commands
            assert not model.disk(2, al=2, cx=0x0102, dx=0x180)[0]
            assert not model.ata[0x1F6] & 0x40 and model.taskfiles[-2][2] == 86 and model.command_lba == 87
    print('S32/S36/S37 explicit/BPB precedence, native CHS, packet exclusion and EDD switch PASS', flush=True)


def reset_geometry():
    # Independent device state: PATA SRST clears both devices' initialized
    # CHS parameters (kernel.org libATA guide, Error handling / Reset).
    # Do not decode hardware addresses using the BIOS's own geometry bytes.
    class ResetDisk(Disk):
        def __init__(self, kinds):
            super().__init__(kinds)
            self.hardware_geometry = [(16, 63), (16, 63)]

        def port_out(self, cpu, port, size, value, unused):
            if port == 0x3F6 and value & 4:
                self.hardware_geometry[:] = [(16, 63), (16, 63)]
            if port == 0x1F7 and value == 0x91:
                self.hardware_geometry[self.unit] = (
                    (self.ata.get(0x1F6, 0) & 15) + 1, self.ata.get(0x1F2, 0))
            super().port_out(cpu, port, size, value, unused)
            if port == 0x1F7 and value in (0x20, 0x30) and not self.ata[0x1F6] & 0x40:
                heads, sectors = self.hardware_geometry[self.unit]
                cylinder = self.ata.get(0x1F4, 0) | self.ata.get(0x1F5, 0) << 8
                self.command_lba = ((cylinder * heads + (self.ata[0x1F6] & 15)) * sectors
                                    + self.ata.get(0x1F3, 0) - 1)
                self.taskfiles[-1] = (self.unit, value, self.command_lba, self.ata[0x1F2])

    cases = [(('ata', 'ata'), (48, 1), False),
             (('ata', 'ata'), (0, 0), False),
             (('ata', 'ata'), (48, 1), True),
             (('packet', 'ata'), (48, 1), False),
             (('ata', 'absent'), (48, 1), False)]
    for kinds, types, lba in cases:
        m = ResetDisk(kinds)
        for data in m.payloads:
            struct.pack_into('<H', data, 98, 0x200 if lba else 0)
        policies = b'\x01' + b''.join(
            record(1, 1, cylinders=306, heads=4, sectors=17, precomp=128, landing=305)
            if kind == 1 else record(kind, 1, cylinders=120, heads=5 if unit == 0 else 4)
            for unit, kind in enumerate(types))
        detect(m, policies)
        units = [unit for unit, kind in enumerate(kinds) if kind == 'ata']
        logical_geometry = [(4, 17) if kind == 1 else (5 if unit == 0 else 4, 63)
                            if kind else (16, 63) for unit, kind in enumerate(types)]
        expected = [logical_geometry[unit] if types[unit] and not lba else (16, 63)
                    for unit in range(2)]
        for unit in units:
            assert m.hardware_geometry[unit] == expected[unit], (
                kinds, types, lba, unit, m.hardware_geometry, m.selected_commands,
                bytes(m.cpu.mem_read(0x9FC00 + unit * 512 + 0x1D0, 12)).hex())
            sector = b'BOOT' + bytes(506) + b'\x55\xAA'
            for word in range(256):
                m.disk_words[unit, word] = struct.unpack_from('<H', sector, word * 2)[0]
        # Actual bootstrap -> installed INT13 reset -> signed first-disk read.
        from unicorn import UC_HOOK_CODE
        stop = m.cpu.hook_add(UC_HOOK_CODE, lambda cpu, a, n, u: cpu.emu_stop(),
                             None, 0x7C00, 0x7C00)
        try:
            m.cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
            m.cpu.emu_start(0xF0000 + rtc.symbol('int19'), 0xFFFFFF, count=16000000)
        finally:
            m.cpu.hook_del(stop)
        assert m.cpu.reg_read(x.UC_X86_REG_CS) == 0 and m.cpu.reg_read(x.UC_X86_REG_IP) == 0x7C00
        assert m.cpu.mem_read(0x7C00, 4) == b'BOOT'
        for reset_drive in range(len(units)):
            for function in (None, 0, 0x0D):
                if function is not None:
                    previous = len(m.selected_commands)
                    assert not m.disk(function, dx=0x80 + reset_drive)[0]
                    restored = [unit for unit, command in m.selected_commands[previous:] if command == 0x91]
                    assert restored == [unit for unit in units if not lba]
                for logical, unit in enumerate(units):
                    assert m.hardware_geometry[unit] == expected[unit]
                    heads, sectors = logical_geometry[unit]
                    target = (heads + 1) * sectors + 1  # C=1 H=1 S=2
                    payload = struct.pack('<H', 0xB100 + unit) * 256
                    m.cpu.mem_write(0x21000, payload)
                    assert not m.disk(3, cx=0x0102, dx=0x180 + logical)[0]
                    assert m.taskfiles[-1][2] == target
                    m.cpu.mem_write(0x21000, bytes(512))
                    assert not m.disk(2, cx=0x0102, dx=0x180 + logical)[0]
                    assert m.taskfiles[-1][2] == target
                    assert m.cpu.mem_read(0x21000, 512) == payload
    print('Reset geometry: actual INT19, AH00/AH0D, both CHS slots including Auto, LBA/packet/absent exclusions and nonzero read/write PASS', flush=True)


def ui():
    # Reach User at the end of the paged menu, edit every numeric field, save.
    script = TYPE_MENU + [0x51] * 4 + [28]
    numbers = ('120', '4', '17', '128', '119')
    for number in numbers:
        script += [0x50, 28] + setup.keys(number + '\r')
    script += [0x50, 0x4D, 0x50, 0x4D, 0x50, 0x4D, 0x44, 28]
    model = setup.Setup()
    model.open(script.copy())
    assert model.warm
    expected = record(48, 1, 1, 1, 120, 4, 17, 128, 119)
    assert model.cmos[0x45:0x51] == expected, model.cmos[0x45:0x51].hex()
    model.call('settings_load')
    assert bytes(model.cpu.mem_read(model.base + 0x191, 12)) == expected
    # Summary owns its scratch, not persistent active settings.
    before = bytes(model.cpu.mem_read(model.base + 0x190, 25))
    model.script = []
    model.call('post_debug_summary')
    assert bytes(model.cpu.mem_read(model.base + 0x190, 25)) == before
    model = setup.Setup(segment=0x8FC0)
    model.open(script[:4] + [0x50] + script[4:])
    assert model.warm and model.cmos[0x51:0x5D] == expected
    assert model.cmos[0x45:0x51] == record()
    disk = Disk(('ata', 'ata'))
    detect_saved(disk, model.cmos)
    assert bytes(disk.cpu.mem_read(0x9FFD0, 12)) == expected
    assert not disk.disk(8, dx=0x81)[0]
    cx, dx = disk.cpu.reg_read(x.UC_X86_REG_CX), disk.cpu.reg_read(x.UC_X86_REG_DX)
    assert ((cx >> 8) | ((cx & 0xC0) << 2)) + 2 == 120
    assert (dx >> 8) + 1 == 4 and cx & 63 == 17 and dx & 255 == 2
    fdpt = bytearray(16)
    struct.pack_into('<H', fdpt, 0, 120)
    fdpt[2], fdpt[7], fdpt[14] = 4, 4, 17
    struct.pack_into('<H', fdpt, 5, 128)
    struct.pack_into('<H', fdpt, 12, 119)
    assert bytes(disk.cpu.mem_read(0x9FEE0, 16)) == fdpt
    # Invalid numeric edits and canceled editors cannot alter User defaults.
    invalid = TYPE_MENU + [0x51] * 4 + [28, 0x50]
    for value in ('0', '17', '64', '65536', '65536'):
        invalid += [28] + setup.keys(value + '\r\x1b') + [0x50]
    model = setup.Setup()
    model.open(invalid + [0x44, 28])
    assert model.warm and model.cmos[0x45:0x51] == record(48)
    print('S31/S38/S39 real keyboard paged type/User fields/save, relocation and summary ownership PASS', flush=True)


def presets_and_cancel():
    steps = 0
    for kind, data in enumerate(PRESETS, 1):
        if data is None:
            continue
        steps += 1
        model = setup.Setup()
        def popup_columns(m):
            if m.text(5, 26, 16) != 'PHOENIX DISK TYPE':
                return
            assert m.text(6, 26, 38) == 'Type            Cyls    Heads   Sectors'
            for row in range(7, 19):
                name = m.text(row, 26, 12).strip()
                if not name.startswith('Type '):
                    continue
                number = int(name[5:])
                cyl, heads, _, _ = PRESETS[number - 1]
                for col, value in ((42, cyl), (50, heads), (58, 17)):
                    assert m.text(row, col, 5).strip() == str(value), (row, col, number)
                    colors = bytes(m.cpu.mem_read(0xB8000 + row * 160 + col * 2 + 1, 10))[::2]
                    assert colors == bytes((0x70 if number == kind else 0x17,)) * 5
                assert m.text(row, 78, 2).strip() == ''
        model.observer = popup_columns
        model.open(TYPE_MENU + [0x50] * steps + [28, 0x44, 28])
        cylinders, heads, precomp, landing = data
        expected = record(kind, cylinders=cylinders, heads=heads, sectors=17,
                          precomp=precomp, landing=landing)
        assert model.cmos[0x45:0x51] == expected, kind
        model.call('settings_load')
        assert model.cpu.mem_read(model.base + 0x174, 1) == b'\x01'
        disk = Disk()
        struct.pack_into('<I', disk.payloads[0], 120, 0x10000000)
        detect_saved(disk, model.cmos)
        assert disk.cpu.mem_read(0x9FCF2, 2) == bytes((heads, 17))
        fdpt = bytearray(16)
        struct.pack_into('<H', fdpt, 0, cylinders)
        fdpt[2], fdpt[7], fdpt[8], fdpt[14] = heads, 4, 8 if heads > 8 else 0, 17
        struct.pack_into('<H', fdpt, 5, precomp)
        struct.pack_into('<H', fdpt, 12, landing)
        assert bytes(disk.cpu.mem_read(0x9FCE0, 16)) == fdpt, kind
        assert not disk.disk(8)[0]
        cx, dx = disk.cpu.reg_read(x.UC_X86_REG_CX), disk.cpu.reg_read(x.UC_X86_REG_DX)
        assert ((cx >> 8) | ((cx & 0xC0) << 2)) + 2 == cylinders, kind
        assert (dx >> 8) + 1 == heads and cx & 63 == 17 and dx & 255 == 1
        assert struct.unpack('<I', disk.cpu.mem_read(0x9FC2E, 4))[0] == cylinders * heads * 17
    changed = TYPE_MENU + [0x50, 28]
    for ending, save_defaults in (([0x43, 28, 0x44, 28], True), ([1, 1, 1, 28], False)):
        model = setup.Setup()
        before = bytes(model.cmos)
        active = bytes(model.cpu.mem_read(model.base + 0x190, 25))
        model.open(changed + ending)
        if save_defaults:
            assert model.warm and bytes(model.cmos[0x44:0x5D]) == DEFAULT
        else:
            assert not model.warm and bytes(model.cmos) == before
        assert bytes(model.cpu.mem_read(model.base + 0x190, 25)) == active
    class FailedSave(setup.Setup):
        def port_in(self, cpu, port, size, unused):
            value = super().port_in(cpu, port, size, unused)
            return value ^ 255 if port == 0x71 and self.index == 0x45 and (0x40, 73) in self.writes else value
    model = FailedSave()
    seen = []
    def observe(m):
        if 'CMOS verification failed.' in m.text(19, 23, 46):
            assert not m.warm and m.cpu.mem_read(m.base + 0x191, 1) == b'\x00'
            seen.append(True)
            m.observer = None
            m.script = [1, 1, 1, 28]
    model.observer = observe
    model.open(changed + [0x44, 28])
    assert seen and not model.warm
    print('S29/S31/S38 all43 valid numbered types, reserved skips, Defaults/Discard and failed-save containment PASS', flush=True)


def availability():
    master = [0x50, 28, 0x50, 0x50, 28]
    # Auto and preset types skip all geometry; User permits all fields.
    for kind, fields in ((0, [0, 1, 7, 8, 9]), (1, [0, 1, 7, 8, 9]),
                         (48, list(range(10)))):
        model = setup.Setup()
        saved(model, b'\x01' + record(kind) + record())
        model.call('settings_load')
        seen = []
        def observe(m):
            if m.cpu.mem_read(m.base + 0x188, 1) != b'\x00':
                return
            field = m.cpu.mem_read(m.base + 0xF7, 1)[0]
            if not seen or seen[-1] != field:
                seen.append(field)
            assert field in fields
            for index in range(2, 7):
                row = (5,6,7,8,9,10,11)[index]
                for col in (24, 49):
                    color = m.cpu.mem_read(0xB8000 + row * 160 + col * 2 + 1, 1)[0]
                    if kind != 48:
                        assert color == 8
            assert m.text(13, 24, 16) == 'TRANSFER OPTIONS'
            assert m.text(15, 24, 10) == 'Block Mode'
            assert m.text(22, 24, 33).strip() == ''
            if not m.script and not m.pending:
                m.observer = None
                m.script = [1, 1, 1, 28]
        model.observer = observe
        model.open(master + [0x50] * 12 + [0x48] * 12)
        assert seen == fields + fields[-2::-1], seen
    # Disabling a device leaves its enable switch reachable, including at ends.
    model = setup.Setup()
    seen = []
    def disabled(m):
        if m.cpu.mem_read(m.base + 0x188, 1) != b'\x00' or m.cpu.mem_read(m.base + 0x181, 1) != b'\x00':
            return
        assert m.cpu.mem_read(m.base + 0xF7, 1)[0] in (0,1)
        assert m.text(5, 49, 8) == 'Disabled'
        for index in range(2, 10):
            row = (5,6,7,8,9,10,11,14,15,16)[index]
            for col in (24, 49):
                assert m.cpu.mem_read(0xB8000 + row * 160 + col * 2 + 1, 1) == b'\x08'
        seen.append(True)
        if not m.script and not m.pending:
            m.observer = None
            m.script = [1, 1, 1, 28]
    model.observer = disabled
    model.open(master + [0x4D] + [0x50] * 12 + [0x48] * 12)
    assert seen
    # Disabled controller skips both device entries, without locking its switch.
    model = setup.Setup()
    saved(model, b'\x00' + record() + record())
    model.call('settings_load')
    seen = []
    def controller(m):
        if m.cpu.mem_read(m.base + 0xF5, 2) != b'\x01\x01':
            return
        field = m.cpu.mem_read(m.base + 0xF7, 1)[0]
        assert field in (0, 1, 4, 5, 6)
        if not seen or seen[-1] != field:
            seen.append(field)
        assert m.text(11, 24, 22) == 'Primary IDE Controller'
        assert m.text(11, 49, 8) == 'Disabled'
        for row in (8, 9):
            for col in (24, 49):
                assert m.cpu.mem_read(0xB8000 + row * 160 + col * 2 + 1, 1) == b'\x08'
        if not m.script and not m.pending:
            m.observer = None
            m.script = [1, 1, 28]
    model.observer = controller
    model.open([0x50, 28] + [0x50] * 6 + [0x48] * 6)
    assert seen == [0, 1, 4, 5, 6, 5, 4, 1, 0], seen
    print('Fixed columns, type popup geometry/colors, gray dependencies and skipped keyboard focus PASS', flush=True)


def policy_choices():
    for unit in (0, 1):
        prefix = [0x50, 28] + [0x50] * (2 + unit) + [28]
        for field, offset, values in ((2, 1, range(4)), (3, 2, range(9)), (4, 3, range(2))):
            for value in values:
                model = setup.Setup()
                active = bytes(model.cpu.mem_read(model.base + 0x190, 25))
                def observe(m):
                    assert bytes(m.cpu.mem_read(m.base + 0x190, 25)) == active
                model.observer = observe
                model.open(prefix + [0x50] * field + [0x4D] * value + [0x44, 28])
                assert model.warm
                expected = bytearray(record())
                expected[offset] = value
                assert model.cmos[0x45 + unit * 12:0x51 + unit * 12] == expected
                assert model.cmos[0x45 + (1 - unit) * 12:0x51 + (1 - unit) * 12] == record()
                disk = Disk(('ata', 'ata'))
                detect_saved(disk, model.cmos)
                assert bytes(disk.cpu.mem_read(0x9FDD0 + unit * 512, 12)) == expected
    nondefault = b'\x01' + record(translation=3, block=5, edd_off=1) + record(translation=2, block=3)
    model = setup.Setup()
    setup.settings_fixture(model, types=0x53, hdd=0, boot=2, seek=0xA5)
    model.cmos[0x3F] = 0xA5
    saved(model, nondefault)
    model.call('settings_load')
    active = bytes(model.cpu.mem_read(model.base + 0x190, 25))
    model.open([0x43, 28, 0x44, 28])
    assert model.warm and bytes(model.cmos[0x44:0x5D]) == DEFAULT
    assert model.cmos[0x10] == 0x40 and model.cmos[0x3B:0x3D] == b'\x13\x01'
    assert model.cmos[0x3E:0x40] == b'\x02\0'
    assert bytes(model.cpu.mem_read(model.base + 0x190, 25)) == active
    for action in ('defaults', 'save'):
        model = setup.Setup()
        saved(model, nondefault)
        model.call('settings_load')
        active = bytes(model.cpu.mem_read(model.base + 0x190, 25))
        before = bytes(model.cmos)
        snapshots = []
        def observe(m):
            assert bytes(m.cpu.mem_read(m.base + 0x190, 25)) == active
            snapshots.append(bytes(m.cpu.mem_read(m.base + 0x1B0, 25)))
        model.observer = observe
        ending = [0x43, 1, 0x44, 28] if action == 'defaults' else [0x44, 1, 1, 1, 1, 28]
        model.open([0x50, 28, 0x50, 0x50, 28, 0x50, 0x50, 0x4D] + ending)
        changed = bytearray(nondefault)
        changed[2] = 0
        assert bytes(changed) in snapshots
        assert DEFAULT not in snapshots, 'canceled Defaults changed the draft'
        if action == 'defaults':
            assert model.warm and bytes(model.cmos[0x44:0x5D]) == changed
        else:
            assert not model.warm and bytes(model.cmos[0x10:]) == before[0x10:]
    print('B27 every translation/block/EDD choice on master+slave, saved reload, canceled Defaults/Save and active ownership PASS', flush=True)


def none_choice():
    # Select None with real keyboard input on each position; never persist UI49.
    payload = b'\x01' + record(1, cylinders=306, heads=4, sectors=17,
                              precomp=128, landing=305) + record()
    for unit in (0, 1):
        prefix = [0x50, 28] + [0x50] * (2 + unit) + [28, 0x50]
        for popup, apply in ((False, True), (True, True), (True, False)):
            model = setup.Setup()
            saved(model, payload)
            model.call('settings_load')
            before = bytes(model.cpu.mem_read(model.base + 0x190, 25))
            seen = []
            def observe(m):
                assert bytes(m.cpu.mem_read(m.base + 0x190, 25)) == before
                if m.text(6, 49, 4) == 'None':
                    seen.append(True)
                    for row in (7, 8, 9, 10, 11, 14, 15, 16):
                        assert m.cpu.mem_read(0xB8000 + row*160 + 49*2+1,1) == b'\x08'
            model.observer = observe
            # Master starts Type1, slave Auto. Left wraps through Auto to None.
            left = [0x4B] * (2 if unit == 0 else 1)
            change = [28] + left + [28 if apply else 1] if popup else left
            model.open(prefix + change + [0x44, 28])
            assert model.warm and bool(seen) == apply
            expected = bytearray(payload)
            if unit == 0 and not popup:
                expected[1] = 0  # Inline arrows applied Auto before reaching None.
            assert bytes(model.cmos[0x44:0x5D]) == expected
            model.call('settings_load')
            flag = 0x171 if unit == 0 else 0x177
            assert model.cpu.mem_read(model.base+flag,1) == bytes((not apply,))
            disk = Disk(('ata','ata'))
            detect_saved(disk, model.cmos)
            publication(disk, (not apply,1) if unit == 0 else (1,not apply))
            assert disk.superio & 0x20 == 0, 'None disabled the shared controller'
            if apply:
                # The locked device can be re-enabled directly from its type.
                saved_cmos = bytes(model.cmos)
                model = setup.Setup()
                model.cmos[:] = saved_cmos
                model.call('settings_load')
                model.open(prefix + [0x4D, 0x44, 28])
                model.call('settings_load')
                assert model.cpu.mem_read(model.base+flag,1) == b'\x01'
                assert model.cmos[0x45+unit*12] == 0
    # A physically present pair with both set None causes no reset/IDENTIFY.
    for cold in (False, True):
        model = setup.production_post_model(kinds=('ata','ata'))
        setup.schema2_fixture(model, types=0, flags=0x73, order=(2,0,0))
        saved(model, payload)
        card = importlib.import_module('test-legacy-boot')
        model.cpu.mem_write(0xC8000,bytes(card.rom(0,provider=True)))
        def before_rom(m,name):
            if name == 'option_rom_discovery':
                assert m.disk_device.reset_count == 0 and not m.disk_device.selected_commands
                assert m.cpu.mem_read(0x475,1) == b'\0'
                assert m.cpu.mem_read(m.base+0x20,1) == b'\0'
                assert m.cpu.mem_read(m.base+0x220,1) == b'\0'
        model.startup_observer = before_rom
        model.startup(reset=cold,production_controls=True,through_boot=True)
        assert model.cpu.mem_read(0x7C00,4) == b'CARD'
        assert model.cpu.mem_read(0x475,1) == b'\x01'
        assert not model.disk_device.selected_commands
    print('IDE None: keyboard/popup/save/cancel/re-enable, preserved records, per-position detection, cold/warm option-ROM boot PASS',flush=True)


if __name__ == '__main__':
    settings()
    transfer()
    geometry()
    reset_geometry()
    ui()
    presets_and_cancel()
    availability()
    policy_choices()
    none_choice()
