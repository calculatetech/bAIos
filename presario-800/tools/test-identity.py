"""Parse the actual ROM as an independent DOS-era SMBIOS reader."""
import hashlib
import importlib
import os
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    build = ROOT / os.environ.get('BAIOS_BUILD_DIRECTORY', 'build')
    rom = (build / 'baios-presario800-system.rom').read_bytes()
    entries = [i for i in range(0, len(rom), 16) if rom[i:i+4] == b'_SM_']
    assert len(entries) == 1
    offset = entries[0]
    ep = rom[offset:offset+31]
    assert ep[5:8] == bytes((31, 2, 2)) and not sum(ep) & 255
    assert ep[16:21] == b'_DMI_' and not sum(ep[16:31]) & 255
    assert ep[10:16] == bytes(6) and ep[30] == 0x22
    length, address, count = struct.unpack_from('<HIH', ep, 22)
    start = address - 0xF0000
    assert start >= offset + 31 and start + length <= 0xF065 and count == 3
    maximum = struct.unpack_from('<H', ep, 8)[0]
    records = []
    pos = start
    while pos < start + length:
        kind, size, handle = struct.unpack_from('<BBH', rom, pos)
        assert size >= 4 and pos+size <= start+length
        end = rom.index(b'\0\0', pos+size) + 2
        assert end <= start+length and end-pos <= maximum
        pool = rom[pos+size:end-2]
        strings = pool.split(b'\0') if pool else []
        records.append((kind, size, handle, rom[pos:pos+size], strings))
        pos = end
    assert pos == start+length and len(records) == count
    assert [(r[0], r[1], r[2]) for r in records] == [(0, 0x13, 0), (1, 0x19, 1), (127, 4, 2)]
    bios, system, end = records
    assert bios[3][4:10] == bytes((1, 2, 0, 0xF0, 3, 1))
    assert bios[3][10:] == bytes((8,)) + bytes(8)
    assert bios[4] == [b'bAIos', b'0.1.0', b'10/05/2026']
    assert system[3][4:8] == bytes((1, 2, 0, 0))
    assert system[3][8:24] == bytes(16) and system[3][24] == 2
    assert system[4] == [b'Compaq', b'Presario 800'] and not end[4]
    assert rom[0xFFF5:0xFFFD] == b'10/05/26' and rom[0xFFFE] == 0xFC
    # Execute the retained descriptor interface and original Speedsys scanner.
    setup = importlib.import_module('test-setup')
    model = setup.Setup()
    x = setup.x
    model.setup(ah=0xC0,flags=0x202)
    model.cpu.mem_write(0x90000,b'\xcd\x15\x90')
    model.cpu.emu_start(0x90000,0x90002,count=100000)
    assert not model.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1
    assert model.cpu.reg_read(x.UC_X86_REG_IP)==2
    descriptor = model.cpu.reg_read(x.UC_X86_REG_ES)*16 + model.cpu.reg_read(x.UC_X86_REG_BX)
    assert model.cpu.mem_read(descriptor, 10) == bytes.fromhex('08 00 FC 01 00 74 40 00 00 00')
    seen = []
    def observe(m):
        assert m.text(0, 72, 5) == '0.1.0' and m.text(1, 69, 8) == '10/05/26'
        seen.append(True)
        m.observer = None
    model.observer = observe
    model.open([1, 28])
    assert seen
    code = (ROOT.parent/'reference/software/speedsys/4.78/SPEEDSYS-code.bin').read_bytes()
    assert hashlib.sha256(code).hexdigest() == 'b43f9ed7f8efa0f11561b3213b82c9727571fafd2fec1695b8cbfd0fe816eee0'
    scan = importlib.import_module('test-speedsys-rom-id').scan
    assert scan(code, rom) == (0x2000, 0xF000)
    marker = b'1999, BAIOS'
    assert rom.count(marker) == 1
    assert scan(code, bytes([255])*65536) == (0xF000, 0xEFFE)
    print('ROM identity: SMBIOS2.2 records/checksums/pointer, Setup version/date, INT15/C0 and original Speedsys scan PASS')


if __name__ == '__main__':
    main()
