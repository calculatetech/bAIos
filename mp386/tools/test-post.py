"""Check MP386's common POST lifecycle and board cache adapter."""
import argparse
import importlib
import json
from pathlib import Path
import struct

from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x
from fixture import PORT

cache = importlib.import_module('test-cache')
memory = importlib.import_module('test-memory')
port = importlib.import_module('test-port')
shadow = importlib.import_module('test-shadow')


def activation(image):
    m = cache.configured(image)
    m.cpu.mem_write(0x413,struct.pack('<H',632))
    stop = m.symbol('core_verify_initialization')
    sizes = ((0,3),(2048,3),(3072,0x23),(4096,0x23),(5120,0x33),
             (7168,0x43),(9216,0x53),(11264,0x63),(13312,0x6B),(15232,0x6B))
    def activate(expected):
        m.cpu.mem_write(0x9F01F,b'\x07')
        initial = m.controls[0xE2] = 0xAC
        m.io.clear()
        shadow.invoke(m,'mp_cache_enable')
        index, writes = None, []
        for direction,port,size,value in m.io:
            if direction == 'out' and port == 0x5A:
                index = value
            if direction == 'out' and port == 0x5B:
                writes.append((index,value))
        assert writes == [(0xE2,initial|2),(0xE0,expected),(0xE2,initial&~2)],writes
        assert m.controls[0xE0] == expected and m.controls[0xE2] == initial
        assert m.index == 0x0D and m.cpu.mem_read(0x9F01F,1) == b'\x0E'
    for extended,expected in sizes:
        m.cpu.mem_write(0x9E0D0,struct.pack('<H',extended))
        activate(expected)
    for base,expected in ((256,0x69),(512,0x6A),(632,0x6B)):
        m.cpu.mem_write(0x413,struct.pack('<H',base))
        m.cpu.mem_write(0x9E0D0,struct.pack('<H',15232))
        for diagnostic in (0,0x40,0x80,0xC0,0x58):
            m.cmos[0x0E] = diagnostic
            m.cmos[0x30:0x32] = b'\x00\x00'  # A stale CMOS count cannot choose policy.
            activate(expected)
            assert m.cmos[0x0E] == diagnostic
            assert not any(row[1] == 0x71 for row in m.io)
            assert m.index == 0x0D and m.cpu.mem_read(0x9F01F,1) == b'\x0E'
    return dict(memory_policy_cases=len(sizes),CMOS_independence_cases=15,
                authoritative_size=True,NMI_restored=True)


def data_failure(image):
    m = cache.configured(image)
    maps = dict(m.maps)
    latch = m.speaker
    failed,hook = cache.qualification_fault(m,'helper0',lambda addr: m.symbol(f'oem_cache_{addr:04X}'))
    shadow.invoke(m,'cache_test')
    m.cpu.hook_del(hook)
    assert failed and m.maps == maps
    assert m.controls[0xE0] == 0 and not m.controls[0xE2]&2
    assert m.cpu.mem_read(0x9F01F,1) == b'\x13'
    assert m.speaker == latch and m.index == 0x0D
    shadow.invoke(m,'mp_cache_enable')
    assert m.controls[0xE0] == 0
    return dict(data_failure_returns=True,displaced_maps_restored=True,
                cache_stays_off=True,stack_flags_NMI_restored=True)


def memory_services(image):
    m = cache.configured(image)
    m.cpu.mem_write(0x40E,struct.pack('<H',0x9E00))
    m.cpu.mem_write(0x9E0D0,struct.pack('<H',15232))
    stop = m.symbol('core_verify_initialization')
    for function in (0xE820,0x8800):
        m.cpu.mem_write(0x6FFA,struct.pack('<3H',stop,0xF000,0x246))
        memory.window(m,m.symbol('int15'),stop,
                      ((x.UC_X86_REG_EAX,function),(x.UC_X86_REG_EDX,0x534D4150),
                       (x.UC_X86_REG_ECX,24),(x.UC_X86_REG_EBX,0),
                       (x.UC_X86_REG_ES,0x2000),(x.UC_X86_REG_DI,0x100),
                       (x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x6FFA)))
        assert bool(m.cpu.reg_read(x.UC_X86_REG_EFLAGS)&1) == (function == 0xE820)
        if function == 0x8800:
            assert m.cpu.reg_read(x.UC_X86_REG_AX) == 15232
        assert m.cpu.reg_read(x.UC_X86_REG_SP) == 0x7000
    return dict(E820_recovery_removed=True,AH88_extended_KiB=15232)


def presentation(image):
    m = cache.configured(image)
    stop = m.symbol('core_verify_initialization')
    for status,text in ((1,'Disabled'),(3,'32 KB'),(7,'32 KB'),(14,'32 KB'),(19,'Cache test failed')):
        m.cpu.mem_write(0x9F01F,bytes((status,)))
        m.cpu.mem_write(0x6FFE,struct.pack('<H',stop))
        memory.window(m,m.symbol('post_cache_name'),stop,
                      ((x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x6FFE),
                       (x.UC_X86_REG_FS,0x9E00)))
        address = 0xF0000+m.cpu.reg_read(x.UC_X86_REG_SI)
        assert bytes(m.cpu.mem_read(address,32)).split(b'\0')[0].decode() == text
    failed = cache.boots(image,fault='helper0')
    return dict(fixed_capacity_KB=32,status_cases=5,external_data_failure_boots=failed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,default=PORT/'build/baios-mp386.bin')
    args = parser.parse_args()
    results = {}
    for name,check in (('activation',activation),('data_failure',data_failure),
                       ('memory_services',memory_services),('presentation',presentation),('boots',cache.boots),
                       ('RAM',port.ram_checks)):
        results[name] = check(args.image.resolve())
        print('PASS',name,json.dumps(results[name]),flush=True)
    folder = PORT/'build/tests/results'
    folder.mkdir(exist_ok=True)
    (folder/'post.json').write_text(json.dumps(results,indent=2)+'\n')
