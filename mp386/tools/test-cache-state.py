"""Check DOS cache state, verified CMOS acknowledgment, and native cache retry."""
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PORT.parent))
from shared.tools.ram_proof import Listing
OUT = PORT/'build/diagnostics/cache-state'
FIRMWARES = tuple(PORT/'build'/name/'baios-mp386.bin' for name in ('oem-cache','cache-state-recovery','cmos-cache'))
CONTROL = dict(zip((0xE0,0xE1,0xE2,0x92,0xE6,0xE7),(0x6B,1,0x80,0,2,0)))
TI = {0x800:0x200,0x803:0,0:0,2:0x8100,3:0x4101,7:0xAA00,
      0x100:0x100,0x102:0x8100,0x103:0x4101,0x107:0xAA00,
      0x200:0x200,0x202:0x8100,0x203:0x4101,0x207:0xAA00}


def run(raw, protected, apply=False, fault=None, diagnostic=0, read_zero=False, stored=0x6B, checksum_fault=None, firmware=None, low_test=False):
    cpu = Uc(UC_ARCH_X86,UC_MODE_16)
    cpu.mem_map(0,0x110000)
    cpu.mem_write(0x10100,raw)
    firmware = firmware or FIRMWARES[-1]
    rom = bytearray(firmware.read_bytes())
    if fault == 'rom-image':
        rom[0xFF00] ^= 1
    if fault == 'rom-owner':
        entry = Listing(firmware.with_suffix('.lst')).symbol('mp_cache_enable')
        before = rom[entry]
        rom[entry] ^= 1
        rom[0xFFF0] -= rom[entry]-before
        assert sum(rom) == sum(firmware.read_bytes())
    cpu.mem_write(0xF0000,bytes(rom))
    cpu.mem_write(0x40E,struct.pack('<H',0x9E00))
    cpu.mem_write(0x413,struct.pack('<H',632))
    cpu.mem_write(0x9F004,struct.pack('<I',0x5833504D if fault != 'signature' else 0))
    cpu.mem_write(0x9F00E,bytes((stored,)))
    cpu.mem_write(0x9F01C,b'\x03\x00\x02'+bytes((7 if stored == 0 else 14,)))
    if fault == 'base':
        cpu.mem_write(0x413,struct.pack('<H',631))
    if fault == 'segment':
        cpu.mem_write(0x40E,struct.pack('<H',0x9DC0))
    if fault == 'policy':
        cpu.mem_write(0x9F00E,b'\x01')
    if fault == 'qualification':
        cpu.mem_write(0x9F01F,b'\x03')
    if fault == 'count':
        cpu.mem_write(0x9F01C,b'\x00\x00')
    cmos = bytearray((i*7+3)&255 for i in range(128))
    cmos[0x0E] = diagnostic
    cmos[0x30:0x32] = struct.pack('<H',15232)
    cmos[0x2E:0x30] = struct.pack('>H',sum(cmos[0x10:0x2E])&0xFFFF)
    if checksum_fault in ('high','low'):
        cmos[0x2E if checksum_fault == 'high' else 0x2F] ^= 1
    original_cmos = bytes(cmos)
    for name,value in (('CS',0x1000),('DS',0x1000),('ES',0x1000),('SS',0x1000),
                       ('SP',0xFF00),('IP',0x100),('CR0',0x11 if protected else 0x10),('EFLAGS',0x202)):
        cpu.reg_write(getattr(x,'UC_X86_REG_'+name),value)
    state = dict(index=0x803F,control=0xE1,output='',exit=None,reads=[],writes=[],
                 values=CONTROL.copy(),rtc_index=0,transient_rom_instructions=0,base_writes=[])
    if apply:
        state['values'][0xE0] = 0
        state['values'][0xE2] = 0x8C
        if fault == 'clock':
            state['values'][0x92] = 0x12
    def port_in(u,port,size,unused):
        state['reads'].append((port,size))
        if port == 0x26:
            return state['index']
        if port == 0x24:
            assert size == 2
            return 0x8120 if fault == 'mode' and state['index'] == 2 else TI[state['index']]
        if port == 0x5B:
            assert size == 1
            return 0 if read_zero and state['control'] == 0xE0 else state['values'][state['control']]
        if port == 0x71:
            return cmos[state['rtc_index']&127]
        if port == 0x84:
            return 0xFF
        return {0x49:0xBE,0x5E:0,0x5F:0xFF if fault == 'switch' else 0x7F}[port]
    def port_out(u,port,size,value,unused):
        state['writes'].append((port,size,value))
        assert port in ((0x26,0x5A,0x5B,0x70,0x71) if apply else (0x26,0x5A)), ('Hardware data write',port)
        if port == 0x26:
            assert size == 2
            state['index'] = value
        elif port == 0x5A:
            assert size == 1
            state['control'] = value
        elif port == 0x70:
            state['rtc_index'] = value
        elif port == 0x71:
            assert state['rtc_index'] == 0x8E and value == diagnostic&0xBF
            assert not state['values'][0xE2]&2
            if checksum_fault != 'latch':
                cmos[0x0E] = value
        else:
            assert size == 1 and state['control'] in (0xE0,0xE2)
            state['values'][state['control']] = value
    def interrupt(u,vector,unused):
        assert vector == 0x21
        assert struct.unpack('<H',u.mem_read(0x413,2))[0] == (631 if fault == 'base' else 632), 'Temporary RAM size reached DOS'
        ah = u.reg_read(x.UC_X86_REG_AH)
        if ah == 9:
            address = u.reg_read(x.UC_X86_REG_DS)*16+u.reg_read(x.UC_X86_REG_DX)
            state['output'] += bytes(u.mem_read(address,200)).split(b'$')[0].decode('ascii')
        elif ah == 2:
            state['output'] += chr(u.reg_read(x.UC_X86_REG_DL))
        else:
            assert ah == 0x4C
            state['exit'] = u.reg_read(x.UC_X86_REG_AL)
            u.emu_stop()
    cpu.hook_add(UC_HOOK_INSN,port_in,None,1,0,x.UC_X86_INS_IN)
    cpu.hook_add(UC_HOOK_INSN,port_out,None,1,0,x.UC_X86_INS_OUT)
    cpu.hook_add(UC_HOOK_INTR,interrupt)
    def memory_write(u,access,address,size,value,unused):
        assert not state['values'][0xE2]&2, ('RAM/stack write in transient cache window',hex(address))
        if address < 0x415 and address+size > 0x413:
            assert low_test and address == 0x413 and size == 2
            assert not u.reg_read(x.UC_X86_REG_EFLAGS)&0x200, 'RAM input changed with IRQs enabled'
            state['base_writes'].append(value)
    cpu.hook_add(UC_HOOK_MEM_WRITE,memory_write)
    def instruction(u,address,size,unused):
        if state['values'][0xE2]&2:
            assert 0xF0000 <= address < 0x100000, ('Cache window executed outside ROM',hex(address))
            state['transient_rom_instructions'] += 1
    cpu.hook_add(UC_HOOK_CODE,instruction)
    cpu.emu_start(0x10100,0x30000,count=1000000)
    assert cpu.reg_read(x.UC_X86_REG_EFLAGS)&0x200
    assert cpu.reg_read(x.UC_X86_REG_SP) == 0xFF00, 'ROM/DOS return frame leaked stack'
    if protected:
        assert state['exit'] == 1 and not state['reads'] and not state['writes']
    elif fault and fault.startswith('rom-'):
        assert state['exit'] == 2 and not state['reads'] and not state['writes']
        assert 'Unknown or changed bAIos ROM. No hardware changed.' in state['output']
    elif checksum_fault:
        assert state['exit'] == 2 and state['index'] == 0x803F and state['rtc_index'] == 0x0D
        assert not any(row[0] == 0x5B for row in state['writes'])
        assert 'AT CMOS checksum invalid or not acknowledged. Cache request skipped.' in state['output']
        assert bytes(cmos) == original_cmos
    elif fault:
        assert state['exit'] == 2 and not any(row[0] in (0x5B,0x70) for row in state['writes'])
        assert state['index'] == 0x803F
        if fault not in ('switch','mode','clock'):
            assert 'No qualified bAIos cache policy' in state['output']
            values = (631 if fault == 'base' else 632,0x9DC0 if fault == 'segment' else 0x9E00,
                      0 if fault == 'signature' else 0x5833,0 if fault == 'signature' else 0x504D,
                      3 if fault == 'qualification' else 14,1 if fault == 'policy' else 0x6B,
                      0 if fault == 'count' else 3)
            assert ('BOOT KB/EBDA/magic-hi/lo/flags/policy/MCUs: '+
                    ' '.join(f'{v:04X}' for v in values)+' \r\n') in state['output']
    elif apply:
        effective = diagnostic&0xBF
        expected = 0 if effective&0x80 else (0x69 if low_test else 0x6B)
        assert state['exit'] == 0 and state['index'] == 0x803F
        assert state['values'][0xE0] == expected and state['values'][0xE2] == 0x8C
        assert state['rtc_index'] == 0x0D
        assert state['transient_rom_instructions'] > 30
        assert cpu.mem_read(0x9F00E,1) == bytes((expected,))
        if expected:
            assert cpu.mem_read(0x9F01F,1) == b'\x0E'
        assert [row[2] for row in state['writes'] if row[0] == 0x5B] == [0x8E,expected,0x8C]
        assert f'CMOS diagnostic 0E: {diagnostic:02X} -> {effective:02X}\r\n' in state['output']
        assert f'Stored policy {stored:02X}; requested {expected:02X}; after E0/E2: {(0 if read_zero else expected):02X} 8C ' in state['output']
        assert ('Diagnostic gate kept cache off' if expected == 0 else 'Run the same benchmark now.') in state['output']
        if low_test:
            assert state['base_writes'] == [256,632]
            if expected:
                assert 'Run TGENABLE to restore the normal cache policy.' in state['output']
    else:
        assert state['exit'] == 0 and state['index'] == 0x803F
        assert state['reads'] == [(0x26,2)]+[(p,1) for p in (0x49,0x5E,0x5F)]+[(0x5B,1)]*6+[(0x24,2)]*14
        assert len(state['writes']) == 21
        assert 'PORT 49/5E/5F: BE 00 7F \r\n' in state['output']
        assert 'CONTROL E0/E1/E2/92/E6/E7: 6B 01 80 00 02 00 \r\n' in state['output']
        assert 'BOOT KB/EBDA/magic-hi/lo/flags/policy/MCUs: 0278 9E00 5833 504D 000E 006B 0003 \r\n' in state['output']
        assert 'ATU ID/CTRL3: 0200 0000 \r\n' in state['output']
        for unit in range(3):
            assert f'{unit*256:04X} 8100 4101 AA00 \r\n' in state['output']
    expected_cmos = bytearray(original_cmos)
    if apply and not protected and not fault and not checksum_fault:
        expected_cmos[0x0E] &= 0xBF
    assert bytes(cmos) == bytes(expected_cmos), 'Settings or unrelated diagnostic bits changed'
    assert struct.unpack('<H',cpu.mem_read(0x413,2))[0] == (631 if fault == 'base' else 632)
    if protected or fault or checksum_fault or not low_test:
        assert not state['base_writes'], 'Temporary BDA change on a refused or ordinary request'
    return state


def rom_owners():
    """Embed exact owner bytes and return targets for the installed candidates."""
    rows = []
    for path in FIRMWARES:
        raw = path.read_bytes()
        listing = Listing(path.with_suffix('.lst'))
        spans = []
        for first,last in (('mp_cache_record_read','mp_memory_finish'),('mp_cache_enable','mp_cache_text'),
                           ('oem_cache_23FC','oem_cache_2454')):
            begin,end = listing.symbol(first),listing.symbol(last)
            spans.append((begin,raw[begin:end]))
        begin,end = listing.symbol('oem_cache_92EB'),listing.symbol('oem_cache_93C1')+1
        spans.append((begin,raw[begin:end]))
        iret = listing.symbol('default_iret')
        assert raw[iret] == 0xCF
        spans.append((iret,b'\xCF'))
        rows.append(dict(name=path.parent.name,sum32=sum(raw),entry=listing.symbol('mp_cache_enable'),iret=iret,
                         spans=sorted(spans)))
    rows.sort(key=lambda row:row['sum32'])
    assert len({row['sum32'] for row in rows}) == len(rows)
    lines = [f'cache_rom_count equ {len(rows)}','cache_roms:']
    for i,row in enumerate(rows):
        lines.extend((f"dd 0x{row['sum32']:08X}",f"dw 0x{row['entry']:04X},0x{row['iret']:04X},cache_rom_{i},{len(row['spans'])}"))
    for i,row in enumerate(rows):
        lines.append(f'cache_rom_{i}:')
        for offset,payload in row['spans']:
            assert payload
            lines.append(f'dw 0x{offset:04X},{len(payload)}')
            for j in range(0,len(payload),16):
                lines.append('db '+','.join(f'0x{value:02X}' for value in payload[j:j+16]))
    (OUT/'rom-cache-owner.inc').write_text('\n'.join(lines)+'\n')
    return [dict(name=row['name'],sum32=f"{row['sum32']:08X}",entry=f"{row['entry']:04X}",iret=f"{row['iret']:04X}",
                 verified_bytes=sum(len(data) for _,data in row['spans'])) for row in rows]


def checksum_instructions():
    """The DOS acknowledgment uses the firmware's identical checksum owner."""
    old = Listing(PORT/'build/cmos-cache/baios-mp386.lst')
    new = Listing(OUT/'TGENABLE.lst')
    a = (PORT/'build/cmos-cache/baios-mp386.bin').read_bytes()
    b = (OUT/'TGENABLE.COM').read_bytes()
    first,last = (old.symbol(name) for name in ('update_cmos_checksum','cmos_checksum_end'))
    nfirst,nlast = (new.symbol(name) for name in ('update_cmos_checksum','cmos_checksum_end'))
    assert a[first:last] == b[nfirst:nlast], 'Shared checksum owner differs between ROM and DOS'
    return last-first


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    owners = rom_owners()
    nasm = Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe'
    def build(name,defines=()):
        subprocess.run([str(nasm),'-w+error','-f','bin','-I',str(PORT/'src')+os.sep,'-I',str(PORT.parent/'shared/src')+os.sep,'-I',str(OUT)+os.sep,
                        *defines,'-l',str(OUT/(name+'.lst')),'-o',str(OUT/(name+'.COM')),
                        str(PORT/'tools/cache-state.asm')],check=True)
    build('TGCACHE')
    raw = (OUT/'TGCACHE.COM').read_bytes()
    report = dict(size=len(raw),sum32=f'{sum(raw):08X}',real_mode=run(raw,False),protected_mode=run(raw,True))
    (OUT/'cache-state-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print(report['real_mode']['output'])
    print('PASS: exact snapshot, index restored, no configuration data writes, protected-mode refusal')
    build('TGENABLE',('-DAPPLY_CACHE_POLICY=1',))
    raw = (OUT/'TGENABLE.COM').read_bytes()
    request = dict(size=len(raw),sum32=f'{sum(raw):08X}',ROM_owners=owners,shared_checksum_owner_bytes=checksum_instructions(),
                   ROM_execution={path.parent.name:run(raw,False,apply=True,stored=0,diagnostic=0x58,firmware=path) for path in FIRMWARES},
                   applied=run(raw,False,apply=True),
                   restore_low_test=run(raw,False,apply=True,stored=0x69),
                   derived_policy=run(raw,False,apply=True,diagnostic=0x10),
                   diagnostic_gate=run(raw,False,apply=True,diagnostic=0x40),
                   zero_policy=run(raw,False,apply=True,stored=0),
                   zero_policy_checksum_acknowledged=run(raw,False,apply=True,stored=0,diagnostic=0x40),
                   zero_policy_power_gate=run(raw,False,apply=True,stored=0,diagnostic=0x80),
                   physical_58=run(raw,False,apply=True,stored=0,diagnostic=0x58),
                   power_and_checksum=run(raw,False,apply=True,stored=0,diagnostic=0xD8),
                   checksum_failures={f:run(raw,False,apply=True,stored=0,diagnostic=0x58,checksum_fault=f) for f in ('high','low','latch')},
                   mismatch_readback=run(raw,False,apply=True,read_zero=True),
                   failures={f:run(raw,False,apply=True,fault=f) for f in ('base','segment','signature','policy','qualification','count','switch','mode','clock','rom-image','rom-owner')},
                   protected_mode=run(raw,True,apply=True))
    (OUT/'cache-request-check.json').write_text(json.dumps(request,indent=2)+'\n')
    print(request['applied']['output'])
    print(request['zero_policy_checksum_acknowledged']['output'])
    print(request['physical_58']['output'])
    print('PASS: exact ROM owners, ROM-only transient execution, changed-ROM refusal, verified checksum acknowledgment, hardware gates, index/NMI/IF restoration, no transient RAM writes')
    build('TGLOW',('-DAPPLY_CACHE_POLICY=1','-DCACHE_LOW_TEST=1'))
    raw = (OUT/'TGLOW.COM').read_bytes()
    low = dict(size=len(raw),sum32=f'{sum(raw):08X}',
               ROM_execution={path.parent.name:run(raw,False,apply=True,diagnostic=0x58,firmware=path,low_test=True) for path in FIRMWARES},
               power_gate=run(raw,False,apply=True,diagnostic=0x80,low_test=True),
               checksum_failures={f:run(raw,False,apply=True,diagnostic=0x58,checksum_fault=f,low_test=True) for f in ('high','low','latch')},
               failures={f:run(raw,False,apply=True,fault=f,low_test=True) for f in request['failures']},
               protected_mode=run(raw,True,apply=True,low_test=True))
    (OUT/'cache-low-check.json').write_text(json.dumps(low,indent=2)+'\n')
    print(low['ROM_execution']['cmos-cache']['output'])
    print('PASS: OEM 69 policy via unmodified ROM, BDA restored before DOS, ordinary 6B restore, all refusal paths preserve BDA')


if __name__ == '__main__':
    main()
