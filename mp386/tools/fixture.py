"""Synthetic Tiger/AT device seams; this does not qualify physical hardware."""
import importlib
import functools
import re
import struct
import sys
from pathlib import Path

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
sys.path.insert(0, str(PORT.parent/'presario-800/tools'))
from shared.tools.ram_proof import Listing
from shared.tools.peripheral_proof import UART, Printer
rtc = importlib.import_module('test-rtc')
setup = importlib.import_module('test-setup')


class Tiger(setup.Setup):
    def __init__(self, image, banks=(1, 1, 1, 1), wide=True, cache=False, controllers=None, dirty_maps=True, cache_bytes=32768):
        image = Path(image)
        self.listing = Listing(image.with_suffix('.lst'))
        self.symbol = functools.lru_cache(None)(self.listing.symbol)
        holdoff = (self.symbol('.cpu_holdoff_begin', 'startup'),
                   self.symbol('.cpu_holdoff_end', 'startup'))
        for line in self.listing.lines:
            if match := re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]', line):
                if re.search(r'\binvd\b', line) and holdoff[0] <= int(match[1],16) < holdoff[1]:
                    continue  # Runtime guard still rejects INVD on this386 fixture.
                assert not re.search(r'\b(?:wbinvd|invd|bswap|rdtsc)\b', line), line
        folder = image.parent/'fixture'
        folder.mkdir(exist_ok=True)
        (folder/'baios-presario800-system.rom').write_bytes(image.read_bytes())
        rtc.BUILD = folder
        rtc.symbol = lambda name: self.symbol(
            'RTC_INTERRUPT_LABEL' if name == 'int1a' else
            'startup' if name == '.warm_start' else name)
        self.banks = banks
        if controllers is None:
            size = (0, 16, 64, 256)
            controllers = ((size[min(banks[:2])], size[min(banks[2:])]),)
        self.controllers = tuple(tuple(pair) for pair in controllers)
        self.ram_banks = {}
        for unit, pair in enumerate(self.controllers):
            for bank, pages in enumerate(pair):
                assert 0 <= pages <= 512
                data = bytearray(pages*65536)
                for page in range(pages):
                    data[page*65536:page*65536+2] = b'\x55\x55'
                self.ram_banks[unit, bank] = data
        self.maps = {}
        self.memory_trace = []
        self.capture_memory = False
        self.invalid_decodes = []
        self.map_programmed = False
        if dirty_maps:
            for unit in range(len(self.controllers)):
                for page in range(64):
                    self.maps[unit, False, page] = 0x8000+page
        self.wide = wide
        self.cache = cache
        self.cache_bytes = cache_bytes
        self.cache_data = {}
        self.disk_switches = 0
        self.board_switches = 0
        self.clock_switches = 0xBE
        self.control_index = 0
        self.controls = {0xE2: 0x8F}
        self.ti_index = 0
        self.ti = {0x800: 0x200 if wide else 0, 0x801: 0x06A4, 0x802: 0x1515, 0x803: 0, 0x804: 3}
        for unit in range(len(self.controllers)):
            profile = 0x10E4 if unit == 0 else 0x36E4
            self.ti.update({unit*256: unit*256, unit*256+1: 0,
                            unit*256+2: 0x8100, unit*256+3: 0x4001,
                            unit*256+4: profile, unit*256+5: profile,
                            unit*256+6: 0, unit*256+7: 0})
        self.ti_stage = None
        self.pit1_count = 0xFF
        self.pit1_load = []
        self.pit1_latch = []
        self.ti_trace = {'cold': [], 'warm': []}
        self.probe = False
        self.map_programs = 0
        self.bank_data = {}
        self.reference = False
        self.reference_stop = None
        self.nvram = bytearray([0xFF])*1024
        self.nv_phase = 'idle'
        self.nv_address = 0
        self.nv_last = 0
        self.nv_writes = []
        self.sys_flag = 0
        self.kbc_cb = 0x44
        self.kbc_output = 0xCF
        self.kbc_next = None
        self.reset_pending = False
        self.reset_count = 0
        self.processor_reset_count = 0
        self.booted = False
        self.running = False
        self.visits = []
        self.code_observer = None
        self.uarts = {0x3F8: UART(), 0x2F8: UART()}
        self.printer = Printer()
        self.ata = {i: 0 for i in range(8)}
        self.ata[7] = 0x50
        self.ata_fifo = bytearray()
        self.ata_log = []
        self.disk = bytes(1024)
        self.signed_boot = True
        self.port92_accesses = []
        self.instructions = set()
        self.ram_reads = 0
        self.script_after_post = [28]
        self.post_script_armed = False
        super().__init__(segment=0x9E00)
        self.cpu.hook_del(self.code_hook)
        self.cpu.hook_add(UC_HOOK_CODE, self.code, begin=1,
                          end=0xF0000+self.symbol('mp386_ram_sweep'))
        self.cpu.hook_add(UC_HOOK_CODE, self.code,
                          begin=0xF0000+self.symbol('chipset_post_recovery_notice'),
                          end=0xFFFFFF)
        self.cpu.hook_add(UC_HOOK_MEM_READ, self.memory_read)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.memory_write)
        self.cpu.mem_map(0x200000, 30*1024*1024)
        self.raw_mem_write = self.cpu.mem_write
        self.rom = bytearray(image.read_bytes())
        self.shadow_writes = 0
        self.shadow_written = set()
        self.cpu.mem_write = self.external_memory_write
        self.cmos = self.cmos[:64]
        self.cmos[0x0E] = 0
        self.cmos[0x0F] = 0
        self.cmos[0x38:0x40] = bytes(8)
        self.cpu.mem_write(0xC0000, self.video_rom())
        self.seed_physical(0, 0x110000, bytes.fromhex('44332211'))
        self.seed_physical(0, 0x10000, bytes.fromhex('aabbccdd'))

    @staticmethod
    def video_rom():
        raw = bytearray(32768)
        raw[:4] = b'\x55\xaa\x40\xcb'
        raw[0x100] = 0xCF
        raw[-1] = (-sum(raw)) & 255
        return bytes(raw)

    def port_in(self, cpu, port, size, unused):
        if self.ti_stage:
            self.ti_trace[self.ti_stage].append(('in', port, size, None, cpu.reg_read(x.UC_X86_REG_IP)))
        if port == 0x41:
            assert size == 1 and self.pit1_latch
            value = self.pit1_latch.pop(0)
            if self.ti_stage:
                self.ti_trace[self.ti_stage][-1] = ('in', port, size, value, cpu.reg_read(x.UC_X86_REG_IP))
            return value
        if port == 0x24:
            assert size == 2
            index = self.ti_index
            if index & 0x8000:
                unit = (index >> 12) & 7
                high = bool(self.ti.get(unit*256+2, 0) & 0x20)
                value = self.maps.get((unit, high, index & (0x7FC if high else 0x3F)), 0)
            else:
                value = self.ti.get(index, 0xFFFF if index < 0x800 and index & 255 == 0 else 0)
            if self.ti_stage:
                self.ti_trace[self.ti_stage][-1] = ('in', port, size, value, cpu.reg_read(x.UC_X86_REG_IP))
            return value
        if port == 0x26:
            return self.ti_index
        if port == 0x48:
            if self.nv_phase == 'data':
                self.nv_phase = 'ack'
                self.nv_last = self.nvram[self.nv_address]
            else:
                self.nv_phase = 'handshake'
                self.nv_last = 0
            return self.nv_last
        if port == 0x49:
            return self.clock_switches
        if port == 0x5E:
            return self.board_switches
        if port == 0x5F:
            return (0 if self.cache else 0x80) | self.disk_switches
        if port == 0x5B:
            return self.controls.get(self.control_index, 0)
        if port == 0x64:
            return self.sys_flag | int(bool(getattr(self, 'pending', [])))
        if port == 0x60:
            return self.pending.pop(0) if self.pending else 0xFF
        if port == 0x92:
            self.port92_accesses.append(('in', size))
            raise AssertionError('MP386 accessed port92')
        if port == 0x71:
            # The original AT RTC aliases the upper64 indexes.
            self.delayed = True
            return rtc.Clock.port_in(self, cpu, port, size, unused)
        if port in (0x1F7, 0x3F6):
            return 0 if self.ata[6] & 0x10 else self.ata[7]
        if port == 0x1F0:
            assert size == 2 and len(self.ata_fifo) >= 2
            value = int.from_bytes(self.ata_fifo[:2], 'little')
            del self.ata_fifo[:2]
            if not self.ata_fifo:
                self.ata[7] = 0x50
            return value
        if 0x1F1 <= port <= 0x1F6:
            return self.ata[port-0x1F0]
        for base, uart in self.uarts.items():
            if base <= port < base+8:
                return uart.read(port-base)
        if 0x378 <= port < 0x37B:
            return self.printer.read(port-0x378)
        if any(base <= port < base+8 for base in (0x3E8, 0x2E8)):
            return 255
        if any(base <= port < base+3 for base in (0x3BC, 0x278)):
            return 255
        if port in (0x3BA, 0x3DA, 0x3C0):
            return 0
        if port == 0x3CC:
            return 1
        if port in (0xEB, 0xED):
            return 0
        return super().port_in(cpu, port, size, unused)

    def port_out(self, cpu, port, size, value, unused):
        if port == 0x5A:
            self.control_index = value
            return
        if port == 0x5B:
            self.controls[self.control_index] = value
            if self.control_index == 0xE0:
                self.cache_data.clear()
            return
        if self.ti_stage:
            self.ti_trace[self.ti_stage].append(('out', port, size, value, cpu.reg_read(x.UC_X86_REG_IP)))
        if port == 0x43 and value in (0x70, 0x40, 0x54):
            if value == 0x40:
                self.pit1_count = max(0, self.pit1_count-1)
                self.pit1_latch = [self.pit1_count & 255, self.pit1_count >> 8]
            else:
                self.pit1_load = []
            return
        if port == 0x41:
            self.pit1_load.append(value)
            if len(self.pit1_load) == 2:
                self.pit1_count = int.from_bytes(bytes(self.pit1_load), 'little')
            return
        if port == 0x26:
            assert size == 2
            self.ti_index = value
            return
        if port == 0x24:
            assert size == 2
            index = self.ti_index
            if index & 0x8000:
                unit = (index >> 12) & 7
                assert unit < len(self.controllers), ('absent map controller', hex(index))
                high = bool(self.ti.get(unit*256+2, 0) & 0x20)
                self.maps[unit, high, index & (0x7FC if high else 0x3F)] = value
                self.map_programmed = True
                self.map_programs += 1
                self.ti_index += 4 if high else 1
            else:
                if index < 0x800:
                    unit = index >> 8
                    if unit >= len(self.controllers):
                        return
                keep = self.ti.get(index, 0) & (0xF200 if index == 0x800 else 0xF700 if index < 0x800 and index & 255 == 0 else 0)
                if index < 0x800 and index & 255 == 1:
                    value &= ~8       # Observed readback is0; command effects are unmodeled.
                if index == 0x802:
                    value = (value & 255)*0x101
                self.ti[index] = value | keep
                if index < 0x800 and index & 255 == 7:
                    self.sync_system_rom()
            return
        if port == 0x48:
            if self.nv_phase == 'handshake':
                assert value == self.nv_last
                self.nv_phase = 'high'
            elif self.nv_phase == 'high':
                self.nv_address = value << 8
                self.nv_phase = 'low'
            elif self.nv_phase == 'low':
                self.nv_address |= value
                assert 0x200 <= self.nv_address < 0x240
                self.nv_phase = 'data'
            elif self.nv_phase == 'data':
                self.nvram[self.nv_address] = value
                self.nv_writes.append((self.nv_address, value))
                self.nv_phase = 'idle'
            else:
                assert self.nv_phase == 'ack' and value == self.nv_last
                self.nv_phase = 'idle'
            return
        if port == 0x70:
            self.index = value & (0x7F if self.reference else 0x3F)
            self.delayed = True
            return
        if port == 0x71:
            self.delayed = True
            return rtc.Clock.port_out(self, cpu, port, size, value, unused)
        if port == 0x92:
            self.port92_accesses.append(('out', value))
            raise AssertionError('MP386 accessed port92')
        if port == 0x64:
            if value == 0xFE:
                if self.cmos[0x0F] == 1:
                    self.processor_reset_count += 1
                else:
                    self.reset_count += 1
                self.reset_pending = True
                cpu.emu_stop()
            elif value in (0x60, 0xD1):
                self.kbc_next = value
            elif value == 0xD0:
                self.pending.append(self.kbc_output)
            elif value == 0x20:
                self.pending.append(self.kbc_cb)
            elif value == 0xAA:
                self.pending.append(0x55)
            elif value == 0xAD:
                self.kbc_cb |= 0x10
            elif value == 0xAE:
                self.kbc_cb &= ~0x10
            elif value == 0xA7:
                pass
            else:
                raise AssertionError(('KBC command', hex(value)))
            return
        if port == 0x60:
            if self.kbc_next == 0x60:
                self.kbc_cb = value
                self.sys_flag = value & 4
            elif self.kbc_next == 0xD1:
                assert value & 1, '8042 reset asserted while changing A20'
                self.kbc_output = value
            elif value == 0xFF:
                self.pending.extend((0xFA, 0xAA))
            else:
                self.pending.append(0xFA)
            self.kbc_next = None
            return
        if port == 0x1F7:
            self.ata_log.append(value)
            self.ata_command(value)
            return
        if 0x1F1 <= port <= 0x1F6:
            self.ata[port-0x1F0] = value
            return
        if port == 0x3F6:
            if not value & 4:
                self.ata.update({1: 1, 2: 1, 3: 1, 4: 0, 5: 0, 7: 0x50})
            return
        for base, uart in self.uarts.items():
            if base <= port < base+8:
                uart.write(port-base, value)
                return
        if 0x378 <= port < 0x37B:
            self.printer.write(port-0x378, value)
            return
        if any(base <= port < base+8 for base in (0x3E8, 0x2E8)) or any(base <= port < base+3 for base in (0x3BC, 0x278)):
            return
        if port in (0xEB, 0xED, 0x84, 0x8D, 0x8E, 0x8F, 0x0D, 0x08, 0x0B, 0xDA, 0xD0, 0xD6, 0xD4, 0x41, 0x3B8, 0x3D8, 0x3C0, 0x3B4, 0x3B5, 0x3D4, 0x3D5, 0xF0, 0xF1):
            self.delayed = True
            return
        if port == 0xE9:
            assert value == 0x5A, ('boot observer failed', hex(value))
            self.booted = True
            cpu.emu_stop()
            return
        if port == 0x40:
            self.pit_counter = 0xFFFF
            return
        return super().port_out(cpu, port, size, value, unused)

    def ata_command(self, command):
        if self.ata[6] & 0x10:
            self.ata[7] = 0
            return
        if command == 0xEC:
            data = bytearray(512)
            for index, value in ((0, 0x40), (1, 16), (3, 4), (6, 17), (49, 0x200), (60, 1088)):
                struct.pack_into('<H', data, index*2, value)
            model = b'MP386 INDEPENDENT ATA FIXTURE'.ljust(40)
            data[54:94] = b''.join(model[i:i+2][::-1] for i in range(0, 40, 2))
            self.ata_fifo = data
            self.ata[7] = 0x58
        elif command in (0x20, 0xC4):
            lba = (self.ata[3] | self.ata[4] << 8 | self.ata[5] << 16 | (self.ata[6] & 15) << 24) if self.ata[6] & 0x40 else ((self.ata[4] | self.ata[5] << 8)*4+(self.ata[6] & 15))*17+self.ata[3]-1
            count = self.ata[2] or 256
            self.ata_fifo = bytearray(self.disk[lba*512:(lba+count)*512])
            assert len(self.ata_fifo) == count*512, ('disk range', lba, count)
            self.ata[7] = 0x58
        elif command in (0x90, 0x91, 0xEF, 0x70):
            self.ata[1] = 1
            self.ata[7] = 0x50
        else:
            raise AssertionError(('ATA command', hex(command)))

    def seed_physical(self, unit, offset, data):
        for i, byte in enumerate(data):
            position = offset+i
            for bank in range(2):
                storage = self.ram_banks.get((unit, bank), bytearray())
                if position < len(storage):
                    storage[position] = byte
                    break
                position -= len(storage)

    def external_memory_write(self, address, data):
        # Python-side interrupt delivery/test stimuli must use the same backing.
        if 0xF0000 <= address and address+len(data) <= 0x100000:
            self.rom[address-0xF0000:address-0xF0000+len(data)] = data
        if address < 0xA0000 or 0x100000 <= address < 0x2000000:
            if not self.map_programmed:
                self.seed_physical(0, address, data)
            else:
                for i, byte in enumerate(data):
                    key = self.ram_key(address+i)
                    if key:
                        self.ram_banks[key[0], key[1]][key[2]] = byte
                    self.cache_write(address+i, byte)
        self.raw_mem_write(address, data)

    def cache_address(self, address):
        return address if self.a20_enabled() else address & ~0x100000

    def a20_enabled(self):
        # Physical OEM TGA20 matrix: either E1 or KBC P2 opens the gate.
        return bool(self.controls.get(0xE1, 0) & 0x20 or self.kbc_output & 2)

    def cache_read(self, address, value):
        # Synthetic direct-mapped data cache for native alias/cleanup checks.
        # Its capacity and instruction-fetch behavior are not hardware proof.
        if self.cache and self.controls.get(0xE0, 0):
            address = self.cache_address(address)
            slot = address % self.cache_bytes
            old = self.cache_data.get(slot)
            if old is not None and old[0] == address:
                return old[1]
            self.cache_data[slot] = (address, value)
        return value

    def cache_write(self, address, value):
        if self.cache and self.controls.get(0xE0, 0):
            address = self.cache_address(address)
            self.cache_data[address % self.cache_bytes] = (address, value)

    def shadow_route(self, address):
        shift = 8+2*((address-0xF0000)//16384)
        if not any(self.ti[unit*256+7] >> shift & 3 for unit in range(len(self.controllers))):
            return None, 0
        key = self.ram_key(address)
        if key is None:
            return None, 0
        bits = self.ti[key[0]*256+7] >> shift & 3
        return key, bits

    def sync_system_rom(self):
        # Unicorn instruction fetch bypasses data hooks; update its fetch view.
        data = bytearray(self.rom)
        for page in range(4):
            address = 0xF0000+page*16384
            key, bits = self.shadow_route(address)
            if key is not None and bits & 2:
                unit, bank, offset = key
                data[page*16384:(page+1)*16384] = self.ram_banks[unit, bank][offset:offset+16384]
        self.raw_mem_write(0xF0000, bytes(data))

    def ram_key(self, address):
        if address >= 0x100000 and not self.a20_enabled():
            address &= ~0x100000
        matches = []
        for unit, pair in enumerate(self.controllers):
            mode = self.ti.get(unit*256+2, 0)
            raw = bool(mode & 0x40)
            high = raw or address >= 0x100000
            index = (address >> 16)*4 if high else address >> 14
            entry = self.maps.get((unit, high, index), 0)
            if not entry & 0x8000:
                continue
            if raw:
                bank = int(bool(entry & 0x4000))
                length = pair[bank]*65536
                offset = (entry & 0x7FF)*16384+(address & 0xFFFF)
                key = (unit, bank, offset % length) if length else None
            else:
                offset = (entry & 0x7FF)*16384+(address & (0xFFFF if high else 0x3FFF))
                # Captured onboard geometry aliases bit12 under the temporary36E4 profile.
                if unit == 0 and self.ti.get(3) == 0x4101 and self.ti.get(4,0) & 0x2000:
                    offset &= ~0x1000
                if offset < pair[0]*65536:
                    key = (unit, 0, offset)
                else:
                    offset -= pair[0]*65536
                    key = (unit, 1, offset) if offset < pair[1]*65536 else None
            matches.append((unit, key))
        assert len(matches) <= 1, ('multiple MCU decoders', hex(address), matches)
        return matches[0][1] if matches else None

    def write_bus(self, address, data):
        for i, byte in enumerate(data):
            key = self.ram_key(address+i)
            assert key is not None, ('unmapped RAM write', hex(address+i))
            unit, bank, offset = key
            self.ram_banks[unit, bank][offset] = byte
        self.cpu.mem_write(address, data)

    def memory_read(self, cpu, access, address, size, value, unused):
        if 0xF0000 <= address < 0x100000:
            data = bytearray()
            for i in range(size):
                key, bits = self.shadow_route(address+i)
                byte = self.ram_banks[key[0], key[1]][key[2]] if key and bits & 2 else self.rom[address+i-0xF0000]
                data.append(self.cache_read(address+i, byte))
            self.raw_mem_write(address, bytes(data))
            return
        if 0xA0000 <= address < 0x100000:
            if self.map_programmed:
                assert all(self.ram_key(address+i) is None for i in range(size)), ('RAM overlays ROM/video', hex(address))
            return
        if address >= 0x2000000:
            return
        data = bytearray()
        for i in range(size):
            key = self.ram_key(address+i)
            byte = self.ram_banks[key[0], key[1]][key[2]] if key else 255
            data.append(self.cache_read(address+i, byte))
        self.raw_mem_write(address, bytes(data))
        if self.capture_memory:
            self.memory_trace.append(('read', address, size, int.from_bytes(data, 'little')))
        if self.running and 0x10000 <= address:
            self.ram_reads += 1

    def memory_write(self, cpu, access, address, size, value, unused):
        if 0xF0000 <= address < 0x100000:
            for i, byte in enumerate(value.to_bytes(size, 'little')):
                key, bits = self.shadow_route(address+i)
                assert key is not None and bits & 1, ('write to read-only ROM', hex(address+i))
                self.ram_banks[key[0], key[1]][key[2]] = byte
                self.shadow_writes += 1
                self.shadow_written.add(address+i)
                self.cache_write(address+i, byte)
            return
        if 0xA0000 <= address < 0x100000 or address >= 0x2000000:
            return
        if self.capture_memory:
            self.memory_trace.append(('write', address, size, value))
        for i, byte in enumerate(value.to_bytes(size, 'little')):
            key = self.ram_key(address+i)
            if key:
                self.ram_banks[key[0], key[1]][key[2]] = byte
            self.cache_write(address+i, byte)

    def code(self, cpu, address, size, unused):
        if self.reference:
            if address == self.reference_stop:
                cpu.emu_stop()
            return
        if self.code_observer:
            self.code_observer(self, address)
        for label, stage in (('tiger_cold', 'cold'), ('tiger_warm', 'warm')):
            if address == 0xF0000+self.symbol(label):
                self.ti_stage = stage
        if address == 0xF0000+self.symbol('.count_memory', 'startup'):
            # INT15 fixture payload is installed after the destructive OEM probe.
            self.seed_physical(0, 0x110000, bytes.fromhex('44332211'))
        if address in (0xF0000+self.symbol('.count_memory', 'startup'), 0xF0000+self.symbol('.ram_ready', 'startup')):
            self.ti_stage = None
        if address == 0xC0003:
            assert cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200, 'VGA entered with IF clear'
            assert self.masks[0x21] == 0xFB and self.masks[0xA1] == 0xFF
            assert self.kbc_cb & 0x5F == 0x54
            assert self.processor_reset_count == 0
            assert cpu.reg_read(x.UC_X86_REG_ES) == 0x40
            assert cpu.reg_read(x.UC_X86_REG_DS) == 0xC000
            assert bytes(cpu.mem_read(0x467, 4)) == bytes.fromhex('030000c0')
            cpu.mem_write(0x40, struct.pack('<HH', 0x100, 0xC000))
            sp = cpu.reg_read(x.UC_X86_REG_SP)
            ss = cpu.reg_read(x.UC_X86_REG_SS)*16
            ip, cs = struct.unpack('<HH', cpu.mem_read(ss+sp, 4))
            cpu.reg_write(x.UC_X86_REG_SP, sp+4)
            cpu.reg_write(x.UC_X86_REG_CS, cs)
            cpu.reg_write(x.UC_X86_REG_IP, ip)
            return
        data = bytes(cpu.mem_read(address, size))
        if data == b'\x9f' and bytes(cpu.mem_read(address-2, 2)) == b'\xf6\xf3':
            flags = cpu.reg_read(x.UC_X86_REG_EFLAGS)
            cpu.reg_write(x.UC_X86_REG_EFLAGS, (flags & ~0xD5) | 4)
        assert not data.startswith((b'\x0f\x08', b'\x0f\x09', b'\x0f\x31')), ('486 instruction', hex(address), data.hex())
        if data[:2] == b'\x0f\xa2':
            raise AssertionError('CPUID executed on386 fixture')
        if data == b'\x66\x9d':
            ss = cpu.reg_read(x.UC_X86_REG_SS)*16
            sp = cpu.reg_read(x.UC_X86_REG_SP)
            flags = int.from_bytes(cpu.mem_read(ss+sp, 4), 'little') & ~0x00240000
            cpu.mem_write(ss+sp, flags.to_bytes(4, 'little'))
        if address == 0xF0000+self.symbol('hard_halt'):
            raise AssertionError(('firmware halt', self.posts[-12:], self.console))
        if address == 0xF0000+self.symbol('post_clock_alert') and not self.post_script_armed:
            self.script = self.script_after_post.copy()
            self.script_after_post = []
            self.post_script_armed = True
        # Reuse external PIT/FDC interrupt delivery, without its donor reset stop.
        old = self.warm_entry
        self.warm_entry = -1
        super().code(cpu, address, size, unused)
        self.warm_entry = old

    def interrupt(self, cpu, vector, unused):
        if vector in (0x10, 0x42) and cpu.reg_read(x.UC_X86_REG_AX) == 0x1130:
            cpu.reg_write(x.UC_X86_REG_ES, 0xC000)
            cpu.reg_write(x.UC_X86_REG_BP, 0x1000)
            cpu.reg_write(x.UC_X86_REG_CX, 16)
            cpu.reg_write(x.UC_X86_REG_DX, 24)
            return
        super().interrupt(cpu, vector, unused)

    def irq_scans(self, scans):
        for scan in scans:
            self.pending.append(scan)
            cpu = self.cpu
            for reg, value in ((x.UC_X86_REG_CS, 0x9000), (x.UC_X86_REG_IP, 0),
                               (x.UC_X86_REG_SS, 0), (x.UC_X86_REG_SP, 0x7000),
                               (x.UC_X86_REG_EFLAGS, 0x202)):
                cpu.reg_write(reg, value)
            rtc.Clock.interrupt(self, cpu, 9, None)
            cpu.emu_start(cpu.reg_read(x.UC_X86_REG_CS)*16+cpu.reg_read(x.UC_X86_REG_IP),
                          0x90000, count=100000)
            if self.reset_pending:
                return
            assert cpu.reg_read(x.UC_X86_REG_CS)*16+cpu.reg_read(x.UC_X86_REG_IP) == 0x90000

    def reset_processor(self):
        for reg, value in ((x.UC_X86_REG_CR0, 0x10), (x.UC_X86_REG_EFLAGS, 2), (x.UC_X86_REG_CS, 0xF000), (x.UC_X86_REG_IP, 0xFFF0), (x.UC_X86_REG_DS, 0), (x.UC_X86_REG_ES, 0), (x.UC_X86_REG_FS, 0), (x.UC_X86_REG_GS, 0), (x.UC_X86_REG_SS, 0), (x.UC_X86_REG_EAX, 0), (x.UC_X86_REG_EBX, 0), (x.UC_X86_REG_ECX, 0), (x.UC_X86_REG_EDX, 0x0308), (x.UC_X86_REG_ESI, 0), (x.UC_X86_REG_EDI, 0), (x.UC_X86_REG_EBP, 0), (x.UC_X86_REG_ESP, 0)):
            self.cpu.reg_write(reg, value)

    def boot(self, warm=False, count=50000000):
        self.running = True
        self.booted = False
        self.reset_pending = False
        self.post_script_armed = False
        if not warm:
            self.sys_flag = 0
        self.reset_processor()
        self.cpu.emu_start(0xFFFF0, 0x1000000, count=count)
        if self.reset_pending:
            return self.boot(warm=True, count=count)
        assert self.booted, ('no signed boot', hex(self.cpu.reg_read(x.UC_X86_REG_CS)), hex(self.cpu.reg_read(x.UC_X86_REG_IP)), self.posts[-16:], self.console)
