"""Check real IRQ1/INT16 codes and BIOS descriptors consumed by Windows."""
import functools
import importlib
import struct

setup = importlib.import_module('test-setup')
rtc = importlib.import_module('test-rtc')
rtc.symbol = functools.cache(rtc.symbol)
x = rtc.x


def invoke(model, ax, cx=0, vector=0x16, flags=0x202):
    cpu = model.cpu
    for reg, value in ((x.UC_X86_REG_CS, 0x9000), (x.UC_X86_REG_IP, 0),
                       (x.UC_X86_REG_SS, 0), (x.UC_X86_REG_SP, 0x7000),
                       (x.UC_X86_REG_AX, ax), (x.UC_X86_REG_CX, cx),
                       (x.UC_X86_REG_DX, 0xBEEF), (x.UC_X86_REG_EFLAGS, flags)):
        cpu.reg_write(reg, value)
    cpu.mem_write(0x90000, bytes((0xCD, vector, 0x90)))
    if vector == 0x16:
        for index, name in enumerate(('EAX','EBX','ECX','EDX','ESI','EDI','EBP','ESP')):
            reg = getattr(x, 'UC_X86_REG_'+name)
            cpu.reg_write(reg, (0xA100+index)<<16 | cpu.reg_read(reg)&65535)
        for name, value in (('DS',0x2345),('ES',0x3456),('FS',0x4567),('GS',0x5678)):
            cpu.reg_write(getattr(x, 'UC_X86_REG_'+name), value)
        before = {name:cpu.reg_read(getattr(x,'UC_X86_REG_'+name)) for name in rtc.REGS}
    cpu.emu_start(0x90000, 0x90002, count=100000)
    assert cpu.reg_read(x.UC_X86_REG_IP) == 2
    assert cpu.reg_read(x.UC_X86_REG_SP) == 0x7000
    assert cpu.reg_read(x.UC_X86_REG_DX) == 0xBEEF
    if vector == 0x16:
        for name, value in before.items():
            result = cpu.reg_read(getattr(x,'UC_X86_REG_'+name))
            assert (result>>16 == value>>16 if name=='EAX' else result==value), (name,value,result)
    return cpu.reg_read(x.UC_X86_REG_AX), cpu.reg_read(x.UC_X86_REG_EFLAGS)


def main():
    model = setup.Setup()
    model.cpu.mem_write(0x49E, b'\0')  # External runtime context, not POST.
    model.cpu.mem_write(0x496, b'\x10')
    model.cpu.mem_write(0x4A8, bytes.fromhex('16 FC 00 C0'))  # VGA save-table pointer.
    for function in (0x0100, 0x1100):
        for flags in (2, 3, 0x402, 0x403, 0x202, 0x603):
            result = invoke(model, function, flags=flags)[1]
            assert result & 0x241 == 0x240, 'Empty poll must enable IF and set ZF/clear CF like OEM'
            assert result & 0x400 == flags & 0x400
            assert invoke(model, 0x0500, 0x1E61)[0] == 0x0500
            result = invoke(model, function, flags=flags)
            assert result[0] == 0x1E61 and result[1] & 0x241 == 0x201
            assert result[1] & 0x400 == flags & 0x400
            assert invoke(model, 0)[0] == 0x1E61  # Poll must not consume the key.
    print('INT16 AH01/AH11 OEM IF/ZF/CF contract and DF preservation: PASS')
    for scan, expected in ((2, 0x7800), (0x0B, 0x8100), (0x0C, 0x8200),
                           (0x0D, 0x8300), (0x4A, 0x4A00)):
        model.scans([0x38, scan, scan | 128, 0xB8])
        assert invoke(model, 0x1000)[0] == expected
        assert invoke(model, 0x1100)[1] & 64
    for scan in (0x47, 0x48, 0x49, 0x4B, 0x4D, 0x4F, 0x50, 0x51, 0x52, 0x53):
        for function, ascii_code in ((0, 0), (0x10, 0xE0)):
            model.scans([0xE0, scan, 0xE0, scan | 128])
            assert invoke(model, function << 8)[0] == scan << 8 | ascii_code
    for scan, normal, enhanced in ((0x1C, 0x1C0D, 0xE00D),
                                   (0x35, 0x352F, 0xE02F)):
        for function, expected in ((0, normal), (0x10, enhanced)):
            model.scans([0xE0, scan, 0xE0, scan | 128])
            assert invoke(model, function << 8)[0] == expected
    model.scans([0x38, 0xE0, 0x38])
    assert invoke(model, 0x1200)[0] == 0x0A08
    model.scans([0xB8])
    assert invoke(model, 0x1200)[0] == 0x0808
    model.scans([0xE0, 0xB8])
    assert invoke(model, 0x1200)[0] == 0
    model.scans([0x1D, 0xE0, 0x1D])
    assert invoke(model, 0x1200)[0] == 0x0504
    model.scans([0x9D])
    assert invoke(model, 0x1200)[0] == 0x0404
    model.scans([0xE0, 0x9D])
    assert invoke(model, 0x1200)[0] == 0
    assert model.cpu.mem_read(0x496, 1) == b'\x10'
    assert invoke(model, 0x0900)[0] == 0x0920
    assert invoke(model, 0x0A37)[0] == 0x0A37
    assert invoke(model, 0x0500, 0x4BE0)[0] == 0x0500
    assert invoke(model, 0x1100)[0] == 0x4BE0
    assert invoke(model, 0x0000)[0] == 0x4B00
    for index in range(15):
        assert invoke(model, 0x0500, 0x1E61)[0] == 0x0500
    tail = bytes(model.cpu.mem_read(0x41C, 2))
    assert invoke(model, 0x0500, 0x3062)[0] == 0x0501
    assert bytes(model.cpu.mem_read(0x41C, 2)) == tail
    for index in range(15):
        assert invoke(model, 0x1000)[0] == 0x1E61
    assert invoke(model, 0xC037, vector=0x15)[0] == 0
    pointer = model.cpu.reg_read(x.UC_X86_REG_ES) * 16 + model.cpu.reg_read(x.UC_X86_REG_BX)
    descriptor = bytes(model.cpu.mem_read(pointer, 10))
    assert descriptor == bytes.fromhex('08 00 FC 01 00 74 40 00 00 00')
    assert bytes(model.cpu.mem_read(0x4A8, 4)) == bytes.fromhex('16 FC 00 C0')
    for segment in (0x9FC0, 0x8FC0):
        model.cpu.mem_write(0x40E, struct.pack('<H', segment))
        ax, flags = invoke(model, 0xC137, vector=0x15)
        assert not flags & 1, 'Advertised EBDA must be discoverable through INT15/C1'
        assert ax == 0xC137 and model.cpu.reg_read(x.UC_X86_REG_ES) == segment
    print('Real IRQ1 codes, enhanced/legacy INT16, modifiers, buffer full, C0/C1: PASS')
    windows_ebios()


def windows_ebios():
    """Run the retained Windows EBIOS real initializer against actual BIOS owners."""
    backup = rtc.ROOT / 'build/presario800-card.vhd'
    if not backup.exists():
        print('Retained Windows EBIOS fixture absent: skipped')
        return
    fat = importlib.import_module('memory-fixture').Fat16(backup)
    try:
        image = fat.read('WINDOWS/SYSTEM/WIN386.EXE')
    finally:
        fat.vhd.close()
    code = image[0x37800:0x37900]
    assert code[:34] == bytes.fromhex(
        'F7 C3 01 00 0F 85 94 00 F9 B4 C0 CD 15 72 5F 0A E4 75 5B '
        '26 F6 47 05 04 74 54 33 C0 8E C0 B4 C1 CD 15')
    model = setup.Setup()
    cpu = model.cpu
    cpu.mem_write(0x12 * 4, struct.pack('<HH', rtc.symbol('int12'), 0xF000))
    cpu.mem_write(0x90000, code)
    cpu.mem_write(0x7000, struct.pack('<H', 0xFFF0))
    for reg, value in ((x.UC_X86_REG_CS, 0x9000), (x.UC_X86_REG_IP, 0),
                       (x.UC_X86_REG_DS, 0x9000), (x.UC_X86_REG_SS, 0),
                       (x.UC_X86_REG_SP, 0x7000), (x.UC_X86_REG_BX, 0),
                       (x.UC_X86_REG_EDX, 0), (x.UC_X86_REG_EFLAGS, 0x202)):
        cpu.reg_write(reg, value)
    cpu.emu_start(0x90000, 0x9FFF0, count=100000)
    assert cpu.reg_read(x.UC_X86_REG_IP) == 0xFFF0
    assert cpu.reg_read(x.UC_X86_REG_AX) == 0  # Device_Load_Ok.
    assert cpu.reg_read(x.UC_X86_REG_EDX) == 0x00C0009F
    table = 0x90000 + cpu.reg_read(x.UC_X86_REG_BX)
    assert bytes(cpu.mem_read(table, 4)) == struct.pack('<HH', 0x9F, 0)
    print('Original WIN386 EBIOS initialization and page exclusion: PASS')


if __name__ == '__main__':
    main()
