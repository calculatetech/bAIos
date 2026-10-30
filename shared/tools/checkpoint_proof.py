"""Execute shared defaults, saved-policy and boot-selection owners."""
import argparse
import json
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR
from unicorn import x86_const as x

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from shared.tools.ram_proof import Listing, constants


def run(image):
    listing = Listing(image.with_suffix('.lst'))
    state = constants(ROOT / 'shared/src/pc/state.inc')
    state.update(constants(ROOT / 'shared/src/firmware/boot.inc'))
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x100000)
    raw = image.read_bytes()
    u.mem_write(0x100000 - len(raw), raw)
    base, code = 0x80000, 0xF0000
    u.mem_write(0x40E, struct.pack('<H', base >> 4))
    cmos, selected, writes = bytearray(256), [0], []
    nv_phase, nv_index = [0], [0]
    pit, pit_byte = [0xFFFF], [0]

    def inp(cpu, port, size, _):
        if port == 0x40:
            value = pit[0] >> (8 * pit_byte[0]) & 255
            pit_byte[0] ^= 1
            if not pit_byte[0]:
                pit[0] = (pit[0] - 0x1000) & 65535
            return value
        if port == 0x48:
            value = cmos[0x40 + nv_index[0]] if nv_phase[0] == 3 else 0
            nv_phase[0] = 0
            return value
        return cmos[selected[0]] if port == 0x71 else 0

    def out(cpu, port, size, value, _):
        if port == 0x48:
            if nv_phase[0] == 2:
                nv_index[0] = value & 0x3F
            elif nv_phase[0] == 3:
                cmos[0x40 + nv_index[0]] = value
                writes.append((0x40 + nv_index[0], value))
            nv_phase[0] = (nv_phase[0] + 1) % 4
        if port == 0x70:
            selected[0] = value & 0x7F
        elif port == 0x71:
            cmos[selected[0]] = value
            writes.append((selected[0], value))

    u.hook_add(UC_HOOK_INSN, inp, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, out, None, 1, 0, x.UC_X86_INS_OUT)

    def call(name):
        for reg, value in ((x.UC_X86_REG_CS, 0xF000), (x.UC_X86_REG_DS, 0),
                           (x.UC_X86_REG_FS, base >> 4), (x.UC_X86_REG_SS, 0),
                           (x.UC_X86_REG_SP, 0x7000), (x.UC_X86_REG_EFLAGS, 0x202)):
            u.reg_write(reg, value)
        u.mem_write(0x7000, struct.pack('<H', 0x8000))
        u.emu_start(code + listing.symbol(name), code + 0x8000, count=1000000)
        assert u.reg_read(x.UC_X86_REG_IP) == 0x8000, (name, hex(u.reg_read(x.UC_X86_REG_CS)), hex(u.reg_read(x.UC_X86_REG_IP)), hex(u.reg_read(x.UC_X86_REG_SP)))
        if name == 'settings_save':
            assert not u.reg_read(x.UC_X86_REG_EFLAGS) & 1, name

    def get(name, size=1):
        return bytes(u.mem_read(base + state[name], size))

    def put(name, value):
        u.mem_write(base + state[name], bytes((value,)))

    def order(prefix):
        return [get(prefix + suffix)[0] for suffix in ('BOOT', 'BOOT_SECOND', 'BOOT_THIRD', 'BOOT_FOURTH')]

    call('settings_load')
    assert order('C_') == [3, 1, 2, 0] and not writes
    call('setup_defaults')
    assert order('U_') == [3, 1, 2, 0] and not writes
    # Both real menus call setup_defaults; follow the same save and reload owners.
    call('settings_save')
    saved = bytes(cmos)
    writes.clear()
    call('settings_load')
    assert order('C_') == [3, 1, 2, 0] and bytes(cmos) == saved and not writes
    chipset = get('C_CHIP', 24)
    if 'm919' in image.parts:
        assert chipset[1:4] == b'\x01\x00\x40'
    elif 'presario-800' in image.parts:
        assert chipset[4] & 8 and chipset[9] & 1 and not chipset[9] & 8
    elif 'pb430' in image.parts:
        assert chipset[1:3] == b'\x01\x01'

    for name, value in (('U_BOOT', 2), ('U_BOOT_SECOND', 1), ('U_BOOT_THIRD', 3)):
        put(name, value)
    if 'm919' in image.parts:
        u.mem_write(base + state['U_CHIP'] + 3, b'\x00')
    call('settings_save')
    saved = bytes(cmos)
    writes.clear()
    call('settings_load')
    assert order('C_') == [2, 1, 3, 0] and bytes(cmos) == saved and not writes
    if 'm919' in image.parts:
        assert get('C_CHIP', 4)[3] == 0, 'valid WT setting was overwritten'
        u.reg_write(x.UC_X86_REG_DI, state['C_CHIP'])
        call('chipset_safe_defaults')
        assert get('C_CHIP', 3)[1:] == b'\x00\x01'

    # Schema 1 stores an order selector, not four independent targets.
    for mode, expected in ((0, [1, 2, 0, 0]), (1, [2, 1, 0, 0]), (2, [2, 0, 0, 0])):
        cmos[0x10] = 0x40
        cmos[0x38:0x40] = bytes((ord('B'), ord('8'), 1, 1, mode, 0, 0, 0))
        cmos[0x3D] = (-sum(cmos[0x38:0x3D]) - cmos[0x10]) & 255
        legacy = bytes(cmos)
        writes.clear()
        call('settings_load')
        assert order('C_') == expected, (mode, order('C_'))
        assert bytes(cmos) == legacy and not writes

    cmos[0x38] = 0
    writes.clear()
    call('settings_load')
    assert order('C_') == [3, 1, 2, 0] and not writes
    # Observe real dispatch targets. Disk/provider execution belongs to separate proofs.
    put('C_PORTS', 0)
    u.mem_write(base + state['C_PORTS'] + state['P_FLOPPY'], b'\x01')
    put('F_TYPES', 0x40)
    u.mem_write(0x475, b'\x01')
    put('B_CURSOR', 0)
    attempts = []
    def interrupt(cpu, number, _):
        assert number == 0x13, number
        flags = cpu.reg_read(x.UC_X86_REG_EFLAGS)
        sp = cpu.reg_read(x.UC_X86_REG_SP) - 6
        stack = cpu.reg_read(x.UC_X86_REG_SS) << 4
        cpu.mem_write(stack + sp, struct.pack('<HHH', cpu.reg_read(x.UC_X86_REG_IP),
                                             cpu.reg_read(x.UC_X86_REG_CS), flags & 0xFFFF))
        cpu.reg_write(x.UC_X86_REG_SP, sp)
        cpu.reg_write(x.UC_X86_REG_EFLAGS, flags & ~0x300)
        cpu.reg_write(x.UC_X86_REG_CS, 0xF000)
        cpu.reg_write(x.UC_X86_REG_IP, listing.symbol('int13'))
    u.hook_add(UC_HOOK_INTR, interrupt)
    def target(cpu, address, size, _):
        attempts.append(3 if address == code + listing.symbol('cd_boot') else
                        2 if cpu.reg_read(x.UC_X86_REG_DL) & 0x80 else 1)
        cpu.emu_stop()
    handles = [u.hook_add(UC_HOOK_CODE, target, None, code + listing.symbol(name),
                         code + listing.symbol(name)) for name in ('cd_boot', 'int13')]
    for _ in range(3):
        u.reg_write(x.UC_X86_REG_CS, 0xF000)
        u.emu_start(code + listing.symbol('boot_candidate'), code + 0x8000, count=200000)
    for handle in handles:
        u.hook_del(handle)
    assert attempts == [3, 1, 2], attempts
    return dict(image=str(image), cold_defaults=True, confirmed_defaults=True,
                saved_order_preserved=True,
                legacy_orders_preserved=True,
                saved_cache_policy_preserved=True if 'm919' in image.parts else None,
                recovery_preserved=True if 'm919' in image.parts else None,
                selected_targets=attempts)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    rows = [run(p.resolve()) for p in args.images]
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps(rows, indent=2))
