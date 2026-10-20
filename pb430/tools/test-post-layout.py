"""Check the live cache/RAM gap through start, completion and redraw."""
import importlib
import json
import struct
import sys
from pathlib import Path

timing = importlib.import_module('test-timing-setup')
PORT = Path(__file__).resolve().parents[1]
image = Path(sys.argv[1]) if len(sys.argv) > 1 else PORT / 'build/baios-pb430.bin'
rows = []
for enabled, failed in ((0, 0), (1, 0), (0, 2), (1, 2)):
    m = timing.model(image)
    m.cpu.mem_write(m.base+0x78, struct.pack('<H', 15360))
    m.cpu.mem_write(m.base+0x1000, bytes.fromhex('1111'))
    m.cpu.mem_write(m.base+0x1003, bytes((1, 2, 1, 0)))
    m.cpu.mem_write(m.base+0x100D, bytes((failed,)))
    m.cpu.mem_write(m.base+0x61, bytes((1, enabled)))
    m.registers[4] &= ~1
    m.cpu.reg_write(timing.x.UC_X86_REG_CR0, 0x60000010)
    m.cpu.mem_write(m.base+0x51, b'\x01')
    m.cpu.mem_write(m.base+0x50, b'\x01')
    expected = 'Cache test failed' if failed else '512 KB' if enabled else '512 KB Off'
    finished = False
    for owner in ('post_ui_begin', 'post_ram_start', 'post_ram_finish', 'post_ui_begin'):
        m.call(owner)
        screen = bytes(m.cpu.mem_read(0xB8000, 4000))[::2].decode('cp437')
        lines = [screen[row*80:(row+1)*80] for row in range(25)]
        assert 'l1 cache' in lines[3].lower() and 'l2 cache' in lines[4].lower(), lines[:8]
        assert lines[3][24:].strip() == 'Enabled', lines[3]
        assert lines[4][24:].strip() == expected, lines[4]
        assert lines[5] == ' '*80, lines[5]
        assert 'RAM Test' in lines[6], lines[6]
        finished |= owner == 'post_ram_finish'
        if finished:
            assert 'Memory Banks' in lines[7] and lines[7][24:].strip() == '0 1 2 3', lines[7]
            m.cpu.mem_write(m.base+0x51, b'\x02')
        rows.append({'owner': owner, 'enabled': enabled, 'failed': failed,
                     'l2': expected, 'blank_row': 5, 'ram_row': 6, 'banks_visible': finished})
output = image.parent/'post-layout-results.json'
output.write_text(json.dumps(rows, indent=2)+'\n')
print('PASS live L2/blank/RAM rows through start, completion and redraw')
