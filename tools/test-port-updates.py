"""Exercise the real snapshot runner with disposable source, commands and artifacts."""
import ast
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]


def main():
    spec = importlib.util.spec_from_file_location('port_updates', ROOT/'tools/update-ports.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    actual = runner.declarations()
    assert {'presario-800', 'pb430', 'm919', 'mp386'} <= set(actual)
    print('PASS complete maintained-port declarations, test-file and named-case inventory', flush=True)
    parent = ROOT/'.agent/test-results'
    parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='port-update-check-', dir=parent) as folder:
        root = Path(folder).resolve()
        assert root.is_relative_to(parent.resolve())
        for relative in ('tools/update-ports.py', 'tools/clean-port-update.ps1', 'shared/tools/build-cleanup.ps1', 'shared/tools/candidates.py'):
            target = root/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/relative, target)
        (root/'.gitignore').write_text('build/\n.agent/\ninputs/\nopaque/\ninstalled/\n', encoding='utf-8')
        (root/'note.txt').write_text('uncommitted current source Ω', encoding='utf-8')
        (root/'inputs').mkdir()
        (root/'inputs/input.bin').write_bytes(b'private input')
        (root/'reference/media/dos').mkdir(parents=True)
        (root/'reference/media/dos/test-card.vhd').write_bytes(b'snapshot DOS media')
        (root/'installed/.git').mkdir(parents=True)
        (root/'installed/.git/private-metadata').write_text('must not copy')
        (root/'installed/resource.bin').write_bytes(b'installed resource')
        quote = lambda p: "'"+str(p).replace("'", "''")+"'"
        subprocess.run(runner.command_line(['powershell','-Command',
            'New-Item -ItemType Junction -Path '+quote(root/'opaque')+' -Target '+quote(root/'installed')+' | Out-Null']),
            check=True, capture_output=True)
        build = '''from pathlib import Path
import json,sys,hashlib
p=Path(__file__).resolve().parents[1];r=p.parent
if (r/'fail-prepare.txt').exists() and p.name=='alpha' and '--final' not in sys.argv:raise SystemExit(7)
(p/'build').mkdir(exist_ok=True)
(p/'build/approved.bin').write_bytes(b'nested builder overwrote only snapshot')
if '--final' in sys.argv:
 data=(b'NEW:'+ (r/'note.txt').read_bytes()).ljust(64,b'!')[:64]
 (p/'build/final.bin').write_bytes(data[:1] if (r/'bad-artifact.txt').exists() else data)
 (p/'build/build-info.json').write_text(json.dumps(dict(version='0.1.1',files=[dict(name='final.bin',sha256=hashlib.sha256(data).hexdigest(),size=len(data),sum32=f'{sum(data):08X}',built_at='2026-10-27T12:30:00+00:00')])))
with (r/'events.txt').open('a') as stream:stream.write(p.name+(':candidate' if '--final' in sys.argv else ':prepare')+'\\n')
events=r/'.agent/test-results/fixture/events.json';events.parent.mkdir(parents=True,exist_ok=True)
events.write_text(json.dumps((r/'events.txt').read_text().splitlines()))
'''
        proof = '''from pathlib import Path
import json,os,sys
CASES=('one','two')
p=Path(__file__).resolve().parents[1];r=p.parent
assert sys.dont_write_bytecode and os.environ['PYTHONUTF8']=='1'
assert os.environ['BAIOS_BUILD_DIRECTORY']=='build'
assert Path(os.environ['BAIOS_DOS_VHD'])==r/'reference/media/dos/test-card.vhd'
assert Path(os.environ['BAIOS_DOS_VHD']).read_bytes()==b'snapshot DOS media'
assert (r/'note.txt').read_text(encoding='utf-8')=='uncommitted current source Ω'
assert (r/'inputs/input.bin').read_bytes()==b'private input'
assert (r/'opaque/resource.bin').read_bytes()==b'installed resource'
assert not (r/'opaque/.git').exists()
assert not (r/'opaque').is_symlink() and not (hasattr(Path,'is_junction') and (r/'opaque').is_junction())
if (r/'mutate-input.txt').exists():Path((r/'mutate-input.txt').read_text()).write_bytes(b'unexpected original input write')
case=sys.argv[sys.argv.index('--case')+1]
with (r/'events.txt').open('a') as stream:stream.write(p.name+':'+case+'\\n')
if case=='two':
 from wrapped_proof import run
 from later_proof import check
 run();check('via-wrapper')
events=r/'.agent/test-results/fixture/events.json';events.parent.mkdir(parents=True,exist_ok=True)
events.write_text(json.dumps((r/'events.txt').read_text().splitlines()))
(p/'build/comparison.json').write_text('{"comparison":"current"}')
(p/'build/review.png').write_bytes(b'current screenshot fixture')
if (r/'fail-check.txt').exists() and (r/'fail-check.txt').read_text()==p.name+':'+case:raise SystemExit(9)
'''
        wrapped = '''from pathlib import Path
def run():
 p=Path(__file__).resolve().parents[1]
 with (p.parent/'events.txt').open('a') as stream:stream.write(p.name+':wrapped\\n')
if __name__=='__main__':run()
'''
        independent = '''from pathlib import Path
import json,sys
def record(case):
 p=Path(__file__).resolve().parents[1];r=p.parent
 with (r/'events.txt').open('a') as stream:stream.write(p.name+':proof-'+case+'\\n')
 (r/'.agent/test-results/fixture/events.json').write_text(json.dumps((r/'events.txt').read_text().splitlines()))
 if case=='last' and (r/'fail-later.txt').exists():raise SystemExit(13)
CASES={'first':lambda:record('first'),'last':lambda:record('last'),'via-wrapper':lambda:record('wrapper')}
def check(case):CASES[case]()
if __name__=='__main__':check(sys.argv[1])
'''
        originals, declarations = {}, {}
        for port in ('alpha', 'zulu'):
            (root/port/'tools').mkdir(parents=True)
            (root/port/'src').mkdir()
            (root/port/'src/bios.asm').write_text('; fixture entry')
            (root/port/'tools/build.py').write_text(build, encoding='utf-8')
            (root/port/'tools/test-proof.py').write_text(proof, encoding='utf-8')
            (root/port/'tools/wrapped_proof.py').write_text(wrapped, encoding='utf-8')
            (root/port/'tools/later_proof.py').write_text(independent, encoding='utf-8')
            (root/port/'tools/module_proof.py').write_text('def run():raise AssertionError("module helper is not an entry point")\n')
            (root/port/'build').mkdir()
            approved = root/port/'build/approved.bin'
            approved.write_bytes(b'approved original ROM')
            originals[approved] = approved.read_bytes()
            old_evidence=root/port/'build/review/shared-update'
            for stale in ('logs/foreign--old.log','results/.agent/private.json','results/other-port/old.json'):
                path=old_evidence/stale;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('obsolete copied evidence')
            declarations[port] = dict(schema=1, resources=['opaque'], inputs=['inputs/input.bin','reference/media/dos/test-card.vhd'],
                prepare=[dict(id='build', argv=['python',port+'/tools/build.py'])],
                checks=[dict(id=case, argv=['python',port+'/tools/test-proof.py','--case',case]) for case in ('one','two')]
                       +[dict(id='proof-'+case, argv=['python',port+'/tools/later_proof.py',case]) for case in ('first','last')],
                case_sets=[dict(script=port+'/tools/test-proof.py', variable='CASES'),
                           dict(script=port+'/tools/later_proof.py', variable='CASES',argument=None,covered_by={'via-wrapper':'two'})],
                wrapped_tests={port+'/tools/wrapped_proof.py':['two']},
                historical_checks=[dict(id='retired', argv=['python',port+'/tools/test-proof.py','--case','one'],
                                        inputs=['inputs/retired.bin'], reason='Retired fixture requires its original ROM')],
                candidates=[dict(id='final', argv=['python',port+'/tools/build.py','--final'])],
                artifacts=[dict(path=port+'/build/final.bin', name='candidate.bin', size=64, physical=True)])
            (root/port/'validation.json').write_text(json.dumps(declarations[port]), encoding='utf-8')
        (root/'held/src').mkdir(parents=True)
        (root/'held/tools').mkdir()
        (root/'held/src/bios.asm').write_text('; held')
        (root/'held/tools/build.py').write_text('raise AssertionError("held port executed")')
        (root/'held/validation.json').write_text(json.dumps(dict(schema=1,hold='defective hardware')))
        subprocess.run(['git','init','-q',str(root)], check=True, capture_output=True)
        deleted = root/'deleted.txt'
        deleted.write_text('tracked source deleted before staging')
        subprocess.run(['git','add','deleted.txt'], cwd=root, check=True, capture_output=True)
        deleted.unlink()
        copied = root/'.agent/deletion-snapshot'
        hashes = runner.snapshot(root, copied)
        assert 'deleted.txt' not in hashes and not (copied/'deleted.txt').exists()
        assert (copied/'note.txt').read_bytes() == (root/'note.txt').read_bytes()
        assert Path('deleted.txt') not in runner.source_files(root)
        print('PASS unstaged tracked deletion omitted from snapshot and preservation inventory', flush=True)

        def invoke(*args, code=0):
            env = os.environ.copy()
            env['BAIOS_BUILD_DIRECTORY'] = 'host-only-output-must-not-be-used'
            env['BAIOS_DOS_VHD'] = str(root/'inputs/input.bin')
            result = subprocess.run([sys.executable,'-B',str(root/'tools/update-ports.py'),*args],
                                    cwd=root, env=env, capture_output=True, text=True, encoding='utf-8')
            assert result.returncode == code, result.stdout+'\n'+result.stderr
            for path, expected in originals.items():
                assert path.read_bytes() == expected
            return json.loads((root/'.agent/test-results/port-update/current.json').read_text(encoding='utf-8'))

        def inventory(code=0, error=None):
            current=root/'.agent/test-results/port-update/current.json'
            before=current.read_bytes() if current.exists() else None
            result=subprocess.run([sys.executable,'-B',str(root/'tools/update-ports.py'),'--list'],cwd=root,
                                  capture_output=True,text=True,encoding='utf-8')
            assert result.returncode==code,(result.stdout,result.stderr)
            if error:assert error in result.stderr,result.stderr
            assert (current.read_bytes() if current.exists() else None)==before
            for path,expected in originals.items():assert path.read_bytes()==expected

        inventory()
        report = invoke()
        assert report['status'] == 'passed' and report['full']
        assert report['held_ports']=={'held':'defective hardware'}
        assert report['original_inputs_unchanged'] and report['approved_images_unchanged']
        assert not report['workspace_retained'] and not Path(report['workspace']).exists()
        assert report['source_files']['note.txt'] == hashlib.sha256((root/'note.txt').read_bytes()).hexdigest()
        assert len(report['historical_exclusions']) == 2
        candidates = {}
        for port in ('alpha','zulu'):
            item = report['ports'][port]['artifacts'][0]
            path = Path(item['path']);data = path.read_bytes()
            assert len(data) == item['size'] == 64 and item['sum32'] == f'{sum(data):08X}'
            assert item['sha256'] == hashlib.sha256(data).hexdigest()
            assert (path.parent/'validation-report.json').is_file()
            own=json.loads((path.parent/'validation-report.json').read_text())
            assert set(own['ports'])=={port} and all(c['port']==port for c in own['commands'])
            assert all(p.name.startswith(port+'--') for p in (path.parent/'logs').iterdir())
            assert (path.parent/'results/comparison.json').is_file()
            assert not (path.parent/'results/.agent').exists()
            assert not (path.parent/'results/other-port').exists()
            assert not (path.parent/'logs/foreign--old.log').exists()
            assert not any((path.parent/'results'/other).exists() for other in ('alpha','zulu'))
            candidates[path] = data
        for command in report['commands']:
            if command['argv'][0] == sys.executable:
                assert command['argv'][1] == '-B'
            if command['phase'] == 'cleanup':
                assert '-NoProfile' in command['argv']
            assert Path(command['log']).is_file()
        expected = [('alpha','build','prepare'),('alpha','one','checks'),('alpha','two','checks'),
                    ('alpha','proof-first','checks'),('alpha','proof-last','checks'),
                    ('zulu','build','prepare'),('zulu','one','checks'),('zulu','two','checks'),
                    ('zulu','proof-first','checks'),('zulu','proof-last','checks'),
                    ('alpha','final','candidates'),('zulu','final','candidates'),
                    ('alpha','evidence-cleanup','cleanup'),('zulu','evidence-cleanup','cleanup'),
                    ('source','workspace-cleanup','cleanup')]
        assert [(c['port'],c['id'],c['phase']) for c in report['commands']] == expected
        def evidence(result):
            retained = {Path(row['path']).relative_to(Path(result['workspace']).parent/'results').as_posix(): row
                        for row in result['evidence']}
            for port in ('alpha','zulu'):
                for name, value in (('comparison.json', b'{"comparison":"current"}'),
                                    ('review.png', b'current screenshot fixture')):
                    row = retained[port+'/build/'+name]
                    raw = Path(row['path']).read_bytes()
                    assert raw == value and len(raw) == row['size'] and hashlib.sha256(raw).hexdigest() == row['sha256']
            events = retained['.agent/test-results/fixture/events.json']
            return json.loads(Path(events['path']).read_text())
        assert evidence(report) == ['alpha:prepare','alpha:one','alpha:two','alpha:wrapped','alpha:proof-wrapper',
                                    'alpha:proof-first','alpha:proof-last',
                                    'zulu:prepare','zulu:one','zulu:two','zulu:wrapped','zulu:proof-wrapper',
                                    'zulu:proof-first','zulu:proof-last','alpha:candidate','zulu:candidate']
        print('PASS actual uncommitted snapshot, private resources, sequential commands, cleanup, preserved originals and checksummed artifacts', flush=True)

        (root/'fail-later.txt').write_text('fail independent later proof')
        failed=invoke(code=1)
        assert failed['status']=='failed' and failed['workspace_retained']
        assert all(any(c['port']==port and c['id']=='proof-last' and c['returncode']==13 for c in failed['commands'])
                   for port in ('alpha','zulu'))
        assert not any(c['phase']=='candidates' for c in failed['commands'])
        assert failed['original_inputs_unchanged'] and failed['approved_images_unchanged']
        for path,expected in candidates.items():assert path.read_bytes()==expected
        (root/'fail-later.txt').unlink()
        print('PASS real wrapped/direct proof events precede candidates; later proof failure replaces success and preserves originals',flush=True)

        (root/'fail-check.txt').write_text('alpha:one')
        failed = invoke(code=1)
        assert failed['status'] == 'failed' and failed['workspace_retained']
        assert any(c['port']=='alpha' and c['id']=='two' and c['status']=='passed' for c in failed['commands'])
        assert failed['ports']['zulu']['status']=='passed'
        assert not any(c['phase']=='candidates' for c in failed['commands'])
        (root/'fail-check.txt').unlink()
        for path, expected in candidates.items():assert path.read_bytes()==expected
        (root/'fail-prepare.txt').write_text('fail alpha prepare')
        failed = invoke(code=1)
        assert failed['ports']['alpha']['status']=='blocked'
        assert not any(c['phase']=='checks' and c['port']=='alpha' for c in failed['commands'])
        assert failed['ports']['zulu']['status']=='passed'
        (root/'fail-prepare.txt').unlink()
        (root/'inputs/input.bin').unlink()
        failed=invoke(code=1)
        assert all(p['status']=='blocked' for p in failed['ports'].values())
        (root/'inputs/input.bin').write_bytes(b'private input')
        print('PASS current failure replaces prior success, independent checks continue, failed prepare blocks dependents and missing inputs never pass', flush=True)

        for args in (('--check','one'),('--port','alpha')):
            partial=invoke(*args)
            assert partial['status']=='partial' and not partial['full']
            assert not any(c['phase']=='candidates' for c in partial['commands'])
            for path, expected in candidates.items():assert path.read_bytes()==expected
            assert not Path(partial['workspace']).exists()
            if args[0] == '--check':
                assert evidence(partial) == ['alpha:prepare','alpha:one','zulu:prepare','zulu:one']
        historical=invoke('--historical', code=1)
        assert historical['status']=='failed' and all(p['status']=='blocked' for p in historical['ports'].values())
        print('PASS check/port subsets cannot promote; explicitly requested historical missing inputs fail', flush=True)

        missing=root/'alpha/validation.json';saved=missing.read_bytes();missing.unlink()
        assert invoke(code=1)['status']=='failed'
        missing.write_bytes(saved)
        omitted=root/'alpha/tools/test-omitted.py';omitted.write_text('raise SystemExit(0)')
        assert 'Undeclared tests' in invoke(code=1)['error']
        omitted.unlink()
        for name in ('tools/test-later.py','shared/tests/test-later.py'):
            later=root/name;later.parent.mkdir(parents=True,exist_ok=True)
            later.write_text('raise SystemExit(0)')
            assert 'Undeclared common tests' in invoke(code=1)['error']
            later.unlink()
        history=root/'tools/test-repository-layout.py'
        history.write_text('raise SystemExit(8)')
        legacy=invoke('--check','one')
        assert any(e['id']=='repository-layout-history' and e['status']=='excluded-historical' for e in legacy['historical_exclusions'])
        legacy=invoke('--historical',code=1)
        assert any(c['id']=='repository-layout-history' and c['returncode']==8 for c in legacy['commands'])
        history.unlink()
        source=root/'alpha/tools/test-proof.py';source.write_text(proof.replace("('one','two')", "('one','two','later')"),encoding='utf-8')
        assert 'Undeclared cases' in invoke(code=1)['error']
        source.write_text(proof,encoding='utf-8')
        duplicate=dict(declarations['alpha'])
        duplicate['checks']=duplicate['checks']+[duplicate['checks'][0]]
        missing.write_text(json.dumps(duplicate),encoding='utf-8')
        assert 'duplicate command ID' in invoke(code=1)['error']
        missing.write_bytes(saved)
        entry=root/'alpha/tools/new_proof.py'
        entry.write_text("if '__main__'==__name__:print('independent proof')\n")
        inventory(code=1,error='Undeclared tests')
        declared=json.loads(saved)
        declared['checks'].append(dict(id='new-proof',argv=['python','alpha/tools/new_proof.py']))
        missing.write_text(json.dumps(declared),encoding='utf-8')
        inventory()
        entry.unlink();missing.write_bytes(saved)
        for owner in ('missing','build','retired','final'):
            declared=json.loads(saved)
            declared['wrapped_tests']['alpha/tools/wrapped_proof.py']=[owner]
            missing.write_text(json.dumps(declared),encoding='utf-8')
            inventory(code=1,error='Invalid current wrapper coverage')
            declared=json.loads(saved)
            declared['case_sets'][1]['covered_by']['via-wrapper']=owner
            missing.write_text(json.dumps(declared),encoding='utf-8')
            inventory(code=1,error='Invalid current case coverage')
        declared=json.loads(saved)
        declared['wrapped_tests']['alpha/tools/absent_proof.py']=['two']
        missing.write_text(json.dumps(declared),encoding='utf-8')
        inventory(code=1,error='Invalid current wrapper coverage')
        missing.write_bytes(saved)
        entry=root/'alpha/tools/later_proof.py'
        entry.write_text(independent.replace("record('wrapper')}","record('wrapper'),'later':lambda:record('later')}"),encoding='utf-8')
        inventory(code=1,error='Undeclared cases')
        later=dict(id='proof-later',argv=['python','alpha/tools/later_proof.py','later'])
        for group in ('prepare','historical_checks','candidates'):
            declared=json.loads(saved);declared[group].append(later)
            missing.write_text(json.dumps(declared),encoding='utf-8')
            inventory(code=1,error='Undeclared cases')
        declared=json.loads(saved);declared['checks'].append(later)
        missing.write_text(json.dumps(declared),encoding='utf-8');inventory()
        declared=json.loads(saved);declared['case_sets'][1]['covered_by']['later']='two'
        source.write_text(proof.replace("run();check('via-wrapper')","run();check('via-wrapper');check('later')"),encoding='utf-8')
        missing.write_text(json.dumps(declared),encoding='utf-8');inventory()
        source.write_text(proof,encoding='utf-8');entry.write_text(independent,encoding='utf-8');missing.write_bytes(saved)
        print('PASS real --list: executable proof discovery, module-only exclusion, current wrapper IDs, literal positional cases and current-only credits',flush=True)

        tree=ast.parse((ROOT/'m919/tools/timing_boundaries.py').read_text(encoding='utf-8'))
        nodes=[node for node in tree.body if (isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='CASES' for t in node.targets))
               or (isinstance(node,ast.FunctionDef) and node.name=='check')
               or (isinstance(node,ast.If) and isinstance(node.test,ast.Compare) and isinstance(node.test.left,ast.Name) and node.test.left.id=='__name__')]
        assert len(nodes)==3
        mapping=nodes[0].value
        keys=[ast.literal_eval(key) for key in mapping.keys]
        handlers=[value.id for value in mapping.values]
        mapping.keys.append(ast.Constant('inventory-later'));mapping.values.append(ast.Name(id='inventory_later',ctx=ast.Load()))
        stubs='\n'.join('def '+handler+'():return record('+repr(key)+')' for key,handler in zip(keys+['inventory-later'],handlers+['inventory_later']))
        prelude='\n'.join(('import hashlib,json,sys','from pathlib import Path',
            'REPOSITORY=Path('+repr(str(ROOT))+')','PORT=Path('+repr(str(root/'timing-dispatch'))+')',
            "(PORT/'build/research/hardware').mkdir(parents=True,exist_ok=True)",
            "sys.argv=['timing_boundaries.py','all']",'events=[]',
            'def record(name):events.append(name);return [{}]',stubs))+'\n'
        oracle='\nassert events=='+repr(keys+['inventory-later'])+",events\nprint('all actual dispatcher handlers reached')\n"
        program=prelude+ast.unparse(ast.Module(body=nodes,type_ignores=[]))+oracle
        complete=subprocess.run([sys.executable,'-B','-c',program],capture_output=True,text=True,encoding='utf-8')
        assert complete.returncode==0,(complete.stdout,complete.stderr)
        frozen=ast.parse(ast.unparse(ast.Module(body=nodes,type_ignores=[])))
        loop=frozen.body[-1].body[0]
        assert isinstance(loop,ast.For) and isinstance(loop.iter,ast.IfExp)
        loop.iter.body=ast.Tuple(elts=[ast.Constant(key) for key in keys],ctx=ast.Load())
        prefix=subprocess.run([sys.executable,'-B','-c',prelude+ast.unparse(frozen)+oracle],capture_output=True,text=True,encoding='utf-8')
        assert prefix.returncode and 'AssertionError' in prefix.stderr
        assert 'timing-boundaries-inventory-later:' in complete.stdout and 'timing-boundaries-inventory-later:' not in prefix.stdout
        print('PASS extracted actual timing-boundaries CLI/check executes every opaque handler; frozen-prefix contrast fails',flush=True)

        (root/'bad-artifact.txt').write_text('bad size')
        failed=invoke(code=1)
        assert failed['status']=='failed' and 'Incorrect artifact size' in failed['ports']['alpha']['error']
        for path,expected in candidates.items():assert path.read_bytes()==expected
        print('PASS missing declarations, new test files/cases and damaged final artifacts reject rather than reuse stale output', flush=True)
        (root/'bad-artifact.txt').unlink()
        (root/'mutate-input.txt').write_text(str(root/'inputs/input.bin'))
        changed=invoke(code=1)
        assert not changed['original_inputs_unchanged'] and changed['workspace_retained']
        for path,expected in candidates.items():assert path.read_bytes()==expected
        (root/'inputs/input.bin').write_bytes(b'private input')
        (root/'mutate-input.txt').unlink()
        print('PASS an unexpected original-input write prevents candidate promotion', flush=True)

        rejected=subprocess.run(runner.command_line(['powershell','-File',str(root/'tools/clean-port-update.ps1'),'-Path',str(root/'inputs')]),
                                cwd=root,capture_output=True,text=True)
        assert rejected.returncode != 0 and (root/'inputs/input.bin').read_bytes()==b'private input'
        guarded = root/'.agent/test-results/port-update/guard/workspace'
        guarded.mkdir(parents=True)
        sentinel = guarded/'keep.bin';sentinel.write_bytes(b'owned sentinel')
        bridge = '& '+quote(root/'tools/clean-port-update.ps1')+' -Path '+quote(guarded)
        busy = subprocess.run(runner.command_line(['powershell','-Command',
            'function global:Get-Process { [pscustomobject]@{Id=1} }; '+bridge]),capture_output=True,text=True)
        assert busy.returncode and 'An emulator is running' in busy.stderr and sentinel.read_bytes()==b'owned sentinel'
        junction = guarded/'outside'
        subprocess.run(runner.command_line(['powershell','-Command',
            'New-Item -ItemType Junction -Path '+quote(junction)+' -Target '+quote(root/'inputs')+' | Out-Null']),
            check=True,capture_output=True)
        try:
            unsafe = subprocess.run(runner.command_line(['powershell','-Command',bridge]),capture_output=True,text=True)
            assert unsafe.returncode and 'Reparse' in unsafe.stderr
            assert sentinel.read_bytes()==b'owned sentinel' and (root/'inputs/input.bin').read_bytes()==b'private input'
        finally:
            subprocess.run(['pwsh','-NoProfile','-Command',
                'Remove-Item -LiteralPath '+quote(junction)+' -Force'],check=True,capture_output=True)
        print('PASS cleanup bridge rejects an outside path without changing its input', flush=True)


if __name__ == '__main__':
    main()
