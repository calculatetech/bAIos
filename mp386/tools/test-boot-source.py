"""Run the shared failed-HDD/CD/Other producer proof through actual Tiger POST."""
import argparse
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from fixture import Tiger

cd = importlib.import_module('test-cdboot')


class Bus(Tiger):
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
        nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
        subprocess.run([nasm, '-w+error', '-f', 'bin', '-o', str(binary), str(source)], check=True)
        return binary.read_bytes()
    def factory(images, option_rom):
        m = Bus(image)
        m.disk_device = cd.Packet(images)
        m.disk_device.cpu = m.cpu
        if option_rom is not None:m.cpu.mem_write(0xC8000, option_rom)
        entry = 0xF0000+m.symbol('chipset_visible_ram_test')
        m.code_observer = lambda model,address:model.pending.append(1) if address == entry else None
        return m
    rows = []
    for other in (False, True):
        rows += cd.source_geometry_lifecycle(other, factory=factory, start=lambda m:m.boot(),
                                             assemble=assemble, check_post_ff=False)
    (folder/'result.json').write_text(json.dumps(rows, indent=2)+'\n')
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    check(parser.parse_args().image)
