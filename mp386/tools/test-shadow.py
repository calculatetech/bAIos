"""OEM allocation, native shadow I/O and fault-path checks; no hardware claims."""
import argparse
import importlib
import json
import struct
from pathlib import Path

from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x

from fixture import Tiger, PORT

memory = importlib.import_module('test-memory')
port = importlib.import_module('test-port')
PAIRS = ((16, 16), (64, 64), (64, 64))


def configured(image, pairs=PAIRS, cache=False):
    m = Tiger(image, controllers=pairs, cache=cache)
    memory.window(m, m.symbol('startup'), m.symbol('.ram_ready', 'startup'))
    counts = [p for pair in pairs for p in pair]+[0]*(6-len(pairs)*2)
    m.cpu.mem_write(0x9F010, struct.pack('<6HH', *counts, len(pairs)))
    assert m.controls[0xE0] == 0 and not m.controls[0xE2] & 2
    m.cpu.mem_write(0x9F01F, b'\x01')
    m.cpu.mem_write(0x9E061, b'\x01')  # System ROM Shadow defaults to Enabled.
    return m


def invoke(m, name, **kwargs):
    stop = m.symbol('core_verify_initialization')
    m.cpu.mem_write(0x6FFE, struct.pack('<H', stop))
    registers = ((x.UC_X86_REG_SS, 0), (x.UC_X86_REG_SP, 0x6FFE),
                 (x.UC_X86_REG_FS, 0x9E00), (x.UC_X86_REG_EFLAGS, 0x646))
    memory.window(m, m.symbol(name), stop, registers, **kwargs)
    assert m.cpu.reg_read(x.UC_X86_REG_SP) == 0x7000
    assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) == 0x646


def backing(m):
    return bytes(m.ram_banks[0, 0][0xA0000:0xB0000])


def records(image):
    results = []
    for pairs in (PAIRS, ((16, 0), (64, 64), (0, 0)), ((16, 0), (0, 0), (64, 64))):
        m = configured(image, pairs)
        data = bytes(m.cpu.mem_read(0x600, 256))
        high = next(unit for unit, pair in enumerate(pairs) if sum(sum(p) for p in pairs[:unit+1]) > 16)
        local = 16-sum(sum(p) for p in pairs[:high])
        assert struct.unpack_from('<H', data, 0xAD)[0] == high*0x1000+local*4
        assert data[0x4E:0x50] == bytes((40, 4)) and data[0x81] == 1
        assert struct.unpack_from('<H', data, 0xB3)[0] == 0x28
        assert all(m.maps[0, False, 0x3C+i] == 0x8028+i for i in range(4))
        for address in (0x100000, 0x1FFFFF):
            assert m.ram_key(address) is not None
        results.append(memory.mapper_comparison(image, pairs))
    return results


def prepare(image):
    m = configured(image)
    preserved = bytes((i*37+11)&255 for i in range(16384))
    m.write_bus(0x80000, preserved)
    original_maps = dict(m.maps)
    fill_io = []
    begin, end = (m.symbol(name, 'mp_shadow_prepare') for name in ('.fill_begin', '.fill_end'))
    def capture(cpu, address, size, unused):
        if address == 0xF0000+begin:
            m.ti_trace['cold'].clear()
        if address == 0xF0000+end:
            fill_io.extend(memory.hardware_trace(m))
    hook = m.cpu.hook_add(UC_HOOK_CODE, capture)
    invoke(m, 'mp_shadow_prepare')
    m.cpu.hook_del(hook)
    assert m.maps == original_maps, 'Aperture mapping was not restored'
    assert m.ram_banks[0, 0][0x80000:0x84000] == preserved
    assert backing(m) == Path(image).read_bytes(), 'Not every ROM byte reached backing'
    assert m.shadow_written == set(range(0xF0000, 0x100000))
    assert m.cpu.mem_read(0x9F01E, 1) == b'\x01'
    assert all(m.ti[unit*256+7] == 0 for unit in range(3))
    # Keep the existing safe boundary when a high window is not writable RAM.
    original_decoder = m.ram_key
    m.ram_key = lambda address: None if 0xFE0000 <= address < 0x1000000 else original_decoder(address)
    m.cpu.reg_write(x.UC_X86_REG_EAX, 18*1024*1024)
    invoke(m, 'memory_qualify_contiguous')
    assert m.cpu.reg_read(x.UC_X86_REG_EAX) == 0xFE0000
    m.ram_key = original_decoder
    # Run the unmodified native fill with only its private record read replaced.
    native = configured(image)
    data = bytes(native.cpu.mem_read(0x600, 256))
    native.ti_trace['cold'].clear()
    memory.window(native, 0x6F59, 0x6FA6,
                  ((x.UC_X86_REG_SS, 0), (x.UC_X86_REG_SP, 0x7000)),
                  raw=memory.oem_image(), record_reads=data)
    assert fill_io == memory.hardware_trace(native), 'Native fill hardware operation order'
    assert backing(native) == memory.oem_image()
    # The native late owner reads MCU0 and writes the modified word first to
    # the source controller, then to every controller. This is persistent state.
    native.ti_trace['cold'].clear()
    memory.window(native, 0x89E7, 0x8A73, record_reads=data)
    m.ti_trace['cold'].clear()
    invoke(m, 'mp_shadow_activate')
    assert memory.hardware_trace(m) == memory.hardware_trace(native)
    assert all(m.ti[unit*256+7] == 0xAA00 for unit in range(3))
    assert bytes(m.cpu.mem_read(0xF0000, 65536)) == Path(image).read_bytes()
    assert m.cpu.mem_read(0x9F01E, 1) == b'\x02'
    return dict(full_copy_bytes=len(m.shadow_written), native_fill_io=len(fill_io),
                native_activation_io=len(memory.hardware_trace(m)), aperture_restored=True,
                unwritable_boundary_still_limited_KiB=16256)


def failures(image):
    results = []
    for fault in ('no-holdoff', 'wrong-F-map', 'competing-aperture', 'pattern', 'copy'):
        m = configured(image)
        if fault == 'no-holdoff':
            m.cpu.mem_write(0x9F01F, b'\x00')
        if fault == 'wrong-F-map':
            m.maps[0, False, 0x3C] = 0x8001
        if fault == 'competing-aperture':
            m.maps[1, False, 0x20] = 0x8000
        if fault in ('pattern', 'copy'):
            class BadRAM(bytearray):
                def __setitem__(self, index, value):
                    if index == 0xA0123 and (fault == 'pattern' or m.ti[7] == 0x5500):
                        value ^= 1
                    super().__setitem__(index, value)
            m.ram_banks[0, 0] = BadRAM(m.ram_banks[0, 0])
        old_maps = dict(m.maps)
        invoke(m, 'mp_shadow_prepare')
        assert m.maps == old_maps
        assert m.cpu.mem_read(0x9F01E, 1) == b'\x00'
        assert len(m.shadow_written) == (65536 if fault == 'copy' else 0)
        invoke(m, 'mp_shadow_activate')
        assert all(m.ti[unit*256+7] == 0 for unit in range(3))
        results.append(dict(fault=fault, shadow_disabled=True, aperture_restored=True))
    return results


def boots(image):
    results = []
    seed = port.machine(image, cache=True)
    seed.boot()
    for pairs in (((16, 16),), PAIRS):
        m = port.machine(image, controllers=pairs, cache=False)
        m.cmos[:] = seed.cmos
        m.nvram[:] = seed.nvram
        m.script_after_post = []
        rendered = []
        warm = False
        preserved = []
        def post_status(mm, address):
            if (warm or pairs == PAIRS) and address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
                # Exercise the real Escape path; the unchanged18MiB RAM sweep
                # is outside this focused shadow integration check.
                mm.pending.append(0x01)
            if warm and address == 0xF0000+mm.symbol('post_ui_begin'):
                assert mm.ram_banks[0, 1][0x80000:0x80004] == b'KEEP'
                preserved.append(True)
            if address == 0xF0000+mm.symbol('option_rom_discovery'):
                assert 'Shadowed' in mm.text(16, 24, 40)
                rendered.append(True)
        m.code_observer = post_status
        m.boot(count=100000000)
        assert m.booted and not m.reset_count
        assert m.cpu.mem_read(m.base+0x101E, 1) == b'\x02'
        assert backing(m) == Path(image).read_bytes()
        assert rendered
        print('PASS cold shadow boot', pairs, flush=True)
        m.controls[0xE1] |= 0x20
        m.write_bus(0x180000, b'KEEP')
        copies = m.shadow_writes
        cold = len(m.ti_trace['cold'])
        warm = True
        m.boot(warm=True)
        assert m.booted and m.shadow_writes >= copies+65536
        assert len(m.ti_trace['cold']) == cold
        assert len(rendered) == 2
        assert preserved
        assert all(m.ti[unit*256+7] == 0xAA00 for unit in range(len(pairs)))
        results.append(dict(controllers=pairs, cold=True, warm=True, extended_payload_preserved_through_shadow_prepare=True))
        print('PASS cold/warm shadow boot', pairs, flush=True)
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=PORT/'build/oem-shadow/baios-mp386.bin')
    parser.add_argument('--case', choices=('records', 'prepare', 'failures', 'boot'), required=True)
    args = parser.parse_args()
    result = {'records': records, 'prepare': prepare, 'failures': failures, 'boot': boots}[args.case](args.image)
    (args.image.parent/f'shadow-{args.case}.json').write_text(json.dumps(result, indent=2)+'\n')
    print('PASS', args.case, json.dumps(result))


if __name__ == '__main__':
    main()
