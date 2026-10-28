"""M919 adapters for the shared assembled RAM proof and native interaction."""
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

PORT = Path(__file__).resolve().parents[1]
REPOSITORY = PORT.parent
sys.path.insert(0, str(REPOSITORY))
from shared.tools.ram_proof import constants, run
from shared.tools.rom import build, configuration, verify
from shared.tools.emulator import run_86box


def baseline(config):
    """Build the previous RAM owner without depending on another test's output."""
    folder = PORT/'build/hardware-tests/ram-baseline'
    r = build(PORT,str(folder.relative_to(PORT)))
    overlay = folder/'firmware'
    overlay.mkdir(exist_ok=True)
    source = (PORT/'tests/baselines/ram-test.inc').read_bytes()
    (overlay/'ram-test.inc').write_bytes(source)
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    image = Path(r['path'])
    subprocess.run([nasm,'-w+error','-f','bin','-I',str(folder)+'/',
                    '-I',str(PORT/'src')+'/', '-I',str(REPOSITORY/'shared/src')+'/',
                    '-l',str(image.with_suffix('.lst')),'-o',str(image),str(PORT/'src/bios.asm')],check=True)
    raw = bytearray(image.read_bytes())
    raw[config['rom']['checksum_offset']] = 0
    raw[config['rom']['checksum_offset']] = (-sum(raw)) & 255
    image.write_bytes(raw)
    verified = verify(PORT,image)
    verified['identity'] = config['identity']
    verified['ram_source'] = 'tests/baselines/ram-test.inc'
    (folder/'rom-checksums.json').write_text(json.dumps(verified,indent=2)+'\n')
    return image


def bounded():
    _, config = configuration(PORT)
    state = constants(REPOSITORY/'shared/src/pc/state.inc')
    r = build(PORT, 'build/hardware-tests/ram-proof')
    rom = r['path']
    results = [run(rom, config['rom'], state)]
    print('Randomized full three-pattern dword coverage/restoration and machine state: PASS',flush=True)
    results.append(run(rom,config['rom'],state,coverage=False,
                       caller_cr0=0x10,caller_flags=0x93,caller_gates=(0x0F,0x42)))
    for case in ('esc','delete'):
        results.append(run(rom,config['rom'],state,coverage=False,input_case=case))
    for block in (0x10000, 0x9D800, 0x100000, 2049*1024-1024):
        for position in ('first', 'middle', 'last'):
            results.append(run(rom, config['rom'], state, fault=(block,position), coverage=False))
    for pattern in (0xAA55AA55,0):
        for position in ('first','middle','last'):
            results.append(run(rom,config['rom'],state,fault=(0x10000,position),
                               fault_pattern=pattern,coverage=False))
    results.append(run(rom, config['rom'], state, fault=(0x10000,'middle'),
                       defaults=True, coverage=False))
    for bit in range(2,11):
        results.append(run(rom, config['rom'], state, alias_bit=bit, coverage=False))
    previous = baseline(config)
    results.append(run(previous,config['rom'],state,coverage=True,legacy=True))
    assert results[-1]['pattern_form'] == 'address XOR opposing two passes'
    assert results[-1]['ranges'] == results[0]['ranges'] and results[-1]['dwords'] == results[0]['dwords']
    benchmark = []
    for kib in (2048,16384):
        old = run(previous, config['rom'], state, kib=kib, ebda=0x9E00,
                  coverage=False, legacy=True)
        new = run(rom, config['rom'], state, kib=kib, ebda=0x9E00,
                  coverage=False, legacy=True)
        assert old['ranges'] == new['ranges'] and old['dwords'] == new['dwords']
        benchmark.append({'baseline':old, 'candidate':new,
                          'ratio':new['seconds']/old['seconds']})
    decodes = {name:run(image,config['rom'],state,kib=2048,ebda=0x9E00,
                        coverage=False,legacy=True,decode=True)
               for name,image in (('baseline',previous),('candidate',rom))}
    decodes['definition'] = 'Decoded instructions and instruction bytes, consecutive repeated REP EIP counted once; modeled work, not physical fetches or time'
    return {'bounded':results, 'benchmark':benchmark,'decode_work':decodes}


def native_checks(cases=('esc','pause','delete','transient','persistent')):
    spec = importlib.util.spec_from_file_location('m919_post',PORT/'tools/test-post.py')
    post = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(post)
    results = []
    for case in cases:
        flags = 2 if case == 'esc' else 4
        recovery = case in ('transient','persistent')
        defines = ['EMULATOR_RAM_SKIP_TEST','EMULATOR_RAM_PROOF','EMULATOR_POST_SUMMARY_TEST']
        if recovery:
            defines.remove('EMULATOR_RAM_PROOF')
            defines.append('EMULATOR_RAM_PROOF_RECOVERY')
        if case == 'persistent':
            defines.append('EMULATOR_RAM_PROOF_PERSISTENT')
        if case == 'pause':
            defines.append('EMULATOR_RAM_PROOF_PAUSE')
        if case == 'delete':
            defines += ['EMULATOR_RAM_PROOF_DELETE','EMULATOR_SETUP_TEST',
                        'EMULATOR_SETUP_SAVE_FIELDS','EMULATOR_RAM_SETUP_BOOT']
        vm,roms,rom = post.fixture('hardware-ram-'+case,{0:65},types=0x40,
                                   defines=defines,ram_flags=flags,l1=recovery)
        config = vm.parent/'test-configuration.inc'
        config.write_text(config.read_text()+f'%define TEST_RAM_PROOF_DELETE {int(case=="delete")}\n'
                          +f'%define TEST_RAM_PROOF_RECOVERY {int(recovery)}\n')
        boot = vm.parent/'ram-boot.bin'
        post.assemble(PORT/'tests/core-ram-boot.asm',boot,[vm.parent,PORT/'tests',REPOSITORY/'shared/src'])
        with (vm/'disk-0.img').open('r+b') as disk:
            disk.write(boot.read_bytes())
        inputs = {name:hashlib.sha256(path.read_bytes()).hexdigest()
                  for name,path in (('initial_nvram',vm/'nvr/m919.nvr'),
                                    ('boot_observer',boot),('configuration',config))}
        exit_code = run_86box(vm,roms,timeout=150)
        assert exit_code == (0x6A if case == 'persistent' else 0x68), (case,hex(exit_code))
        results.append({'case':case,'exit':exit_code,'rom_sha256':rom['sha256'],
                        'input_sha256':inputs,
                        'oracle':{'esc':'Real progress then IRQ1 ordinary a preserved through real Esc, actual boot/INT13',
                                  'pause':'Real Pause; E1 tails, FA/FE replies, release, prefix, timer-only ticks hold progress; fresh make consumed; Passed and boot/INT13',
                                  'delete':'Progress then real navigation Delete; real Setup changes, save, reset, reload, next Passed POST and boot/INT13',
                                  'transient':'Real visible failure and full 2KiB/CR0/GDTR/gate restoration; saved L1 policy, real 8042 reset, defaults reload, exactly two POSTs, next full RAM pass and boot/INT13',
                                  'persistent':'Same real failure/reset/defaults path; full block and machine restoration again, actual E7 branch after exactly one reset; terminal observed before hard_halt'}[case]})
        print(f'Native RAM {case}: {exit_code:02X}',flush=True)
    return results


def check(native=False):
    result = bounded()
    if native:
        result['native'] = native_checks()
    sources = ('shared/src/firmware/ram-test.inc','shared/src/pc/state.inc',
               'shared/src/firmware/post.inc','shared/src/pc/keyboard-irq.inc',
               'shared/src/pc/keyboard-bios.inc','shared/tools/ram_proof.py',
               'shared/tests/firmware/setup-test.inc','m919/tests/core-ram.inc',
               'm919/tests/core-ram-boot.asm','m919/tools/ram_proof.py',
               'm919/tools/test-hardware.py','m919/tools/test-build.py','m919/port.json',
               'm919/src/hardware/startup-core.inc','m919/src/hardware/board-core.inc',
               'm919/src/hardware/chipset-core.inc','shared/src/pc/rtc.inc','m919/tools/test-post.py')
    result['source_sha256'] = {name:hashlib.sha256((REPOSITORY/name).read_bytes()).hexdigest()
                               for name in sources}
    for case in result.get('native',[]):
        case['source_sha256'] = result['source_sha256']
    result['limits'] = ['Flat external DRAM and tied-line models prove the assembled RAM owner only.',
                        'Native 86Box proves composed keyboard/Setup/reset/boot paths; physical POST timing and memory wiring remain unmeasured.',
                        'Bounded failures stop at reset entry or E7; native transient and persistent cases close the actual 8042 reset/defaults/retry path. Persistent E7 is observed immediately before hard_halt.']
    path = PORT/'build/research/hardware/ram-proof.json'
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'scenarios':len(result['bounded']),
                      'benchmark':[{'kib':b['baseline']['kib'],'baseline_seconds':b['baseline']['seconds'],
                                    'candidate_seconds':b['candidate']['seconds'],
                                    'services':[b['baseline']['services'],b['candidate']['services']]}
                                   for b in result['benchmark']],
                      'decode':[result['decode_work'][name]['decode'] for name in ('baseline','candidate')],
                      'record':str(path)},indent=2), flush=True)
    return result


if __name__ == '__main__':
    check('--native' in sys.argv)
