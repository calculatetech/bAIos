"""Check actual ROM output, configuration substitution, and input preservation."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys

PORT = Path(__file__).resolve().parents[1]
REPOSITORY = PORT.parent
sys.path.insert(0, str(REPOSITORY))
from shared.tools.rom import build, configuration, verify


def main():
    result = build(PORT,'build/build-tests/current')
    _, config = configuration(PORT)
    raw = Path(result['path']).read_bytes()
    assert len(raw) == 128*1024 and sum(raw) % 256 == 0
    assert raw[:65536] == b'\xFF'*65536 and sum(raw[65536:]) % 256 == 0
    for source in (PORT/'src', REPOSITORY/'shared/src'):
        for path in source.rglob('*.inc'):
            assert 'POST_STAGE_DIAGNOSTIC' not in path.read_text(), path
    assert not (PORT/'src/hardware/post-diagnostic.inc').exists()
    offset, segment = struct.unpack_from('<HH',raw,0x1FFF1)
    entry=segment*16+offset-config['rom']['base']
    assert (segment,offset)==(config['rom']['reset_segment'],config['rom']['reset_entry_offset'])
    assert raw[entry] == 0xFA
    month,day,year = config['identity']['release_date'].split('/')
    assert raw[0x1FFF5:0x1FFFD] == f'{month}/{day}/{year[-2:]}'.encode('ascii')
    folder = PORT/'build/build-tests'
    folder.mkdir(parents=True,exist_ok=True)
    for name,mutation in [('size',raw[:-1]),('checksum',raw[:100]+bytes([raw[100]^1])+raw[101:]),
                          ('reset',raw[:0x1FFF1]+bytes([raw[0x1FFF1]^1])+raw[0x1FFF2:])]:
        altered = bytearray(mutation)
        if name == 'reset':
            altered[config['rom']['checksum_offset']] = (altered[config['rom']['checksum_offset']]-1)&255
        image = folder/(name+'.bin')
        image.write_bytes(altered)
        try:
            verify(PORT,image)
        except ValueError:
            pass
        else:
            raise AssertionError('Verifier accepted incorrect '+name)
    try:
        build(PORT,'../outside-output')
    except ValueError:
        pass
    else:
        raise AssertionError('Builder accepted output outside the selected build directory')
    alternate = folder/'port with spaces'
    (alternate/'src/hardware').mkdir(parents=True,exist_ok=True)
    for source in (PORT/'src').glob('*.inc'):
        shutil.copyfile(source,alternate/'src'/source.name)
    shutil.copyfile(PORT/'src/bios.asm',alternate/'src/bios.asm')
    for source in (PORT/'src/hardware').glob('*.inc'):
        shutil.copyfile(source,alternate/'src/hardware'/source.name)
    config['identity'].update(vendor='Configured vendor',model='Configured model',version='9.8.7',release_date='12/31/2027')
    config['rom'].update(model_byte=0xF8)
    (alternate/'port.json').write_text(json.dumps(config),encoding='utf-8')
    varied = build(alternate)
    candidate = Path(varied['path']).read_bytes()
    assert b'9.8.7\0' in candidate and b'Configured vendor Configured model\0' in candidate
    assert candidate[0x1FFF5:0x1FFFD] == b'12/31/27'
    assert struct.unpack_from('<HH',candidate,0x1FFF1) == (config['rom']['reset_entry_offset'],config['rom']['reset_segment'])
    assert candidate[entry] == 0xFA and candidate[-2] == 0xF8
    entrypoints = []
    output_directory = 'build/build-tests/output with spaces'
    output_image = PORT/output_directory/('baios-'+PORT.name+'.bin')
    commands = [
        ([sys.executable,'-B',str(REPOSITORY/'tools/build-rom.py'),str(PORT),'--output',output_directory],True),
        ([sys.executable,'-B',str(REPOSITORY/'tools/verify-rom.py'),str(PORT),'--image',str(output_image)],True),
        (['pwsh','-NoProfile','-File',str(PORT/'tools/build.ps1'),'-OutputDirectory',output_directory],True),
        (['pwsh','-NoProfile','-File',str(PORT/'tools/verify-rom.ps1'),'-Image',str(output_image)],True),
        ([sys.executable,'-B',str(REPOSITORY/'tools/build-rom.py'),str(PORT),'--output','../outside-output'],False),
        (['pwsh','-NoProfile','-File',str(PORT/'tools/build.ps1'),'-OutputDirectory','../outside-output'],False),
        ([sys.executable,'-B',str(REPOSITORY/'tools/verify-rom.py'),str(PORT),'--image',str(folder/'checksum.bin')],False),
        (['pwsh','-NoProfile','-File',str(PORT/'tools/verify-rom.ps1'),'-Image',str(folder/'checksum.bin')],False),
    ]
    for command,accepted in commands:
        completed = subprocess.run(command,cwd=PORT,capture_output=True,text=True)
        assert (completed.returncode == 0) == accepted,(command,completed.stderr)
        if accepted:
            assert json.loads(completed.stdout)['sha256'] == result['sha256']
        entrypoints.append({'command':command,'exit':completed.returncode,'accepted':accepted})
    record = REPOSITORY/'.agent/test-results/m919-post.json'
    record.parent.mkdir(parents=True,exist_ok=True)
    evidence = json.loads(record.read_text(encoding='utf-8')) if record.exists() else {}
    protected = dict(evidence.get('protected_before',{}))
    removed = 'm919/reference/9-15-98.rom'
    if removed in protected and not (REPOSITORY/removed).exists():
        assert hashlib.sha256((PORT/'reference/9190914S.ROM').read_bytes()).hexdigest() == protected[removed]
        del protected[removed]  # User removed this exact duplicate; retain historical evidence.
    for name,expected in protected.items():
        assert hashlib.sha256((REPOSITORY/name).read_bytes()).hexdigest() == expected, name
    services_path = REPOSITORY/'.agent/test-results/m919-services.json'
    services = json.loads(services_path.read_text(encoding='utf-8')) if services_path.exists() else evidence.get('shared_extraction',{})
    for name,variant in services.get('variants',{}).items():
        before,after = Path(variant['before_command'][-2]),Path(variant['after_command'][-2])
        if before.exists() and after.exists():
            assert before.read_bytes() == after.read_bytes(), name
        else:
            assert variant['before_sha256'] == variant['after_sha256'], name
    spec=importlib.util.spec_from_file_location('m919_matrix',PORT/'tools/test-post.py')
    runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
    contract=(PORT/'docs/plans/M919-002-post.md').read_text(encoding='utf-8')
    table=contract[contract.index('| Boundary |'):contract.index('The input-domain lens')]
    required=set(re.findall(r'--case ([a-z0-9-]+)',table))
    assert set(runner.ALL_CASES)==required and len(runner.ALL_CASES)==len(required)
    invoked=[];original_run=runner.subprocess.run;original_argv=sys.argv
    try:
        runner.subprocess.run=lambda command,check:invoked.append(command)
        sys.argv=[str(PORT/'tools/test-post.py'),'--case','all']
        runner.main()
    finally:
        runner.subprocess.run=original_run;sys.argv=original_argv
    assert invoked==[[sys.executable,'-B',str(PORT/'tools/test-post.py'),'--case',case] for case in runner.ALL_CASES]
    evidence['build_checks'] = {'integrity':result,'metadata_substitution':varied,
        'rejected':['wrong size','wrong checksum','wrong reset target','outside output'],
        'entrypoints':entrypoints,
        'matrix_dispatch':{'required_cases':list(runner.ALL_CASES),'exact_once':True,'frozen_contract_coverage':True},
        'protected_files':len(protected), 'presario_variants':list(services.get('variants',{}))}
    evidence['shared_extraction'] = services
    record.write_text(json.dumps(evidence,indent=2)+'\n',encoding='utf-8')
    print('ROM integrity, alternate metadata/layout/path, and output guard: PASS')
    print(f'Matrix dispatcher covers all {len(required)} frozen named cases once: PASS')
    print(f"Retained task evidence: {len(protected)} protected inputs; {len(services.get('variants',{}))} Presario variants")


if __name__ == '__main__':
    main()
