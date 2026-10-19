"""Execute assembled RAM firmware against flat RAM and external I/O seams."""
import hashlib
import random
import re
import struct
import time
from pathlib import Path

from unicorn import (Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN,
                     UC_HOOK_INTR, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE)
from unicorn import x86_const as x


class Listing:
    def __init__(self, path):
        self.lines = Path(path).read_text().splitlines()

    def row(self, name, start=0):
        return next(i for i in range(start, len(self.lines))
                    if re.search(r'(?<![\w.])' + re.escape(name) + r':\s*$', self.lines[i]))

    def offset(self, row):
        return next(int(m[1], 16) for line in self.lines[row + 1:]
                    if (m := re.match(r'\s*\d+\s+([0-9A-F]{8})\s+(?:[0-9A-F]|<bin )', line)))

    def symbol(self, name, owner=None):
        return self.offset(self.row(name, self.row(owner) if owner else 0))


def constants(path):
    """Only literal state offsets needed by the independent runner."""
    return {m[1]: int(m[2], 0) for line in Path(path).read_text().splitlines()
            if (m := re.match(r'%define\s+(\w+)\s+(0x[\da-fA-F]+|\d+)\s*(?:;.*)?$', line))}


def run(rom, layout, state, kib=2049, ebda=0x9DD0, fault=None, alias_bit=None,
        defaults=False, coverage=True, legacy=False, decode=False,
        caller_cr0=0x60000010,caller_flags=0x246,caller_gates=(0x23,0x40),
        input_case=None,fault_pattern=0x55AA55AA):
    """Bounded RAM owner proof. Reset/terminal halt are observed, not replaced."""
    raw = Path(rom).read_bytes()
    listing = Listing(Path(rom).with_suffix('.lst'))
    code = layout['code_segment'] << 4
    start = listing.symbol('chipset_visible_ram_test')
    finish = listing.row('chipset_post_recovery_notice')
    first = listing.row('chipset_visible_ram_test')
    compares = [int(m[1], 16) for line in listing.lines[first:finish]
                if 'repe scasd' in line and
                (m := re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]', line))]
    scalar_compares = [int(m[1],16) for line in listing.lines[first:finish]
                       if 'cmp [edi], ecx' in line and
                       (m := re.match(r'\s*\d+\s+([0-9A-F]{8})\s+[0-9A-F]',line))]
    base = ebda << 4
    end = kib * 1024
    ranges = ((0x10000, base), (0x100000, end))
    expected_dwords = sum((b-a)//4 for a,b in ranges)
    u = Uc(UC_ARCH_X86, UC_MODE_16)
    u.mem_map(0, (end + 0x100FFF) & ~0xFFF)
    initial = random.Random(0xB105).randbytes(end)
    if alias_bit is not None:
        physical = bytearray(initial)
        step = 1 << alias_bit
        for a,b in ranges:
            for at in range(a,b,step*2):
                physical[at+step:min(at+step*2,b)] = physical[at:min(at+step,b)]
        initial = bytes(physical)
    u.mem_write(0, initial)
    u.mem_write(layout['base'], raw)
    u.mem_write(0, bytes(0x10000))
    u.mem_write(base, initial[base:base+8192])
    u.mem_write(0x40E, struct.pack('<H', ebda))
    u.mem_write(base + state['S_EXTENDED_KIB'], struct.pack('<H', min(kib-1024,0xFC00)))
    u.mem_write(base + state['S_EXTENDED_KIB32'], struct.pack('<I', kib-1024))
    u.mem_write(base + state['S_INSTALLED_KIB32'], struct.pack('<I', kib-1024))
    u.mem_write(base + state['P_PHASE'], bytes((0 if legacy else 1,)))
    u.mem_write(base + state['P_RAM_FLAGS'], b'\x00')
    u.mem_write(base + state['S_SETUP_REQUEST'], b'\x00')
    u.mem_write(0x451, b'\x01')
    u.mem_write(0x400 + state['KB_POST_STATE'], b'\x01')
    u.mem_write(0x41A, struct.pack('<HH', 0x1E, 0x1E))
    u.mem_write(0x480, struct.pack('<HH', 0x1E, 0x3E))
    u.mem_write(0x6FFE, struct.pack('<H', 0xFFF0))
    registers = {x.UC_X86_REG_EAX:0x12345678, x.UC_X86_REG_EBX:0x87654321,
                 x.UC_X86_REG_ECX:0xABCD1234, x.UC_X86_REG_EDX:0x76543210,
                 x.UC_X86_REG_ESI:0x24681357, x.UC_X86_REG_EDI:0x13572468,
                 x.UC_X86_REG_EBP:0x19283746, x.UC_X86_REG_DS:0x200,
                 x.UC_X86_REG_ES:0x300, x.UC_X86_REG_FS:0x400,
                 x.UC_X86_REG_GS:0x500, x.UC_X86_REG_CS:layout['code_segment'],
                 x.UC_X86_REG_SS:0, x.UC_X86_REG_SP:0x6FFE,
                 x.UC_X86_REG_EFLAGS:caller_flags, x.UC_X86_REG_CR0:caller_cr0}
    for reg, value in registers.items():
        u.reg_write(reg, value)
    u.reg_write(x.UC_X86_REG_GDTR, (0, 0x5000, 0x37, 0))
    gdtr = u.reg_read(x.UC_X86_REG_GDTR)
    reserved = bytes(u.mem_read(base,8192))
    ports = {0x61:caller_gates[0], 0x92:caller_gates[1]}
    cmos = bytearray(128)
    cmos[0x36] = 0x1A if defaults else 0
    index = 0
    terminal = []
    services = []
    injected = []
    decoded = {'instructions':0,'code_bytes':0}
    previous = None
    compare_ips = set(compares+scalar_compares)
    queue = []
    input_sent = False
    irq_entries = []
    masks = bytearray(end//4)
    writes = {0x55AA55AA:0, 0xAA55AA55:0, 0:0}
    reads = dict.fromkeys(writes, 0)
    def usable(address):
        return any(a <= address < b for a,b in ranges)
    def incoming(cpu, port, size, context):
        if port == 0x64:
            return int(bool(queue))
        if port == 0x60:
            return queue.pop(0) if queue else 0
        if port == 0x20:
            return 0  # Independent PIC: no pending/in-service IRQ1.
        return cmos[index] if port == 0x71 else ports.get(port, 0)
    def outgoing(cpu, port, size, value, context):
        nonlocal index
        if port == 0x70:
            index = value & 127
        elif port == 0x71:
            cmos[index] = value
        else:
            ports[port] = value
    def interrupt(cpu, number, context):
        if number == 0x10:
            return  # External display provider only.
        assert input_case and number in (9,0x15), ('Unexpected interrupt',number)
        irq_entries.append(number)
        sp = cpu.reg_read(x.UC_X86_REG_SP)
        for value in (cpu.reg_read(x.UC_X86_REG_EFLAGS),cpu.reg_read(x.UC_X86_REG_CS),
                      cpu.reg_read(x.UC_X86_REG_IP)):
            sp -= 2
            cpu.mem_write(sp,struct.pack('<H',value & 65535))
        cpu.reg_write(x.UC_X86_REG_SP,sp)
        cpu.reg_write(x.UC_X86_REG_EFLAGS,cpu.reg_read(x.UC_X86_REG_EFLAGS) & ~0x300)
        cpu.reg_write(x.UC_X86_REG_CS,layout['code_segment'])
        cpu.reg_write(x.UC_X86_REG_IP,listing.symbol('int09' if number == 9 else 'int15'))
    def service(cpu, address, size, context):
        nonlocal input_sent
        sp = cpu.reg_read(x.UC_X86_REG_SP)
        at = struct.unpack('<I', cpu.mem_read(sp,4))[0]
        services.append(at)
        if input_case and not input_sent and at >= 0x100000:
            queue.extend((0x1E,1) if input_case == 'esc' else (0xE0,0x53))
            input_sent = True
    def stop(cpu, address, size, context):
        terminal.append(context)
        cpu.emu_stop()
    def fetched(cpu,address,size,context):
        nonlocal previous
        if address != previous:
            decoded['instructions'] += 1
            decoded['code_bytes'] += size
        previous = address
    def compare(cpu, address, size, context):
        if fault is not None and not injected:
            block = cpu.reg_read(x.UC_X86_REG_EDI)
            count = cpu.reg_read(x.UC_X86_REG_ECX)
            saved = struct.unpack('<I',cpu.mem_read(cpu.reg_read(x.UC_X86_REG_SP)+4,4))[0]
            target_block, position = fault
            if count and block == target_block == saved and cpu.reg_read(x.UC_X86_REG_EAX) == fault_pattern:
                offset = {'first':0, 'middle':count//2*4, 'last':(count-1)*4}[position]
                at = block + offset
                cpu.mem_write(at, bytes(v ^ 0xFF for v in cpu.mem_read(at, 4)))
                injected.append(at)
    def memory_write(cpu, access, address, size, value, context):
        if not usable(address):
            return
        assert size == 4 and address % 4 == 0, ('RAM access width', address, size)
        assert cpu.reg_read(x.UC_X86_REG_CR0) & 0x60000000 == 0x60000000
        assert not(cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200), 'RAM write with IRQs enabled'
        if alias_bit is not None:
            # A tied address line maps the pair to the same physical storage.
            cpu.mem_write(address ^ (1 << alias_bit), struct.pack('<I', value & 0xFFFFFFFF))
        pattern = value if compares else value ^ address
        if pattern in writes and (compares or pattern != 0):
            writes[pattern] += 1
            masks[address//4] |= {0x55AA55AA:1, 0xAA55AA55:2, 0:4}[pattern]
    def memory_read(cpu, access, address, size, value, context):
        ip = cpu.reg_read(x.UC_X86_REG_IP)
        if usable(address) and ip in compare_ips:
            expected = cpu.reg_read(x.UC_X86_REG_EAX if compares else x.UC_X86_REG_ECX)
            pattern = expected if compares else expected ^ address
            assert pattern in reads
            assert bytes(cpu.mem_read(address, size)) == struct.pack('<I', expected)[:size] or injected
            reads[pattern] += 1
    u.hook_add(UC_HOOK_INSN, incoming, None, 1, 0, x.UC_X86_INS_IN)
    u.hook_add(UC_HOOK_INSN, outgoing, None, 1, 0, x.UC_X86_INS_OUT)
    u.hook_add(UC_HOOK_INTR, interrupt)
    address = code + listing.symbol('.keyboard', 'chipset_visible_ram_test')
    u.hook_add(UC_HOOK_CODE, service, None, address, address)
    for name in ('controlled_defaults_restart', 'hard_halt'):
        address = code + listing.symbol(name)
        u.hook_add(UC_HOOK_CODE, stop, name, address, address)
    if fault is not None:
        for offset in compares:
            u.hook_add(UC_HOOK_CODE, compare, None, code+offset, code+offset)
    if decode:
        u.hook_add(UC_HOOK_CODE, fetched)
    if coverage or alias_bit is not None:
        u.hook_add(UC_HOOK_MEM_WRITE, memory_write)
    if coverage:
        u.hook_add(UC_HOOK_MEM_READ, memory_read)
    t = time.perf_counter()
    u.emu_start(code+start, code+0xFFF0,
                count=max(200000000,expected_dwords*(32 if scalar_compares else 12)))
    seconds = time.perf_counter()-t
    failed = fault is not None or alias_bit is not None
    assert terminal == (['hard_halt' if defaults else 'controlled_defaults_restart'] if failed else []), terminal
    assert u.reg_read(x.UC_X86_REG_CR0) == registers[x.UC_X86_REG_CR0]
    assert u.reg_read(x.UC_X86_REG_GDTR) == gdtr
    assert (ports[0x61],ports[0x92]) == caller_gates, ports
    for a,b in ranges:
        assert bytes(u.mem_read(a, b-a)) == initial[a:b], ('RAM not restored', hex(a), hex(b))
    after = bytearray(u.mem_read(base,8192))
    for a,b in ((state['P_RAM_FLAGS'],state['P_RAM_FLAGS']+1),
                (state['S_RAM_TEST_BUFFER'],state['S_RAM_TEST_BUFFER']+state['RAM_TEST_BLOCK_SIZE'])):
        after[a:b] = reserved[a:b]
    if input_case == 'delete':
        assert after[state['S_SETUP_REQUEST']] == 1
        after[state['S_SETUP_REQUEST']] = reserved[state['S_SETUP_REQUEST']]
    assert bytes(after) == reserved, 'Excluded EBDA overwritten'
    assert bytes(u.mem_read(base+8192,0xA0000-base-8192)) == initial[base+8192:0xA0000]
    # Live state, backup and VGA are excluded; the reserved hardware gap is untouched.
    assert bytes(u.mem_read(0xA0000, 0x18000)) == initial[0xA0000:0xB8000]
    assert bytes(u.mem_read(0xB9000, layout['base']-0xB9000)) == initial[0xB9000:layout['base']]
    assert bytes(u.mem_read(layout['base'], len(raw))) == raw
    if not failed:
        assert u.reg_read(x.UC_X86_REG_IP) == 0xFFF0
        if not input_case:
            assert services and services[-1] == end, ('Incomplete tested extent',services[-1:] , end)
        for reg,value in registers.items():
            if reg not in (x.UC_X86_REG_SP,):
                assert u.reg_read(reg) == value, ('Caller state', reg, hex(u.reg_read(reg)), hex(value))
        assert u.reg_read(x.UC_X86_REG_SP) == 0x7000
        if not legacy:
            assert bytes(u.mem_read(base+state['P_RAM_FLAGS'], 1)) == bytes((2 if input_case else 4,))
            text = b'Skipped' if input_case else b'Passed'
            cells = bytes(u.mem_read(0xB8000+5*160+34*2,len(text)*2))
            assert cells[::2] == text and cells[1::2] == b'\x07'*len(text)
        if input_case:
            assert input_sent and irq_entries == [9,0x15,9,0x15], irq_entries
            if input_case == 'esc':
                assert bytes(u.mem_read(0x41E,2)) == b'a\x1e'
        if coverage:
            mask = 7 if compares else 3
            for a,b in ranges:
                assert masks[a//4:b//4] == bytes((mask,))*((b-a)//4), ('Incomplete pattern coverage', a,b)
            expected = {pattern:expected_dwords if compares or pattern else 0 for pattern in writes}
            assert reads == expected, reads
            assert writes == expected, writes
        assert all(sum(max(0,min(b,hi)-max(a,lo)) for lo,hi in ranges) <= 16384
                   for a,b in zip((0x10000,)+tuple(services),services)), 'Keyboard service work exceeds 16 KiB'
    elif defaults:
        assert ports.get(0x80) == 0xE7
    else:
        assert cmos[0x69] == 0xD2 and cmos[0x36] == 0x1A, (cmos[0x69],cmos[0x36])
    if fault is not None:
        assert injected, 'Requested fault was never injected'
    return {'kib':kib, 'ebda':hex(base), 'ranges':ranges, 'dwords':expected_dwords,
            'patterns_written':writes if coverage else None,
            'patterns_compared':reads if coverage else None,
            'pattern_form':'constant three passes + address witnesses' if compares else 'address XOR opposing two passes',
            'restored':True, 'caller_state_restored':not failed,
            'CR0_GDTR_A20_parity_restored':True, 'fault':fault, 'alias_bit':alias_bit,
            'fault_pattern':fault_pattern if fault else None,
            'caller_CR0':caller_cr0,'caller_flags':caller_flags,'caller_gates':caller_gates,
            'input_case':input_case,'IRQ_entries':irq_entries,
            'terminal':terminal or ['returned'], 'services':len(services),
            'progress_cells':bytes(u.mem_read(0xB8000+5*160+24*2,16)).hex() if not legacy else None,
            'decode':decoded if decode else None,
            'seconds':seconds, 'rom_sha256':hashlib.sha256(raw).hexdigest(),
            'measurement':'Unicorn host execution; not physical POST time'}
