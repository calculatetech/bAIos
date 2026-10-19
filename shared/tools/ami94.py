"""Bounded native decoding of the 128 KiB AMIBIOSC 10/10/94 format.

Directory placement and native output signatures are checked. This does not
establish an original module checksum or hardware compatibility.
"""
import hashlib
import struct


def decode(raw):
    from unicorn import Uc, UC_ARCH_X86, UC_MODE_16
    from unicorn import x86_const as x

    if len(raw) != 0x20000 or not raw.startswith(b'AMIBIOSC10/10/94'):
        raise ValueError('Unsupported AMI94 image format')
    count = struct.unpack_from('<H',raw,0x10)[0]
    if not 1 <= count <= 7 or 0x12+count*4 > 0x30:
        raise ValueError('Invalid AMI94 directory bounds')
    entries = [struct.unpack_from('<BBH',raw,0x12+i*4) for i in range(count)]
    directory = {ident:(page,offset) for ident,page,offset in entries}
    if len(directory) != count or not {0,2,3} <= directory.keys():
        raise ValueError('Invalid AMI94 core module directory')
    base = directory[3][1]
    if base % 16 or not raw[base:base+8] == b'AMIBIOS ' or base+0x1900 > len(raw):
        raise ValueError('Invalid native AMI94 decompressor placement')
    modules = {}
    main = bytearray(0x10000)
    for ident,page,offset in entries:
        item = {'input_offset':offset,'directory_destination':page << 8}
        modules[ident] = item
        if ident & 0x80 or ident == 3:
            continue
        if not 0x30 <= offset <= base-8:
            raise ValueError('Invalid AMI94 compressed record offset')
        packed,expanded = struct.unpack_from('<II',raw,offset)
        if packed < 8 or offset+packed > base or not 0 < expanded <= 0x10000:
            raise ValueError('Invalid AMI94 compressed record bounds')
        cpu = Uc(UC_ARCH_X86,UC_MODE_16)
        cpu.mem_map(0,0x200000)
        cpu.mem_write(0xE0000,raw)
        for reg,value in ((x.UC_X86_REG_CS,0xE000+base//16),
                          (x.UC_X86_REG_DS,0x5000),(x.UC_X86_REG_SS,0x7000),
                          (x.UC_X86_REG_SP,0xFFE0)):
            cpu.reg_write(reg,value)
        cpu.mem_write(0x7FFE0,struct.pack('<HHHHH',0x1900,offset,0xE000,0,0x8000))
        cpu.emu_start(0xE0000+base+0x60,0xE0000+base+0x1900,count=15000000)
        if cpu.reg_read(x.UC_X86_REG_IP) != 0x1900:
            raise ValueError('Native AMI94 decompressor exceeded its instruction budget')
        data = bytes(cpu.mem_read(0x80000,expanded))
        item.update(packed=packed,expanded=expanded,data=data,
                    sha256=hashlib.sha256(data).hexdigest())
        if ident in (0,2):
            destination = page << 8
            if destination+expanded > len(main):
                raise ValueError('Invalid AMI94 core output bounds')
            main[destination:destination+expanded] = data
    if (main[:8] != b'AMIBIOSP' or main[0x8000:0x8008] != b'AMIBIOS '
            or main[0xFFF0:0xFFF5] != raw[0x1FFF0:0x1FFF5]):
        raise ValueError('Native AMI94 core signatures or reset vector do not match')
    return bytes(main),modules
