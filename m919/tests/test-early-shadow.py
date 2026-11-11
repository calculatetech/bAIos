"""Check real early shadow copies and their read/write control order."""
import importlib.util
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('early_shadow_post', ROOT/'shared/tests/test-live-post.py')
post = importlib.util.module_from_spec(spec)
spec.loader.exec_module(post)
from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from shared.tools.pci_proof import Endpoint, PCI
from shared.tools.ram_proof import constants


def check(source,warm,name):
    shadow = bytearray(131072)
    written = bytearray(131072)
    bus = post.ProbeBus()
    expected=bytearray(source)
    expected[0x81C]=0
    expected[0x81C]=(-sum(expected[0x800:65536]))&255

    class Host(Endpoint):
        def write(self, offset, size, value):
            super().write(offset, size, value)
            if self.raw[0x55] & 0x80:
                assert all(written[65536:]), 'F reads enabled before its complete copy'
                assert shadow[65536:] == source[65536:]
                if self.raw[0x54] & 1:
                    assert all(written[:65536]), 'E reads enabled before its complete copy'
                    assert shadow[:65536] == expected[:65536]

    host = Host(identity=0x88811060)
    host.raw[0x54] = 0xA5 if warm else 0xA4
    host.raw[0x55] = 0xC0 if warm else 0x40
    bus.pci = PCI({0x80: host})
    m = post.p.isa_machine('m919', bus, 'build')
    m.cpu.mem_write(0xE0000,source)

    def read(cpu,access,address,size,value,unused):
        at=address-0xE0000
        data=shadow if host.raw[0x55]&0x80 and host.raw[0x54]&1 else source
        cpu.mem_write(address,bytes(data[at:at+size]))

    def write(cpu, access, address, size, value, unused):
        assert not host.raw[0x55] & 0x40, 'Write-protected shadow copy'
        at = address - 0xE0000
        shadow[at:at+size] = value.to_bytes(size, 'little')
        written[at:at+size] = b'\1' * size

    m.cpu.hook_add(UC_HOOK_MEM_WRITE, write, None, 0xE0000, 0xFFFFF)
    m.cpu.hook_add(UC_HOOK_MEM_READ,read,None,0xE0000,0xEFFFF)
    m.call('board_firmware_shadow')
    assert host.raw[0x54] == 0xA5 and host.raw[0x55] == 0xC0
    assert all(written) and shadow == expected
    assert shadow[:4]==b'\x55\xAA\x04\xCB' and sum(shadow[:0x800])%256==sum(shadow[0x800:65536])%256==0
    assert shadow[0x8000:0x10000]==source[0x8000:0x10000],'NVS snapshot was changed'
    layout = constants(ROOT/'m919/src/hardware/board-definition.inc')
    m.cpu.mem_write(m.base + layout['HW_VGA_END'], (0xC800).to_bytes(2, 'little'))
    m.call('board_vga_shadow')
    assert host.raw[0x54] == 0xA7 and host.raw[0x55] == 0xC0
    changes = [row for row in host.writes if row[0] == 0x55]
    assert changes[-2:] == [(0x55, 1, 0x80), (0x55, 1, 0xC0)], changes
    result = dict(complete_E_F_copies_before_enable=True, E_shadow_preserved_during_VGA_copy=True,
                  unrelated_region_bits_preserved=True, final_write_protection=True,
                  valid_split_reservation_checksums=True,warm=warm)
    folder = ROOT/'m919/build/tests/video-first'
    folder.mkdir(parents=True, exist_ok=True)
    (folder/(name+'-visible-E.bin')).write_bytes(shadow[:65536])
    return result


def main():
    source=(ROOT/'m919/build/baios-m919.bin').read_bytes()
    spec=importlib.util.spec_from_file_location('shadow_escd',ROOT/'shared/tests/test-escd.py')
    escd=importlib.util.module_from_spec(spec);spec.loader.exec_module(escd)
    flash=escd.Flash()
    data=bytearray(177);data[:8]=bytes.fromhex('B100414346470002')
    for at in range(12,175):data[at]=(at*29)&255
    assert flash.request(0x43,data)==0
    persisted=bytes(flash.flash)+source[65536:]
    assert sum(persisted[:65536])%256!=0,'Persistence stimulus did not alter E-bank checksum'
    rows={name:check(raw,warm,name) for name,raw,warm in (
        ('factory-cold',source,False),('persisted-cold',persisted,False),('persisted-warm',persisted,True))}
    folder=ROOT/'m919/build/tests/video-first'
    (folder/'early-shadow-check.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(rows,indent=2))


if __name__ == '__main__':
    main()
