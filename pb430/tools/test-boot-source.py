"""Run the shared failed-HDD/CD/Other producer proof through PB430 cold POST."""
import argparse
import importlib
import json
from pathlib import Path
import sys

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from core_proof import ACC

timing = importlib.import_module('test-timing-setup')
suite = importlib.import_module('test-port')
cd = importlib.import_module('test-cdboot')


class Bus(ACC):
    def __init__(self, *args, **kwargs):
        self.disk_device = None
        super().__init__(*args, **kwargs)

    def port_in(self, cpu, port, size, unused):
        if self.disk_device is not None and (0x1F0 <= port <= 0x1F7 or port == 0x3F6):
            return self.disk_device.port_in(cpu, port, size, unused)
        return super().port_in(cpu, port, size, unused)

    def port_out(self, cpu, port, size, value, unused):
        if self.disk_device is not None and (0x1F0 <= port <= 0x1F7 or port == 0x3F6):
            return self.disk_device.port_out(cpu, port, size, value, unused)
        return super().port_out(cpu, port, size, value, unused)


def check(image):
    folder = PORT/'build/tests/results/boot-source'
    folder.mkdir(parents=True, exist_ok=True)
    def assemble(name, text):
        source, binary = folder/(name+'.asm'), folder/(name+'.bin')
        source.write_bytes(text.encode())
        suite.assemble(source, binary)
        return binary.read_bytes()
    def factory(images, option_rom):
        chip = bytearray(timing.DEFAULT)
        chip[6] = 1
        m = timing.model(image, chip, Bus)
        m.disk_device = cd.Packet(images)
        m.disk_device.cpu = m.cpu
        if option_rom is not None:m.cpu.mem_write(0xC8000, option_rom)
        m.stop_address = 0xF0000+m.listing.symbol('.wait', 'boot_retry')
        return m
    rows = []
    for other in (False, True):
        rows += cd.source_geometry_lifecycle(other, factory=factory, start=lambda m:m.cold_boot(),
                                             assemble=assemble, check_post_ff=False)
    (folder/'result.json').write_text(json.dumps(rows, indent=2)+'\n')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    check(parser.parse_args().image)
