"""Boot a legacy CHS disk that requires volatile parameters after every reset."""
import argparse
import importlib
import json
from pathlib import Path
import struct

from fixture import Tiger

port = importlib.import_module('test-port')


class ParameterDisk(Tiger):
    def __init__(self, image, chs=True, reject=False):
        self.chs, self.reject = chs, reject
        self.initialized = False
        self.ata_events = []
        self.failed_reads = 0
        super().__init__(image)
        self.disk = port.boot_sector()

    def port_out(self, cpu, address, size, value, unused):
        if address == 0x3F6 and value & 4:
            self.initialized = False
            self.ata_events.append(('reset',))
        return super().port_out(cpu, address, size, value, unused)

    def ata_command(self, command):
        if self.ata[6] & 0x10:
            return super().ata_command(command)
        if command == 0xEC:
            data = bytearray(512)
            for index, value in ((0, 0x40), (1, 989), (3, 15), (6, 56),
                                 (49, 0 if self.chs else 0x200), (60, 0xAD28), (61, 12)):
                struct.pack_into('<H', data, index*2, value)
            model = b'WDC AC2420H'.ljust(40)
            data[54:94] = b''.join(model[i:i+2][::-1] for i in range(0, 40, 2))
            self.ata_fifo, self.ata[7] = data, 0x58
            return
        if command == 0x91:
            heads, sectors = (self.ata[6] & 15)+1, self.ata[2]
            assert (heads, sectors) == (15, 56)
            self.ata_events.append(('parameters', heads, sectors))
            self.initialized = not self.reject
            self.ata[1], self.ata[7] = (4, 0x51) if self.reject else (1, 0x50)
            return
        if command == 0x20:
            if self.chs and not self.initialized:
                self.failed_reads += 1
                self.ata[1], self.ata[7] = 0x10, 0x51
                return
            assert bool(self.ata[6] & 0x40) != self.chs
            lba = (self.ata[3] | self.ata[4] << 8 | self.ata[5] << 16 |
                   (self.ata[6] & 15) << 24) if not self.chs else (
                   ((self.ata[4] | self.ata[5] << 8)*15+(self.ata[6] & 15))*56+self.ata[3]-1)
            count = self.ata[2] or 256
            self.ata_events.append(('read', lba, count))
            self.ata_fifo = bytearray(self.disk[lba*512:(lba+count)*512])
            assert len(self.ata_fifo) == count*512
            self.ata[7] = 0x58
            return
        return super().ata_command(command)


def check(image, expect_failure=False):
    rows = []
    for chs, reject in ((True, False),) if expect_failure else ((True, False), (False, False), (True, True)):
        m = ParameterDisk(image, chs=chs, reject=reject)
        def observer(mm, address):
            if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
                mm.pending.append(1)
            if address == 0xF0000+mm.symbol('boot_retry'):
                mm.cpu.emu_stop()
        m.code_observer = observer
        for warm in (False, True):
            start = len(m.ata_events)
            try:
                m.boot(warm=warm, count=10000000)
            except AssertionError as error:
                assert (expect_failure or reject) and error.args[0][0] == 'no signed boot', error
            else:
                assert not expect_failure and not reject and m.booted
            events = m.ata_events[start:]
            if expect_failure:
                assert m.failed_reads and not any(e[0] == 'parameters' for e in events)
            elif reject:
                assert not m.cpu.mem_read(m.base+0x20, 1)[0]
                assert any(e[0] == 'parameters' for e in events)
                assert not any(e[0] == 'read' for e in events)
            else:
                assert not m.failed_reads and m.booted
                assert m.cpu.mem_read(m.base+0x1E2, 1)[0] == int(chs)
                assert any(e[0] == 'parameters' for e in events) == chs
                initialized = not chs
                for event in events:
                    if event[0] == 'reset': initialized = not chs
                    elif event[0] == 'parameters': initialized = True
                    elif event[0] == 'read': assert initialized
                assert {e[1] for e in events if e[0] == 'read'} >= {0, 1}
            rows.append(dict(CHS=chs, rejected=reject, warm=warm,
                             signed_boot=m.booted, events=events))
            print('PASS', rows[-1], flush=True)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--expect-failure', action='store_true')
    args = parser.parse_args()
    rows = check(args.image, args.expect_failure)
    (args.image.parent/'chs-boot.json').write_text(json.dumps(rows, indent=2)+'\n')
