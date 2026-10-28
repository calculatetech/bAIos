"""Focused OEM memory-owner checks; synthetic decoding is not hardware proof."""
import argparse
import hashlib
import importlib
import json
from pathlib import Path
import re
import struct

from unicorn import UC_HOOK_CODE
from unicorn import x86_const as x
from capstone import Cs, CS_ARCH_X86, CS_MODE_16

from fixture import Tiger, PORT

port_tests = importlib.import_module('test-port')
OEM_SHA256 = '573eae691f78fcfc2906acfb59abe3cf8ffb3d8cfc37d761318018b430f900e7'


def oem_image():
    raw = bytearray(65536)
    raw[::2] = (PORT/'reference/mp386even.bin').read_bytes()
    raw[1::2] = (PORT/'reference/mp386odd.bin').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == OEM_SHA256
    return bytes(raw)


def window(m, start, stop, registers=(), raw=None, record_reads=None, record_writes=None):
    """Run a bounded window. Only the OEM private-storage helper is replaceable."""
    m.reference = True
    m.reference_stop = 0xF0000+stop
    if raw is not None:
        m.cpu.mem_write(0xF0000, raw)
    for register, value in ((x.UC_X86_REG_CS, 0xF000),
                            (x.UC_X86_REG_SS, 0xF000),
                            (x.UC_X86_REG_DS, 0), (x.UC_X86_REG_ES, 0),
                            (x.UC_X86_REG_EFLAGS, 2)) + tuple(registers):
        m.cpu.reg_write(register, value)
    def boundary(cpu, address, size, unused):
        if address == 0xF0000+stop:
            cpu.emu_stop()
        if record_writes is not None and address == 0xF9EB8:
            ax = cpu.reg_read(x.UC_X86_REG_AX)
            record_writes.append((cpu.reg_read(x.UC_X86_REG_DX), ax >> 8))
            cpu.reg_write(x.UC_X86_REG_AX, (ax & 0xFF00) | (ax >> 8))
            cpu.reg_write(x.UC_X86_REG_IP, cpu.reg_read(x.UC_X86_REG_BP))
        if record_reads is not None and address == 0xF9ECB:
            index = cpu.reg_read(x.UC_X86_REG_DX)
            assert 0x240 <= index <= 0x2FF, hex(index)
            ax = cpu.reg_read(x.UC_X86_REG_AX)
            cpu.reg_write(x.UC_X86_REG_AX, (ax & 0xFF00) | record_reads[index-0x200])
            cpu.reg_write(x.UC_X86_REG_IP, cpu.reg_read(x.UC_X86_REG_BP))
    hook = m.cpu.hook_add(UC_HOOK_CODE, boundary)
    m.ti_stage = 'cold'
    m.capture_memory = True
    m.cpu.emu_start(0xF0000+start, 0x1000000, count=1000000)
    m.cpu.hook_del(hook)
    assert m.cpu.reg_read(x.UC_X86_REG_IP) == stop, hex(m.cpu.reg_read(x.UC_X86_REG_IP))


def configured(image, pairs):
    m = Tiger(image, controllers=pairs, dirty_maps=False)
    m.maps.clear()
    for unit in range(len(pairs)):
        m.ti[unit*256+2] = 0x8160
    return m


def hardware_trace(m):
    return [row[:4] for row in m.ti_trace['cold'] if row[1] in (0x24, 0x26)]


def mapper_instructions(image, raw):
    candidate = Path(image).read_bytes()
    model = Tiger(image)
    addresses = {int(match[1],16): model.symbol('oem_map_'+match[1])
                 for line in model.listing.lines
                 if (match := re.search(r'\boem_map_([A-F0-9]{4}):',line))}
    relocated = addresses | {0x9ECB: model.symbol('mp_memory_read_record'),
                             0x1C4C: model.symbol('mp_memory_ti_write'),
                             0x1C6B: model.symbol('mp_memory_ti_read'),
                             0x1388: model.symbol('mp_memory_mapped')}
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    count = 0
    for original, address in addresses.items():
        old = next(decoder.disasm(raw[original:original+15],original,count=1))
        new = next(decoder.disasm(candidate[address:address+15],address,count=1))
        expected = old.op_str
        if old.mnemonic.startswith('j') or (old.mnemonic == 'mov' and old.op_str.startswith(('bp,','sp,'))):
            expected = re.sub(r'0x[0-9a-f]+',lambda m: hex(relocated.get(int(m[0],16)&65535,int(m[0],16))),expected)
        if old.mnemonic == 'xchg':
            expected = ', '.join(sorted(expected.split(', ')))
            actual = ', '.join(sorted(new.op_str.split(', ')))
        else:
            actual = new.op_str
        assert (old.mnemonic,expected) == (new.mnemonic,actual), (hex(original),expected,actual)
        if original+old.size in addresses and old.mnemonic != 'jmp':
            assert address+new.size == addresses[original+old.size], hex(original)
        count += 1
    assert count > 200
    return dict(window='OEM106B..12FC +2414..2452 instructions', instructions=count,
                identical_except_relocations=True)


def native_probe_instructions(image, raw, checked=False):
    model=Tiger(image)
    candidate=Path(image).read_bytes()
    first,last=(0x1C55,0x1C6B) if checked else (0x1E45,0x1E99)
    prefix='mp_memory_ti_check' if checked else 'mp_probe_oem'
    start,end=model.symbol(prefix+'_begin'),model.symbol(prefix+'_end')
    decoder=Cs(CS_ARCH_X86,CS_MODE_16)
    def instructions(data,base):
        rows=[]
        for instruction in decoder.disasm(data,base):
            operand=instruction.op_str
            if instruction.mnemonic.startswith('j') and operand.startswith('0x'):
                operand=hex((int(operand,16)-base)&65535)
            rows.append((instruction.mnemonic,operand,instruction.size))
        return rows
    old=instructions(raw[first:last],first)
    new=instructions(candidate[start:end],start)
    assert old == new,('native probe instructions',old,new)
    assert end-start == last-first
    return dict(window=f'OEM{first:04X}..{last-2:04X} complete instructions',instructions=len(old),
                complete_branches_and_memory_operations=True)


def oem_controller_policy(image):
    raw = oem_image()
    assert hashlib.sha256(raw).hexdigest() == OEM_SHA256
    pairs = ((16,16),(64,64),(64,64))
    cases=[]
    for gate in (0,1,4):
        old, new = (Tiger(image,controllers=pairs,dirty_maps=not gate) for _ in range(2))
        old.board_switches=new.board_switches=gate
        writes=[]
        window(old,0x07C0,0x08B7,raw=raw,record_writes=writes)
        window(new,new.symbol('mp_memory_prepare_begin'),new.symbol('mp_memory_prepare_end'),
               ((x.UC_X86_REG_EBP,len(pairs)<<16),))
        assert writes == [(0x2DD,3)]
        expected,unit=[],0
        for row in old.ti_trace['cold']:
            expected.append(row[:4])
            if row[:2] == ('in',0x5E):
                if not gate:
                    profile=0x10E4 if unit == 0 else 0x36E4
                    expected += [('out',0x26,2,unit*256+4),('out',0x24,2,profile),
                                 ('out',0x26,2,unit*256+5),('out',0x24,2,profile)]
                unit+=1
        assert unit == 3
        assert expected == [row[:4] for row in new.ti_trace['cold']],('Complete OEM prepare order',gate)
        assert old.memory_trace == new.memory_trace,('Native geometry RAM operations',gate)
        assert [(new.ti[u*256+4],new.ti[u*256+5]) for u in range(3)] == [(0x10E4,0x10E4),(0x36E4,0x36E4),(0x36E4,0x36E4)]
        cases.append(dict(reset_gate=gate,IO=len(expected),memory=len(new.memory_trace)))
    old, new = Tiger(image, controllers=pairs), Tiger(image, controllers=pairs)
    window(old, 0x08C4, 0x092D, ((x.UC_X86_REG_ECX,3),(x.UC_X86_REG_EBX,0)), raw)
    window(new, new.symbol('mp_memory_map_clear_begin'), new.symbol('mp_memory_map_clear_end'),
           ((x.UC_X86_REG_EBP, len(pairs) << 16),))
    assert hardware_trace(old) == hardware_trace(new), 'Complete OEM map-clear order'
    assert old.maps == new.maps
    return dict(window='OEM07C0..08B4 then08B7..092B', controllers=3,
                prepare_cases=cases, complete_map_clear_IO=len(hardware_trace(old)),
                identical=True, adaptations=['Captured4/5 fallback only when native geometry gate is clear',
                    'Controller count held inCPU state instead of privateOEM NV02DD'])


def original_windows(image):
    raw = oem_image()
    assert hashlib.sha256(raw).hexdigest() == OEM_SHA256
    rows = [oem_controller_policy(image), native_probe_instructions(image,raw), mapper_instructions(image, raw)]
    pairs = ((16, 64), (64, 16), (0, 0))
    # Complete native seed sweep, including every address beyond installed RAM.
    old, new = configured(image, pairs), configured(image, pairs)
    window(old, 0x0F2C, 0x0F74,
           ((x.UC_X86_REG_BX, len(pairs)), (x.UC_X86_REG_DI, 0)), raw)
    window(new, new.symbol('mp_memory_seed_begin'), new.symbol('mp_memory_probe_begin'),
           ((x.UC_X86_REG_EBP, len(pairs) << 16), (x.UC_X86_REG_SI, 0)))
    assert hardware_trace(old) == hardware_trace(new), 'OEM seed hardware order'
    assert old.memory_trace == new.memory_trace, 'OEM seed RAM transactions'
    rows.append(dict(window='OEM0F2C..0F72 seed', io=len(hardware_trace(old)),
                     memory=len(old.memory_trace), identical=True))
    # Each bank's unchanged native probe, with empty, unequal and alias cases.
    for bank in range(6):
        old, new = configured(image, pairs), configured(image, pairs)
        for m in (old, new):
            for storage in m.ram_banks.values():
                storage[:] = bytes(len(storage))
        unit, side = divmod(bank, 2)
        window(old, 0x1DB3, 0x1E09,
               ((x.UC_X86_REG_AX, side << 14),
                (x.UC_X86_REG_DX, 0x8004+(unit << 12)+side)), raw)
        count = old.cpu.reg_read(x.UC_X86_REG_CX)
        window(new, new.symbol(f'mp_memory_bank{bank}_begin'),
               new.symbol(f'mp_memory_bank{bank}_end'),
               ((x.UC_X86_REG_EBP, len(pairs) << 16),))
        assert count == pairs[unit][side] == new.cpu.reg_read(x.UC_X86_REG_CX)
        # Adapter disables the fixed probe aperture after each bank; native1D19
        # does this after both banks. All actual probe operations are retained.
        assert hardware_trace(old) == hardware_trace(new)[:-2], bank
        assert hardware_trace(new)[-2:] == [('out', 0x26, 2, 0x8000+(unit << 12)),
                                           ('out', 0x24, 2, 0)]
        assert old.memory_trace == new.memory_trace, ('OEM probe RAM transactions', bank)
        rows.append(dict(window=f'OEM1DB3..1E07 bank{bank}', pages=count,
                         memory=len(old.memory_trace), identical=True,
                         adaptation='Disable aperture after each bank'))
    return rows


def bus_checks(m, pairs):
    m.controls[0xE1] |= 0x20  # OEM E1 bit5 owns A20; KBC output is independent.
    total = sum(map(sum, pairs))*65536
    assert m.maps.get((0, True, 0), 0) == 0, 'Temporary scratch aperture remains'
    for address in (0xA0000, 0xB8000, 0xC0000, 0xD0000, 0xE0000, total):
        assert m.ram_key(address) is None, ('disabled CPU window', hex(address))
    probes = [0x10000, 0x9FFFC, 0x100000, total-4]
    if total > 0x1000000:
        probes += [0xFFFFFC, 0x1000000, 0x1000004]
    boundary = 0
    for unit, pair in enumerate(pairs):
        for bank, pages in enumerate(pair):
            if pages:
                probes += [max(boundary, 0x100000), boundary+pages*65536-4]
            boundary += pages*65536
    probes = sorted({a for a in probes if a < total and not 0xA0000 <= a < 0x100000})
    keys = [m.ram_key(a) for a in probes]
    assert None not in keys and len(set(keys)) == len(keys), (probes, keys)
    for i, address in enumerate(probes):
        m.write_bus(address, struct.pack('<I', 0x12340000+i))
    for i, address in enumerate(probes):
        key = m.ram_key(address)
        assert bytes(m.ram_banks[key[0],key[1]][key[2]:key[2]+4]) == struct.pack('<I', 0x12340000+i)
        assert cpu_read(m,address) == 0x12340000+i
    # Real decode at the record-read mode gap, without any Python phase flag.
    before = m.ram_key(0x600)
    m.ti[2] = 0x8160
    assert m.ram_key(0x600) is None, 'Unmapped8160 record read was hidden by flat RAM'
    assert cpu_read(m,0x600) == 0xFFFFFFFF
    m.maps[0, True, 0] = 0x8000
    assert m.ram_key(0x600) == before
    assert all(m.ram_key(a) == (0,0,a) for a in (0, 0x600, 0xCFFC, 0xFFFF))
    m.maps[0, True, 0] = 0
    m.ti[2] = 0x8100
    assert m.ram_key(0x600) == before
    m.reference = False
    m.ti_stage = None
    m.capture_memory = False
    return len(probes)


def cpu_read(m, address):
    # Execute an actual address32 operand32 read, avoiding Unicorn host API
    # reads, which intentionally bypass CPU memory hooks.
    m.cpu.mem_write(0xFFED0, b'\x67\x66\xA1'+struct.pack('<I',address))
    window(m,0xFED0,0xFED7)
    return m.cpu.reg_read(x.UC_X86_REG_EAX)


def mapper_comparison(image, pairs):
    new = Tiger(image, controllers=pairs)
    new.reference = True
    stop = new.symbol('oem_map_106B')
    # Capture generated private records and actual cold setup immediately before
    # the imported mapper. No original OEM configuration records are consumed.
    window(new, new.symbol('startup'), stop,
           ((x.UC_X86_REG_EDX, 0x0308), (x.UC_X86_REG_ESP, 0),))
    records = bytes(new.cpu.mem_read(0x600, 256))
    bases = []
    for unit,(a,b) in enumerate(pairs):
        control = 0x4101 if a and a == b else 0x4001
        assert new.ti[unit*256+3] == control
        assert struct.unpack_from('<H', records, 0xA5+unit*2)[0] == control, 'Mapper changes established bank routing'
        base = 0  # The physical bank-routing baseline used zero on every MCU.
        assert records[0x99+unit] == base, 'Controller base differs from the working board policy'
        bases.append(base)
    old = Tiger(image, controllers=pairs)
    old.maps = dict(new.maps)
    old.ti = dict(new.ti)
    old.map_programmed = True
    raw = oem_image()
    window(old, 0x106B, 0x1388, raw=raw, record_reads=records)
    new.ti_trace['cold'].clear()
    new.memory_trace.clear()
    window(new, stop, new.symbol('mp_memory_mapped'))
    assert hardware_trace(old) == hardware_trace(new), 'Complete native mapper I/O'
    assert old.maps == new.maps and old.ti == new.ti
    assert [new.ti[unit*256] for unit in range(len(pairs))] == [unit*256+base for unit,base in enumerate(bases)]
    return dict(window='OEM106B..12FC +2414..2452 mapper',
                io=len(hardware_trace(old)), identical=True, controller_base_MiB=bases,
                adaptation='Private NV read helper replaced by qualified RAM records')


def reset_reference(image):
    """Compare native windows taken from one uninterrupted reset-to-boot run."""
    pairs = ((16,16),(64,64),(64,64))
    m = port_tests.machine(image,controllers=pairs,cache=False)
    names = ['startup','tiger_cold','mp_memory_prepare_begin','mp_memory_map_clear_begin',
             'mp_memory_environment_begin','mp_memory_environment_end',
             'mitsubishi_board_reset_kind_begin','mitsubishi_board_reset_kind_end',
             'mp_memory_refresh_begin','mp_memory_refresh_end',
             'mitsubishi_board_defaults_begin','mitsubishi_board_defaults_end',
             'mp_memory_seed_begin']+[f'mp_memory_bank{i}_begin' for i in range(6)]+[
             'mp_memory_normal_begin','mp_memory_normal_end','mp_memory_scratch_ready',
             'oem_map_106B','mp_memory_scratch_teardown_begin',
             'mp_memory_scratch_teardown_end','.ram_ready']
    targets = {}
    for name in names:
        offset = m.symbol(name,'startup') if name == '.ram_ready' else m.symbol(name)
        targets.setdefault(0xF0000+offset,[]).append(name)
    states, events = {}, []
    def observe(mm,address):
        for name in targets.get(address,[]):
            if name in states:
                continue
            events.append(name)
            states[name] = (len(mm.ti_trace['cold']),len(mm.memory_trace),dict(mm.ti),dict(mm.maps))
            if name == 'mp_memory_seed_begin':
                assert not mm.memory_trace, 'RAM touched before early refresh completed'
                assert not mm.cpu.reg_read(x.UC_X86_REG_EFLAGS) & 0x200
                trace = [row[:4] for row in mm.ti_trace['cold']]
                first=states['mp_memory_refresh_begin'][0]
                last=states['mp_memory_refresh_end'][0]
                assert trace[first:last] == [
                    ('out',0x43,1,0x70),
                    ('out',0x41,1,0xFF),('out',0x41,1,0),('out',0x43,1,0x40),
                    ('in',0x41,1,0xFE),('in',0x41,1,0),
                    ('out',0x43,1,0x54),('out',0x41,1,0x12)]
            if name == 'oem_map_106B':
                states['records'] = bytes(mm.cpu.mem_read(0x600,256))
            if name == '.ram_ready':
                mm.capture_memory = False
        if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
            mm.pending.append(1)
    m.code_observer = observe
    m.capture_memory = True
    m.boot(count=5000000)
    assert events == names,events
    raw = oem_image()
    comparisons = []
    def compare(first,last,start,stop,registers=(),records=None,probe=False,prepare=False):
        a,b = states[first],states[last]
        old = Tiger(image,controllers=pairs)
        old.ti,old.maps = dict(a[2]),dict(a[3])
        old.map_programmed = True
        if probe:
            for storage in old.ram_banks.values():
                storage[:] = bytes(len(storage))  # Complete OEM seed cleared each probe sentinel.
        window(old,start,stop,registers,raw=raw,record_reads=records,
               record_writes=[] if prepare else None)
        expected = [row[:4] for row in old.ti_trace['cold']]
        if prepare:
            adjusted,unit = [],0
            for row in expected:
                adjusted.append(row)
                if row[:2] == ('in',0x5E):
                    value = 0x10E4 if unit == 0 else 0x36E4
                    adjusted += [('out',0x26,2,unit*256+4),('out',0x24,2,value),
                                 ('out',0x26,2,unit*256+5),('out',0x24,2,value)]
                    unit += 1
            expected = adjusted
        actual = [row[:4] for row in m.ti_trace['cold'][a[0]:b[0]]]
        if probe:
            assert actual[-2:] == [('out',0x26,2,0x8000+(probe-1)//2*0x1000),('out',0x24,2,0)]
            actual = actual[:-2]
        assert actual == expected,(first,'I/O',len(actual),len(expected))
        if first.startswith('mp_memory_bank') or first == 'mp_memory_seed_begin':
            assert m.memory_trace[a[1]:b[1]] == old.memory_trace,(first,'RAM operations')
        comparisons.append(dict(window=first,complete_IO=len(actual),native_match=True))
    compare('mp_memory_prepare_begin','mp_memory_map_clear_begin',0x07C0,0x08B7,prepare=True)
    compare('mp_memory_map_clear_begin','mp_memory_environment_begin',0x08C4,0x092D,
            ((x.UC_X86_REG_ECX,3),(x.UC_X86_REG_EBX,0)))
    compare('mp_memory_seed_begin','mp_memory_bank0_begin',0x0F2C,0x0F74,
            ((x.UC_X86_REG_BX,3),(x.UC_X86_REG_DI,0)))
    for bank in range(6):
        unit,side = divmod(bank,2)
        compare(f'mp_memory_bank{bank}_begin',f'mp_memory_bank{bank+1}_begin' if bank < 5 else 'mp_memory_normal_begin',
                0x1DB3,0x1E09,((x.UC_X86_REG_AX,side<<14),
                (x.UC_X86_REG_DX,0x8004+(unit<<12)+side)),probe=bank+1)
    compare('oem_map_106B','mp_memory_scratch_teardown_begin',0x106B,0x1388,records=states['records'])
    a,b = states['mp_memory_normal_begin'][0],states['mp_memory_normal_end'][0]
    assert [row[:4] for row in m.ti_trace['cold'][a:b]] == [
        row for unit in range(3) for row in [('out',0x26,2,unit*256+2),('out',0x24,2,0x8100),
                                           ('out',0x26,2,unit*256+3),('out',0x24,2,0x4101)]]
    assert struct.unpack('<6HH',m.cpu.mem_read(m.base+0x1010,14)) == (16,16,64,64,64,64,3)
    cold = tuple(m.ti_trace['cold'])
    m.controls[0xE1] |= 0x20
    m.write_bus(0x180000,b'KEEP')
    m.script_after_post = []
    m.boot(warm=True,count=5000000)
    assert tuple(m.ti_trace['cold']) == cold
    assert m.ram_banks[0,1][0x80000:0x80004] == b'KEEP'
    assert m.booted
    return dict(reset_order=names,native_windows=comparisons,six_bank_inventory=True,
                scratch_teardown=True,warm_payload_retained=True,signed_boot=True)


def probe_bound_check(image):
    m=Tiger(image,controllers=((512,0),))
    m.ram_banks[0,0][:]=bytes(len(m.ram_banks[0,0]))  # The production seed clears sentinels first.
    initial=tuple((reg,0x77770000) for reg in (x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,
                  x.UC_X86_REG_ECX,x.UC_X86_REG_EDX,x.UC_X86_REG_ESI,x.UC_X86_REG_EDI))
    calls=[]
    def leaf(cpu,address,size,unused): calls.append(address)
    address=0xF0000+m.symbol('mp_probe_oem_begin')
    hook=m.cpu.hook_add(UC_HOOK_CODE,leaf,begin=address,end=address)
    window(m,m.symbol('mp_memory_bank0_begin'),m.symbol('mp_memory_bank0_end'),
           initial+((x.UC_X86_REG_EBP,1<<16),))
    m.cpu.hook_del(hook)
    assert len(calls) == m.cpu.reg_read(x.UC_X86_REG_CX) == 512
    assert m.cpu.reg_read(x.UC_X86_REG_EAX)>>16 == 512
    assert all(m.cpu.reg_read(reg)>>16 == 0x7777 for reg,value in initial[1:])
    return dict(explicit_page_cap=512,leaf_calls=len(calls),other_upper_bank_counts_preserved=True)


def identity_masks_checks(image):
    rows=[]
    # These non-ID bits are masked by OEM; true wrong identities must still stop.
    for atu,mcu,rejected in ((0x1200,0x1000,None),(0x0100,0,'atu'),(0x0200,0x0300,'mcu')):
        m=Tiger(image,controllers=((16,16),))
        m.ti[0x800],m.ti[0]=atu,mcu
        stop=m.symbol('mitsubishi_atu_failed' if rejected == 'atu' else 'mp_memory_failed') if rejected else m.symbol('.count_memory','startup')
        window(m,m.symbol('.cold','startup'),stop)
        rows.append(dict(ATU=hex(atu),MCU=hex(mcu),rejection=rejected,OEM_ID_masks_preserved=True))
    return rows


def geometry_boot_check(image,cache=False):
    # Execute the restored geometry path from reset through signed boot.
    m=port_tests.machine(image,controllers=((16,16),(64,64),(64,64)),dirty_maps=False,cache=cache)
    m.board_switches=1
    decoder=m.ram_key
    m.ram_key=lambda address: None if 0xFE0000 <= address < 0x1000000 else decoder(address)
    m.code_observer=lambda mm,a: mm.pending.append(1) if a == 0xF0000+mm.symbol('chipset_visible_ram_test') else None
    m.boot(count=5000000)
    assert m.booted and m.ti[4] == m.ti[5] == 0x10E4
    assert struct.unpack('<6H',m.cpu.mem_read(m.base+0x1010,12)) == (16,16,64,64,64,64)
    assert struct.unpack('<H',m.cpu.mem_read(m.base+0xD0,2))[0] == 15232
    if cache:
        assert m.controls[0xE0] == 0x6B
    return dict(native_geometry_reset_to_signed_boot=True,six_bank_inventory=True,cache_enabled=cache)


def early_rom_checksum_check(image):
    m=Tiger(image)
    m.rom[0xFFF5]^=1
    window(m,m.symbol('mitsubishi_board_reset_kind_end'),m.symbol('mp_memory_failed'))
    return dict(corrupt_ROM_read_rejected_before_refresh=True)


def early_sequence_checks(image):
    return [native_probe_instructions(image,oem_image(),checked=True),probe_bound_check(image),
            *identity_masks_checks(image),early_rom_checksum_check(image),
            geometry_boot_check(image),geometry_boot_check(image,cache=True)]


def normal_policy_checks(image):
    """Check count preservation and routing selection before low RAM exists."""
    rows = []
    registers = (x.UC_X86_REG_EAX, x.UC_X86_REG_EBX, x.UC_X86_REG_ECX,
                 x.UC_X86_REG_EDX, x.UC_X86_REG_ESI, x.UC_X86_REG_EDI)
    for pairs in (((16,16),), ((16,16),(64,64),(64,64)),
                  ((16,64),(64,16),(0,0)), ((16,0),(0,64),(8,8))):
        m = Tiger(image, controllers=pairs)
        counts = tuple(v for pair in pairs for v in pair) + (0,)*(6-len(pairs)*2)
        initial = tuple((reg, pages << 16 | 0x5A5A) for reg,pages in zip(registers,counts))
        from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
        def no_ram(cpu, kind, address, size, value, unused):
            assert address >= 0xA0000, ('RAM before final routing', hex(address))
        hook = m.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, no_ram)
        window(m, m.symbol('mp_memory_normal_begin'), m.symbol('mp_memory_normal_end'),
               initial + ((x.UC_X86_REG_EBP, len(pairs) << 16),))
        m.cpu.hook_del(hook)
        assert tuple(m.cpu.reg_read(reg) >> 16 for reg in registers) == counts
        expected = [0x4101 if a and a == b else 0x4001 for a,b in pairs]
        assert [m.ti[unit*256+3] for unit in range(len(pairs))] == expected
        assert all(m.ti[unit*256+2] == 0x8100 for unit in range(len(pairs)))
        assert not m.maps or all(not high for unit,high,index in m.maps)
        rows.append(dict(controllers=pairs, control_words=expected,
                         upper_counts_preserved=True, no_RAM_access=True))
    return rows


def boot_checks(image):
    rows = []
    cases = [((16,16),), ((16,16),(64,64),(64,64)),
             ((16,16),(0,0),(0,0)), ((16,64),(64,16),(0,0)),
             ((16,16),(0,0),(64,16)), ((8,16),(32,64),(128,256))]
    for pairs in cases:
        m = port_tests.machine(image, controllers=pairs, cache=True)
        preserved = bytes((i*37+11)&255 for i in range(0xC0))
        m.nvram[0x240:0x300] = preserved
        phases = dict(scratch=False, teardown=False)
        writes = []
        def observer(mm, address):
            if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
                mm.pending.append(1)  # This check owns mapping; the RAM suite owns the sweep.
            if address == 0xF0000+mm.symbol('mp_memory_scratch_ready'):
                phases['scratch'] = True
            if address == 0xF0000+mm.symbol('mp_memory_scratch_teardown_begin'):
                phases['teardown'] = True
            if address == 0xF0000+mm.symbol('mp_memory_scratch_teardown_end'):
                phases['teardown'] = False
        m.code_observer = observer
        from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
        def access(cpu, kind, address, size, value, unused):
            if address >= 0xA0000:
                return
            assert not phases['teardown'], ('RAM in teardown gap', hex(address))
            if not phases['scratch']:
                assert address in (0, 0xCFFC) or 0x500 <= address < 0x700, ('Unsafe pre-RAM access', hex(address))
            if kind == 17:
                writes.append(address)
        hook = m.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, access)
        m.boot(count=30000000)
        m.cpu.hook_del(hook)
        assert m.booted and not m.processor_reset_count
        counts = tuple(struct.unpack('<6H', m.cpu.mem_read(m.base+0x1010, 12)))
        expected = tuple(v for pair in pairs for v in pair)+(0,)*(6-len(pairs)*2)
        assert counts == expected, (counts, expected)
        assert bytes(m.nvram[0x240:0x300]) == preserved
        visible = ' '.join(str(i) for i,pages in enumerate(expected) if pages)
        assert m.text(4,58,12).strip() == visible
        assert all(m.ti[unit*256+2] == 0x8100 and
                   m.ti[unit*256+3] == (0x4101 if pairs[unit][0] and pairs[unit][0] == pairs[unit][1] else 0x4001) and
                   m.ti[unit*256+10] == 0x00FF and
                   m.ti[unit*256+4] == m.ti[unit*256+5] == (0x10E4 if unit == 0 else 0x36E4)
                   for unit in range(len(pairs)))
        pages = sum(expected)
        assert struct.unpack('<H', m.cpu.mem_read(m.base+0xD0, 2))[0] == pages*64-1024
        probes = bus_checks(m, pairs)
        m.write_bus(0x180000, b'KEEP')
        cold = len(m.ti_trace['cold'])
        m.script_after_post = []
        m.boot(warm=True, count=30000000)
        assert len(m.ti_trace['cold']) == cold, 'Warm restart re-entered destructive probe'
        assert all(m.ti[unit*256+2] == 0x8100 for unit in range(len(pairs)))
        m.controls[0xE1] |= 0x20
        key = m.ram_key(0x180000)
        assert m.ram_banks[key[0],key[1]][key[2]:key[2]+4] == b'KEEP'
        assert bytes(m.nvram[0x240:0x300]) == preserved
        rows.append(dict(controllers=pairs, installed_kib=pages*64,
                         bank_counts=counts, cold=True, warm=True,
                         signed_disk_boot=True, bus_edges=probes,
                         original_nv_preserved=True))
    return rows


def rejection_checks(image):
    rows = []
    for fault in ('fourth', 'hole', 'identity', 'atu'):
        pairs = ((16,16),)* (4 if fault == 'fourth' else 3)
        m = port_tests.machine(image, controllers=pairs, cache=True)
        if fault == 'hole':
            m.ti[0x100] = 0xFFFF
        elif fault == 'identity':
            m.ti[0] = 0x0300
        elif fault == 'atu':
            m.ti[0x800] = 0x1100
        try:
            m.boot(count=1000000)
        except AssertionError as error:
            assert 'firmware halt' in str(error), str(error)
        else:
            raise AssertionError(('Unsupported topology accepted',fault))
        assert not m.nv_writes
        rows.append(dict(fault=fault,rejected=True))
    m = port_tests.machine(image, cache=True)
    m.boot(count=30000000)
    cold = len(m.ti_trace['cold'])
    # A stale/inconsistent persisted inventory must force a fresh cold probe.
    m.cpu.mem_write(m.base+0x1000,b'\x3F\x00')
    m.script_after_post = []
    m.boot(warm=True,count=30000000)
    assert len(m.ti_trace['cold']) > cold
    rows.append(dict(stale_inventory_reprobed=True))
    return rows


def ram_checks(image):
    rows = []
    seed = port_tests.machine(image,cache=True)
    seed.boot()
    for pairs in (((16,16),),((16,16),(64,64),(64,64))):
        m = port_tests.machine(image,controllers=pairs,cache=False)
        m.cmos[:] = seed.cmos
        m.nvram[:] = seed.nvram
        m.script_after_post = []
        if pairs == ((16,16),(64,64),(64,64)):
            decoder = m.ram_key
            m.ram_key = lambda address: None if 0xFE0000 <= address < 0x1000000 else decoder(address)
        observed = []
        def complete(mm,address):
            if address == 0xF0000+mm.symbol('init_peripherals'):
                assert 'Passed' in mm.text(6,34,19)
                assert mm.cpu.mem_read(mm.base+0x50,1) == b'\x04'
                observed.append(True)
        m.code_observer = complete
        m.boot(count=100000000)
        assert observed and m.booted
        if len(pairs) == 3:
            assert struct.unpack('<H',m.cpu.mem_read(m.base+0xD0,2))[0] == 15232
        rows.append(dict(controllers=pairs,cache=False,ram_test_passed=True,
                         signed_disk_boot=True,reads=m.ram_reads))
    return rows


def cache_off_checks(image):
    """Compare the complete executed cache-Off window with native OEM code."""
    raw = oem_image()
    assert hashlib.sha256(raw).hexdigest() == OEM_SHA256
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    rows = []
    for value in (0, 2, 0x80, 0x82, 0x8C, 0x8E, 0x55, 0xFF):
        old = Tiger(image, controllers=((16,16),))
        records = []
        def capture(m, start, stop, entry, registers, original=False):
            instructions, io, pending = [], [], []
            def observer(cpu, address, size, unused):
                if pending:
                    io.append(('in', pending.pop(), cpu.reg_read(x.UC_X86_REG_AL)))
                if not 0xF0000+start <= address < 0xF0000+stop:
                    # The two native helpers live outside the main window.
                    if not original or not 0xF23FC <= address < 0xF2414:
                        return
                ins = next(decoder.disasm(bytes(cpu.mem_read(address,size)), address & 65535))
                if original and (address & 65535) in (0x93AD,0x93B0,0x93B3):
                    return  # Unused private OEM bookkeeping is omitted.
                operand = ins.op_str
                if ins.mnemonic.startswith('j') or (ins.mnemonic == 'mov' and operand.startswith('bp,')):
                    operand = re.sub(r'0x[0-9a-f]+','target',operand)
                instructions.append((ins.mnemonic,operand))
                if ins.mnemonic == 'in':
                    pending.append(int(operand.split(', ')[1],0))
                if ins.mnemonic == 'out':
                    io.append(('out',int(operand.split(', ')[0],0),cpu.reg_read(x.UC_X86_REG_AL)))
                assert not cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200
            from unicorn import UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
            def memory(cpu,kind,address,size,value,unused):
                ip = cpu.reg_read(x.UC_X86_REG_IP)
                assert not (start <= ip < stop or original and 0x23FC <= ip < 0x2414), ('RAM in E2 window',hex(ip),hex(address))
            h = m.cpu.hook_add(UC_HOOK_CODE,observer)
            mem = m.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE,memory)
            try:
                window(m,entry,stop,registers,raw if original else None,
                       record_writes=records if original else None)
            finally:
                m.cpu.hook_del(h)
                m.cpu.hook_del(mem)
            return instructions,io
        old.controls[0xE2] = value
        old.controls[0xE0] = 0xFF
        native, native_io = capture(old,0x92EB,0x93C1,0x92EB,(),True)
        assert records == [(0x2FF,0)]
        expected_io = [('out',0x5A,0xE2),('in',0x5B,value),
                       ('out',0x5A,0xE2),('out',0x5B,value|2),('in',0x5F,0x80),
                       ('out',0x5A,0xE0),('out',0x5B,0),
                       ('out',0x5A,0xE2),('out',0x5B,value&0xFD)]
        assert native_io == expected_io, native_io
        for enabled in (False,True):
            for flags in (0x46,0x246):
                m = Tiger(image,controllers=((16,16),),cache=enabled)
                m.controls[0xE2],m.controls[0xE0] = value,0xFF
                registers = ((x.UC_X86_REG_SS,0),(x.UC_X86_REG_SP,0x8000),
                             (x.UC_X86_REG_FS,0x9E00),(x.UC_X86_REG_EFLAGS,flags))
                saved = tuple((reg,0x12340000+i*0x1111) for i,reg in enumerate(
                    (x.UC_X86_REG_EAX,x.UC_X86_REG_EBX,x.UC_X86_REG_ECX,x.UC_X86_REG_EDX,
                     x.UC_X86_REG_ESI,x.UC_X86_REG_EDI,x.UC_X86_REG_EBP)))
                start,end = m.symbol('mitsubishi_cache_off_begin'),m.symbol('mitsubishi_cache_off_end')
                instructions,io = capture(m,start,end,m.symbol('mitsubishi_cache_off_initialize'),
                                           registers+saved)
                if enabled:
                    assert not io and m.controls[0xE0] == 0xFF and m.controls[0xE2] == value
                else:
                    assert instructions == native, (instructions,native)
                    assert io == native_io and m.controls[0xE0] == 0 and m.controls[0xE2] == value&0xFD
                window(m,end,end+3,registers=((x.UC_X86_REG_SS,0),))
                assert m.cpu.reg_read(x.UC_X86_REG_SP) == 0x8000
                assert m.cpu.reg_read(x.UC_X86_REG_EFLAGS) == flags
                assert all(m.cpu.reg_read(reg) == data for reg,data in saved)
                assert not m.nv_writes
                rows.append(dict(E2=value,cache_enabled=enabled,IF=bool(flags&0x200),
                                 complete_native_window=not enabled,registers_and_flags_preserved=True))
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, default=PORT/'build/expansion-init/baios-mp386.bin')
    parser.add_argument('--case', choices=('original', 'sequence', 'mapper', 'routing', 'boot', 'reject', 'ram', 'cache-off'), required=True)
    args = parser.parse_args()
    tests = {'original': original_windows,
             'sequence':lambda p: [oem_controller_policy(p),*early_sequence_checks(p),reset_reference(p)],
             'mapper': lambda p: [mapper_comparison(p, ((16,16),(64,64),(64,64))),
                                  mapper_comparison(p, ((16,16),(0,0),(64,16)))],
             'routing': normal_policy_checks,
             'boot': boot_checks, 'reject': rejection_checks, 'ram': ram_checks,
             'cache-off': cache_off_checks}
    result = tests[args.case](args.image)
    output = args.image.parent/('memory-'+args.case+'.json')
    output.write_text(json.dumps(dict(case=args.case, result=result), indent=2)+'\n')
    print('PASS', args.case, json.dumps(result))


if __name__ == '__main__':
    main()
