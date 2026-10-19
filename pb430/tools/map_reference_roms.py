"""Reconstruct both supplied ROMs and retain every decoded instruction and CFG edge."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess

from capstone import Cs, CS_ARCH_X86, CS_MODE_16, CS_GRP_CALL, CS_GRP_JUMP, CS_GRP_RET, CS_GRP_IRET
from capstone.x86_const import X86_OP_IMM
from build import SOURCE_HASHES

PORT = Path(__file__).resolve().parents[1]

# These entries come from the annotated hardware evidence, not a scan for opcodes.
PB_ENTRIES = {
    0xE05B: 'normal_reset', 0xE111: 'reset_continuation',
    0xF163: 'initial_chipset_table', 0x8E88: 'warm_cache_prepare',
    0x8F07: 'cold_sram_probe', 0x9306: 'timing_table_executor',
    0x94B1: 'shadow_finish', 0x9631: 'software_restart_cache',
    0x968E: 'pulse_restart_cache', 0x9706: 'late_cache_owner',
    0x9795: 'cache_fill', 0x97C7: 'late_cache_parent',
    0x97D3: 'parent_controller_policy', 0x9808: 'controller_speed_pin',
    0x98BC: 'dram_map', 0x9D63: 'cache_ranges',
    0xA168: 'chipset_read', 0xA171: 'chipset_write',
    0xDC2C: 'cmos_read', 0x4C02: 'boot_tail',
    0x7E8B: 'restart_dispatch', 0x7F27: 'software_restart',
}


def decode(raw, address):
    decoder = Cs(CS_ARCH_X86, CS_MODE_16)
    decoder.detail = True
    return next(decoder.disasm(raw[address:address+15], address, count=1), None)


def graph(raw, seeds, segment, inline_print=()):
    decoded, edges, unresolved = {}, [], []
    inline_words = {}
    continuations = {}
    strings = {}
    pending = list(seeds)
    while pending:
        address = pending.pop()
        while 0 <= address < len(raw) and address not in decoded:
            ins = decode(raw, address)
            if ins is None:
                unresolved.append([f'{address:04X}', 'invalid instruction'])
                break
            decoded[address] = ins
            following = address + ins.size
            # ACC386 uses an immutable ROM word as the return stack for these calls.
            if ins.bytes[:1] == b'\xBC' and ins.size == 3 and raw[following:following+1] == b'\xE9':
                slot = struct.unpack_from('<H', raw, address+1)[0]
                if slot == address+6 and slot+2 <= len(raw):
                    resume = struct.unpack_from('<H', raw, slot)[0]
                    if resume == slot+2:
                        inline_words[slot] = resume
                        edges.append([f'{address:04X}', 'rom-stack-return', f'{resume:04X}'])
                        pending.append(resume)
            # Direct stackless calls put the continuation immediately after JMP (or NOP).
            if ins.mnemonic == 'mov' and len(ins.operands) == 2 and ins.operands[1].type == X86_OP_IMM:
                register = ins.op_str.split(',')[0]
                resume = ins.operands[1].imm & 0xFFFF
                jump = decode(raw, following)
                if register in ('bp', 'di', 'si', 'bx', 'dx') and jump and jump.mnemonic == 'jmp' and jump.operands[0].type == X86_OP_IMM and resume in (following+jump.size, following+jump.size+1):
                    continuations[address] = resume
                    edges.append([f'{address:04X}', f'{register}-continuation', f'{resume:04X}'])
                    pending.append(resume)
            transfer = ins.group(CS_GRP_CALL) or ins.group(CS_GRP_JUMP)
            if transfer:
                target = None
                immediates = [op.imm for op in ins.operands if op.type == X86_OP_IMM]
                if ins.mnemonic in ('ljmp', 'lcall') and len(immediates) == 2:
                    target = (immediates[0] << 4) + immediates[1] - (segment << 4)
                elif len(immediates) == 1:
                    target = immediates[0] & 0xFFFF
                if target is not None and 0 <= target < len(raw):
                    edges.append([f'{address:04X}', ins.mnemonic, f'{target:04X}'])
                    pending.append(target)
                    if ins.group(CS_GRP_CALL) and target in inline_print:
                        end = raw.find(b'\0', following)
                        assert end >= following, 'Unterminated inline string'
                        strings[following] = end+1
                        following = end+1
                else:
                    unresolved.append([f'{address:04X}', f'{ins.mnemonic} {ins.op_str}'])
                if ins.mnemonic in ('jmp', 'ljmp'):
                    break
            if ins.group(CS_GRP_RET) or ins.group(CS_GRP_IRET):
                break
            address = following
    return decoded, sorted(edges), sorted(unresolved), inline_words, continuations, strings


def map_rom(name, output, extra_seeds):
    raw = (PORT/'reference'/name).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == SOURCE_HASHES[name]
    stem = Path(name).stem.lower()
    sections = [(0, raw, 0xF000)] if len(raw) == 65536 else [(0, raw[:65536], 0xE000), (65536, raw[65536:], 0xF000)]
    source = ['; Byte-exact NASM reconstruction. Instruction text is an annotation.',
              '; CFG means statically reached from documented entries; it is not an execution trace.',
              '; LINEAR is an unverified decode of bytes that can be data. Never infer callers from it.',
              'bits 16', 'org 0']
    report = {'input': name, 'sha256': SOURCE_HASHES[name], 'bytes': len(raw), 'sections': []}
    for file_base, section, segment in sections:
        seeds = {0xFFF0: 'reset_vector'} if segment == 0xF000 else {3: 'video_option_entry'}
        if segment == 0xF000:
            for address in (0xE6F2,0xE82E,0xEC59,0xF065,0xF841,0xF84D,0xF859,0xFE6E,0xFF53):
                seeds[address] = f'compatibility_entry_{address:04x}'
        if name.startswith('pb430') and segment == 0xF000:
            seeds.update(PB_ENTRIES)
        if segment == 0xF000:
            seeds.update(extra_seeds)
        inline_print = (0xD3E5,) if name.startswith('pb430') and segment == 0xF000 else ()
        reached, edges, unresolved, inline_words, continuations, strings = graph(section, seeds, segment, inline_print)
        if name == 'acc386.BIN':
            assert len(inline_words)==83, 'ACC386 ROM-stack call coverage changed'
            assert inline_words[0x133C]==0x133E
            assert ['15FC','jmp','1583'] in edges
        if name.startswith('pb430') and segment==0xF000:
            assert strings[0x6F55]==0x6F75
            assert ['97C8','call','9706'] in edges and ['97CE','call','9808'] in edges
            assert 0x3B57 in reached and 0x3B58 in reached, 'Real overlapping entries must both survive'
        addresses = set(reached) | set(seeds)
        conflicts = []
        for address, ins in reached.items():
            for inner in range(address+1, address+ins.size):
                if inner in addresses:
                    conflicts.append([f'{address:04X}', f'{inner:04X}'])
        # A separate CFG listing keeps overlapping instruction entries intact.
        cfg = [f'; {name} {segment:04X}:0000; all static paths, including overlapping entries']
        for address, ins in sorted(reached.items()):
            cfg.append(f'{segment:04X}:{address:04X} file={file_base+address:05X} {ins.bytes.hex():30} {ins.mnemonic} {ins.op_str}')
        (output/f'{stem}-{segment:04x}-cfg.txt').write_text('\n'.join(line.rstrip() for line in cfg)+'\n', encoding='utf-8')
        address = 0
        while address < len(section):
            if address in seeds:
                source.append(f'; ENTRY {seeds[address]}')
            if address in inline_words:
                source.append(f'L_{file_base+address:05X}: dw 0x{inline_words[address]:04X} ; {segment:04X}:{address:04X} DATA ROM-stack return')
                address += 2
                continue
            if address in strings:
                end = strings[address]
                while address < end:
                    data = section[address:min(address+16,end)]
                    source.append(f'L_{file_base+address:05X}: db '+','.join(f'0x{b:02X}' for b in data)+f' ; {segment:04X}:{address:04X} DATA inline string '+repr(data))
                    address += len(data)
                continue
            ins = reached.get(address) or decode(section, address)
            size = ins.size if ins else 1
            # Do not let an unverified linear instruction hide a known entry.
            boundary = next((a for a in range(address+1, address+size) if a in addresses or a in inline_words), None)
            if boundary is not None:
                size = boundary-address
                ins = None
            data = section[address:address+size]
            state = 'CFG' if address in reached and ins is not None else 'LINEAR'
            annotation = f'{ins.mnemonic} {ins.op_str}' if ins else 'data / undecoded boundary'
            source.append(f'L_{file_base+address:05X}: db '+','.join(f'0x{b:02X}' for b in data)+f' ; {segment:04X}:{address:04X} {state} {annotation}')
            address += size
        report['sections'].append({'segment': f'{segment:04X}', 'file_offset': file_base,
            'seeds': {f'{k:04X}':v for k,v in seeds.items()}, 'instructions': len(reached),
            'decoded_bytes': len({a for i in reached.values() for a in range(i.address,i.address+i.size)}),
            'edges': edges, 'unresolved_transfers': unresolved, 'overlapping_entries': conflicts})
        report['sections'][-1]['rom_stack_words'] = {f'{k:04X}':f'{v:04X}' for k,v in inline_words.items()}
        report['sections'][-1]['register_continuations'] = {f'{k:04X}':f'{v:04X}' for k,v in continuations.items()}
        report['sections'][-1]['inline_strings'] = {f'{k:04X}':f'{v:04X}' for k,v in strings.items()}
    asm = output/f'{stem}.asm'
    asm.write_text('\n'.join(line.rstrip() for line in source)+'\n', encoding='utf-8')
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    binary = output/f'{stem}-reconstructed.bin'
    subprocess.run([nasm, '-f', 'bin', '-o', str(binary), str(asm)], check=True)
    assert binary.read_bytes() == raw, name
    report['byte_identical_reassembly'] = True
    (output/f'{stem}-flow.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=PORT/'build/reference-maps')
    parser.add_argument('--entries', type=Path, default=PORT/'reference/maps/entries.json')
    args = parser.parse_args()
    output = args.output.resolve()
    assert output.is_relative_to(PORT/'build'), 'Generate under pb430/build; publish reviewed text separately'
    output.mkdir(parents=True, exist_ok=True)
    entries = json.loads(args.entries.read_text()) if args.entries.exists() else {}
    results = []
    for name in SOURCE_HASHES:
        extra = {int(k,16):v for k,v in entries.get(name,{}).items()}
        report = map_rom(name, output, extra)
        results.append({k:v for k,v in report.items() if k != 'sections'})
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    main()
