"""Execute legacy INT13 services in the actual ROM with a bounded ATA model."""
import importlib
import struct
from unicorn import x86_const as x

rtc = importlib.import_module('test-rtc')


class Disk(rtc.Clock):
    def __init__(self, binary=False, hour24=True):
        super().__init__(binary, hour24)
        self.cpu.mem_write(0x4C, struct.pack('<HH', rtc.symbol('int13'), 0xF000))
        self.cpu.mem_write(0x9FC20, b'\x01')
        self.cpu.mem_write(0x9FC2E, struct.pack('<I', 3970048))
        self.cpu.mem_write(0x9FCF2, bytes((16, 63)))
        self.cpu.mem_write(0x9FD71, b'\x01')  # Loaded HDD Auto for direct ATA tests.
        self.cpu.mem_write(0x9FDE3, b'\x01')  # Selected physical controller enabled.
        self.cpu.mem_write(0x9FD90, b'\x01')  # Additive default controller policy.
        self.ata = {0x1F1: 1}
        self.commands = []
        self.data_reads = 0
        self.data_writes = []
        self.data_widths = []
        self.reject = None
        self.absent = False
        self.identify = bytearray(512)
        struct.pack_into('<H', self.identify, 3 * 2, 16)
        struct.pack_into('<H', self.identify, 6 * 2, 63)
        struct.pack_into('<H', self.identify, 49 * 2, 0x0200)
        struct.pack_into('<I', self.identify, 60 * 2, 3970048)
        self.identify_word = 0
        self.pit_counter = 0xFFFF
        self.pit_byte = 0
        self.pit_latches = 0
        self.post_codes = []
        self.identify_complete_flags = None

    def interrupt(self, cpu, vector, unused):
        if vector == 0x10:  # POST model strings; retained VGA tested in86Box.
            assert cpu.reg_read(x.UC_X86_REG_AH) == 0x0E
            return
        super().interrupt(cpu, vector, unused)

    def port_in(self, cpu, port, size, unused):
        if port == 0x3F1:
            return 0x3F  # SuperIO CR0, opaque except controller-enable contract.
        if port == 0x40:
            value = (self.pit_counter >> (8 * self.pit_byte)) & 255
            self.pit_byte ^= 1
            return value
        if port == 0x1F0:
            expected = 1 if self.ata.get(0x1F7) == 0x22 and len(self.data_widths) >= 256 else 2
            assert size == expected, 'READ LONG ECC requires byte I/O after 256 words'
            self.data_widths.append(size)
            self.data_reads += 1
            if self.ata.get(0x1F7) == 0xEC:
                value = struct.unpack_from('<H', self.identify, self.identify_word * 2)[0]
                self.identify_word += 1
                return value
            return 0xA55A if size == 2 else 0xE0 + len(self.data_widths) - 257
        if port in (0x1F7, 0x3F6):
            if self.absent or self.ata.get(0x1F6, 0) & 0x10:
                return 0
            command = self.ata.get(0x1F7, 0)
            if command == self.reject:
                return 0x51
            return 0x58 if command in (0x20, 0x22, 0x30, 0x32, 0x50) or (command == 0xEC and self.identify_word < 256) else 0x50
        if port == 0x1F1:
            return 1
        if 0x1F2 <= port <= 0x1F6:
            return self.ata.get(port, 0)
        return super().port_in(cpu, port, size, unused)

    def port_out(self, cpu, port, size, value, unused):
        if port in (0x3F0, 0x3F1):
            return
        if port == 0x43 and value == 0:
            self.pit_counter = (self.pit_counter - 1024) & 0xFFFF
            self.pit_byte = 0
            self.pit_latches += 1
            return
        if port == 0x80:
            self.post_codes.append(value)
            if value == 0x7D:
                self.identify_complete_flags = cpu.reg_read(x.UC_X86_REG_EFLAGS)
            return
        if port == 0x0A:
            assert value == 6, 'idle floppy service must mask DMA channel2'
            return
        if 0x1F0 <= port <= 0x1F7 or port == 0x3F6:
            if port == 0x1F0:
                expected = 1 if self.ata.get(0x1F7) == 0x32 and len(self.data_widths) >= 256 else 2
                assert size == expected, 'WRITE LONG ECC requires byte I/O after 256 words'
                self.data_widths.append(size)
                self.data_writes.append(value)
            else:
                self.ata[port] = value
                if port == 0x1F7:
                    self.data_widths.clear()
                    self.commands.append(value)
            return
        return super().port_out(cpu, port, size, value, unused)

    def disk(self, ah, al=1, cx=1, dx=0x80, bx=0x1000, es=0x2000, flags=0x602):
        self.setup(ah, cx, dx, flags=flags)
        caller_flags = flags
        self.cpu.reg_write(x.UC_X86_REG_AL, al)
        self.cpu.reg_write(x.UC_X86_REG_BX, bx)
        self.cpu.reg_write(x.UC_X86_REG_ES, es)
        caller = getattr(self, 'call_segment', 0x9000) * 16
        self.cpu.reg_write(x.UC_X86_REG_CS, caller >> 4)
        before = self.state()
        self.cpu.mem_write(caller, b'\xcd\x13\x90')
        self.cpu.emu_start(caller, caller + 2, count=4000000)
        assert self.cpu.reg_read(x.UC_X86_REG_CS) == caller >> 4
        assert self.cpu.reg_read(x.UC_X86_REG_IP) == 2
        after = self.state()
        for name in rtc.REGS:
            if name == 'EAX' or (ah in (8, 0x15) and name in ('ECX', 'EDX')):
                assert before[name] >> 16 == after[name] >> 16, name
            else:
                assert before[name] == after[name], (name, before[name], after[name])
        flags = self.cpu.reg_read(x.UC_X86_REG_EFLAGS)
        assert (flags & 0x600) == ((caller_flags & 0x400) | 0x200)
        status = self.cpu.mem_read(0x474, 1)[0]
        ebda = struct.unpack('<H', self.cpu.mem_read(0x40E, 2))[0] * 16
        selected = ebda + (0x200 if self.cpu.mem_read(ebda + 0x220, 1)[0] and
                            (dx == 0x81 or not self.cpu.mem_read(ebda + 0x20, 1)[0]) else 0)
        assert status == self.cpu.mem_read(selected + 0x21, 1)[0]
        return bool(flags & 1), self.cpu.reg_read(x.UC_X86_REG_AX), status

    def post_call(self, name, flags=2):
        cmos_before = bytes(self.cmos)
        self.setup(flags=flags)
        self.cpu.reg_write(x.UC_X86_REG_FS, 0x9FC0)
        self.cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
        self.cpu.reg_write(x.UC_X86_REG_SP, 0x7FFE)
        ss = self.cpu.reg_read(x.UC_X86_REG_SS)
        self.cpu.mem_write(ss * 16 + 0x7FFE, b'\xff\xff')
        self.cpu.emu_start(0xF0000 + rtc.symbol(name), 0xFFFFF,
                           count=16000000)  # Includes the full absent-device poll.
        assert self.cpu.reg_read(x.UC_X86_REG_IP) == 0xFFFF
        if name == 'ata_identify_selected':
            assert bytes(self.cmos) == cmos_before  # Caller owns CMOS publication.
        else:
            checksum = sum(self.cmos[0x10:0x2E]) & 0xFFFF
            assert self.cmos[0x2E:0x30] == checksum.to_bytes(2, 'big')


class Pair(Disk):
    """Opaque devices only; detection, routing and BIOS services remain native."""
    def __init__(self, kinds):
        super().__init__()
        self.kinds = kinds
        self.cpu.mem_write(0x9FD77, b'\x01')
        self.payloads = []
        self.selected_commands = []
        self.reset_count = 0
        self.needs_reset = False
        self.busy_latches = 0
        self.drq_latches = 0
        self.command_latch = 0
        self.packet_requires_pio = False
        self.packet_needs_device_reset = False
        self.packet_device_resets = []
        self.packet_poll_ports = []
        for unit, kind in enumerate(kinds):
            data = bytearray(self.identify)
            struct.pack_into('<H', data, 0, 0x8580 if kind == 'packet' else 0x40)
            struct.pack_into('<I', data, 120, (unit + 1) * 131072)
            name = ('FIXTURE ' + kind.upper() + str(unit)).ljust(40).encode()
            data[54:94] = b''.join(name[i:i+2][::-1] for i in range(0, 40, 2))
            self.payloads.append(data)

    @property
    def unit(self):
        return (self.ata.get(0x1F6, 0) >> 4) & 1

    def port_in(self, cpu, port, size, unused):
        kind = self.kinds[self.unit]
        command = self.ata.get(0x1F7, 0)
        if port in (0x1F7, 0x3F6):
            if kind == 'absent':
                return 0
            if kind == 'packet' and command == 0xA1 and self.packet_requires_pio and self.ata.get(0x1F1, 1):
                return 0  # Firmware with inherited DMA/overlap does not offer PIO.
            if kind == 'packet' and command == 0xA1 and self.identify_word < 256:
                self.packet_poll_ports.append(port)
                if self.packet_needs_device_reset and self.unit not in self.packet_device_resets:
                    return 0  # Old packet firmware needs the directed reset fallback.
            if self.needs_reset or self.pit_latches < self.busy_latches:
                return 0x80
            if command in (0xEC, 0xA1) and self.pit_latches - self.command_latch < self.drq_latches:
                return 0x80
            if kind == 'packet' and not any(unit == self.unit for unit, _ in self.selected_commands):
                return 0  # ATAPI startup may have no DRDY or other status bits.
            if kind == 'packet' and command == 0xEC:
                return 0x51
            return 0x58 if command in (0x20, 0x30) or (command in (0xEC, 0xA1) and self.identify_word < 256) else 0x50
        if kind == 'packet' and command in (0, 0xEC) and port in (0x1F4, 0x1F5):
            return {0x1F4: 0x14, 0x1F5: 0xEB}[port]
        if port == 0x1F0:
            if command in (0xEC, 0xA1):
                assert not cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x600, 'IDENTIFY transfer must mask IRQs and clear DF'
                value = struct.unpack_from('<H', self.payloads[self.unit], self.identify_word * 2)[0]
                self.identify_word += 1
                return value
            return 0xA001 + self.unit
        return super().port_in(cpu, port, size, unused)

    def port_out(self, cpu, port, size, value, unused):
        if port == 0x3F6 and value & 4:
            self.reset_count += 1
            self.needs_reset = False
            self.ata[0x1F7] = 0
        if port == 0x1F7:
            if self.kinds[self.unit] == 'packet' and value == 0xA1:
                assert self.ata.get(0x3F6, 0) == 0x0A, 'polled IDENTIFY did not suppress device IRQ'
            if value == 8:
                assert self.kinds[self.unit] == 'packet', 'DEVICE RESET sent to an ATA disk'
                self.packet_device_resets.append(self.unit)
            self.identify_word = 0
            self.selected_commands.append((self.unit, value))
            self.command_latch = self.pit_latches
        super().port_out(cpu, port, size, value, unused)


def check_pair():
    for kinds in (('ata', 'ata'), ('ata', 'packet'), ('packet', 'ata'),
                  ('absent', 'ata'), ('ata', 'absent'), ('packet', 'packet')):
        model = Pair(kinds)
        clock = bytes(model.cmos[:0xE]) + bytes(model.cmos[0x32:0x33])
        model.post_call('ata_detect_primary')
        disks = [unit for unit, kind in enumerate(kinds) if kind == 'ata']
        assert model.cpu.mem_read(0x475, 1)[0] == len(disks)
        assert model.cmos[0x12] == (0xFF if len(disks) == 2 else (0xF0 if disks else 0))
        for unit, kind in enumerate(kinds):
            base = 0x9FC00 + unit * 0x200
            assert model.cpu.mem_read(base + 0x20, 1)[0] == (kind == 'ata')
            assert model.cpu.mem_read(base + 0x169, 1)[0] == (kind == 'packet')
            if kind != 'absent':
                assert bytes(model.cpu.mem_read(base + 0x140, 40)).decode().strip() == 'FIXTURE ' + kind.upper() + str(unit)
        for logical, unit in enumerate(disks):
            vector = 0x104 if logical == 0 else 0x118
            assert struct.unpack('<HH', model.cpu.mem_read(vector, 4)) == (0xE0, 0x9FC0 + unit * 0x20)
            assert model.disk(8, dx=0x80 + logical)[0] is False
            assert model.cpu.reg_read(x.UC_X86_REG_DL) == len(disks)
            for function, command in ((0, None), (2, 0x20), (3, 0x30), (4, 0x40), (9, 0x91), (0x0C, 0x70), (0x11, 0x10), (0x14, 0x90)):
                assert model.disk(function, dx=0x80 + logical)[0] is False, (kinds, logical, function)
                assert model.unit == unit
                if command:
                    assert model.selected_commands[-1] == (unit, command)
            assert model.disk(2, dx=0x80 + logical)[0] is False
            assert struct.unpack('<H', model.cpu.mem_read(0x21000, 2))[0] == 0xA001 + unit
            model.cpu.mem_write(0x25A5A, b'\x1E\x00' + bytes(28))
            assert model.disk(0x48, dx=0x80 + logical)[0] is False
            assert struct.unpack('<I', model.cpu.mem_read(0x25A5A + 16, 4))[0] == (unit + 1) * 131072
        if disks:
            # Relocation keeps both records and far pointers coherent.
            model.cpu.mem_write(0x8FC00, bytes(model.cpu.mem_read(0x9FC00, 1024)))
            model.cpu.mem_write(0x40E, struct.pack('<H', 0x8FC0))
            model.post_call('publish_disk_cmos')
            for logical, unit in enumerate(disks):
                assert model.disk(2, dx=0x80 + logical)[0] is False
                assert model.unit == unit
                vector = 0x104 if logical == 0 else 0x118
                assert struct.unpack('<HH', model.cpu.mem_read(vector, 4)) == (0xE0, 0x8FC0 + unit * 0x20)
        assert bytes(model.cmos[:0xE]) + bytes(model.cmos[0x32:0x33]) == clock
    print('Primary ATA/ATAPI pair: independent detection, numbering, CMOS, ABI, device selection and relocation PASS')
    # Real POST enables IRQ0/IRQ1 before detection. Direct transfer entry also
    # proves buffer direction and the caller flags, without POST string output.
    for kind in ('ata', 'packet'):
        model = Pair((kind, 'absent'))
        model.cpu.mem_write(0x7FE, b'\xCC' * 516)
        model.post_call('ata_identify_selected', flags=0x602)
        assert model.identify_complete_flags & 0x600 == 0x600
        assert model.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
        assert bytes(model.cpu.mem_read(0x800, 512)) == model.payloads[0]
        assert bytes(model.cpu.mem_read(0x7FE, 2)) == b'\xCC\xCC'
        assert bytes(model.cpu.mem_read(0xA00, 2)) == b'\xCC\xCC'
    model = Pair(('ata', 'packet'))
    model.post_call('ata_detect_primary', flags=0x202)
    assert model.cpu.mem_read(0x9FF69, 1) == b'\x01'
    assert model.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
    print('IDENTIFY transfer: IRQ exclusion, forward512-byte buffer and caller IF/DF restoration PASS')
    # A stale bus and slow response must not disappear at a faster CPU speed.
    model = Pair(('ata', 'packet'))
    model.needs_reset = True
    model.busy_latches = 1200
    model.drq_latches = 800
    model.packet_requires_pio = True
    model.post_call('ata_detect_primary')
    assert model.reset_count == 1 and model.pit_latches >= 2800
    assert model.cpu.mem_read(0x9FF69, 1) == b'\x01'
    assert (0, 0xA1) not in model.selected_commands
    assert model.cpu.mem_read(0x9FF6A, 1) == b'\x07'
    model = Pair(('ata', 'packet'))
    model.cpu.mem_write(0x9FD71, b'\0')
    model.cpu.mem_write(0x9FD77, b'\0')
    model.post_call('ata_detect_primary')
    assert model.reset_count == 0 and not model.selected_commands
    model = Pair(('packet', 'absent'))
    model.post_call('ata_detect_primary')
    assert model.selected_commands[0] == (0, 0xA1), 'packet reset signature was lost'
    for delayed, stage in (('busy_latches', 2), ('drq_latches', 3)):
        model = Pair(('ata', 'absent'))
        setattr(model, delayed, 1000000)
        model.post_call('ata_detect_primary')
        assert model.cpu.mem_read(0x9FC20, 1) == b'\0'
        assert model.cpu.mem_read(0x9FD6A, 2) == bytes((stage, 0x80))
        assert model.cpu.mem_read(0x9FC21, 1) == b'\x80'
        assert 60000 <= model.pit_latches < 60010, 'timeout was not bounded'
    print('POST IDENTIFY: shared reset, PIT-timed BSY/DRQ and bounded timeout, packet signature, disabled channel PASS')
    model = Pair(('ata', 'packet'))
    model.packet_needs_device_reset = True
    model.post_call('ata_detect_primary')
    assert model.cpu.mem_read(0x9FF69, 1) == b'\x01'
    assert model.reset_count == 1 and model.packet_device_resets == [1]
    assert model.selected_commands[-3:] == [(1, 0xA1), (1, 8), (1, 0xA1)]
    assert model.ata[0x3F6] == 0, 'packet identification changed runtime IRQ policy'
    assert set(model.packet_poll_ports) == {0x3F6}, 'packet poll acknowledged INTRQ before data'
    packet_codes = model.post_codes[model.post_codes.index(0x75):]
    assert packet_codes[:9] == [0x75, 0x76, 0x77, 0x78, 0x79, 0x7A, 0x7B, 0x75, 0x76]
    # Progressive POST no longer calls the raw-report formatter (code83h).
    assert [0x7C, 0x7D, 0x7E, 0x81, 0x82, 0x84, 0x85] == packet_codes[-7:]
    assert model.disk(2)[0] is False and model.unit == 0
    class FailedPacket(Pair):
        def __init__(self, reset_hangs=False):
            super().__init__(('ata', 'packet'))
            self.reset_hangs = reset_hangs
        def port_in(self, cpu, port, size, unused):
            if self.unit == 1 and port in (0x1F7, 0x3F6):
                command = self.ata.get(0x1F7, 0)
                if command == 0xA1:
                    return 0
                if command == 8 and self.reset_hangs:
                    return 0x80
            return super().port_in(cpu, port, size, unused)
    for reset_hangs in (False, True):
        model = FailedPacket(reset_hangs)
        model.post_call('ata_detect_primary')
        assert model.cpu.mem_read(0x9FF69, 1) == b'\0'
        assert model.packet_device_resets == [1] and model.reset_count == 1
        assert model.selected_commands.count((1, 0xA1)) == (1 if reset_hangs else 2)
        assert model.cpu.mem_read(0x9FF6A, 1)[0] == (8 if reset_hangs else 9)
        assert 120000 <= model.pit_latches < 121000, 'packet retry/reset wait was unbounded'
        assert model.ata[0x3F6] == 0 and model.disk(2)[0] is False
    print('ATAPI IDENTIFY: polled nIEN/Alternate Status, directed reset retry and unchanged ATA master PASS')
    # Diagnostic uses real CMOS/IDE ports and the opaque DOS console only.
    model = Pair(('ata', 'packet'))
    model.post_call('ata_detect_primary')
    model.ata[0x1F6] = 0xA0
    selection = model.ata[0x1F6]
    clock, commands = bytes(model.cmos), list(model.selected_commands)
    model.setup(flags=0x202)
    model.cpu.reg_write(x.UC_X86_REG_CS, 0x2000)
    model.cpu.reg_write(x.UC_X86_REG_IP, 0x100)
    model.cpu.mem_write(0x20100, (rtc.ROOT / 'build/diagnostics/HWSTATE.COM').read_bytes())
    model.cpu.emu_start(0x20100, 0x30000, count=100000)
    assert model.dos_exit == 0
    assert 'CMOS 10,38..3F:' in model.dos_output and 'Slave:' in model.dos_output
    assert bytes(model.cmos) == clock and model.selected_commands == commands
    assert model.ata[0x1F6] == selection
    print('HWSTATE.COM: read-only CMOS and both IDE positions; selection restored PASS')


def check_pair_buffers():
    class BufferDisk(Pair):
        call_segment = 0x7000  # Keep the caller outside the relocated EBDA's adjacent buffers.

        def port_in(self, cpu, port, size, unused):
            if self.ata.get(0x1F7) in (0x22, 0x32, 0x50) and port in (0x1F7, 0x3F6):
                return 0x58
            if port == 0x1F0 and size == 1:
                return 0xE0  # Four opaque ECC bytes after a LONG sector.
            return super().port_in(cpu, port, size, unused)

        def setup(self, *args, **kwargs):
            super().setup(*args, **kwargs)
            if getattr(self, 'parameter_buffer', None) is not None:
                self.cpu.reg_write(x.UC_X86_REG_DS, self.parameter_buffer >> 4)
                self.cpu.reg_write(x.UC_X86_REG_SI, self.parameter_buffer & 15)

    for segment in (0x9FC0, 0x8FC0):
        for kinds, logical in ((('ata', 'ata'), 0), (('ata', 'ata'), 1),
                               (('absent', 'ata'), 0)):
            for function in (2, 3, 5, 0x0A, 0x0B, 0x42, 0x43, 0x48):
                length = 26 if function == 0x48 else 516 if function in (0x0A, 0x0B) else 512
                base = segment * 16
                for address, rejected in ((base - length, False), (base, True),
                                           (base + 0x200, True), (base + 1024, False)):
                    model = BufferDisk(kinds)
                    model.post_call('ata_detect_primary')
                    if segment != 0x9FC0:
                        model.cpu.mem_write(base, bytes(model.cpu.mem_read(0x9FC00, 1024)))
                        model.cpu.mem_write(0x40E, struct.pack('<H', segment))
                    if function >= 0x42:
                        model.cpu.mem_write(0x25A5A, struct.pack('<BBHHHQ', 16, 0, 1,
                                             address & 15, address >> 4, 0))
                    if function == 0x48:
                        model.parameter_buffer = address
                        model.cpu.mem_write(address, b'\x1A\x00')
                    if not rejected and function in (3, 5, 0x0B, 0x43):
                        payload = bytes(i & 255 for i in range(length))
                        model.cpu.mem_write(address, payload)
                    model.selected_commands.clear()
                    model.data_writes.clear()
                    result = model.disk(function, al=0 if function >= 0x42 else 1, dx=0x80 + logical,
                                        es=address >> 4, bx=address & 15)
                    assert result[0] == rejected, (segment, kinds, logical, function, hex(address), result)
                    if rejected:
                        assert result[2] == 4 and not model.selected_commands
                    elif function in (2, 0x0A, 0x42):
                        unit = 1 if kinds[0] == 'absent' else logical
                        assert bytes(model.cpu.mem_read(address, 512)) == struct.pack('<H', 0xA001 + unit) * 256
                        if function == 0x0A:
                            assert model.cpu.mem_read(address + 512, 4) == b'\xE0' * 4
                    elif function in (3, 5, 0x0B, 0x43):
                        expected = list(struct.unpack('<256H', payload[:512]))
                        if function == 0x0B:
                            expected.extend(payload[512:])
                        assert model.data_writes == expected, (segment, function, address)
                    elif function == 0x48:
                        assert model.cpu.mem_read(address, 2) == b'\x1A\x00'
                        unit = 1 if kinds[0] == 'absent' else logical
                        assert struct.unpack('<I', model.cpu.mem_read(address + 16, 4))[0] == (unit + 1) * 131072
    print('Primary pair buffers: both EBDA halves protected; adjacent CHS/EDD/parameter buffers accepted after relocation PASS')


def floppy_buffer_model(segment=0x9FC0):
    setup = importlib.import_module('test-setup')

    class FloppyBuffer(setup.Setup):
        call_segment = 0x7000

        def __init__(self, segment):
            super().__init__(segment=segment)
            self.cpu.mem_write(0x4C, struct.pack('<HH', rtc.symbol('int13'), 0xF000))
            self.dma_address = self.dma_byte = 0
            self.dma_count = 0
            self.transferred = None

        def port_out(self, cpu, port, size, value, unused):
            if port == 0x0C:
                self.dma_byte = 0
            elif port in (4, 5):
                shift = self.dma_byte * 8
                if port == 4:
                    self.dma_address = (self.dma_address & ~(255 << shift)) | value << shift
                else:
                    self.dma_count = (self.dma_count & ~(255 << shift)) | value << shift
                self.dma_byte ^= 1
            elif port == 0x81:
                self.dma_address = (self.dma_address & 65535) | value << 16
            elif port in (0x0A, 0x0B):
                pass  # Opaque ISA DMA mode/mask.
            elif port == 0x3F5 and (self.fdc_command or value in (0x4A, 0x46, 0x45, 0x4D)):
                command = self.fdc_command[0] if self.fdc_command else value
                if command not in (0x4A, 0x46, 0x45, 0x4D):
                    return super().port_out(cpu, port, size, value, unused)
                self.fdc_command.append(value)
                if len(self.fdc_command) == {0x4A: 2, 0x46: 9, 0x45: 9, 0x4D: 6}[command]:
                    data, self.fdc_command = self.fdc_command, []
                    self.fdc_log.append(tuple(data))
                    if command == 0x46:
                        self.cpu.mem_write(self.dma_address, b'\x5A\xA5' * ((self.dma_count + 1) // 2))
                    if command != 0x4A:
                        self.transferred = bytes(self.cpu.mem_read(self.dma_address, self.dma_count + 1))
                    self.fdc_fifo.extend((data[1] & 7, 0, 0, 0, 0, 1, 2))
                    self.fdc_irq = True
            else:
                super().port_out(cpu, port, size, value, unused)

    return FloppyBuffer(segment)


def check_floppy_buffers():
    for segment in (0x9FC0, 0x8FC0):
        base = segment * 16
        for drive in (0, 1):
            for function in (2, 3, 5):
                count = (18 if drive == 0 else 15) if function == 5 else 1
                length = count * 4 if function == 5 else 512
                for address, rejected in ((base - length, False), (base, True),
                                           (base + 0x200, True), (base + 1024, False)):
                    model = floppy_buffer_model(segment)
                    if not rejected:
                        payload = b'\x35' * length
                        if function == 5:
                            payload = b''.join(bytes((0, 0, sector, 2)) for sector in range(1, count + 1))
                        model.cpu.mem_write(address, payload)
                    result = Disk.disk(model, function, al=count, dx=drive, es=address >> 4, bx=address & 15)
                    case = (segment, drive, function, address, result)
                    assert result[0] == rejected and result[1] >> 8 == (9 if rejected else 0), case
                    if rejected:
                        assert not model.fdc_log and model.transferred is None
                    else:
                        assert model.transferred == (b'\x5A\xA5' * 256 if function == 2 else payload), case
                        assert model.fdc_log[-1][1] & 3 == drive, case
    print('Floppy buffer guard: real INT13 read/write/format reject both EBDA halves and accept adjacent DMA buffers after relocation PASS')


def check_windows_irq():
    """Run the installed WDCTRL IRQ gate after production controller detection."""
    fat = importlib.import_module('memory-fixture').Fat16(rtc.ROOT.parent / 'reference/media/dos/test-card.vhd')
    try:
        driver = fat.read('WINDOWS/SYSTEM/WIN386.EXE')
    finally:
        fat.vhd.close()
    gate = driver[0x265EB:0x265F1]
    assert gate == bytes.fromhex('E4 A1 A8 40 75 6B')
    for enabled, absent in ((True, False), (True, True), (False, True)):
        model = Disk()
        model.absent = absent
        model.cpu.mem_write(0x9FD90, bytes((enabled,)))
        model.masks = {0x21: 0xFC, 0xA1: 0xEF}
        model.post_call('ata_detect_primary')
        assert model.masks == {0x21: 0xF8 if enabled else 0xFC,
                               0xA1: 0xAF if enabled else 0xEF}
        cpu = model.cpu
        cpu.mem_write(0x90000, gate)
        cpu.reg_write(x.UC_X86_REG_CS, 0x9000)
        cpu.reg_write(x.UC_X86_REG_IP, 0)
        cpu.emu_start(0x90000, 0x90006, count=3)
        assert cpu.reg_read(x.UC_X86_REG_IP) == (6 if enabled else 0x71)
    print('Original WDCTRL IRQ gate: enabled/absent/disabled controller handoff PASS')
    # Execute the original driver geometry checks through the production
    # INT13 handler, rather than duplicating its comparison in Python.
    from unicorn import UC_HOOK_CODE
    for capacity in (3970048, 64512, 32 * 63):
        model = Disk()
        cpu = model.cpu
        cpu.mem_write(0x9FC2E, struct.pack('<I', capacity))
        cpu.mem_write(0x9FCF2, bytes((64, 63)))
        result = model.disk(8)
        assert not result[0]
        cx = cpu.reg_read(x.UC_X86_REG_CX)
        cylinder = (cx >> 8) | ((cx & 0xC0) << 2)
        count = struct.unpack('<H', cpu.mem_read(0x9FCE0, 2))[0]
        assert cylinder == max(count - 2, 0)
        if count == 1:
            continue  # No room for WDCTRL's reserved-cylinder convention.
        cpu.mem_write(0x90000, driver[0x26000:0x271C1])
        cpu.mem_write(0x90008, struct.pack('<HH', rtc.symbol('int13'), 0xF000))
        cpu.mem_write(0x96800, bytes(18))
        for reg, value in ((x.UC_X86_REG_CS, 0x9000), (x.UC_X86_REG_IP, 0x83A),
                           (x.UC_X86_REG_DS, 0x9000), (x.UC_X86_REG_ES, 0x9FC0),
                           (x.UC_X86_REG_DI, 0xE0), (x.UC_X86_REG_SS, 0x9000),
                           (x.UC_X86_REG_SP, 0x6000), (x.UC_X86_REG_BP, 0x6800),
                           (x.UC_X86_REG_DX, 0x80), (x.UC_X86_REG_EFLAGS, 0x202)):
            cpu.reg_write(reg, value)
        cpu.hook_add(UC_HOOK_CODE, lambda c, address, size, unused:
                     c.emu_stop() if address == 0x90AAA else None)
        cpu.emu_start(0x9083A, 0x90882, count=500000)
        assert cpu.reg_read(x.UC_X86_REG_IP) == 0x882
        assert cpu.mem_read(0x96806, 2) == b'\x04\0'
    print('Original WDCTRL head/sector/cylinder checks and tiny-disk boundary PASS')


def main():
    # IDE DOS drivers chain master-disk IRQ14 to the original BIOS vector.
    # A bare IRET leaves the slave IRQ and master cascade in service.
    irq = Disk()
    try:
        handler = rtc.symbol('int76')
    except StopIteration:
        handler = rtc.symbol('default_iret')
    irq.cpu.mem_write(0x1D8, struct.pack('<HH', handler, 0xF000))
    irq.cpu.mem_write(0x54, struct.pack('<HH', rtc.symbol('int15'), 0xF000))
    irq.setup(flags=0x602)
    before = irq.state()
    irq.cpu.mem_write(0x90000, b'\xCD\x76\x90')
    irq.cpu.emu_start(0x90000, 0x90002, count=10000)
    assert irq.eois == [(0xA0, 0x66), (0x20, 0x62)], 'IRQ14/cascade was not acknowledged'
    assert irq.cpu.mem_read(0x48E, 1) == b'\xFF', 'OEM disk-completion latch missing'
    assert irq.state() == before and irq.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x600 == 0x600
    assert not irq.commands and not irq.data_reads, 'IRQ handler disturbed ATA task file'
    print('Shared IRQ14: OEM completion latch, both PIC EOIs, register/flags preservation PASS')
    disk = Disk()
    disk.post_call('publish_disk_cmos')
    # These calls failed with AH01 in the baseline, causing SI8 to reset/retry.
    result = disk.disk(0x0C, al=0, cx=0x100, bx=0xFFFF, es=0x9FC0)
    assert not result[0] and result[1] >> 8 == 0, result
    assert disk.commands[-1] == 0x70
    for flags in (0x402, 0x602):
        result = disk.disk(0x10, flags=flags)
        assert not result[0] and result[1] >> 8 == 0, result
    assert disk.disk(4, al=2, bx=0xFFFF, es=0x9FC0)[:2] == (False, 2)
    assert disk.commands[-2:] == [0x40, 0x40] and disk.data_reads == 0
    before = disk.data_reads
    assert disk.disk(2, al=128, bx=0, es=0x8000)[:2] == (False, 128)
    assert disk.data_reads - before == 128 * 256
    assert disk.disk(2, al=128, bx=1, es=0x8000)[0] is True
    assert disk.disk(2, al=129, bx=0, es=0x8000)[0] is True
    assert disk.disk(0x0C, cx=0xFFFF)[0] is True
    assert disk.disk(1) == (True, 0x0404, 4)
    assert disk.disk(0x10)[0] is False
    assert disk.disk(1) == (False, 0, 0)
    for function, command in ((9, 0x91), (0x11, 0x10), (0x14, 0x90)):
        result = disk.disk(function)
        assert not result[0] and result[1] >> 8 == 0, result
        assert disk.commands[-1] == command
    for function in (0, 0x0D):
        result = disk.disk(function)
        assert not result[0] and result[1] >> 8 == 0, result
    for function in (6, 7, 0x0E, 0x0F, 0x12, 0x13, 0x99):
        assert disk.disk(function)[2] == 1
    for function, command in ((0x0A, 0x22), (0x0B, 0x32), (5, 0x50),
                              (4, 0x40), (9, 0x91), (0x0C, 0x70), (0x11, 0x10), (0x14, 0x90)):
        disk.reject = command
        before = len(disk.data_writes)
        reads = disk.data_reads
        result = disk.disk(function)
        assert result[0] is True and result[1] >> 8 == 0x20, result
        assert disk.disk(1)[2] == 0x20
        assert len(disk.data_writes) == before, 'aborted command wrote data'
        assert disk.data_reads == reads, 'aborted command read data'
        disk.reject = None
    for flags in (0x402, 0x602):
        for function in (8, 0x99, 2, 3):
            result = disk.disk(function, flags=flags)
            assert result[0] == (function == 0x99)
            if function == 8:
                assert result[1] >> 8 == 0
                assert disk.cpu.reg_read(x.UC_X86_REG_CX) == 0xD6FF
                assert disk.cpu.reg_read(x.UC_X86_REG_DX) == 0x3F01
            elif function == 0x99:
                assert result[1] >> 8 == 1
            else:
                assert result[1] == 1
    before = disk.data_reads
    assert disk.disk(0x0A)[:2] == (False, 1)
    assert disk.data_reads - before == 260
    assert disk.data_widths == [2] * 256 + [1] * 4
    assert bytes(disk.cpu.mem_read(0x21000, 516)) == bytes.fromhex('5AA5') * 256 + bytes.fromhex('E0E1E2E3')
    before = len(disk.data_writes)
    assert disk.disk(0x0B)[:2] == (False, 1)
    assert len(disk.data_writes) - before == 260
    assert disk.data_widths == [2] * 256 + [1] * 4
    assert disk.data_writes[before:] == [0xA55A] * 256 + list(bytes.fromhex('E0E1E2E3'))
    before = len(disk.data_writes)
    assert disk.disk(5)[:2] == (False, 1)
    assert len(disk.data_writes) - before == 256
    assert disk.ata[0x1F2] == 63
    assert disk.disk(2, bx=0xFF00)[0] is True
    assert disk.disk(0x0A, bx=0xFDFE)[0] is True
    assert disk.disk(8)[0] is False
    assert bytes(disk.cpu.mem_read(0x475, 1)) == b'\x01'
    assert struct.unpack('<HH', disk.cpu.mem_read(0x104, 4)) == (0xE0, 0x9FC0)
    table = bytes(disk.cpu.mem_read(0x9FCE0, 16))
    assert struct.unpack_from('<H', table)[0] == 984
    assert table[2] == 64 and table[14] == 63
    clock = bytes(disk.cmos[:0xE]) + bytes(disk.cmos[0x32:0x33])
    disk.post_call('publish_disk_cmos')
    assert disk.cmos[0x12] == 0xF0 and disk.cmos[0x19] == 47
    assert disk.cmos[0x1B:0x24] == bytes(table[i] for i in (0, 1, 2, 5, 6, 8, 12, 13, 14))
    assert bytes(disk.cmos[:0xE]) + bytes(disk.cmos[0x32:0x33]) == clock
    disk.cpu.mem_write(0x8FC00, bytes(disk.cpu.mem_read(0x9FC00, 1024)))
    disk.cpu.mem_write(0x40E, struct.pack('<H', 0x8FC0))
    # Fixture-owned map changes use POST publication, not an INT13 side effect.
    disk.post_call('publish_disk_cmos')
    assert disk.disk(0x10)[0] is False
    assert struct.unpack('<HH', disk.cpu.mem_read(0x104, 4)) == (0xE0, 0x8FC0)
    disk.cpu.mem_write(0x8FC20, b'\x00')
    disk.post_call('publish_disk_cmos')
    assert disk.disk(0x10)[2] == 0x80
    assert bytes(disk.cpu.mem_read(0x475, 1)) == b'\x00'
    assert bytes(disk.cpu.mem_read(0x104, 4)) == bytes(4)
    # Compose POST detection through both table owners, rather than seeding
    # the detected state. IDENTIFY words3/6/60 are the retained ATA contract.
    for absent in (False, True):
        detected = Disk()
        detected.absent = absent
        clock = bytes(detected.cmos[:0xE]) + bytes(detected.cmos[0x32:0x33])
        detected.post_call('ata_identify')
        assert detected.cpu.mem_read(0x475, 1)[0] == (0 if absent else 1)
        assert bytes(detected.cpu.mem_read(0x104, 4)) == (bytes(4) if absent else struct.pack('<HH', 0xE0, 0x9FC0))
        assert bytes(detected.cpu.mem_read(0x118, 4)) == bytes(4)
        expected = bytes(16) if absent else table
        assert bytes(detected.cpu.mem_read(0x9FCE0, 16)) == expected
        assert detected.cmos[0x12] == (0 if absent else 0xF0)
        assert detected.cmos[0x19] == (0 if absent else 47)
        assert detected.cmos[0x1B:0x24] == bytes(expected[i] for i in (0, 1, 2, 5, 6, 8, 12, 13, 14))
        assert bytes(detected.cmos[:0xE]) + bytes(detected.cmos[0x32:0x33]) == clock
    # The OEM floppy return epilogue also forces IF=1, without an IRQ wait.
    floppy = Disk()
    rtc.Clock.call(floppy, 'settings_load', flags=2)
    floppy.cpu.mem_write(0x9FC80, b'\x04\x02')
    for function, status, flags in ((ah, status, flags) for ah, status in
                                    ((1, 0), (1, 0x20), (8, 0), (0x15, 0), (0x99, 0))
                                    for flags in (0x402, 0x602)):
        floppy.setup(function, dx=0, flags=flags)
        floppy.cpu.mem_write(0x441, bytes((status,)))
        before = floppy.state()
        floppy.cpu.mem_write(0x90000, b'\xcd\x13\x90')
        floppy.cpu.emu_start(0x90000, 0x90002, count=4000000)
        assert floppy.cpu.reg_read(x.UC_X86_REG_IP) == 2
        returned_flags = floppy.cpu.reg_read(x.UC_X86_REG_EFLAGS)
        assert returned_flags & 0x600 == 0x600
        expected_ax = {1: status << 8, 8: 0, 0x15: 0x0255, 0x99: 0x0100}[function]
        assert floppy.cpu.reg_read(x.UC_X86_REG_AX) == expected_ax
        assert bool(returned_flags & 1) == (function == 0x99 or bool(status))
        outputs = {'EAX'}
        if function == 8:
            outputs.update(('EBX', 'ECX', 'EDX', 'EDI', 'ES'))
        for name, value in floppy.state().items():
            assert (before[name] >> 16 == value >> 16 if name in outputs else before[name] == value), name
        if function == 8:
            assert floppy.cpu.reg_read(x.UC_X86_REG_BX) == 4
            assert floppy.cpu.reg_read(x.UC_X86_REG_CX) == 0x4F12
            assert floppy.cpu.reg_read(x.UC_X86_REG_DX) == 0x0102
            assert floppy.cpu.reg_read(x.UC_X86_REG_ES) == 0xF000
            pointer = 0xF0000 + floppy.cpu.reg_read(x.UC_X86_REG_DI)
            assert bytes(floppy.cpu.mem_read(pointer, 11)) == bytes.fromhex('DF022502121BFF6CF60F08')
    print('Actual ROM legacy INT13: OEM services, ATA results, buffers, ABI, IF-enable return, status, tables and EBDA relocation PASS')
    check_pair()
    check_pair_buffers()
    check_floppy_buffers()
    check_windows_irq()


if __name__ == '__main__':
    main()
