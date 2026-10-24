"""Check the reversible shadow tag with the installed ROM's real AH87 owner."""
import hashlib
import json
import os
from pathlib import Path
import struct
import subprocess
import sys

from unicorn import Uc, UC_ARCH_X86, UC_MODE_16, UC_HOOK_CODE, UC_HOOK_INSN, UC_HOOK_INTR, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn import x86_const as x

PORT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PORT.parent/'shared/tools'))
from ram_proof import Listing

OUT = PORT/'build/diagnostics/shadow-alias'
IMAGE = PORT/'build/cmos-cache/baios-mp386.bin'
ROM = IMAGE.read_bytes()
assert hashlib.sha256(ROM).hexdigest() == '288ddb666ccd80b82d0173db6a0e969fc3092f1e21eaf91ba3488bbdf8783f24'
assert ROM[0xE000:0xE002] == b'\xFF\xFF'
INT15 = Listing(IMAGE.with_suffix('.lst')).symbol('int15')
FIRMWARES = tuple(PORT/'build'/name/'baios-mp386.bin' for name in ('cmos-cache','cache-state-recovery','oem-cache'))


def check(raw, shape='rom', fault=None, flags=0x246, firmware=IMAGE, chain='direct', physical=False, address_only=False, zero_base=False, upper_alias=False, tail_samples=False):
    rom = firmware.read_bytes()
    int15 = Listing(firmware.with_suffix('.lst')).symbol('int15')
    cpu = Uc(UC_ARCH_X86,UC_MODE_16)
    cpu.mem_map(0,0x2000000)
    cpu.mem_write(0xF0000,rom)
    if fault == 'rom':
        cpu.mem_write(0xF0000,bytes((rom[0]^1,)))
    segment = 0x7000 if fault == 'placement' else 0x1000
    stack = 0x2000
    cpu.mem_write(segment*16+0x100,raw)
    cpu.mem_write(0x54,struct.pack('<HH',int15,0xF000))
    if chain != 'direct':
        target = struct.pack('<HH',int15,0xF000)
        # Execute both standard forwarding forms, including the returned carry flag.
        wrapper = bytes.fromhex('2E FF 2E 00 03' if chain == 'jump' else '9C 2E FF 1E 00 03 CA 02 00')
        cpu.mem_write(0x800,wrapper)
        cpu.mem_write(0xA00,target)
        cpu.mem_write(0x54,struct.pack('<HH',0x100,0x70))
    cpu.mem_write(0x900,b'\xB8\x00\x02'+(b'\xF8' if fault in ('copy_ah','addr_copy_ah') else b'\xF9')+b'\xCA\x02\x00')
    cpu.mem_write(0x40E,struct.pack('<H',0x9E00))
    cpu.mem_write(0x9F004,struct.pack('<I',0 if fault == 'signature' else 0x5833504D))
    cpu.mem_write(0x9F010,struct.pack('<6HHBB',16,16,64,64,64,64,3,0 if fault == 'shadow_state' else 2,1))
    for reg,value in (('CS',segment),('DS',segment),('ES',segment),('SS',stack),('SP',0xFF00),
                      ('IP',0x100),('CR0',0x11 if fault == 'protected' else 0x10),('EFLAGS',flags)):
        cpu.reg_write(getattr(x,'UC_X86_REG_'+reg),value)
    original = (0xFFFF if fault == 'unmapped_backing' else 0xA55A if fault == 'same_tag' else 0x1234) if physical else 0xFFFF
    tag = 0x5AA5 if original == 0xA55A else 0xA55A
    target_map = 0x34 if fault == 'stale_map' else 0
    state = dict(index=0x803F,map=0x8020,target_map=target_map,backing=original,gate=1,control=0,output='',exit=None,
                 map_writes=[],map_ops=[],tag_writes=[],copies=0,bios_calls=0,wrapper_calls=0,ports=[])
    upper_original = 0x8184 if fault == 'upper_slot' else 0x8180
    state.update(mode=0x8100,upper=upper_original,upper_ops=[])
    tail_original = {page:0x1234^(page-0x8180) for page in range(0x8180,0x8200)}
    tail_original[0x8183] = 0xA55A
    state.update(tail_words=dict(tail_original),tail_page=0x8180)
    controls = (bytes(range(16)),bytes(range(16,32)))
    failure_call = {'copy_before':1,'copy':2,'copy_after':3,'copy_ah':2}.get(fault)
    if physical and failure_call:
        failure_call += 2
    if address_only:
        failure_call = {'addr_copy_first':1,'addr_copy_mapped':3,'addr_copy_ah':3}.get(fault)
    if upper_alias:
        failure_call = {'copy_before':3,'upper_copy':4,'copy':5,'copy_after':6,'copy_ah':5}.get(fault)
    address_pages = (0x8000,0x8100,0x8180,0x81C0)
    address_cpus = (0xA00000,0xE00000,0x1000000,0x1100000)
    baseline = bytes(512)
    address_samples = tuple(bytes((i*37+j*19+1)&255 for i in range(512)) for j in range(4))
    if shape == 'identical':
        address_samples = (baseline,)*4
    if shape == 'empty':
        address_samples = (b'\xFF'*512,)*4
    if shape == 'last_source':
        address_samples = (baseline,)*3+(address_samples[-1],)

    def inp(u,port,size,unused):
        state['ports'].append(('in',port,size))
        if port == 0x26:
            return state['index']
        if port == 0x24:
            assert size == 2
            index = state['index']
            if index == 0x800:
                return 0x200
            if upper_alias and index == 0x202:
                return state['mode']
            if upper_alias and index == 0xA400:
                assert state['mode'] == 0x8120
                return state['upper']
            if index == 0x8020:
                return state['map']
            if index == 0xA020 and physical:
                return state['target_map']
            if index in (0x9020,0xA020):
                return 0x8000 if fault == 'overlap' else 0
            if 0x803C <= index < 0x8040:
                return 0x8028+index-0x803C
            unit,reg = divmod(index,256)
            assert unit < 3
            bases = (0,0,10 if fault == 'base' else 0) if zero_base else (0,2,2 if fault == 'base' else 10)
            return {0:unit*256+bases[unit],2:0x8100,
                    3:0x4101,7:0 if fault == 'shadow' else 0xAA00}[reg]
        if port == 0x5F:
            return 0x7F if fault == 'cache' else 0xFF
        assert port == 0x5B and state['control'] == 0xE1 and size == 1
        return state['gate']

    def out(u,port,size,value,unused):
        state['ports'].append(('out',port,size,value))
        if port == 0x26:
            assert size == 2
            state['index'] = value
        elif port == 0x24:
            assert size == 2
            index = state['index']
            if upper_alias and index in (0x202,0xA400):
                assert not u.reg_read(x.UC_X86_REG_EFLAGS)&0x200
                state['upper_ops'].append((index,value))
                if index == 0x202:
                    assert value in (0x8100,0x8120)
                    if not (fault == 'upper_open' and value == 0x8120 or fault == 'upper_close' and value == 0x8100):
                        state['mode'] = value
                else:
                    assert state['mode'] == 0x8120 and value in (0x817C,upper_original)
                    if not (fault == 'upper_write' and value == 0x817C or fault == 'upper_restore' and value == upper_original):
                        state['upper'] = value
                return
            if physical:
                assert index in (0x8020,0xA020)
                allowed = (target_map,0x8000,0x8100,0x817F,0x8180,0x81C0)
                if tail_samples:
                    allowed += tuple(tail_original)
                assert value in ((0x8020,0x20) if index == 0x8020 else allowed)
            else:
                assert index == 0x8020 and value in (0x8020,0x802B)
            state['map_writes'].append(value)
            state['map_ops'].append((index,value))
            mapping = 0x8000 if address_only else 0x8180 if tail_samples else 0x817F if physical else 0x802B
            ignore = (fault == 'ignored_map' and value == mapping or
                      fault == 'restore_map' and value == mapping and sum(v == mapping for v in state['map_writes']) >= 2 or
                      fault == 'restore_owner' and index == 0xA020 and value == target_map or
                      fault == 'ignored_displace' and index == 0x8020 and value == 0x20)
            if not ignore:
                state['target_map' if index == 0xA020 else 'map'] = value
                if tail_samples and index == 0xA020 and value in tail_original:
                    state['tail_page'] = value
                    state['backing'] = state['tail_words'][value]
            assert not (state['map']&0x8000 and state['target_map']&0x8000), 'Competing RAM drivers'
        elif port == 0x5A:
            assert size == 1 and value == 0xE1
            state['control'] = value
        elif port == 0x5B:
            assert size == 1 and state['control'] == 0xE1 and value&~0x20 == 1
            state['gate'] = value
        else:
            if physical and port == 0x80:
                assert size == 1 and value == 0xE4 and fault in ('restore_owner','upper_close','upper_restore')
                state['exit'] = 'halt-E4'
                u.emu_stop()
                return
            assert port == 0x70 and size == 1 and value in (0,0x80,0x8D,0x0D)

    def read(u,access,address,size,value,unused):
        if tail_samples and 0x1000000 <= address < 0x1200000:
            assert address&0x3FFF == 0x2000 and size == 2
            page = 0x8180+(address-0x1000000)//0x4000
            state['tail_page'] = page
            state['backing'] = state['tail_words'][page]
            sample = state['backing']
            if fault == 'tail_map' and page == 0x8185:
                sample ^= 0x100
            if fault == 'tail_follow' and page == 0x81FE and sample != tail_original[page]:
                sample = tail_original[page]
            u.mem_write(address,struct.pack('<H',sample))
        if upper_alias and 0x100E000 <= address < 0x100E002:
            assert state['mode'] == 0x8100
            routed = state['upper'] == 0x817C and shape != 'no_upper'
            u.mem_write(0x100E000,struct.pack('<H',state['backing'] if routed else 0xFFFF))
        if address_only:
            for linear,sample in zip(address_cpus,address_samples):
                if linear <= address < linear+512:
                    u.mem_write(linear,sample)
                    return
            if 0xA80000 <= address < 0xA80200:
                sample = baseline
                if shape in ('relative','last_source') and state['target_map'] in address_pages:
                    sample = address_samples[address_pages.index(state['target_map'])]
                u.mem_write(0xA80000,sample)
                return
        if physical:
            for i,linear in enumerate((0xA00000,0xE00000)):
                if linear <= address < linear+16:
                    sample = b'\xFF'*16 if fault == 'control_empty' and i == 0 else controls[i]
                    u.mem_write(linear,sample)
            if 0x80000 <= address < 0x80010 and state['target_map'] in (0x8000,0x8100):
                i = int(state['target_map'] == 0x8100)
                sample = b'\xFF'*16 if fault == ('control_first','control_second')[i] else controls[i]
                u.mem_write(0x80000,sample)
        aperture = state['target_map'] in tail_original if tail_samples else state['target_map'] == 0x817F if physical else state['map'] == 0x802B
        if address < 0x82002 and address+size > 0x82000 and aperture:
            backing = 0x1234 if fault == 'backing' else state['backing']
            u.mem_write(0x82000,struct.pack('<H',backing))
        if address < 0xFE002 and address+size > 0xFE000:
            u.mem_write(0xFE000,struct.pack('<H',state['backing'] if not physical and shape != 'no_shadow' else 0xFFFF))
        if address < 0xFFE002 and address+size > 0xFFE000:
            u.mem_write(0xFFE000,struct.pack('<H',state['backing'] if shape == 'shadow_alias' else 0xFFFF))

    def write(u,access,address,size,value,unused):
        if address == 0x82000:
            assert (state['target_map'] in tail_original if tail_samples else state['target_map'] == 0x817F if physical else state['map'] == 0x802B)
            saved = tail_original[state['tail_page']] if tail_samples else original
            pattern = 0x5AA5 if saved == 0xA55A else 0xA55A
            assert size == 2 and value in (pattern,saved)
            assert not u.reg_read(x.UC_X86_REG_EFLAGS)&0x200
            state['tag_writes'].append(value)
            ignore = fault in ('ignored_tag','unmapped_backing') and value == pattern or fault == 'restore_word' and value == saved
            if not ignore:
                state['backing'] = value
                if tail_samples:
                    state['tail_words'][state['tail_page']] = value
        else:
            own = segment*16 <= address and address+size <= (segment+0x1000)*16
            own_stack = stack*16 <= address and address+size <= (stack+0x1000)*16
            assert own or own_stack, ('Unexpected external write',hex(address),size)

    def interrupt(u,vector,unused):
        if vector == 0x15:
            assert u.reg_read(x.UC_X86_REG_AX) == 0x8700
            es,si = u.reg_read(x.UC_X86_REG_ES),u.reg_read(x.UC_X86_REG_SI)
            table = bytes(u.mem_read(es*16+si,48))
            source = int.from_bytes(table[0x12:0x15],'little') | table[0x17]<<24
            if address_only:
                assert source in (0xA80000,)+address_cpus and u.reg_read(x.UC_X86_REG_CX) == 256
                if state['target_map'] in address_pages:
                    assert source == 0xA80000 and state['map'] == 0x20
                else:
                    assert state['map'] == 0x8020 and state['target_map'] == target_map
            else:
                assert state['map'] == 0x8020 and state['target_map'] == target_map
                expected_source = ((0xA00000,0xE00000)[state['copies']] if physical and state['copies'] < 2
                                   else 0x1002000+((state['copies']-2)//3)*0x4000 if tail_samples
                                   else 0x100E000 if upper_alias and state['copies'] == 3 and len(state['tag_writes']) == 1 else 0xFFE000)
                assert source == expected_source,(fault,hex(source),hex(expected_source),state['copies'])
                assert u.reg_read(x.UC_X86_REG_CX) == (8 if physical and state['copies'] < 2 else 1)
                if upper_alias:
                    assert state['mode'] == 0x8100
                    if state['copies'] >= 2:
                        assert state['upper'] == 0x817C
            state['copies'] += 1
            target = (0x200,0x70) if state['copies'] == failure_call else (int15,0xF000)
            if chain != 'direct':
                u.mem_write(0xA00,struct.pack('<HH',*target))
            current_flags = u.reg_read(x.UC_X86_REG_EFLAGS)
            ss,sp = u.reg_read(x.UC_X86_REG_SS)*16,u.reg_read(x.UC_X86_REG_SP)
            for word in (current_flags&65535,u.reg_read(x.UC_X86_REG_CS),u.reg_read(x.UC_X86_REG_IP)):
                sp = (sp-2)&65535
                u.mem_write(ss+sp,struct.pack('<H',word))
            u.reg_write(x.UC_X86_REG_SP,sp)
            u.reg_write(x.UC_X86_REG_EFLAGS,current_flags&~0x300)
            offset,owner = struct.unpack('<HH',u.mem_read(0x54,4))
            if chain == 'direct' and state['copies'] == failure_call:
                offset,owner = target
            u.reg_write(x.UC_X86_REG_CS,owner)
            u.reg_write(x.UC_X86_REG_IP,offset)
            return
        assert vector == 0x21
        assert u.reg_read(x.UC_X86_REG_EFLAGS)&0x200 == flags&0x200
        assert state['map'] == 0x8020 and state['target_map'] == target_map and state['index'] == 0x803F
        if upper_alias:
            assert state['mode'] == 0x8100 and state['upper'] == upper_original
        assert tail_samples or state['backing'] == (tag if fault in ('restore_map','restore_word') else original)
        ah = u.reg_read(x.UC_X86_REG_AH)
        if ah == 9:
            address = u.reg_read(x.UC_X86_REG_DS)*16+u.reg_read(x.UC_X86_REG_DX)
            state['output'] += bytes(u.mem_read(address,240)).split(b'$')[0].decode('ascii')
        elif ah == 2:
            state['output'] += chr(u.reg_read(x.UC_X86_REG_DL))
        else:
            assert ah == 0x4C
            state['exit'] = u.reg_read(x.UC_X86_REG_AL)
            u.emu_stop()

    def bios_entry(u,address,size,unused):
        state['bios_calls'] += 1

    def wrapper_entry(u,address,size,unused):
        state['wrapper_calls'] += 1

    cpu.hook_add(UC_HOOK_CODE,bios_entry,None,0xF0000+int15,0xF0000+int15)
    cpu.hook_add(UC_HOOK_CODE,wrapper_entry,None,0x800,0x800)
    cpu.hook_add(UC_HOOK_INSN,inp,None,1,0,x.UC_X86_INS_IN)
    cpu.hook_add(UC_HOOK_INSN,out,None,1,0,x.UC_X86_INS_OUT)
    cpu.hook_add(UC_HOOK_INTR,interrupt)
    cpu.hook_add(UC_HOOK_MEM_READ,read)
    cpu.hook_add(UC_HOOK_MEM_WRITE,write)
    cpu.emu_start(segment*16+0x100,0x2000000,count=2000000)
    if fault in ('restore_owner','upper_close','upper_restore'):
        assert state['exit'] == 'halt-E4' and not state['output']
        if fault == 'restore_owner':
            assert state['map'] == 0x20 and state['target_map'] in address_pages+(0x817F,)
        else:
            assert state['backing'] == original and state['map'] == 0x8020 and state['target_map'] == target_map
        return dict(physical=True,fault=fault,exit=state['exit'],no_competing_drivers=True,no_DOS_return=True)
    expected = 4 if fault in ('restore_map','restore_word') else 3 if fault in ('copy','copy_after','copy_ah') else 2 if fault in ('ignored_tag','unmapped_backing') else int(fault not in (None,'same_tag','stale_map'))
    if physical:
        expected = {'protected':5,'placement':6,'control_first':8,'control_second':9,'control_empty':10}.get(fault,expected)
    if upper_alias and fault == 'upper_copy':
        expected = 3
    if tail_samples and fault in ('tail_map','tail_follow'):
        expected = 8
    if address_only:
        expected = ({'relative':0,'last_source':0,'no_effect':8,'identical':10,'empty':10}[shape]
                    if fault in (None,'stale_map') else
                    {'protected':5,'placement':6,'addr_copy_first':3,'addr_copy_mapped':3,'addr_copy_ah':3}.get(fault,1))
    assert state['exit'] == expected,state
    assert state['gate'] == 1 and state['map'] == 0x8020
    assert tail_samples or state['backing'] == (tag if fault in ('restore_map','restore_word') else original)
    expected_rom = bytearray(rom)
    if fault == 'rom':
        expected_rom[0] ^= 1
    if fault in ('restore_map','restore_word'):
        if not physical:
            expected_rom[0xE000:0xE002] = b'\x5A\xA5'
        assert state['output'] == ('T4-8180\r\n' if tail_samples else 'U4\r\n' if upper_alias else 'B4\r\n') if physical else 'restore failed (reboot)' in state['output']
    assert bytes(cpu.mem_read(0xF0000,65536)) == bytes(expected_rom)
    assert cpu.reg_read(x.UC_X86_REG_SP) == 0xFF00
    assert state['wrapper_calls'] == (0 if chain == 'direct' else state['copies'])
    injected = int(failure_call is not None)
    assert state['bios_calls'] == state['copies']-injected
    if address_only:
        assert not state['tag_writes'], 'Read-only address probe wrote a RAM tag'
        assert state['output'] == f'A{expected:X}\r\n' if expected != 1 else state['output'].startswith('A1-')
        assert len(state['output'].splitlines()) == 1
        if shape in ('identical','empty') and fault is None:
            assert not state['map_ops'], 'Ambiguous samples opened a window'
        if fault in ('protected','placement'):
            assert not state['ports']
        return dict(shape=shape,fault=fault,IF=bool(flags&0x200),firmware=firmware.parent.name,chain=chain,
                    exit=state['exit'],actual_BIOS_calls=state['bios_calls'],map_ops=state['map_ops'],
                    RAM_writes=0,map_index_IF_A20_restored=True,output=state['output'])
    if tail_samples:
        assert state['output'].startswith(f'T{expected:X}'),state
        assert len(state['output'].splitlines()) == 1 and not state['upper_ops']
        assert state['tail_words'] == tail_original or fault == 'restore_word'
        if fault is None:
            assert state['output'] == 'T0\r\n'
            assert state['copies'] == 386 and len(state['tag_writes']) == 256
            assert 0x5AA5 in state['tag_writes']
        if fault in ('tail_map','tail_follow'):
            assert state['output'] == {'tail_map':'T8-8185\r\n','tail_follow':'T8-81FE\r\n'}[fault]
        return dict(fault=fault,IF=bool(flags&0x200),chain=chain,exit=state['exit'],
                    actual_BIOS_calls=state['bios_calls'],tag_writes=len(state['tag_writes']),
                    words_restored=fault != 'restore_word',map_index_IF_A20_restored=True,output=state['output'])
    if upper_alias:
        suffix = {'rom':'P','shadow_alias':'B','no_upper':'N'}[shape] if expected == 0 else ''
        if expected == 1:
            assert state['output'].startswith('U1-')
        else:
            assert state['output'] == f'U{expected:X}{suffix}\r\n',state
        assert len(state['output'].splitlines()) == 1
        assert state['mode'] == 0x8100 and state['upper'] == upper_original
        if fault is None:
            assert state['tag_writes'] == [tag,original]
            assert [v for i,v in state['upper_ops'] if i == 0xA400] == [0x817C,upper_original]
        return dict(shape=shape,fault=fault,IF=bool(flags&0x200),firmware=firmware.parent.name,chain=chain,
                    exit=state['exit'],actual_BIOS_calls=state['bios_calls'],upper_ops=state['upper_ops'],
                    tag_writes=state['tag_writes'],all_maps_mode_index_IF_A20_restored=True,output=state['output'])
    if fault in (None,'same_tag','stale_map'):
        if physical:
            assert state['map_ops'] == [operation for page in (0x8000,0x8100,0x817F,0x817F)
                                        for operation in ((0x8020,0x20),(0xA020,page),(0xA020,target_map),(0x8020,0x8020))]
            assert state['output'] == ('B0R\r\n' if shape == 'shadow_alias' else 'B0H\r\n')
        else:
            assert state['map_writes'] == [0x802B,0x8020,0x802B,0x8020]
        assert state['tag_writes'] == [tag,original]
        low = 'FFFF' if physical or shape == 'no_shadow' else 'A55A'
        high = f'{tag:04X}' if shape == 'shadow_alias' else 'FFFF'
        before = f'{original:04X}' if physical and shape == 'shadow_alias' else 'FFFF'
        if not physical:
            assert f'Low     FE000: FFFF {low} FFFF' in state['output']
            assert f'High   FFE000: {before} {high} {before}' in state['output']
    elif fault in ('protected','placement'):
        assert not state['ports']
    elif fault not in ('copy','copy_after','copy_ah','ignored_tag','unmapped_backing','restore_map','restore_word'):
        assert not state['tag_writes']
    if fault and expected == 1:
        if fault not in ('protected','placement'):
            if physical:
                assert state['output'].startswith('B1-')
            else:
                assert 'Guard ' in state['output'] and ': expected ' in state['output'] and ' read ' in state['output']
                assert 'Last TI index / value:' in state['output']
    if fault == 'shadow_state':
        assert 'Guard 0004: expected 00000002 read 00000000' in state['output']
    if fault == 'shadow' and not physical:
        assert 'Guard 000C: expected 0000AA00 read 00000000' in state['output']
    if fault == 'ignored_map':
        guard = '0000817F read 00000000' if physical else '0000802B read 00008020'
        assert state['output'] == 'B1-0014\r\n' if physical else 'Guard 0014: expected '+guard in state['output']
    if physical:
        assert len(state['output'].splitlines()) == 1 and state['output'].startswith('B')
        if fault in ('ignored_tag','unmapped_backing','control_first','control_second','control_empty'):
            assert state['output'] == {2:'B2\r\n',8:'B8\r\n',9:'B9\r\n',10:'BA\r\n'}[expected]
        if fault in ('control_first','control_second','control_empty'):
            assert not state['tag_writes']
    return dict(shape=shape,fault=fault,IF=bool(flags&0x200),exit=state['exit'],
                firmware=firmware.parent.name,chain=chain,physical=physical,wrapper_calls=state['wrapper_calls'],
                actual_BIOS_calls=state['bios_calls'],map_writes=state['map_writes'],tag_writes=state['tag_writes'],
                word_restored=fault not in ('restore_map','restore_word'),map_index_IF_A20_restored=True,output=state['output'])


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    owners = sorted(sum(p.read_bytes()) for p in FIRMWARES)
    assert len(set(owners)) == len(owners)
    assert all(p.read_bytes()[0xE000:0xE002] == b'\xFF\xFF' for p in FIRMWARES)
    lines = [f'%define ALIAS_ROM_SUM32 0x{sum(ROM):08X}',f'%define ALIAS_ROM_COUNT {len(owners)}','%macro ALIAS_ROM_ROWS 0']
    for checksum in owners:
        lines += [f'dd 0x{checksum:08X}']
    lines += ['%endmacro']
    (OUT/'shadow-alias-rom.inc').write_text('\n'.join(lines)+'\n')
    nasm = Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe'
    subprocess.run([str(nasm),'-w+error','-f','bin','-I',str(OUT)+os.sep,
                    '-l',str(OUT/'TGSHADOW.lst'),'-o',str(OUT/'TGSHADOW.COM'),str(PORT/'tools/shadow-alias.asm')],check=True)
    raw = (OUT/'TGSHADOW.COM').read_bytes()
    offset = Listing(OUT/'TGSHADOW.lst').symbol('write_map')
    assert raw[offset:offset+6] == bytes.fromhex('92 E7 26 92 E7 24'), 'Existing mp_mcu_write sequence changed'
    results = [check(raw,shape,flags=flags) for shape in ('rom','shadow_alias','no_shadow') for flags in (0x46,0x246)]
    results += [check(raw,firmware=p) for p in FIRMWARES]
    results += [check(raw,shape,firmware=p,chain=chain) for p in FIRMWARES
                for chain in ('jump','call') for shape in ('rom','shadow_alias','no_shadow')]
    results += [check(raw,fault=f) for f in ('protected','placement','signature','cache','shadow','shadow_state','overlap','rom',
                                           'backing','ignored_map','ignored_tag','copy_before','copy','copy_after','copy_ah','restore_map')]
    results += [check(raw,fault=f,chain=chain) for chain in ('jump','call')
                for f in ('copy_before','copy','copy_after','copy_ah','restore_map')]
    report = dict(size=len(raw),sum32=f'{sum(raw):08X}',ROM_SHA256=hashlib.sha256(ROM).hexdigest(),cases=results,
                  scope='Actual installed-ROM AH87; modeled RAM/ROM/shadow routes. This does not prove physical routing.')
    (OUT/'shadow-alias-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS',len(results),'contexts;',len(raw),'bytes; SUM32',report['sum32'])
    print(results[0]['output'])
    print(results[2]['output'])
    assert hashlib.sha256(raw).hexdigest() == '918870b2b4bac53391b098eb912e7121b4d81ce4c2917d0b7962b65a98a58f71', 'Validated TGSHADOW changed'
    subprocess.run([str(nasm),'-w+error','-f','bin','-DMP386_RAM_BACKING','-I',str(OUT)+os.sep,
                    '-l',str(OUT/'TGBACK.lst'),'-o',str(OUT/'TGBACK.COM'),str(PORT/'tools/shadow-alias.asm')],check=True)
    ram = (OUT/'TGBACK.COM').read_bytes()
    cases = [check(ram,shape,firmware=p,chain=chain,physical=True) for p in FIRMWARES
             for chain in ('direct','jump','call') for shape in ('rom','shadow_alias')]
    cases += [check(ram,fault=f,chain='call',physical=True) for f in ('same_tag','stale_map','protected','placement','signature','cache','shadow',
              'overlap','rom','base','ignored_displace','ignored_map','ignored_tag','unmapped_backing','control_first','control_second','control_empty',
              'copy_before','copy','copy_after','copy_ah','restore_map','restore_word','restore_owner')]
    backing = dict(size=len(ram),sum32=f'{sum(ram):08X}',cases=cases,
                   scope='Native known-ROM AH87 and OEM-derived aperture handover. The fixture cannot prove physical DRAM or ROM priority.')
    (OUT/'ram-backing-check.json').write_text(json.dumps(backing,indent=2)+'\n')
    print('PASS hidden RAM',len(cases),'contexts;',len(ram),'bytes; SUM32',backing['sum32'])
    print(cases[0]['output'])
    assert hashlib.sha256(ram).hexdigest() == '49326a776eddfc679bb09ce841929f90e80d4fedb3a2294f5111863bdb6f92fb', 'Bench TGBACK changed'
    subprocess.run([str(nasm),'-w+error','-f','bin','-DMP386_RAM_BACKING','-DMP386_APERTURE_ADDRESS','-I',str(OUT)+os.sep,
                    '-l',str(OUT/'TGADDR.lst'),'-o',str(OUT/'TGADDR.COM'),str(PORT/'tools/shadow-alias.asm')],check=True)
    addr = (OUT/'TGADDR.COM').read_bytes()
    addresses = [check(addr,shape,chain=chain,firmware=p,physical=True,address_only=True) for p in FIRMWARES
                 for chain in ('direct','jump','call') for shape in ('relative','last_source','no_effect','identical','empty')]
    addresses += [check(addr,'relative',fault=f,chain='call',physical=True,address_only=True) for f in
                  ('protected','placement','signature','cache','shadow','base','stale_map','ignored_displace','ignored_map',
                   'addr_copy_first','addr_copy_mapped','addr_copy_ah','restore_owner')]
    addresses += [check(addr,'relative',flags=0x46,physical=True,address_only=True)]
    report = dict(size=len(addr),sum32=f'{sum(addr):08X}',cases=addresses,
                  scope='Read-only RAM fingerprints through actual ROM AH87, including calls while the exclusive aperture is active. Hardware address decoding remains modeled.')
    (OUT/'aperture-address-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS address probe',len(addresses),'contexts;',len(addr),'bytes; SUM32',report['sum32'])
    print(addresses[0]['output'])
    zero_image = PORT/'build/zero-base/baios-mp386.bin'
    zero_out = PORT/'build/diagnostics/zero-base'
    zero_out.mkdir(parents=True,exist_ok=True)
    zero_sum = sum(zero_image.read_bytes())
    (zero_out/'shadow-alias-rom.inc').write_text(
        f'%define ALIAS_ROM_SUM32 0x{zero_sum:08X}\n%define ALIAS_ROM_COUNT 1\n'
        f'%macro ALIAS_ROM_ROWS 0\ndd 0x{zero_sum:08X}\n%endmacro\n')
    subprocess.run([str(nasm),'-w+error','-f','bin','-DMP386_RAM_BACKING','-DMP386_ZERO_BASE',
                    '-I',str(zero_out)+os.sep,'-l',str(zero_out/'TGZERO.lst'),
                    '-o',str(zero_out/'TGZERO.COM'),str(PORT/'tools/shadow-alias.asm')],check=True)
    zero = (zero_out/'TGZERO.COM').read_bytes()
    contexts = [check(zero,shape,firmware=zero_image,chain=chain,physical=True,zero_base=True)
                for chain in ('direct','jump','call') for shape in ('rom','shadow_alias')]
    contexts += [check(zero,firmware=zero_image,chain='call',physical=True,zero_base=True,fault=f)
                 for f in ('base','control_first','control_second','control_empty','ignored_displace',
                           'ignored_map','ignored_tag','copy','copy_after','restore_word','restore_owner')]
    contexts += [check(zero,firmware=zero_image,physical=True,zero_base=True,flags=0x46)]
    result = dict(size=len(zero),sum32=f'{sum(zero):08X}',cases=contexts,
                  scope='Repeat the guarded low-aperture controls under the restored cold-boot zero-base policy; hardware decoding is modeled.')
    (zero_out/'zero-base-check.json').write_text(json.dumps(result,indent=2)+'\n')
    print('PASS zero-base probe',len(contexts),'contexts;',len(zero),'bytes; SUM32',result['sum32'])
    print(contexts[0]['output'])
    assert hashlib.sha256(zero).hexdigest() == '6c2a74510044398937a8ff69e620b7255d788a158c10acc642d897c7f9a90f6e', 'Bench TGZERO changed'
    subprocess.run([str(nasm),'-w+error','-f','bin','-DMP386_RAM_BACKING','-DMP386_ZERO_BASE','-DMP386_UPPER_ALIAS',
                    '-I',str(zero_out)+os.sep,'-l',str(zero_out/'TGUPPER.lst'),
                    '-o',str(zero_out/'TGUPPER.COM'),str(PORT/'tools/shadow-alias.asm')],check=True)
    upper = (zero_out/'TGUPPER.COM').read_bytes()
    listing = Listing(zero_out/'TGUPPER.lst')
    read = listing.symbol('upper_read')+3
    write = listing.symbol('upper_write_map')
    assert upper[read:read+8] == bytes.fromhex('E7 26 EB 00 EB 00 E5 24'), 'Native upper-read I/O delays changed'
    assert upper[write:write+10] == bytes.fromhex('92 E7 26 EB 00 EB 00 92 E7 24'), 'Native upper-write I/O delays changed'
    cases = [check(upper,shape,firmware=zero_image,chain=chain,physical=True,zero_base=True,upper_alias=True)
             for chain in ('direct','jump','call') for shape in ('rom','shadow_alias','no_upper')]
    cases += [check(upper,firmware=zero_image,chain='call',physical=True,zero_base=True,upper_alias=True,fault=f)
              for f in ('base','cache','signature','rom','protected','placement','control_first','control_second',
                        'upper_slot','upper_open','upper_write','upper_close','upper_restore','upper_copy',
                        'copy_before','copy','copy_after','copy_ah','ignored_displace','ignored_map','ignored_tag',
                        'restore_word','restore_owner')]
    cases += [check(upper,firmware=zero_image,physical=True,zero_base=True,upper_alias=True,flags=0x46)]
    report = dict(size=len(upper),sum32=f'{sum(upper):08X}',cases=cases,
                  scope='Relocate one upper slot using the native single-entry MODE view; actual zero-base-ROM AH87, modeled arbitration.')
    (zero_out/'upper-alias-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS upper alias probe',len(cases),'contexts;',len(upper),'bytes; SUM32',report['sum32'])
    print(cases[0]['output'])
    assert hashlib.sha256(upper).hexdigest() == '852c9990e2647b6cf20d74a7b7b7cc30977556435e6e5d14b2d5e7f7f9403975', 'Bench TGUPPER changed'
    subprocess.run([str(nasm),'-w+error','-f','bin','-DMP386_RAM_BACKING','-DMP386_ZERO_BASE','-DMP386_TAIL_SAMPLES',
                    '-I',str(zero_out)+os.sep,'-l',str(zero_out/'TGTAIL.lst'),
                    '-o',str(zero_out/'TGTAIL.COM'),str(PORT/'tools/shadow-alias.asm')],check=True)
    tail = (zero_out/'TGTAIL.COM').read_bytes()
    cases = [check(tail,firmware=zero_image,chain=chain,physical=True,zero_base=True,tail_samples=True)
             for chain in ('direct','jump','call')]
    cases += [check(tail,firmware=zero_image,chain='call',physical=True,zero_base=True,tail_samples=True,fault=f)
              for f in ('tail_map','tail_follow','base','cache','signature','rom','protected','placement',
                        'control_first','control_second','copy_before','copy','copy_after','copy_ah',
                        'ignored_displace','ignored_map','ignored_tag','restore_word','restore_owner')]
    cases += [check(tail,firmware=zero_image,physical=True,zero_base=True,tail_samples=True,flags=0x46)]
    report = dict(size=len(tail),sum32=f'{sum(tail):08X}',cases=cases,
                  scope='One restored word per16KiB block above16MiB; actual installed-ROM AH87 and modeled RAM. Not a full-cell stability test.')
    (zero_out/'tail-samples-check.json').write_text(json.dumps(report,indent=2)+'\n')
    print('PASS tail samples',len(cases),'contexts;',len(tail),'bytes; SUM32',report['sum32'])
    print(cases[0]['output'])


if __name__ == '__main__':
    main()
