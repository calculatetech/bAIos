"""Qualify the actual private executable delta and its compiled interval clamp."""
import hashlib
import importlib
import os
from pathlib import Path
import struct
import tempfile
from unicorn import Uc, UC_ARCH_X86, UC_MODE_64
from unicorn import x86_const as x

runtime = importlib.import_module('legacy-emulator')
ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT/'tools/deps/86box-b10408/86Box.exe'


def hashes(folder):
    return {p.relative_to(folder).as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
            for p in folder.rglob('*') if p.is_file()}


def code_page(data, address):
    pe=struct.unpack_from('<I',data,0x3C)[0]
    count=struct.unpack_from('<H',data,pe+6)[0]
    optional=struct.unpack_from('<H',data,pe+20)[0]
    for i in range(count):
        at=pe+24+optional+40*i
        _,rva,size,raw=struct.unpack_from('<IIII',data,at+8)
        if rva<=address and address+4096<=rva+size:
            offset=raw+address-rva
            return data[offset:offset+4096]
    raise AssertionError('Qualified code page is missing')


def execute(data, mapping_base, requested_base, mapping_end, requested_end, padding=False, specialized=False):
    cpu=Uc(UC_ARCH_X86,UC_MODE_64)
    page=0x40B000 if specialized else 0x413000
    cpu.mem_map(page,4096)
    cpu.mem_write(page,code_page(data,page))
    cpu.mem_map(0x80000000,0x4000)
    registers=[getattr(x,'UC_X86_REG_'+n) for n in
               ('RAX','RBX','RCX','RDX','RSI','RDI','RBP','RSP','R8','R9','R10','R11','R12','R13','R14','R15')]
    for i,reg in enumerate(registers):cpu.reg_write(reg,0x12345600+i)
    for reg,value in ((x.UC_X86_REG_RSP,0x80001000),(x.UC_X86_REG_R9,mapping_base),
                      (x.UC_X86_REG_RCX,mapping_end),(x.UC_X86_REG_RSI,requested_end),
                      (x.UC_X86_REG_EFLAGS,0xAD7)):
        cpu.reg_write(reg,value)
    if specialized:
        for reg,value in ((x.UC_X86_REG_RCX,mapping_base),(x.UC_X86_REG_RDX,requested_base),
                          (x.UC_X86_REG_R11,mapping_end),(x.UC_X86_REG_R12,requested_end)):
            cpu.reg_write(reg,value)
    cpu.mem_write(0x80001000,b'\xA5'*0x200)
    cpu.mem_write(0x800010C0,struct.pack('<Q',requested_base))
    before={reg:cpu.reg_read(reg) for reg in registers}
    flags=cpu.reg_read(x.UC_X86_REG_EFLAGS)
    stack=bytes(cpu.mem_read(0x80001000,0x200))
    entry,end=((0x40BD94,0x40BDAA) if padding else (0x40BA57,0x40BA5E)) if specialized else ((0x413B63,0x413B80) if padding else (0x413241,0x413248))
    cpu.emu_start(entry,end,count=100)
    assert cpu.reg_read(x.UC_X86_REG_RIP)==end
    after={reg:cpu.reg_read(reg) for reg in registers}
    assert bytes(cpu.mem_read(0x80001000,0x200))==stack
    if padding:
        assert after==before and cpu.reg_read(x.UC_X86_REG_EFLAGS)==flags
    else:
        changed=(x.UC_X86_REG_RCX,x.UC_X86_REG_R11) if specialized else (x.UC_X86_REG_R9,x.UC_X86_REG_RCX,x.UC_X86_REG_R10)
        for reg,value in before.items():
            if reg not in changed:assert after[reg]==value
    start_reg,end_reg=(x.UC_X86_REG_RCX,x.UC_X86_REG_R11) if specialized else (x.UC_X86_REG_R9,x.UC_X86_REG_RCX)
    return after[start_reg],after[end_reg],cpu.reg_read(x.UC_X86_REG_EFLAGS)


def main():
    original=SOURCE.read_bytes()
    before=hashes(SOURCE.parent)
    scratch=ROOT/'presario-800/build/tmp';scratch.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='legacy-emulator-',dir=scratch) as name:
        work=Path(name)
        target=runtime.prepare(SOURCE,work/'qualified')
        corrected=target.read_bytes()
        assert hashlib.sha256(corrected).hexdigest()=='7408b232268ea7f600a2d55f923248d57d543fe54a5ec51145e0dff2081d2e07'
        assert len(original)==len(corrected)
        cursor=0
        for offset,old,new in runtime.PATCHES:
            assert corrected[cursor:offset]==original[cursor:offset]
            assert corrected[offset:offset+len(new)]==new
            cursor=offset+len(new)
        assert corrected[cursor:]==original[cursor:]
        copied=hashes(target.parent)
        assert set(copied)==set(before)
        for path,digest in before.items():
            if path!='86Box.exe':assert copied[path]==digest,path
        # Start and end contrasts vary independently, rather than as a product.
        cases=[(0xC0000,start,0x100000,0x100000) for start in (0xB0000,0xC0000,0xFC000)]
        cases += [(0xC0000,0xD0000,end,0x100000) for end in (0xE0000,0x100000,0x120000)]
        for specialized in (False,True):
            for map_base,req_base,map_end,req_end in cases:
                actual=execute(corrected,map_base,req_base,map_end,req_end,specialized=specialized)
                displaced=execute(original,map_base,req_base,map_end,req_end,specialized=specialized)
                assert actual[:2]==(max(map_base,req_base),min(map_end,req_end))
                assert actual[2]==displaced[2], 'Displaced end-comparison flags changed'
            assert execute(original,0xC0000,0xFC000,0x100000,0x100000,specialized=specialized)[0]!=0xFC000
            assert execute(corrected,0xC0000,0xFC000,0x100000,0x100000,padding=True,specialized=specialized)==execute(original,0xC0000,0xFC000,0x100000,0x100000,padding=True,specialized=specialized)
        other=Path(os.environ['LOCALAPPDATA'])/'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe'
        other_digest=hashlib.sha256(other.read_bytes()).hexdigest()
        assert other_digest=='dc236a27e5fccb07d20a60f471e5c1252fbcd82d0505542dd8e4a15c1689e885'
        try:runtime.prepare(other,work/'unsupported')
        except ValueError:pass
        else:raise AssertionError('Different genuine emulator was accepted')
        assert not (work/'unsupported').exists()
        assert hashlib.sha256(other.read_bytes()).hexdigest()==other_digest
    assert hashes(SOURCE.parent)==before
    print('Qualified PE: both compiled owners, twelve independent interval cases, original counterexamples, live padding, exact delta, companions and original inputs PASS',flush=True)


if __name__=='__main__':main()
