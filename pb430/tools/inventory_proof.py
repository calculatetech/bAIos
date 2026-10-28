"""Verify actual NASM dependencies, active owners/symbols and assembled I/O."""
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from capstone import Cs,CS_ARCH_X86,CS_MODE_16
from capstone.x86_const import X86_OP_IMM,X86_OP_REG,X86_REG_DX
from shared.tools.ram_proof import Listing

PORT=Path(__file__).resolve().parents[1]
ROOT=PORT.parent
BASE='tests/shared-source-baseline.json'
REQUIRED=('startup','memory_initialize','memory_probe_bank','cache_initialize','cache_initial_policy','cache_ranges','shadow_system_bios','shadow_system_policy','initialize_video','init_pic_pit','init_rtc','init_superio','init_at_prerequisites','init_keyboard','arm_keyboard_runtime','settings_load','chipset_apply','publish_memory_cmos','chipset_visible_ram_test','init_peripherals','init_floppy','board_floppy_configure','board_floppy_perpendicular','ata_detect_primary','init_mouse','init_fpu','setup_main','setup_post_gate','chipset_late_cache','option_rom_discovery','post_debug_summary','warm_reset','boot_retry','int08','int09','int0e','int11','int12','int13','int14','int15','int16','int17','int18','int19','int1a','int70','int74')
FORBIDDEN={0x22,0x23,0xEC,0xCF8,0xCFC}


def resolve(name,configuration):
    path=Path(name)
    if not path.is_absolute():
        path=PORT/'src'/path
    path=path.resolve()
    assert path.is_relative_to(PORT/'src') or path.is_relative_to(ROOT/'shared/src') or path==configuration or path==PORT/'reference/pb430-m27c1001.bin',('Foreign production source',str(path))
    return path


def validate(image,preprocessed,dependencies,configuration):
    source=preprocessed.read_text();owners={resolve(name,configuration) for name in re.findall(r'^%line\s+\d+\+\d+\s+(.+)$',source,re.M)}
    files={resolve(name,configuration) for name in dependencies}
    assert configuration in files,'Candidate configuration missing from NASM dependencies'
    assert owners<=files,('Emitted owner missing from real NASM dependencies',owners-files)
    hashes={};shared_matches={}
    baseline=json.loads((PORT/BASE).read_text(encoding='utf-8'))
    for path in sorted(files):
        name=path.relative_to(ROOT).as_posix();raw=path.read_bytes()
        hashes[name]=hashlib.sha256(raw).hexdigest()
        if path.is_relative_to(ROOT/'shared/src'):
            shared_matches[name]=hashlib.sha256(raw.replace(b'\r\n',b'\n')).hexdigest()==baseline.get(name)
    labels=re.findall(r'^([A-Za-z_]\w*):',source,re.M)
    assert set(REQUIRED)<=set(labels),('Missing active owner',set(REQUIRED)-set(labels))
    assert not any(name.startswith(('pci_','pcibios','um888','um866','vl82')) for name in labels)
    listing=Listing(image.with_suffix('.lst'));symbols={}
    for name in REQUIRED:
        try:symbols[name]=listing.symbol(name)
        except StopIteration:
            assert name=='int1a',('Missing assembled label',name)
            symbols[name]=listing.symbol('RTC_INTERRUPT_LABEL')
    raw=image.read_bytes();decoder=Cs(CS_ARCH_X86,CS_MODE_16);decoder.detail=True
    operations=[];dx=None
    for line in listing.lines:
        match=re.match(r'\s*\d+\s+([0-9A-F]{8})\s+\S+\s+(?:<\d+>\s*)?(.*)',line)
        if not match:continue
        address=int(match[1],16);text=match[2].strip()
        if not re.match(r'(?:in|out|mov|call|jmp|ret|pop|xor|add|sub|inc|dec|and|or)\b',text):continue
        ins=next(decoder.disasm(raw[65536+address:65536+address+15],address,count=1),None)
        if ins is None:continue
        if ins.mnemonic=='mov' and len(ins.operands)==2 and ins.operands[0].type==X86_OP_REG and ins.operands[0].reg==X86_REG_DX:
            dx=ins.operands[1].imm if ins.operands[1].type==X86_OP_IMM else None
        elif ins.mnemonic in ('in','out'):
            port=ins.operands[0 if ins.mnemonic=='out' else 1]
            value=port.imm if port.type==X86_OP_IMM else dx
            assert value not in FORBIDDEN,('Donor I/O',hex(address),ins.mnemonic,ins.op_str,value)
            operations.append({'offset':address,'instruction':ins.mnemonic+' '+ins.op_str,'port':value})
        elif ins.mnemonic in ('call','jmp','ret') or (ins.operands and ins.operands[0].type==X86_OP_REG and ins.operands[0].reg==X86_REG_DX):dx=None
    assert operations
    return {'dependency_sha256':hashes,'active_owner_files':[p.relative_to(ROOT).as_posix() for p in sorted(owners)],'required_compiled_symbols':symbols,'active_global_labels':labels,'assembled_io':operations,'source_comparison_base':BASE,'shared_source_matches_base':shared_matches}


def run(image):
    image=Path(image).resolve();configuration=image.with_name('configuration.inc')
    folder=PORT/'build/tests/results/native-inventory';folder.mkdir(exist_ok=True)
    nasm=shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    options=[nasm,'-w+error','-I',str(PORT/'src')+'/','-I',str(ROOT/'shared/src')+'/','-I',str(image.parent)+'/']
    original=PORT/'src/bios.asm'
    pp=subprocess.run(options+['-E',str(original)],cwd=PORT/'src',capture_output=True,text=True,check=True).stdout
    deps=subprocess.run(options+['-M','-MT','candidate',str(original)],cwd=PORT/'src',capture_output=True,text=True,check=True).stdout
    (folder/'dependencies.txt').write_text(deps)
    dependencies=re.sub(r'\\\r?\n',' ',deps).split(':',1)[1].split()
    flat=folder/'candidate.asm';flat.write_text(pp)
    result=validate(image,flat,dependencies,configuration);rejected=[]
    for kind,insert in (('umc-index','out 0x22,al'),('pci-config','mov dx,0xCF8\nout dx,eax'),('missing-owner','')):
        altered=pp.replace('startup:\n','startup:\n'+insert+'\n',1) if kind!='missing-owner' else pp.replace('arm_keyboard_runtime:','excluded_runtime_owner:',1).replace('arm_keyboard_runtime\n','excluded_runtime_owner\n')
        path=folder/(kind+'.asm');path.write_text(altered);target=path.with_suffix('.bin')
        subprocess.run(options+['-f','bin','-l',str(target.with_suffix('.lst')),'-o',str(target),str(path)],cwd=PORT/'src',check=True)
        try:validate(target,path,dependencies,configuration)
        except AssertionError:rejected.append(kind)
        else:raise AssertionError('Inventory negative accepted: '+kind)
    # Reject a real donor include dependency, independently of port I/O checks.
    try:resolve(ROOT/'m919/src/hardware/board-core.inc',configuration)
    except AssertionError:rejected.append('foreign-owner')
    else:raise AssertionError('Foreign owner accepted')
    if configuration!=PORT/'build/configuration.inc':
        try:resolve(PORT/'build/configuration.inc',configuration)
        except AssertionError:rejected.append('other-build-configuration')
        else:raise AssertionError('Other build configuration accepted')
    result['negative_discriminators_rejected']=rejected
    return result
