"""Execute the retained VGA clear with the physical Chris failure's ES:DI."""
from pathlib import Path

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16
from unicorn import x86_const as x


def main():
    root = Path(__file__).resolve().parents[1]
    rom = (root / 'build/baios-presario800.bin').read_bytes()
    clear = rom[0x2354:0x235E]
    assert clear == bytes.fromhex('57 33c0 b98000 f3ab 5f c3')
    for segment, offset, wraps in ((0, 0xFF40, True), (0xFF4, 0, False)):
        cpu = Uc(UC_ARCH_X86, UC_MODE_16)
        cpu.mem_map(0, 0x100000)
        cpu.mem_write(0, b'\xa5' * 0x100000)
        cpu.mem_write(0xC2354, clear)
        cpu.reg_write(x.UC_X86_REG_CS, 0xC000)
        cpu.reg_write(x.UC_X86_REG_SS, 0x8000)
        cpu.reg_write(x.UC_X86_REG_SP, 0xFFF0)
        cpu.reg_write(x.UC_X86_REG_ES, segment)
        cpu.reg_write(x.UC_X86_REG_DI, offset)
        cpu.reg_write(x.UC_X86_REG_EFLAGS, 2)
        cpu.emu_start(0xC2354, 0xC235D, count=140)  # Stop before RET.
        assert cpu.reg_read(x.UC_X86_REG_IP) == 0x235D
        assert cpu.reg_read(x.UC_X86_REG_DI) == offset
        assert cpu.reg_read(x.UC_X86_REG_SP) == 0xFFF0
        expected_ivt = b'\0' * 64 + b'\xa5' * 960 if wraps else b'\xa5' * 1024
        assert cpu.mem_read(0, 1024) == expected_ivt
        expected_buffer = b'\0' * 192 + b'\xa5' * 64 if wraps else b'\0' * 256
        assert cpu.mem_read(0xFF40, 256) == expected_buffer
    print('PASS: original FF40 buffer corrupts IVT; normalized pointer preserves IVT.')


if __name__ == '__main__':
    main()
