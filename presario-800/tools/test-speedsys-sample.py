"""Check passive Speedsys sampling across every relocated CPU-test pass."""
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR
from unicorn import x86_const as x


def main():
    root = Path(__file__).resolve().parents[1]
    image = (root / 'build/diagnostics/SPWHERE.COM').read_bytes()
    code = (root.parent / 'reference/software/speedsys/4.78/SPEEDSYS-code.bin').read_bytes()
    hook, old_vector, raw_flag = struct.unpack_from('<HHH', image, image.index(b'SPSM') + 4)
    registers = [getattr(x, 'UC_X86_REG_' + name) for name in
                 ('EAX', 'EBX', 'ECX', 'EDX', 'ESI', 'EDI', 'EBP', 'ESP', 'DS', 'ES', 'FS', 'GS')]
    cases = [(0x5BE0 - (34 - p), 0x3000, p, 0xA346, 0xC1) for p in range(1, 34)]
    for ip, stage in ((0x5C80, 0xC2), (0x5CC0, 0xC3), (0x5D90, 0xC4)):
        cases += [(ip - (34 - p), 0x3000, p, 0xA346, stage) for p in range(1, 34)]
    cases += [(0x5BA5, 0x3000, 33, 0xA346, 0xC0),
              (0x5DEC, 0x3000, 33, 0xA346, 0xC0),
              (0x1581, 0x3000, 33, 0xA346, 0xE0),
              (0x1200, 0xF000, 33, 0xA346, 0xE1),
              (0x1200, 0x2000, 33, 0xA346, 0xE2),
              (0x5C80, 0x3000, 0, 0xA346, 0xEF),
              (0x5C80, 0x3000, 34, 0xA346, 0xEF),
              (0x5C80, 0x3000, 33, 0x1111, None)]
    for raw, flags in ((r, f) for r in (0, 1) for f in (0x2, 0x46, 0x402)):
        for ip, segment, pass_number, caller, expected in cases:
            machine = Uc(UC_ARCH_X86, UC_MODE_16)
            machine.mem_map(0, 0x100000)
            machine.mem_write(0x10100, image)
            machine.mem_write(0x10000 + raw_flag, bytes([raw]))
            application = bytearray(code)
            struct.pack_into('<H', application, 0x5E02, pass_number)
            machine.mem_write(0x30000, bytes(application))
            machine.mem_write(0x10000 + old_vector, struct.pack('<HH', 0, 0xF000))
            for n, reg in enumerate(registers[:7]):
                machine.reg_write(reg, 0x12345678 + n * 0x1020304)
            for n, reg in enumerate(registers[8:]):
                machine.reg_write(reg, 0x4000 + n * 0x100)
            machine.reg_write(x.UC_X86_REG_CS, 0x1000)
            machine.reg_write(x.UC_X86_REG_SS, 0x7000)
            machine.reg_write(x.UC_X86_REG_ESP, 0xF000)
            machine.reg_write(x.UC_X86_REG_EFLAGS, flags)
            frame = struct.pack('<6H', caller, 0x3000, flags, ip, segment, flags | 0x200)
            machine.mem_write(0x7F000, frame)
            before = [machine.reg_read(r) for r in registers]
            posts, reached = [], []

            def stop(uc, address, size, unused):
                if address == 0xF0000:
                    reached.append(address)
                    uc.emu_stop()

            machine.hook_add(UC_HOOK_CODE, stop)
            machine.hook_add(UC_HOOK_INSN, lambda uc, port, size, value, unused: posts.append((port, value)), None, 1, 0, x.UC_X86_INS_OUT)
            machine.emu_start(0x10000 + hook, 0xFFFFF, count=1000)
            assert reached
            assert [machine.reg_read(r) for r in registers] == before
            assert machine.reg_read(x.UC_X86_REG_EFLAGS) == flags
            assert machine.mem_read(0x7F000, len(frame)) == frame
            assert machine.mem_read(0x30000, 65536) == application
            value = ip >> 8 if raw and segment == 0x3000 else expected
            assert posts == ([] if expected is None else [(0x80, value)]), (hex(ip), pass_number, posts)
    print(f'PASS: {len(cases) * 6} sampling cases; phase/page decoding, no application writes, full register/flags/frame preservation.')
    check_fault_capture(image, code, registers)


def check_fault_capture(image, code, registers):
    header = image.index(b'SPSM') + 4
    _, _, _, hook, old_vector, fault, snapshot, halt = struct.unpack_from('<8H', image, header)
    for flags in (0x2, 0x46, 0x402):
        for case in ('match', 'handler', 'installer', 'return', 'service'):
            machine = Uc(UC_ARCH_X86, UC_MODE_16)
            machine.mem_map(0, 0x100000)
            machine.mem_write(0x10100, image)
            application = bytearray(code)
            if case in ('handler', 'installer'):
                application[0x2767 if case == 'handler' else 0xA2D3] ^= 1
            machine.mem_write(0x30000, bytes(application))
            original_vector = struct.pack('<HH', 0, 0xF000)
            installed_vector = struct.pack('<HH', hook, 0x1000)
            machine.mem_write(0x10000 + old_vector, original_vector)
            machine.mem_write(0x84, installed_vector)
            for n, reg in enumerate(registers[:7]):
                machine.reg_write(reg, 0x12345678 + n * 0x1020304)
            machine.reg_write(x.UC_X86_REG_EAX, 0x12343100 if case == 'service' else 0x12343000)
            for n, reg in enumerate(registers[8:]):
                machine.reg_write(reg, 0x4000 + n * 0x100)
            machine.reg_write(x.UC_X86_REG_CS, 0x1000)
            machine.reg_write(x.UC_X86_REG_SS, 0x7000)
            machine.reg_write(x.UC_X86_REG_ESP, 0xF000)
            machine.reg_write(x.UC_X86_REG_EFLAGS, flags)
            frame = struct.pack('<3H', 0x24 if case == 'return' else 0x23, 0x3000, flags | 0x200)
            machine.mem_write(0x7F000, frame)
            before = [machine.reg_read(r) for r in registers]
            reached, posts = [], []

            def stop(uc, address, size, unused):
                if address == 0xF0000:
                    reached.append(address)
                    uc.emu_stop()

            machine.hook_add(UC_HOOK_CODE, stop)
            machine.hook_add(UC_HOOK_INSN, lambda uc, port, size, value, unused: posts.append((port, value)), None, 1, 0, x.UC_X86_INS_OUT)
            machine.emu_start(0x10000 + hook, 0xFFFFF, count=1000)
            assert reached, case
            assert [machine.reg_read(r) for r in registers] == before, case
            assert machine.reg_read(x.UC_X86_REG_EFLAGS) == flags, case
            assert machine.mem_read(0x7F000, 6) == frame, case
            if case == 'match':
                application[0x2767:0x276C] = b'\xEA' + struct.pack('<HH', fault, 0x1000)
            assert machine.mem_read(0x30000, 65536) == application, case
            assert machine.mem_read(0x84, 4) == (original_vector if case == 'match' else installed_vector), case
            assert posts == ([(0x80, 0xD4)] if case == 'match' else []), case

            if case != 'match':
                continue
            # Enter through the patched application handler with a CPU exception frame.
            machine.reg_write(x.UC_X86_REG_CS, 0x3000)
            fault_ip = 0x1604
            frame = struct.pack('<3H', fault_ip, 0x3000, flags | 0x200)
            machine.mem_write(0x7F000, frame)
            mode_calls, stopped = [], []

            def bios(uc, interrupt, unused):
                assert interrupt == 0x10
                mode_calls.append(uc.reg_read(x.UC_X86_REG_AX))
                # A real VGA entry may change registers and DF.
                uc.reg_write(x.UC_X86_REG_EAX, 0xDEADBEEF)
                uc.reg_write(x.UC_X86_REG_DS, 0)
                uc.reg_write(x.UC_X86_REG_EFLAGS, 0x402)

            def fault_stop(uc, address, size, unused):
                if address == 0x10000 + halt:
                    stopped.append(address)
                    uc.emu_stop()

            machine.hook_add(UC_HOOK_INTR, bios)
            machine.hook_add(UC_HOOK_CODE, fault_stop)
            machine.emu_start(0x32767, 0xFFFFF, count=20000)
            assert stopped and mode_calls == [3]
            expected = struct.pack('<4H8I3H', *reversed(before[8:]),
                                   before[5], before[4], before[6], before[7],
                                   before[1], before[3], before[2], before[0],
                                   fault_ip, 0x3000, flags | 0x200)
            assert machine.mem_read(0x10000 + snapshot, 46) == expected
            text = bytes(machine.mem_read(0xB8000, 2000))[::2].decode('ascii', errors='replace')
            assert 'DIVIDE FAULT captured' in text
            assert f'IP CS FLAGS: 1604 3000 {flags | 0x200:04X}' in text
            assert f'{before[0]:08X}' in text and f'{before[3]:08X}' in text
    print('PASS: 15 fault-hook cases, exact five-byte error-path patch, automatic unhook; 3 complete fault snapshots and text-mode reports.')


if __name__ == '__main__':
    main()
