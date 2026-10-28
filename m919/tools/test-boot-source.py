"""Reuse the composed UMC POST context for the shared CD/Other source proof."""
import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from types import SimpleNamespace

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
sys.path.insert(0, str(PORT.parent/'presario-800/tools'))
from shared.tools.ram_proof import Listing
from shared.tools.pci_proof import Endpoint
from geometry_proof import invoke
from pci_proof import compose
from sio_proof import SIO

cd = importlib.import_module('test-cdboot')


class Bus(SIO):
    def __init__(self, images, option_rom):
        endpoints = {0x60:Endpoint(cls=0x030000),
                     0x58:Endpoint(identity=0x673B1060, cls=0x01018F, pi_writable=5)}
        super().__init__(endpoints=endpoints)
        self.disk_device = cd.Packet(images)
        self.option_rom = option_rom

    def prepare(self, cpu):
        super().prepare(cpu)
        self.disk_device.cpu = cpu
        if self.option_rom is not None:cpu.mem_write(0xC8000, self.option_rom)

    def pci_write(self, address, port, size, value):
        super().pci_write(address, port, size, value)
        # The separate ISA ROM remains decoded outside the VGA provider extent.
        if self.option_rom is not None and self.machine is not None:
            self.machine.mem_write(0xC8000, self.option_rom)

    def incoming(self, cpu, port, size):
        if 0x1F0 <= port <= 0x1F7 or port == 0x3F6:
            return self.disk_device.port_in(cpu, port, size, None)
        return super().incoming(cpu, port, size)

    def outgoing(self, cpu, port, size, value):
        if 0x1F0 <= port <= 0x1F7 or port == 0x3F6:
            return self.disk_device.port_out(cpu, port, size, value, None)
        return super().outgoing(cpu, port, size, value)


class CPU:
    """Keep external fixture writes coherent with the existing UMC DRAM store."""
    def __init__(self, cpu, hardware):
        self.cpu, self.hardware = cpu, hardware

    def __getattr__(self, name):
        return getattr(self.cpu, name)

    def mem_write(self, address, data):
        for offset, value in enumerate(data):self.hardware.write(address+offset, 1, value)
        self.cpu.mem_write(address, data)


def check(image):
    image = image.resolve()
    folder = PORT/'build/tests/results/boot-source'
    folder.mkdir(parents=True, exist_ok=True)
    # Packet inherits a legacy external-device fixture constructor. Its private
    # CPU alias must use this board's candidate before the real UMC context runs.
    alias = folder/'fixture'
    alias.mkdir(exist_ok=True)
    (alias/'baios-presario800-system.rom').write_bytes(image.read_bytes()[65536:])
    listing = Listing(image.with_suffix('.lst'))
    cd.rtc.BUILD = alias
    cd.rtc.symbol = lambda name:listing.symbol('RTC_INTERRUPT_LABEL' if name == 'int1a' else 'startup' if name == '.warm_start' else name)
    def assemble(name, text):
        source, binary = folder/(name+'.asm'), folder/(name+'.bin')
        source.write_bytes(text.encode())
        nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
        subprocess.run([nasm, '-w+error', '-f', 'bin', '-o', str(binary), str(source)], check=True)
        return binary.read_bytes()
    def factory(images, option_rom):
        hardware = Bus(images, option_rom)
        _, fixture = compose(hardware)
        executed = PORT/'build/hardware-tests/geometry/baios-m919.bin'
        if executed.read_bytes() != image.read_bytes():
            raise ValueError('M919 boot-source proof requires the exact default candidate; selected image differs from the executed ROM')
        cpu, hardware, _, _, cmos, _ = fixture
        base = int.from_bytes(hardware.read(0x40E, 2), 'little')<<4
        assert cpu.reg_read(cd.x.UC_X86_REG_CR0)&0x40000000 and not hardware.registers[0x50]&0x80
        return SimpleNamespace(cpu=CPU(cpu, hardware), base=base, cmos=cmos,
                               disk_device=hardware.disk_device, console='', fixture=fixture)
    def start(m):
        cpu, hardware, _, _, _, _ = m.fixture
        cpu.reg_write(cd.x.UC_X86_REG_CS, 0xF000)
        cpu.reg_write(cd.x.UC_X86_REG_DS, 0)
        cpu.reg_write(cd.x.UC_X86_REG_ES, 0)
        cpu.reg_write(cd.x.UC_X86_REG_FS, m.base>>4)
        invoke(m.fixture, 'settings_load')
        invoke(m.fixture, 'ata_detect_primary', count=1000000)
        hardware.phase, hardware.stop, hardware.continuing = 'boot', None, False
        for reg,value in ((cd.x.UC_X86_REG_CS,0),(cd.x.UC_X86_REG_IP,0x8000),
                          (cd.x.UC_X86_REG_DS,0),(cd.x.UC_X86_REG_SS,0),
                          (cd.x.UC_X86_REG_SP,0x7000),(cd.x.UC_X86_REG_EFLAGS,0x202)):
            cpu.reg_write(reg,value)
        m.cpu.mem_write(0x8000, b'\xCD\x19')
        cpu.emu_start(0x8000, 0xFFFFF, count=4000000)
    rows = []
    for other in (False, True):
        rows += cd.source_geometry_lifecycle(other, factory=factory, start=start,
                                             assemble=assemble, check_post_ff=False)
    (folder/'result.json').write_text(json.dumps(rows, indent=2)+'\n')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    check(parser.parse_args().image)
