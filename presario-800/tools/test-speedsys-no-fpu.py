"""Check the one-byte Speedsys diagnostic patch and its register contract."""
import hashlib
from pathlib import Path
import struct

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN
from unicorn import x86_const as x


def main():
    root = Path(__file__).resolve().parents[1]
    image = (root / "build/diagnostics/SPNOFPU.COM").read_bytes()
    code = (root.parent / "reference/software/speedsys/4.78/SPEEDSYS-code.bin").read_bytes()
    assert hashlib.sha256(code).hexdigest() == "b43f9ed7f8efa0f11561b3213b82c9727571fafd2fec1695b8cbfd0fe816eee0"
    header = image.index(b"SPNF") + 4
    hook, old_vector = struct.unpack_from("<HH", image, header)
    registers = [x.UC_X86_REG_EAX, x.UC_X86_REG_EBX, x.UC_X86_REG_ECX,
                 x.UC_X86_REG_EDX, x.UC_X86_REG_ESI, x.UC_X86_REG_EDI,
                 x.UC_X86_REG_EBP, x.UC_X86_REG_ESP, x.UC_X86_REG_DS,
                 x.UC_X86_REG_ES, x.UC_X86_REG_FS, x.UC_X86_REG_GS]
    for flags in (0x2, 0x46, 0x402):
        for case in ("match", "version", "return", "service"):
            machine = Uc(UC_ARCH_X86, UC_MODE_16)
            machine.mem_map(0, 0x100000)
            machine.mem_write(0x10100, image)
            application = bytearray(code)
            if case == "version":
                application[0x5BD4] ^= 1
            machine.mem_write(0x30000, bytes(application))
            original_vector = struct.pack("<HH", 0, 0xF000)
            machine.mem_write(0x10000 + old_vector, original_vector)
            installed_vector = struct.pack("<HH", hook, 0x1000)
            machine.mem_write(0x84, installed_vector)
            for n, reg in enumerate(registers[:7]):
                machine.reg_write(reg, 0x12345678 + n * 0x1020304)
            machine.reg_write(x.UC_X86_REG_EAX, 0x12343000 if case != "service" else 0x12343100)
            for n, reg in enumerate(registers[8:]):
                machine.reg_write(reg, 0x4000 + n * 0x100)
            machine.reg_write(x.UC_X86_REG_CS, 0x1000)
            machine.reg_write(x.UC_X86_REG_SS, 0x7000)
            machine.reg_write(x.UC_X86_REG_ESP, 0xF000)
            machine.reg_write(x.UC_X86_REG_EFLAGS, flags)
            frame = struct.pack("<HHH", 0x24 if case == "return" else 0x23, 0x3000, flags | 0x200)
            machine.mem_write(0x7F000, frame)
            before = [machine.reg_read(r) for r in registers]
            posts = []
            reached = []

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
            if case == "match":
                application[0x5BD3] = 0xEB
            assert machine.mem_read(0x30000, 65536) == application, case
            assert machine.mem_read(0x84, 4) == (original_vector if case == "match" else installed_vector), case
            assert posts == ([(0x80, 0xD0)] if case == "match" else []), case
    print("PASS: 12 hook cases; one-byte patch, mismatch rejection, register/flags/frame preservation, automatic unhook.")


if __name__ == "__main__":
    main()
