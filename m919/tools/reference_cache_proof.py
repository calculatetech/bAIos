"""Compare assembled activation with executable non-M919 Phoenix instructions."""
import hashlib
import json
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_MEM_READ
from unicorn import x86_const as x

from geometry_proof import PORT, mapped, invoke

REFERENCE_SHA = '7ddabc826f82e295086fe04e2f462145f20d8c51911864a77c2c74aaf079499e'


class Trace:
    def __init__(self):
        self.events = []
        self.spans = []
        self.active = False
        self.last_ip = None
        self.span = None
        self.config = 0
        self.registers = {}
        self.observe_inputs = False
        self.decoder = Cs(CS_ARCH_X86, CS_MODE_16)

    def step(self, u, address, size):
        if not self.active:
            return
        raw = bytes(u.mem_read(address, size))
        ins = next(self.decoder.disasm(raw, address)) if address != self.last_ip else None
        if ins is not None:
            assert not ins.mnemonic.startswith(('push', 'pop')), (hex(address), ins.mnemonic)
            assert ins.mnemonic not in ('call', 'ret', 'enter', 'leave')
        if raw == b'\x0f\x09':
            self.events.append(['wbinvd'])
        elif raw == b'\x0f\x22\xc0':
            self.events.append(['cr0', u.reg_read(x.UC_X86_REG_EAX) & 0x60000000])
        elif self.observe_inputs and raw == b'\xec':
            self.incoming(u, u.reg_read(x.UC_X86_REG_DX), 1, None)
        if 0xF3 in raw and raw[-1] == 0xAD:
            if address != self.last_ip:
                count = u.reg_read(x.UC_X86_REG_ECX)
                start = u.reg_read(x.UC_X86_REG_ESI)
                self.events.append(['fill', start, count])
                self.span = [start, count, 0]
                self.spans.append(self.span)
        else:
            self.span = None
        self.last_ip = address

    def read(self, u, access, address, size, value, user):
        if self.active and self.span is not None:
            start, count, seen = self.span
            assert size == 4 and address == start + seen * 4, (hex(address), self.span, size)
            assert seen < count
            self.span[2] += 1

    def incoming(self, u, port, size, user):
        assert 0xCFC <= port <= 0xCFF and self.config & 0x80000000
        offset = (self.config & 0xFC) + port - 0xCFC
        value = self.registers.get(offset, 0)
        self.events.append(['in', port, size, value])
        return value

    def outgoing(self, u, port, size, value, user):
        self.events.append(['out', port, size, value])
        if port == 0xCF8:
            self.config = value
        elif 0xCFC <= port <= 0xCFF:
            assert self.config & 0x80000000
            self.registers[(self.config & 0xFC) + port - 0xCFC] = value
        else:
            assert (port, size, value) == (0x70, 1, 0x8D)


def reference(image, wb, code):
    """Execute original cache/PCI/fill opcodes; replace only private getters."""
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, 0x1000000)
    u.mem_write(0xE0000, image)
    u.reg_write(x.UC_X86_REG_CS, 0xF000)
    u.reg_write(x.UC_X86_REG_SP, 0x6F00)
    # Execute the reference's own flat-ES prerequisite before the cache path.
    u.emu_start(0xF4D35, 0xF4D65, count=100)
    assert u.reg_read(x.UC_X86_REG_IP) == 0x4D65
    u.reg_write(x.UC_X86_REG_SS, 0)
    u.reg_write(x.UC_X86_REG_SP, 0x6F00)
    u.reg_write(x.UC_X86_REG_CR0, 0x60000010)
    trace = Trace()
    trace.active = True
    trace.registers[0x50] = code

    def step(cpu, address, size, user):
        # CPU descriptor/storage belongs to this BIOS, not to its cache engine.
        # Select the normal AMD/Intel NW=0 path; retain both actual CR0 writes.
        if address == 0xF6310:
            cpu.reg_write(x.UC_X86_REG_BH, 0)
            cpu.reg_write(x.UC_X86_REG_IP, 0x634A)
            return
        if address == 0xF6370:
            cpu.reg_write(x.UC_X86_REG_IP, 0x6390)
            return
        if address == 0xF80DE:
            field = cpu.reg_read(x.UC_X86_REG_DX)
            assert field in (0x6B5, 0x6B6, 0x6BB, 0x6B7)
            enabled = wb and field == 0x6B5
            flags = cpu.reg_read(x.UC_X86_REG_EFLAGS)
            cpu.reg_write(x.UC_X86_REG_EFLAGS, (flags & ~0x40) | (0 if enabled else 0x40))
            sp = cpu.reg_read(x.UC_X86_REG_SP)
            ip = struct.unpack('<H', cpu.mem_read(sp, 2))[0]
            cpu.reg_write(x.UC_X86_REG_SP, sp + 2)
            cpu.reg_write(x.UC_X86_REG_IP, ip)
            return
        # Getters use stack after the first two fills. They are replaced above;
        # retain the source's push/pop/call sites while checking its fill spans.
        if address in (0xF9AF3, 0xF9AF7, 0xF9AFA, 0xF9B13, 0xF9B17, 0xF9B1A,
                       0xF9B28, 0xF9B2C, 0xF9B2F, 0xF9B32, 0xF9B36, 0xF9B39):
            trace.span = None
            trace.last_ip = address
            return
        trace.step(cpu, address, size)

    u.hook_add(UC_HOOK_CODE, step)
    u.hook_add(UC_HOOK_MEM_READ, trace.read)
    u.hook_add(UC_HOOK_INSN, trace.incoming, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, trace.outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    u.emu_start(0xF9AC5, 0xF9B48, count=3000000)
    assert u.reg_read(x.UC_X86_REG_IP) == 0x9B48
    assert all(count == seen for _, count, seen in trace.spans)
    return trace


def candidate(image, wb, code, l1):
    _, fixture = mapped([(16, False, False), None, None, None], expected=16, rom_image=image)
    u, d, listing, state, _, _ = fixture
    base = u.reg_read(x.UC_X86_REG_FS) << 4
    u.reg_write(x.UC_X86_REG_DI, state['C_CHIP'])
    invoke(fixture, 'chipset_defaults')
    for offset, size, value in ((0x1036, 1, code), (0x1037, 1, code),
                                (0x1038, 1, 1), (0x103C, 4, 0x8000 << code),
                                (state['C_CHIP'] + 1, 1, int(l1)),
                                (state['C_CHIP'] + 3, 1, 0x40 if wb else 0)):
        d.write(base + offset, size, value)
    invoke(fixture, 'chipset_apply')
    start = 0xFFFF0000 + listing.symbol('.reference_activate', 'cache_run')
    end = 0xFFFF0000 + listing.symbol('.leave_high', 'cache_run')
    trace = Trace()
    trace.observe_inputs = True

    def step(cpu, address, size, user):
        if address == start:
            trace.active = True
            trace.registers = d.registers
            assert not d.registers[0x50] & 0x80
            assert not d.registers[0x51] & 1
        if address == end:
            trace.active = False
        trace.step(cpu, address, size)

    def outgoing(cpu, port, size, value, user):
        if trace.active:
            trace.outgoing(cpu, port, size, value, user)

    # Existing device callbacks remain authoritative; these extra hooks observe.
    u.hook_add(UC_HOOK_CODE, step)
    u.hook_add(UC_HOOK_MEM_READ, trace.read)
    u.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    invoke(fixture, 'chipset_late_cache', count=3000000)
    assert d.read(base + 0x1038, 1) == b'\x05'
    assert d.registers[0x50] & 0xC0 == (0xC0 if wb else 0x80)
    assert not d.registers[0x51] & 1
    assert bool(u.reg_read(x.UC_X86_REG_CR0) & 0x40000000) != l1
    assert u.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
    assert all(count == seen for _, count, seen in trace.spans)
    return trace


def rejected_extents(image):
    _, fixture = mapped([(16, False, False), None, None, None], expected=16, rom_image=image)
    u, d, _, state, _, _ = fixture
    base = u.reg_read(x.UC_X86_REG_FS) << 4
    u.reg_write(x.UC_X86_REG_DI, state['C_CHIP'])
    invoke(fixture, 'chipset_defaults')
    rejected = []
    for code, installed_kib in ((5, 2048), (6, 4096)):
        d.write(base + 0x1036, 1, code)
        d.write(base + 0x1038, 1, 5)
        d.write(base + 0x103C, 4, 0x8000 << code)
        d.write(base + state['S_EXTENDED_KIB32'], 4, installed_kib - 1024)
        invoke(fixture, 'cache_enable')
        assert not d.registers.get(0x50, 0) & 0x80
        assert d.read(base + 0x1038, 1) == b'\x01'
        rejected.append(dict(size_code=code, installed_kib=installed_kib))
    print('Incomplete reference fill span rejected PASS', flush=True)
    return rejected


def partial_extent_cases(image):
    """Exercise firmware activation; upper-range bypass is a device-model contract."""
    from cache_proof import SRAM, guest
    from geometry_proof import DRAM
    rows = []
    for wb in (False, True):
        d = SRAM(kib=256, ram=64)
        _, fixture = mapped(d.modules, expected=64, memory=d, rom_image=image)
        u, _, _, state, _, _ = fixture
        base = u.reg_read(x.UC_X86_REG_FS) << 4
        u.reg_write(x.UC_X86_REG_DI, state['C_CHIP'])
        invoke(fixture, 'chipset_defaults')
        d.write(base + state['C_CHIP'] + 1, 1, 0)  # Isolate L2 from L1.
        d.write(base + state['C_CHIP'] + 3, 1, 0x40 if wb else 0)
        invoke(fixture, 'chipset_apply')
        invoke(fixture, 'cache_qualify', count=12000000)
        assert d.read(base + 0x1038, 1) == b'\x01'
        assert int.from_bytes(d.read(base + 0x103C, 4), 'little') == 256 * 1024
        d.qualifying = False
        invoke(fixture, 'cache_enable', count=3000000)
        assert d.read(base + 0x1038, 1) == b'\x05'
        assert d.registers[0x50] & 0xC0 == (0xC0 if wb else 0x80)
        assert not d.registers[0x51] & 1
        low, high = 0x102B60, 0x2102B60  # Same cache index, above the 32MiB tag range.
        assert d.cacheable(low) and not d.cacheable(high) and low % d.capacity == high % d.capacity
        before_hits = d.hits
        guest(fixture, 'partial-cache-extent', f'''cli
lgdt [gdtr]
mov eax,cr0
or al,1
mov cr0,eax
jmp dword 8:protected
bits 32
protected:
mov ax,16
mov ds,ax
mov es,ax
mov dword [{low}],0x55AA1234
mov eax,[{low}]
mov eax,[{low}]
mov dword [{high}],0xA55A8765
mov eax,[{low}]
mov [0x8500],eax
mov eax,[{high}]
mov [0x8504],eax
wbinvd
mov eax,[{low}]
mov [0x8508],eax
mov eax,[{high}]
mov [0x850C],eax
wbinvd
mov eax,cr0
and eax,0xFFFFFFFE
mov cr0,eax
jmp word 0:real
bits 16
real:
xor ax,ax
mov ds,ax
mov es,ax
jmp done
align 8
gdt:
dq 0,0x00CF9A000000FFFF,0x00CF92000000FFFF
gdtr:
dw 23
dd gdt
done:
''')
        observed = struct.unpack('<4I', d.read(0x8500, 16))
        assert observed == (0x55AA1234, 0xA55A8765) * 2, observed
        assert DRAM.read(d, low, 4) == struct.pack('<I', 0x55AA1234)
        assert DRAM.read(d, high, 4) == struct.pack('<I', 0xA55A8765)
        assert d.hits > before_hits and (not wb or d.l2_copybacks > 0)
        assert int.from_bytes(d.read(base + state['S_EXTENDED_KIB32'], 4), 'little') == 64 * 1024 - 1024
        assert int.from_bytes(d.read(base + state['S_INSTALLED_KIB32'], 4), 'little') == 64 * 1024 - 1024
        rows.append(dict(wb=wb, cache_kib=256, installed_mib=64, cached_address=low,
                         uncached_address=high, before_after_flush=observed, full_ram_reported=True))
    return rows


def run(image):
    raw = (PORT / 'reference/other-roms/8810AIO.32J').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == REFERENCE_SHA
    rows = []
    for wb, code, l1 in ((False, 3, True), (True, 3, True), (False, 3, False), (True, 5, True)):
        original = reference(raw, wb, code)
        actual = candidate(image, wb, code, l1)
        assert actual.events == original.events, (actual.events, original.events)
        assert actual.spans == original.spans
        row = dict(wb=wb, size_code=code, l1=l1, spans=actual.spans, events=actual.events)
        rows.append(row)
        print('Reference operation order / complete reads / L1 policy', wb, code, l1, 'PASS', flush=True)
    rejected = rejected_extents(image)
    partial = partial_extent_cases(image)
    target = PORT / 'build/tests/manual-rebuild/reference-cache.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(dict(comparisons=rows, rejected=rejected, partial=partial), indent=2) + '\n')
    return rows


if __name__ == '__main__':
    run(PORT / 'build/baios-m919.bin')
