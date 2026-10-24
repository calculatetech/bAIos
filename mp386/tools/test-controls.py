"""Compare assembled MP386 board windows with unchanged OEM instructions."""
import hashlib
import json
import argparse
import sys
from pathlib import Path
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

class Controls:
    def __init__(self, raw, switches=0x80, kind=1, strap49=0, revision=0x1000, et=True):
        self.cpu=Uc(UC_ARCH_X86, UC_MODE_16)
        self.cpu.mem_map(0,0x100000)
        self.cpu.mem_write(0xF0000, raw)
        self.ti={0x800:revision|0x200}
        self.ti_index=0
        self.board={0xE6:0x5A,0xE1:0xA5,0xE2:0xFF}
        self.board_index=0
        self.switches,self.kind,self.strap49=switches,kind,strap49
        self.rtc_index=0
        self.nv={0x2FE:1,0x2CF:kind}
        self.nv_phase='idle'
        self.nv_address=0
        self.readback_fault = None
        self.trace=[]
        self.writes=[]
        self.stopped=False
        self.cpu.hook_add(UC_HOOK_INSN,self.port_in,None,1,0,x.UC_X86_INS_IN)
        self.cpu.hook_add(UC_HOOK_INSN,self.port_out,None,1,0,x.UC_X86_INS_OUT)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE,lambda u,a,p,s,v,d:self.writes.append((p,s,v)))
        self.cpu.reg_write(x.UC_X86_REG_CR0,0x10 if et else 0)
    def port_in(self,cpu,port,size,unused):
        if port==0x24: value=self.ti.get(self.ti_index,0)
        elif port==0x5E: value=1 if self.kind==1 else 4 if self.kind==2 else 0
        elif port==0x5F: value=self.switches
        elif port==0x49: value=self.strap49
        elif port==0x5B: value=self.board.get(self.board_index,0)
        elif port==0x71: value=0xC0 if self.rtc_index==0x0E else 0
        elif port==0x48:
            if self.nv_phase=='data':
                value=self.nv.get(self.nv_address,0)
                self.nv_phase='ack'
            else:
                value=0
                self.nv_phase='handshake'
        else: raise AssertionError(('unexpected input',hex(port)))
        if port == 0x24 and self.ti_index == self.readback_fault:
            value ^= 1
        self.trace.append(('in',port,size,value))
        return value
    def port_out(self,cpu,port,size,value,unused):
        self.trace.append(('out',port,size,value))
        if port==0x26: self.ti_index=value
        elif port==0x24: self.ti[self.ti_index]=value
        elif port==0x5A: self.board_index=value
        elif port==0x5B: self.board[self.board_index]=value
        elif port==0x70: self.rtc_index=value&0x7F
        elif port==0x8E: pass
        elif port==0x48:
            if self.nv_phase=='handshake': self.nv_phase='high'
            elif self.nv_phase=='high':
                self.nv_address=value<<8
                self.nv_phase='low'
            elif self.nv_phase=='low':
                self.nv_address|=value
                self.nv_phase='data'
            elif self.nv_phase=='data':
                self.nv[self.nv_address]=value
                self.nv_phase='idle'
            elif self.nv_phase=='ack': self.nv_phase='idle'
            else: raise AssertionError(('NVRAM phase',self.nv_phase))
        else: raise AssertionError(('unexpected output',hex(port),value))
    def run(self,start,stop):
        self.stopped=False
        for reg,value in ((x.UC_X86_REG_CS,0xF000),(x.UC_X86_REG_IP,start),(x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x7000),(x.UC_X86_REG_DS,0),(x.UC_X86_REG_ES,0),(x.UC_X86_REG_EFLAGS,2)):
            self.cpu.reg_write(reg,value)
        stops = (stop,) if isinstance(stop, int) else stop
        def end(cpu,address,size,unused):
            self.stopped=True
            cpu.emu_stop()
        hooks = [self.cpu.hook_add(UC_HOOK_CODE,end,begin=0xF0000+p,end=0xF0000+p) for p in stops]
        try: self.cpu.emu_start(0xF0000+start,0x100000,count=20000)
        finally:
            for hook in hooks: self.cpu.hook_del(hook)
        assert self.stopped,(hex(start),hex(self.cpu.reg_read(x.UC_X86_REG_IP)))
        assert not self.writes,('pre-RAM memory write',self.writes[:3])
        return self.trace

def oem_rom(port):
    a=(port/'reference/mp386even.bin').read_bytes()
    b=(port/'reference/mp386odd.bin').read_bytes()
    raw=bytearray(65536)
    raw[::2],raw[1::2]=a,b
    assert hashlib.sha256(raw).hexdigest()=='573eae691f78fcfc2906acfb59abe3cf8ffb3d8cfc37d761318018b430f900e7'
    return bytes(raw)


PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PORT.parent))
from shared.tools.ram_proof import Listing


def check(image):
    image = Path(image)
    listing = Listing(image.with_suffix('.lst'))
    candidate = image.read_bytes()
    original = oem_rom(PORT)
    atu_start = listing.symbol('mitsubishi_atu_initialize')
    atu_end = listing.symbol('mitsubishi_atu_end')
    atu_failed = listing.symbol('mitsubishi_atu_failed')
    board_start = listing.symbol('mitsubishi_board_defaults_begin')
    board_end = listing.symbol('mitsubishi_board_defaults_end')
    atu_cases = 0
    for revision in (0, 0x1000):
        for strap in range(8):
            old = Controls(original, strap49=strap, revision=revision)
            old.run(0x712, 0x7C0)
            new = Controls(candidate, strap49=strap, revision=revision)
            new.run(atu_start, atu_end)
            assert new.trace == old.trace, (revision, strap, new.trace, old.trace)
            assert new.ti == old.ti
            atu_cases += 1
    # Preserve OEM rejection when an identification or write/readback check fails.
    for fault in (None, 0x840, 0x841, 0x842, 0x843, 0x802, 0x803):
        old, new = Controls(original), Controls(candidate)
        if fault is None:
            old.ti[0x800] &= ~0x200
            new.ti[0x800] &= ~0x200
        else:
            old.readback_fault = new.readback_fault = fault
        old.run(0x712, (0x723, 0x746, 0x7B1, 0x7BF))
        new.run(atu_start, atu_failed)
        assert new.trace == old.trace, (fault, new.trace, old.trace)
    board_cases = 0
    for kind in (0, 1, 2):
        for switches in range(256):
            for et in (False, True):
                old = Controls(original, kind=kind, switches=switches, et=et)
                old.run(0xC02, 0xC81)
                old.run(0xD3A, 0xED7)
                new = Controls(candidate, kind=kind, switches=switches, et=et)
                kept = {reg: 0xABCD4567+i for i, reg in enumerate((
                    x.UC_X86_REG_EAX, x.UC_X86_REG_EBX, x.UC_X86_REG_EDX,
                    x.UC_X86_REG_ESI, x.UC_X86_REG_EDI, x.UC_X86_REG_EBP))}
                for reg, value in kept.items():
                    new.cpu.reg_write(reg, value)
                new.run(board_start, board_end)
                # Only configuration storage is replaced by adapter-owned defaults.
                expected = [row for row in old.trace if row[1] not in (0x48, 0x70, 0x71)]
                assert new.trace == expected, (kind, switches, et, new.trace, expected)
                assert new.board == old.board
                assert all(new.cpu.reg_read(reg) == value for reg, value in kept.items())
                board_cases += 1
    return dict(image_sha256=hashlib.sha256(candidate).hexdigest(),
                atu_cases=atu_cases, atu_rejection_cases=7, board_cases=board_cases,
                original_hardware_operations_match=True,
                retained_registers_unchanged=True, no_pre_ram_memory_writes=True,
                adaptations=['OEM invalid-configuration defaults replace OEM private NVRAM',
                             'SMSW reads CR0.ET without clearing retained EAX bits'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=PORT/'build/baios-mp386.bin')
    args = parser.parse_args()
    result = check(args.image)
    (args.image.parent/'oem-control-comparison.json').write_text(
        json.dumps(result, indent=2)+'\n', encoding='utf-8')
    print('PASS OEM controls', json.dumps(result))
