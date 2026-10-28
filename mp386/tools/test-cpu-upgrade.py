"""Execute CPU holdoff and FPU policy; synthetic CPU flags are not hardware proof."""
import argparse
import json
import struct
import sys
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import (Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE,
                     UC_HOOK_INSN, UC_HOOK_MEM_WRITE)
from unicorn import x86_const as x

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.tools.ram_proof import Listing


def check(image):
    image = Path(image)
    raw, listing = image.read_bytes(), Listing(image.with_suffix('.lst'))
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    begin = listing.symbol('.cpu_holdoff_begin', 'startup')
    end = listing.symbol('.cpu_holdoff_end', 'startup')
    native = list(decoder.disasm(raw[begin:end], begin))
    assert not any(i.mnemonic.startswith(('push', 'pop', 'call')) for i in native)
    expected = [(0xC0, 0), (0xC1, 0)] + [
        (index, 15 if index == 0xC6 else 0) for index in range(0xC4, 0xD0)]
    rows = []

    def machine(cyrix):
        u = Uc(UC_ARCH_X86, UC_MODE_16)
        u.mem_map(0, 0x100000)
        u.mem_write(0xF0000, raw)
        u.reg_write(x.UC_X86_REG_CS, 0xF000)
        u.reg_write(x.UC_X86_REG_SS, 0)
        u.reg_write(x.UC_X86_REG_SP, 0x7FFE)
        u.reg_write(x.UC_X86_REG_EFLAGS, 2)
        u.mem_write(0x7FFE, struct.pack('<H', 0xFF00))
        def signature(cpu, address, size, unused):
            data = bytes(cpu.mem_read(address, size))
            if data == b'\x9f' and bytes(cpu.mem_read(address-2, 2)) == b'\xf6\xf3':
                flags = cpu.reg_read(x.UC_X86_REG_EFLAGS)
                cpu.reg_write(x.UC_X86_REG_EFLAGS, (flags & ~0xD5) | (0 if cyrix else 4))
        u.hook_add(UC_HOOK_CODE, signature)
        return u

    for cyrix in (False, True):
        u, io, writes, flushes = machine(cyrix), [], [], []
        u.reg_write(x.UC_X86_REG_SS, 0xF000)
        registers = {x.UC_X86_REG_ESP:0xCAFE1234, x.UC_X86_REG_ECX:0xABCD6789,
                     x.UC_X86_REG_EDX:0x76543210, x.UC_X86_REG_ESI:0x13572468,
                     x.UC_X86_REG_EDI:0x24681357, x.UC_X86_REG_EBP:0x87654321}
        for reg, value in registers.items(): u.reg_write(reg, value)
        u.hook_add(UC_HOOK_INSN, lambda cpu,p,s,v,d:io.append((p,s,v)), None,1,0,x.UC_X86_INS_OUT)
        u.hook_add(UC_HOOK_MEM_WRITE, lambda cpu,a,p,s,v,d:writes.append((p,s,v)))
        def opcode(cpu, address, size, unused):
            if bytes(cpu.mem_read(address,size)) == b'\x0f\x08':
                assert cyrix, 'INVD on386'
                flushes.append(address)
        u.hook_add(UC_HOOK_CODE, opcode)
        u.emu_start(0xF0000+begin, 0xF0000+end, count=1000)
        assert u.reg_read(x.UC_X86_REG_IP) == end
        assert not writes, writes
        for reg, value in registers.items(): assert u.reg_read(reg) == value
        pairs = [(io[i][2], io[i+1][2]) for i in range(0,len(io),2)]
        assert all((p,s) == (0x22 if i%2 == 0 else 0x23,1) for i,(p,s,v) in enumerate(io))
        assert pairs == (expected if cyrix else []), pairs
        assert len(flushes) == (2 if cyrix else 0)
        rows.append(dict(cyrix=cyrix, CCR_writes=pairs, invalidations=len(flushes), no_RAM_writes=True))

        u = machine(cyrix)
        u.reg_write(x.UC_X86_REG_DS,0xF000)
        u.reg_write(x.UC_X86_REG_ES,0xB800)
        u.reg_write(x.UC_X86_REG_FS,0x9E00)
        u.emu_start(0xF0000+listing.symbol('post_ui_cache'),0xFFF00,count=5000)
        assert u.reg_read(x.UC_X86_REG_IP) == 0xFF00
        label = bytes(u.mem_read(0xB8000+3*160+24*2,24))[::2].decode().strip()
        assert label == ('Disabled' if cyrix else 'Not present'),label
        rows[-1]['L1_display'] = label

    for forced_absent, fitted in ((True,False),(True,True),(False,False),(False,True)):
        u, ports, x87 = machine(False), {0x21:0xFF, 0xA1:0}, []
        index, board = [0], {}
        u.mem_write(0x410,b'\xff\xff')
        u.reg_write(x.UC_X86_REG_CR0,0x4000001E)
        u.reg_write(x.UC_X86_REG_EAX,0x12345678)
        u.reg_write(x.UC_X86_REG_BP,0x4321)
        u.reg_write(x.UC_X86_REG_DS,0x2345)
        def port_in(cpu,p,s,d):
            if p == 0x5F: return 0x20 if forced_absent else 0
            assert p in ports, hex(p)
            return ports[p]
        def port_out(cpu,p,s,v,d):
            if p == 0x5A: index[0] = v
            elif p == 0x5B: board[index[0]] = v
            else:
                assert p in (0x21,0xA1,0xF0),hex(p)
                ports[p] = v
        def coprocessor(cpu,address,size,d):
            op = next(decoder.disasm(bytes(cpu.mem_read(address,size)),address))
            if op.mnemonic not in ('fninit','fnstsw','fnstcw'): return
            assert not forced_absent, 'x87 instruction despite absent switch'
            x87.append(op.mnemonic)
            if fitted and op.mnemonic != 'fninit':
                bp = cpu.reg_read(x.UC_X86_REG_BP)
                cpu.mem_write(bp+(2 if op.mnemonic == 'fnstcw' else 0),
                              struct.pack('<H',0x37F if op.mnemonic == 'fnstcw' else 0))
            cpu.reg_write(x.UC_X86_REG_IP,(address-0xF0000+size)&0xFFFF)
        u.hook_add(UC_HOOK_INSN,port_in,None,1,0,x.UC_X86_INS_IN)
        u.hook_add(UC_HOOK_INSN,port_out,None,1,0,x.UC_X86_INS_OUT)
        u.hook_add(UC_HOOK_CODE,coprocessor)
        u.emu_start(0xF0000+listing.symbol('init_fpu'),0xFFF00,count=1000)
        assert u.reg_read(x.UC_X86_REG_IP) == 0xFF00
        present = fitted and not forced_absent
        assert bool(int.from_bytes(u.mem_read(0x410,2),'little')&2) == present
        assert board[0x90] == int(not present), board
        assert bool(ports[0xA1]&0x20) != present
        assert u.reg_read(x.UC_X86_REG_EAX) == 0x12345678
        assert u.reg_read(x.UC_X86_REG_BP) == 0x4321
        assert u.reg_read(x.UC_X86_REG_DS) == 0x2345
        assert u.reg_read(x.UC_X86_REG_SP) == 0x8000
        assert u.reg_read(x.UC_X86_REG_CR0) == 0x40000010
        rows.append(dict(forced_absent=forced_absent,fitted=fitted,present=present,x87=x87,
                         control90=board[0x90],stack_preserved=True))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,required=True)
    args = parser.parse_args()
    rows = check(args.image)
    (args.image.parent/'cpu-upgrade.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(f'PASS CPU holdoff and FPU policy: {len(rows)} cases')
