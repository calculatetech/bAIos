"""PnP callers with valid wrapping SS16 stacks and ordinary SS32 stacks."""
import importlib.util
from pathlib import Path
import struct
import sys

from unicorn import UC_HOOK_MEM_WRITE

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
spec = importlib.util.spec_from_file_location('pnp_stack_calls', Path(__file__).with_name('test-pnp.py'))
pnp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pnp)
pnp.OUTPUT = 'build'


def main():
    ports = sys.argv[1:] or ['m919']
    for port in ports:
        pnp.OUTPUT = 'build' if port == 'm919' else 'build/tests/pnp-stack'
        for mode in ('real', 'ss16', 'ss32'):
            caller = pnp.Caller(port, mode)

            def outside_stack(cpu, access, address, size, value, unused):
                if caller.public_active:
                    raise AssertionError(('SS16 local below segment', hex(address)))

            caller.cpu.hook_add(UC_HOOK_MEM_WRITE, outside_stack, None, 0x2F000, 0x2FFFF)
            def available_stack(cpu, access, address, size, value, unused):
                if caller.public_active and caller.mode != 'ss32':
                    top = caller.stack_offset & 0xFFFF
                    for at in range(address - 0x30000, address - 0x30000 + size):
                        assert ((top - at) & 0xFFFF) <= 1024 or ((at - top) & 0xFFFF) < 64
            caller.cpu.hook_add(UC_HOOK_MEM_WRITE, available_stack, None, 0x30000, 0x3FFFF)
            offsets = (0, 0x20, 0x80, 0xE0, 0x100, 0x180, 0x1BD, 0xFFC8, 0xFFF0, 0xFFF8, 0xFFFC) if mode != 'ss32' else (0x100D0,)
            for offset in offsets:
                caller.stack_offset = 0xABCD0000 | offset if mode != 'ss32' else offset
                assert caller.far(0, [0x100, caller.buffer, 0x108, caller.buffer, caller.bios]) == 0
                count = caller.cpu.mem_read(0x20100, 1)[0]
                for handle in range(count):
                    for control in (1, 2):
                        status, node, next_handle = pnp.get_node(caller, handle, control)
                        assert status == 0 and pnp.decode(node)
                        assert next_handle == (handle + 1 if handle + 1 < count else 255)
                request = pnp.get_node(caller, 8, 2)[1]
                caller.cpu.mem_write(0x20200, request)
                assert caller.far(2, [8, 0x200, caller.buffer, 2, caller.bios]) == 0
                assert caller.far(0x0B, [0x100, caller.buffer, caller.bios]) == 0
                assert caller.far(0x40, [0x100, caller.buffer, caller.bios]) == 0
                assert caller.far(0x1234) == 0x81
                if mode != 'ss32':
                    # Fn00's two output pointers target caller locals just above its arguments.
                    caller.stack_output_bytes = 8
                    at = (offset + 16) & 0xFFFF
                    caller.cpu.mem_write(0x30000 + at, b'\xCC' * 4)
                    assert caller.far(0, [at, caller.stack, at + 2, caller.stack, caller.bios]) == 0
                    assert caller.cpu.mem_read(0x30000 + at, 1)[0] == count
                    assert struct.unpack('<H', caller.cpu.mem_read(0x30000 + at + 2, 2))[0] >= 40
                    caller.stack_output_bytes = 0
            print(port, mode, 'node enumeration, both views, full caller state and stack guards PASS', flush=True)

        if port == 'm919':
            spec = importlib.util.spec_from_file_location('pnp_stack_flash', Path(__file__).with_name('test-escd.py'))
            flash = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(flash)
            for kind in ('mx', 'sst'):
                caller = flash.Flash(kind)
                caller.cpu.hook_add(UC_HOOK_MEM_WRITE, outside_stack, None, 0x2F000, 0x2FFFF)
                caller.cpu.hook_add(UC_HOOK_MEM_WRITE, available_stack, None, 0x30000, 0x3FFFF)
                data = bytearray(struct.pack('<H4sBB4xH', 177, b'ACFG', 0, 2, 0) + bytes(range(163)))
                for offset in (0x80, 0x180, 0x1BD, 0xFFF0):
                    caller.stack_offset = 0xABCD0000 | offset
                    assert caller.request(0x43, data) == 0
                    assert caller.read() == flash.canonical(data)
                print(port, kind, 'wrapped-stack flash read/write PASS', flush=True)


if __name__ == '__main__':
    main()
