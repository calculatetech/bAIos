"""Compare complete OEM cache owners; synthetic cache is not hardware proof."""
import argparse
import importlib
import json
import re
import struct
from pathlib import Path

from capstone import Cs, CS_ARCH_X86, CS_MODE_16
from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

from fixture import Tiger, PORT

memory = importlib.import_module('test-memory')
shadow = importlib.import_module('test-shadow')
port = importlib.import_module('test-port')


class CacheTiger(Tiger):
    def __init__(self, *args, **kwargs):
        self.io = []
        self.read_fault = lambda port, size, value: value
        super().__init__(*args, **kwargs)

    def port_in(self, cpu, port, size, unused):
        value = super().port_in(cpu, port, size, unused)
        value = self.read_fault(port, size, value)
        self.io.append(('in', port, size, value))
        return value

    def port_out(self, cpu, port, size, value, unused):
        super().port_out(cpu, port, size, value, unused)
        self.io.append(('out', port, size, value))


def configured(image, pairs=shadow.PAIRS):
    m = CacheTiger(image, controllers=pairs, cache=True)
    memory.window(m, m.symbol('startup'), m.symbol('.ram_ready', 'startup'))
    counts = [n for p in pairs for n in p]+[0]*(6-len(pairs)*2)
    m.cpu.mem_write(0x9F010, struct.pack('<6HH', *counts, len(pairs)))
    m.cpu.mem_write(0x9F00F, bytes((int(bool(m.board_switches & 1)),)))
    m.io.clear()
    m.memory_trace.clear()
    return m


def instructions(image):
    raw, candidate, m = memory.oem_image(), Path(image).read_bytes(), Tiger(image)
    addresses = {int(match[1], 16): m.symbol('oem_cache_'+match[1])
                 for line in m.listing.lines
                 if (match := re.search(r'\boem_cache_([A-F0-9]{4}):', line))}
    relocated = addresses | {0x1C4C: m.symbol('mp_memory_ti_write'),
        0x1C6B: m.symbol('mp_memory_ti_read'), 0x9ECB: m.symbol('mp_cache_record_read'),
        0x9EB8: m.symbol('mp_cache_record_write'), 0x9B43: m.symbol('mp_cache_title'),
        0x9688: m.symbol('mp_cache_register_failed'), 0x9614: m.symbol('mp_cache_register_failed'),
        0x9B8C: m.symbol('mp_cache_data_failed'), 0x0667: m.symbol('mp_cache_return')}
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    count = 0
    for original, address in addresses.items():
        if original in (0x63BD, 0x93C1, 0x9307):
            continue  # Inline title bytes and the caller return boundary.
        old = next(decoder.disasm(raw[original:original+15], original, count=1))
        new = next(decoder.disasm(candidate[address:address+15], address, count=1))
        mnemonic, expected = old.mnemonic, old.op_str
        if mnemonic.startswith('j') or mnemonic == 'call' or (mnemonic == 'mov' and expected.startswith(('bp,', 'sp,'))):
            expected = re.sub(r'0x[0-9a-f]+', lambda v: hex(relocated.get(int(v[0],16)&65535, int(v[0],16))), expected)
        if original == 0x6697:
            expected = hex(m.symbol('mp_cache_pass'))
        actual = new.op_str
        if mnemonic == 'xchg':
            expected, actual = (', '.join(sorted(s.split(', '))) for s in (expected, actual))
        assert (mnemonic, expected) == (new.mnemonic, actual), (hex(original), mnemonic, expected, new.mnemonic, actual)
        if original+old.size in addresses and original not in (0x9305, 0x93BE):
            assert address+new.size == addresses[original+old.size], hex(original)
        count += 1
    assert candidate[addresses[0x63BD]:addresses[0x63CC]] == raw[0x63BD:0x63CC]
    guard = list(decoder.disasm(candidate[addresses[0x9305]:addresses[0x9307]], addresses[0x9305]))
    assert [v.mnemonic for v in guard] == ['jne', 'test', 'je']
    assert guard[1].op_str == 'si, si' and guard[2].op_str == hex(addresses[0x9335])
    for target in (0x663A, 0x664C, 0x665E):
        assert addresses[target+3] == addresses[target]+3, 'Native BP+3 failure continuation'
    late = list(decoder.disasm(candidate[addresses[0x9307]:addresses[0x9335]],addresses[0x9307]))
    assert [(v.mnemonic,v.op_str) for v in late] == [('mov','ah, bh'),('jmp',hex(addresses[0x93A1]))]
    assert count > 350
    return dict(instructions=count, unchanged_native_instructions_compared=True,
                adaptations=['Relocated helpers, records and established display/phase owners',
                             'SI=0 selects native Off branch before RAM exists',
                             'Late E0 policy comes from bAIos state; CMOS validity and saved policy gates removed'])


def qualification_fault(m, fault, reloc):
    """Corrupt an external read; let the unchanged comparison choose its exit."""
    seen, reads = [], {0xE0: 0, 0xE2: 0}
    control_faults = {0x6404: (0xE0, 1), 0x6419: (0xE0, 2),
                      0x6443: (0xE2, 2), 0x645D: (0xE2, 3)}
    def control(port, size, value):
        if port == 0x5B and m.control_index in reads:
            reads[m.control_index] += 1
            if control_faults.get(fault) == (m.control_index, reads[m.control_index]):
                seen.append(True)
                return value ^ 1
        return value
    m.read_fault = control
    phase, helpers = [False], []
    def observe(cpu, address, size, unused):
        offset = address-0xF0000
        if isinstance(fault, int) and fault not in control_faults and offset == reloc(fault):
            phase[0] = True
        if isinstance(fault, str) and offset == reloc(0x249D):
            if not helpers or helpers[-1] != cpu.reg_read(x.UC_X86_REG_BP):
                helpers.append(cpu.reg_read(x.UC_X86_REG_BP))
            phase[0] = len(helpers)-1 == int(fault[-1])
    original = m.cache_read
    def data(address, value):
        result = original(address, value)
        if phase[0] and not seen and 0x30000 <= address < 0x40000:
            seen.append(True)
            return result ^ 1
        return result
    m.cache_read = data
    return seen, m.cpu.hook_add(UC_HOOK_CODE, observe)


def qualification(image):
    rows = []
    faults = (None, 0x6404, 0x6419, 0x6443, 0x645D,
              0x6507, 0x653C, 0x6575, 0x65A6, 0x65DF, 0x65EE,
              'helper0', 'helper1', 'helper2')
    for fault in faults:
        outcomes = []
        for native in (True, False):
            m = configured(image)
            maps = dict(m.maps)
            records = bytearray(256)
            records[0xCF], records[0xDD] = 0, 3
            reloc = lambda addr: addr if native else m.symbol(f'oem_cache_{addr:04X}')
            stopped, rom_reads = [], []
            seen, fault_hook = qualification_fault(m, fault, reloc)
            stops = {reloc(0x6697): 'pass', reloc(0x669A): 'register-failure', reloc(0x673A): 'data-failure'}
            def observe(cpu, address, size, unused):
                offset = address-0xF0000
                if offset in stops:
                    stopped.append(stops[offset])
                    cpu.emu_stop()
            def access(cpu, kind, address, size, value, unused):
                if kind == 16 and 0xF0000 <= address < 0x100000:
                    rom_reads.append((address, size))
                # No RAM stack or extra POST writes are allowed in this window.
                assert not (kind == 17 and 0x6000 <= address < 0x8000), hex(address)
            hooks = [m.cpu.hook_add(UC_HOOK_CODE, observe),
                     m.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, access)]
            # window's declared stop is never reached: one of the three native
            # outcome boundaries above must stop this run.
            try:
                memory.window(m, reloc(0x63CC), 0xFFE0,
                    ((x.UC_X86_REG_SS,0), (x.UC_X86_REG_ESP,0x7000),
                     (x.UC_X86_REG_DS,0xF000), (x.UC_X86_REG_ES,0xF000),
                     (x.UC_X86_REG_FS,0x9E00), (x.UC_X86_REG_SI,0)),
                    raw=memory.oem_image() if native else None,
                    record_reads=records if native else None)
            except AssertionError as error:
                assert stopped and error.args == (hex(m.cpu.reg_read(x.UC_X86_REG_IP)),), str(error)
            for hook in hooks:
                m.cpu.hook_del(hook)
            m.cpu.hook_del(fault_hook)
            assert len(stopped) == 1, (native, fault, stopped, hex(m.cpu.reg_read(x.UC_X86_REG_IP)))
            if fault is not None:
                assert seen, fault
            assert not any(row[1] == 0x80 for row in m.io), 'POST inside native window'
            if stopped[0] != 'register-failure':
                assert m.maps == maps and m.controls[0xE0] == 0 and not m.controls[0xE2] & 2
            transactions = [row for row in m.memory_trace if not 0x9F000 <= row[1] < 0x9F020]
            outcomes.append((stopped[0], m.io, transactions, rom_reads, m.controls, m.maps))
        assert outcomes[0] == outcomes[1], ('OEM execution differs', fault)
        assert outcomes[0][0] == ('pass' if fault is None else 'register-failure' if isinstance(fault,int) and fault < 0x6462 else 'data-failure')
        # Also enter through the adapter and follow its actual return or halt.
        m = configured(image)
        maps, latch = dict(m.maps), m.speaker
        seen, hook = qualification_fault(m, fault, lambda addr: m.symbol(f'oem_cache_{addr:04X}'))
        if outcomes[0][0] == 'register-failure':
            memory.window(m, m.symbol('cache_test'), m.symbol('hard_halt'),
                          ((x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x7000),(x.UC_X86_REG_FS,0x9E00)))
            terminal = 'hard_halt'
            assert m.cpu.mem_read(0x9F01F,1) == b'\x03'
        else:
            shadow.invoke(m, 'cache_test')
            terminal = 'returned'
            assert m.cpu.mem_read(0x9F01F,1) == bytes((7 if fault is None else 19,))
            assert m.maps == maps and m.speaker == latch and m.index == 0x0D
            assert m.controls[0xE0] == 0 and not m.controls[0xE2]&2
        m.cpu.hook_del(hook)
        assert fault is None or seen
        rows.append(dict(fault=fault, result=outcomes[0][0], complete_io=len(outcomes[0][1]),
                         RAM_transactions=len(outcomes[0][2]), ROM_reads=len(outcomes[0][3]),
                         native_match=True, adapter_terminal=terminal, external_fault=fault is not None))
        print('PASS native cache path', fault, flush=True)
    return rows


def policy(image):
    rows = []
    for extended, expected in ((0,3),(2048,3),(3072,0x23),(4096,0x23),(5120,0x33),
        (7168,0x43),(9216,0x53),(11264,0x63),(13312,0x6B),(15232,0x6B),(17408,0x7B)):
        outputs = []
        for native in (True, False):
            m = configured(image)
            m.cmos[0x0E] = 0x10
            m.cmos[0x30:0x32] = struct.pack('<H', extended)
            m.cpu.mem_write(0x413, struct.pack('<H',632))
            records = bytearray(256)
            writes = []
            memory.window(m, 0x92EB if native else m.symbol('oem_cache_92EB'),
                0x93C1 if native else m.symbol('oem_cache_93C1'),
                ((x.UC_X86_REG_SI,1), (x.UC_X86_REG_FS,0x9E00),
                 (x.UC_X86_REG_BH,expected)),
                raw=memory.oem_image() if native else None,
                record_reads=records if native else None, record_writes=writes if native else None)
            assert m.controls[0xE0] == expected and not m.controls[0xE2] & 2
            outputs.append(m.io)
        removed = [row for row in outputs[0] if row[1] in (0x70,0x71)]
        assert len(removed) == 6
        assert [row for row in outputs[0] if row[1] not in (0x70,0x71)] == outputs[1]
        rows.append(dict(extended_KiB=extended, E0=f'{expected:02X}',
                         complete_reference_io=outputs[0],complete_candidate_io=outputs[1],
                         deliberately_removed_CMOS_io=removed))
    for gate in ('early', 'physical-off', 'diagnostic40', 'diagnostic80'):
        m = configured(image)
        m.cache = gate != 'physical-off'
        m.controls[0xE0] = 0x6B
        m.controls[0xE2] |= 2
        m.cmos[0x0E] = 0x40 if gate == 'diagnostic40' else 0x80 if gate == 'diagnostic80' else 0
        memory.window(m, m.symbol('oem_cache_92EB'), m.symbol('oem_cache_93C1'),
                      ((x.UC_X86_REG_SI,0 if gate == 'early' else 1),
                       (x.UC_X86_REG_BH,0x6B),
                       (x.UC_X86_REG_FS,0xABCD)))
        expected = 0 if gate in ('early','physical-off') else 0x6B
        assert m.controls[0xE0] == expected and not m.controls[0xE2] & 2
        assert not any(row[1] in (0x70,0x71) for row in m.io)
        if gate in ('early','physical-off'):
            assert not any(row[1] in (0x70,0x71) for row in m.io)
            assert not m.memory_trace, 'Early holdoff touched RAM'
        rows.append(dict(gate=gate,E0=f'{expected:02X}'))
    # The qualified boundary, not raw installed capacity, feeds CMOS30/31.
    m = configured(image)
    shadow.invoke(m, 'mp_cache_qualify')
    assert m.cpu.mem_read(0x9F01F,1) == b'\x07'
    m.cmos[0x30:0x32] = struct.pack('<H',15232)
    m.cpu.mem_write(0x9E0D0,struct.pack('<H',15232))
    m.cpu.mem_write(0x413, struct.pack('<H',632))
    shadow.invoke(m, 'mp_cache_enable')
    assert m.controls[0xE0] == 0x6B and m.cpu.mem_read(0x9F01F,1) == b'\x0E'
    assert m.index == 0x0D
    return rows


def boots(image, fault=None):
    results = []
    seed = port.machine(image, controllers=((16,16),), cache=False)
    def skip_seed(mm, address):
        if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
            mm.pending.append(0x01)
    seed.code_observer = skip_seed
    seed.boot()
    for enabled in (False, True):
        m = CacheTiger(image, controllers=shadow.PAIRS, cache=enabled)
        m.disk = port.boot_sector()
        fault_seen, fault_hook = qualification_fault(m, fault, lambda addr: m.symbol(f'oem_cache_{addr:04X}'))
        m.cmos[:], m.nvram[:] = seed.cmos, seed.nvram
        m.cmos[0x0E] = 0x58
        m.script_after_post = []
        decoder = m.ram_key
        m.ram_key = lambda address: None if 0xFE0000 <= address < 0x1000000 else decoder(address)
        rendered = []
        held = []
        warm = False
        held_entry = 0xF0000+m.symbol('.cache_held','startup')
        ram_entry = 0xF0000+m.symbol('chipset_visible_ram_test')
        off_entries = {0xF0000+m.symbol(label) for label in
                       ('memory_qualify_contiguous','mp_shadow_prepare','chipset_visible_ram_test','mp_shadow_activate')}
        post_entry = 0xF0000+m.symbol('post_ui_begin')
        option_entry = 0xF0000+m.symbol('option_rom_discovery')
        phases = {0xF0000+m.symbol(label):label for label in
                  ('initialize_video','post_ui_begin','cache_test','post_ui_cache',
                   'chipset_visible_ram_test','init_peripherals','init_floppy',
                   'ata_detect_primary','setup_post_gate','mp_shadow_activate','mp_cache_enable',
                   'option_rom_discovery','post_debug_summary','post_summary_cache','int19')}
        events = []
        def observe(mm, address):
            if address in phases:
                events.append(phases[address])
            if address == post_entry:
                assert 0x26 not in mm.posts[-2:]
                assert mm.cpu.mem_read(mm.base+0x101F,1)[0] == (3 if enabled else 1)
            if address == 0xF0000+mm.symbol('cache_test'):
                assert mm.cpu.mem_read(mm.base+0x101E,1) == b'\x01'
                assert mm.controls[0xE0] == 0
            if address == held_entry:
                assert mm.controls[0xE0] == 0 and not mm.controls[0xE2] & 2
                held.append(True)
            if address in off_entries:
                assert mm.controls[0xE0] == 0 and not mm.controls[0xE2] & 2
                if address == ram_entry:
                    mm.pending.append(0x01)
            if warm and address == post_entry:
                assert mm.ram_banks[0,1][0x80000:0x80004] == b'KEEP'
            if address == option_entry:
                assert 'Shadowed' in mm.text(16,24,40)
                expected = 'Cache test failed' if enabled and fault else '32 KB' if enabled else 'Disabled'
                assert mm.text(4,24,22).strip() == expected, mm.text(4,0,80)
                assert mm.controls[0xE0] == (0x6B if enabled and not fault else 0)
                rendered.append(True)
        m.code_observer = observe
        for restart in (False, True):
            events.clear()
            fault_seen.clear()
            warm = restart
            if restart:
                m.controls[0xE1] |= 0x20
                m.write_bus(0x180000,b'KEEP')
            m.boot(warm=restart,count=50000000)
            assert m.booted and not m.reset_count
            assert struct.unpack('<H',m.cpu.mem_read(m.base+0xD0,2))[0] == 15232
            assert struct.unpack('<H',m.cpu.mem_read(0x413,2))[0] == 632
            assert struct.unpack('<H',m.cpu.mem_read(0x40E,2))[0] == 0x9E00
            assert struct.unpack('<I',m.cpu.mem_read(0x9F004,4))[0] == 0x5833504D
            assert struct.unpack('<6HH',m.cpu.mem_read(0x9F010,14)) == (16,16,64,64,64,64,3)
            assert m.cpu.mem_read(0x9F000,1) == b'\x3F'
            assert m.text(4,58,12).strip() == '0 1 2 3 4 5'
            assert m.text(3,58,10).strip().startswith('15232'), m.text(3,0,80)
            assert m.cpu.mem_read(0x9F00E,1) == bytes((0x6B if enabled and not fault else 0,))
            assert m.cpu.mem_read(0x9F01F,1) == bytes((19 if enabled and fault else 14 if enabled else 1,))
            assert m.cmos[0x0E] == 0x18
            assert m.text(4,20,18).strip() == ('Cache test failed' if enabled and fault else '32 KB' if enabled else 'Disabled')
            required = ['initialize_video','post_ui_begin','cache_test','post_ui_cache',
                        'chipset_visible_ram_test','init_peripherals','init_floppy','ata_detect_primary',
                        'setup_post_gate','mp_shadow_activate','mp_cache_enable','option_rom_discovery',
                        'post_debug_summary','post_summary_cache','int19']
            position = -1
            for name in required:
                position = events.index(name,position+1)
            assert events.count('cache_test') == 1,events
            assert not m.index&0x80
            print('PASS cache',enabled,'warm' if restart else 'cold','signed boot',flush=True)
        assert len(rendered) == 2
        assert len(held) == 2
        assert bool(fault_seen) == bool(enabled and fault)
        m.cpu.hook_del(fault_hook)
        results.append(dict(cache=enabled,cold=True,warm=True,qualified_limit_KiB=16256,
                            physical_banks=[16,16,64,64,64,64],full_POST_order=required,
                            rendered='Cache test failed' if enabled and fault else '32 KB' if enabled else 'Disabled',
                            shadow_active=True,cache_enabled_after_shadow=enabled and not fault))
    return results


def checksums(image):
    rows = []
    for diagnostic,fault in ((0x58,None),(0xD8,None),(0x18,None),(0x58,'high'),(0x58,'low'),(0x58,'latch')):
        m = configured(image,((16,16),))
        m.cmos[:] = bytes((i*7+3)&255 for i in range(64))
        m.cmos[0x0E] = diagnostic
        expected = struct.pack('>H',sum(m.cmos[0x10:0x2E])&0xFFFF)
        m.cmos[0x2E:0x30] = bytes(v^0xFF for v in expected)
        before = bytes(m.cmos)
        dropped = {'high':0x2E,'low':0x2F,'latch':0x0E}.get(fault)
        def drop(cpu,port,size,value,unused):
            if port == 0x71 and m.index&0x7F == dropped:
                m.cmos[dropped] = before[dropped]
        if dropped is not None:
            from unicorn import UC_HOOK_INSN
            m.cpu.hook_add(UC_HOOK_INSN,drop,None,1,0,x.UC_X86_INS_OUT)
        preserved = {getattr(x,'UC_X86_REG_'+name):0x12340000+i for i,name in
                     enumerate(('EAX','EBX','ECX','EDX','ESI','EDI','EBP'))}
        for reg,value in preserved.items():
            m.cpu.reg_write(reg,value)
        shadow.invoke(m,'update_cmos_checksum')
        assert all(m.cpu.reg_read(reg) == value for reg,value in preserved.items())
        after = bytearray(before)
        after[0x2E:0x30] = expected
        if fault in ('high','low'):
            after[dropped] = before[dropped]
        if fault is None:
            after[0x0E] &= 0xBF
        assert bytes(m.cmos) == bytes(after), (diagnostic,fault,list(m.cmos),list(after))
        assert not any(row[1] in (0x5A,0x5B) for row in m.io)
        rows.append(dict(diagnostic_before=f'{diagnostic:02X}',fault=fault,
                         diagnostic_after=f'{m.cmos[0x0E]:02X}',registers_and_flags_preserved=True))
    return rows


def guards(image):
    rows = []
    for pairs in (((16,16),), shadow.PAIRS):
        m = configured(image, pairs)
        shadow.invoke(m,'mp_cache_qualify')
        assert m.cpu.mem_read(0x9F01F,1) == b'\x07'
        assert m.controls[0xE0] == 0 and not m.controls[0xE2] & 2
        rows.append(dict(controllers=len(pairs),qualified=True))
    m = configured(image)
    m.cache = False
    shadow.invoke(m,'mp_cache_qualify')
    assert m.cpu.mem_read(0x9F01F,1) == b'\x01' and 0x26 not in m.posts
    rows.append(dict(physical_off=True,qualification_skipped=True))
    for fault in ('no-aperture','dual-aperture','wrong-mode'):
        m = configured(image)
        if fault == 'no-aperture':
            m.maps[0,False,0xC] = 0
        if fault == 'dual-aperture':
            m.maps[1,False,0xC] = 0x800C
        if fault == 'wrong-mode':
            m.ti[2] = 0x8120
        memory.window(m,m.symbol('mp_cache_qualify'),m.symbol('hard_halt'),
                      ((x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x7000),
                       (x.UC_X86_REG_FS,0x9E00)))
        assert m.cpu.mem_read(0x9F01F,1) == b'\x03' and 0x26 not in m.posts
        assert m.controls[0xE0] == 0 and not m.controls[0xE2] & 2
        rows.append(dict(fault=fault,rejected_before_transient_owner=True))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image',type=Path,default=PORT/'build/oem-cache/baios-mp386.bin')
    parser.add_argument('--case',choices=('instructions','qualification','policy','boot','guards','checksum'),required=True)
    args = parser.parse_args()
    result = {'instructions':instructions,'qualification':qualification,'policy':policy,'boot':boots,'guards':guards,'checksum':checksums}[args.case](args.image)
    (args.image.parent/f'cache-{args.case}.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS',args.case,json.dumps(result) if isinstance(result,dict) else f'{len(result)} cases')


if __name__ == '__main__':
    main()
