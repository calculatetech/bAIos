"""Build and check maintained ports in a disposable copy of current source."""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from shared.tools.candidates import checked, finish
OWNED = ROOT/'.agent/test-results/port-update'
CURRENT = OWNED/'current.json'
GROUPS = ('prepare', 'checks', 'historical_checks', 'candidates')
COMMON_TESTS = ('tools/test-port-updates.py','tools/check-public-source.py','shared/tests/test-emulator.py','tools/test-organization.py')
HISTORICAL_COMMON = {'id':'repository-layout-history','argv':['python','tools/test-repository-layout.py'],
    'reason':'One-time private layout audit pins checkpoint e8054520 and the former two-task roadmap, not current firmware.'}


def relative(value):
    path = PurePosixPath(value)
    if not value or path.is_absolute() or any(p in ('..', '.git') for p in path.parts) or ':' in value or '\\' in value:
        raise ValueError('Expected a repository-relative path: '+value)
    return Path(*path.parts)


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def save(report):
    CURRENT.write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


def owned(path, owner):
    if not path.resolve().is_relative_to(owner.resolve()) or path.resolve() == owner.resolve():
        raise ValueError('Generated path escapes its owner: '+str(path))
    for part in (path, *path.parents):
        if part.is_symlink() or (part.exists() and getattr(part.lstat(), 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise ValueError('Generated path has a reparse ancestor: '+str(part))
    return path


def proof_files(folder):
    result = set()
    for path in (*folder.glob('*_proof.py'), *folder.glob('*_boundaries.py')):
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in tree.body:
            test = node.test if isinstance(node, ast.If) else None
            if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and isinstance(test.ops[0], ast.Eq)):
                continue
            name, value = test.left, test.comparators[0]
            if isinstance(name, ast.Constant):name, value = value, name
            if (isinstance(name, ast.Name) and name.id == '__name__'
                    and isinstance(value, ast.Constant) and value.value == '__main__'):
                result.add(path)
                break
    return result


def declarations(root=ROOT):
    ports = sorted(p.name for p in root.iterdir() if p.is_dir()
                   and (p/'src/bios.asm').is_file()
                   and any((p/'tools'/name).is_file() for name in ('build.py', 'build.ps1')))
    if not ports:
        raise ValueError('No maintained ports found')
    result = {}
    for port in ports:
        path = root/port/'validation.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        if data.get('schema') != 1:
            raise ValueError('Unsupported validation schema: '+str(path))
        if data.get('hold'):
            result[port] = data
            continue
        ids, commands = set(), []
        for group in GROUPS:
            for command in data.get(group, []):
                name, argv = command['id'], command['argv']
                if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*', name) or name in ids:
                    raise ValueError('Invalid or duplicate command ID: '+port+':'+name)
                if not isinstance(argv, list) or not argv or not all(isinstance(x, str) for x in argv):
                    raise ValueError('Expected an argv array: '+port+':'+name)
                ids.add(name)
                commands.extend(argv)
        current_ids = {command['id'] for command in data.get('checks', [])}
        current_commands = {arg for command in data.get('checks', []) for arg in command['argv']}
        wrapped = data.get('wrapped_tests', {})
        if not isinstance(wrapped, dict):
            raise ValueError('Expected a wrapper coverage map: '+port)
        for script, covering in wrapped.items():
            if (not (root/relative(script)).is_file() or not isinstance(covering, list) or not covering
                    or not all(isinstance(name, str) and name in current_ids for name in covering)):
                raise ValueError('Invalid current wrapper coverage: '+port+': '+script)
        tests = {p.relative_to(root).as_posix() for p in (root/port/'tools').glob('test-*')
                 if p.suffix in ('.py', '.ps1')}
        if (root/port/'tools/validate.ps1').is_file():
            tests.add(port+'/tools/validate.ps1')
        proofs = {p.relative_to(root).as_posix() for p in proof_files(root/port/'tools')}
        missing = (tests-set(commands)-wrapped.keys()) | (proofs-current_commands-wrapped.keys())
        if missing:
            raise ValueError('Undeclared tests: '+', '.join(sorted(missing)))
        for coverage in data.get('case_sets', []):
            script = coverage['script']
            tree = ast.parse((root/relative(script)).read_text(encoding='utf-8'))
            argument = coverage.get('argument', '--case')
            if 'variable' in coverage:
                values = [node.value for node in tree.body if isinstance(node, ast.Assign)
                          and any(isinstance(target, ast.Name) and target.id == coverage['variable'] for target in node.targets)]
            else:
                values = [keyword.value for node in ast.walk(tree) if isinstance(node, ast.Call)
                          and isinstance(node.func, ast.Attribute) and node.func.attr == 'add_argument'
                          and node.args and isinstance(node.args[0], ast.Constant) and node.args[0].value == argument
                          for keyword in node.keywords if keyword.arg == 'choices']
            if len(values) != 1:
                raise ValueError('Cannot identify declared case set: '+coverage['script'])
            value = values[0]
            cases = [ast.literal_eval(key) for key in value.keys] if isinstance(value, ast.Dict) else ast.literal_eval(value)
            expected = set(map(str, cases))-set(coverage.get('exclude', []))
            covered = coverage.get('covered_by', {})
            if not isinstance(covered, dict) or any(case not in expected or not isinstance(name, str) or name not in current_ids
                                                   for case, name in covered.items()):
                raise ValueError('Invalid current case coverage: '+script)
            actual = set()
            for command in data.get('checks', []):
                argv = command['argv']
                if script in argv:
                    if argument is None:
                        position = argv.index(script)+1
                        if position < len(argv):actual.add(argv[position])
                    else:
                        actual.update(argv[i+1] for i, arg in enumerate(argv[:-1]) if arg == argument)
            if expected-actual-covered.keys():
                raise ValueError('Undeclared cases: '+script+': '+', '.join(sorted(expected-actual-covered.keys())))
        if not data.get('prepare') or not data.get('checks') or not data.get('candidates') or not data.get('artifacts'):
            raise ValueError('Incomplete validation declaration: '+port)
        for artifact in data['artifacts']:
            relative(artifact['path'])
            relative(artifact['name'])
            if not artifact['path'].startswith(port+'/build/'):
                raise ValueError('Artifact must belong to the selected port build: '+artifact['path'])
        result[port] = data
    declared = set(COMMON_TESTS) | set(HISTORICAL_COMMON['argv'])
    for data in result.values():
        declared.update(data.get('wrapped_tests', {}))
        for group in GROUPS:
            for command in data.get(group,[]):
                declared.update(command['argv'])
    common_files = {p.relative_to(root).as_posix() for folder in ('tools','shared/tests')
                    for p in (root/folder).glob('test-*') if p.suffix in ('.py','.ps1')}
    current = set(COMMON_TESTS)
    for data in result.values():
        current.update(arg for command in data.get('checks', []) for arg in command['argv'])
        current.update(data.get('wrapped_tests', {}))
    common_proofs = {p.relative_to(root).as_posix() for folder in ('tools','shared/tests')
                     for p in proof_files(root/folder)}
    if common_proofs-current:
        raise ValueError('Undeclared common proofs: '+', '.join(sorted(common_proofs-current)))
    if common_files-declared:
        raise ValueError('Undeclared common tests: '+', '.join(sorted(common_files-declared)))
    return result


def source_files(root):
    output = subprocess.check_output(['git', 'ls-files', '-c', '-o', '--exclude-standard', '-z'], cwd=root)
    deleted = subprocess.check_output(['git', 'ls-files', '--deleted', '-z'], cwd=root)
    absent = set(deleted.decode('utf-8').split('\0'))
    return sorted(set(relative(p) for p in output.decode('utf-8').split('\0') if p and p not in absent))


def snapshot(root, workspace):
    hashes = {}
    for name in source_files(root):
        source = root/name
        if not source.is_file():
            raise ValueError('Source file is unavailable: '+str(name))
        data = source.read_bytes()
        target = workspace/name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        hashes[name.as_posix()] = hashlib.sha256(data).hexdigest()
    return hashes


def fingerprint(hashes):
    return hashlib.sha256(json.dumps(hashes, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def command_line(argv):
    if argv[0] == 'python':
        return [sys.executable, '-B', *argv[1:]]
    if argv[0] == 'powershell':
        return [shutil.which('pwsh') or shutil.which('powershell') or 'powershell', '-NoProfile', *argv[1:]]
    if argv[0] == 'nasm':
        nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
        return [nasm, *argv[1:]]
    raise ValueError('Unsupported command interpreter: '+argv[0])


def execute(command, cwd, logs, report, owner, phase):
    argv = command_line(command['argv'])
    log = logs/(owner+'--'+command['id']+'.log')
    begin = time.monotonic()
    row = dict(id=command['id'], phase=phase, argv=argv, cwd=str(cwd), log=str(log))
    print('BEGIN '+owner+':'+command['id'], flush=True)
    missing = [name for name in command.get('inputs', []) if not (cwd/relative(name)).exists()]
    if missing:
        row.update(status='blocked', returncode=None, error='Missing inputs: '+', '.join(missing))
        log.write_text(row['error']+'\n', encoding='utf-8')
    else:
        env = os.environ.copy()
        env.update(PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1', BAIOS_BUILD_DIRECTORY='build',
                   BAIOS_DOS_VHD=str(cwd/'reference/media/dos/test-card.vhd'))
        try:
            with log.open('wb') as stream:
                result = subprocess.run(argv, cwd=cwd, env=env, stdout=stream, stderr=subprocess.STDOUT)
            row.update(returncode=result.returncode, status='passed' if result.returncode == 0 else 'failed')
        except OSError as error:
            row.update(returncode=None, status='failed', error=str(error))
            log.write_text(str(error)+'\n', encoding='utf-8')
    row['seconds'] = round(time.monotonic()-begin, 3)
    print(row['status'].upper()+' '+owner+':'+command['id']+' '+str(row['returncode']), flush=True)
    report['commands'].append(row|{'port': owner})
    save(report)
    return row['status'] == 'passed'


def copy_resource(root, workspace, name, protected):
    source, target = root/relative(name), workspace/relative(name)
    if not source.exists():
        raise FileNotFoundError('Missing resource: '+name)
    def copy_file(source, target):
        source = Path(source)
        protected[source.relative_to(root).as_posix()] = digest(source)
        return shutil.copy2(source, target)
    if source.is_dir():
        shutil.copytree(source, target, dirs_exist_ok=True,
                        copy_function=copy_file, ignore=shutil.ignore_patterns('.git', '__pycache__', '*.pyc'))
        files = [p for p in target.rglob('*') if p.is_file()]
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_file(source, target)
        files = [target]
    return dict(path=name, files=len(files), bytes=sum(p.stat().st_size for p in files))


def approved_images(root, ports):
    return {p.relative_to(root).as_posix(): digest(p) for port in ports
            for p in (root/port/'build').glob('*') if p.is_file()
            and p.suffix.lower() in ('.bin', '.rom', '.lst')}


def retain_evidence(workspace, destination, ports):
    destination.mkdir(parents=True, exist_ok=True)
    rows = []
    for base in [workspace/'.agent/test-results', *(workspace/port/'build' for port in ports)]:
        if not base.exists():
            continue
        for folder, directories, files in os.walk(base):
            directories[:] = sorted(d for d in directories if d not in ('deps', '.git', '__pycache__'))
            for name in sorted(files):
                source = Path(folder)/name
                if source.suffix.lower() not in ('.json', '.png', '.bmp', '.csv'):
                    continue
                owned(source, workspace)
                relative_path = source.relative_to(workspace)
                target = destination/relative_path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
                rows.append(dict(path=str(target), size=target.stat().st_size, sha256=digest(target)))
    return rows


def artifacts(workspace, port, data, staging):
    rows = []
    for item in data['artifacts']:
        source = workspace/relative(item['path'])
        raw = source.read_bytes()
        if not raw or len(raw) != item['size']:
            raise ValueError('Incorrect artifact size: '+str(source))
        build_info = json.loads((source.parent/'build-info.json').read_text())
        recorded = next((row for row in build_info['files'] if row['name'] == source.name), None)
        if not recorded or recorded['sha256'] != hashlib.sha256(raw).hexdigest():
            raise ValueError('Artifact has no matching assembly identity: '+str(source))
        target = staging/port/'build'/relative(item['name'])
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        rows.append(dict(name=item['name'], size=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                         sum32=f'{sum(raw):08X}', physical=item.get('physical', False), path=str(target),
                         version=build_info['version'], built_at=recorded['built_at']))
    if not any(row['physical'] for row in rows):
        raise ValueError('No physical ROM declared for '+port)
    if len({row['version'] for row in rows}) != 1:
        raise ValueError('Candidate members have different assembly versions: '+port)
    identity = dict(schema=1, version=rows[0]['version'],
                    files=[{key:row[key] for key in ('name','size','sha256','sum32','built_at')} for row in rows])
    (staging/port/'build/build-info.json').write_text(json.dumps(identity,indent=2)+'\n')
    checked(staging/port)
    return rows


def run(args, data):
    active = {port for port, declaration in data.items() if not declaration.get('hold')}
    selected = sorted(set(args.port or active))
    unknown = set(selected)-data.keys()
    if unknown:
        raise ValueError('Unknown ports: '+', '.join(sorted(unknown)))
    held = set(selected)-active
    if held:
        raise ValueError('Ports on hold: '+', '.join(sorted(held)))
    checks = set(args.check or [])
    known = {command['id'] for port in selected for command in data[port]['checks']
             + (data[port].get('historical_checks', []) if args.historical else [])}
    if checks-known:
        raise ValueError('Unknown checks: '+', '.join(sorted(checks-known)))
    full = set(selected) == active and not checks
    run_root = OWNED/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S')+'-'+uuid.uuid4().hex[:8])
    workspace, logs = run_root/'workspace', run_root/'logs'
    workspace.mkdir(parents=True)
    logs.mkdir()
    report = dict(status='running', full=full, source_fingerprint=None, source_files={},
                  workspace=str(workspace), commands=[], ports={}, resources=[], input_hashes={}, historical_exclusions=[])
    report['held_ports'] = {port: declaration['hold'] for port, declaration in data.items() if declaration.get('hold')}
    save(report)
    original = approved_images(ROOT, data)
    hashes = snapshot(ROOT, workspace)
    report.update(source_files=hashes, source_fingerprint=fingerprint(hashes), approved_images_before=original)
    catalogue_path = ROOT/'docs/private-inputs.json'
    catalogue = json.loads(catalogue_path.read_text(encoding='utf-8')) if catalogue_path.exists() else []
    copied, failed = set(), False
    for port in selected:
        state = report['ports'][port] = dict(status='running', artifacts=[], historical=[])
        try:
            for item in catalogue:
                if item['path'].startswith(port+'/'):
                    source = ROOT/relative(item['path'])
                    if source.stat().st_size != item['size'] or digest(source) != item['sha256']:
                        raise ValueError('Private input identity changed: '+item['path'])
            resources = data[port].get('inputs', []) + data[port].get('resources', [])
            if args.historical:
                resources += [name for command in data[port].get('historical_checks', []) for name in command.get('inputs', [])]
            for name in resources:
                if name not in copied:
                    begin = time.monotonic()
                    print('COPY '+name, flush=True)
                    row = copy_resource(ROOT, workspace, name, report['input_hashes'])
                    row['seconds'] = round(time.monotonic()-begin, 3)
                    report['resources'].append(row)
                    copied.add(name)
        except (OSError, ValueError) as error:
            state.update(status='blocked', error=str(error))
            failed = True
            save(report)
    # Common checks use the real source checkout; firmware commands use the snapshot.
    (run_root/'emulator-helper').mkdir()
    common = [{'id':'organization','argv':['python','tools/test-organization.py']},
              {'id':'layout','argv':['python','tools/check-layout.py']},
              {'id': 'pipeline-self-check', 'argv': ['python','tools/test-port-updates.py']},
              {'id': 'public-source', 'argv': ['python', 'tools/check-public-source.py']},
              {'id': 'emulator-helper', 'argv': ['python', 'shared/tests/test-emulator.py', str(run_root/'emulator-helper')]}]
    if (ROOT/HISTORICAL_COMMON['argv'][1]).is_file():
        if args.historical:
            common.append(HISTORICAL_COMMON)
        else:
            exclusion=dict(port='source',id=HISTORICAL_COMMON['id'],status='excluded-historical',reason=HISTORICAL_COMMON['reason'])
            report['historical_exclusions'].append(exclusion)
            print('EXCLUDED source:'+exclusion['id']+' '+exclusion['reason'],flush=True)
    for command in common:
        if (ROOT/command['argv'][1]).exists():
            if not execute(command, ROOT, logs, report, 'source', 'checks'):
                failed = True
    for port in selected:
        state, declaration = report['ports'][port], data[port]
        if state['status'] == 'blocked':
            continue
        prepared = True
        for command in declaration['prepare']:
            if not execute(command, workspace, logs, report, port, 'prepare'):
                prepared = False
                break
        if not prepared:
            state['status'] = 'blocked'
            failed = True
            continue
        passed = True
        commands = declaration['checks']
        for command in declaration.get('historical_checks', []):
            if args.historical:
                commands = commands+[command]
            else:
                exclusion = dict(port=port, id=command['id'], status='excluded-historical',
                                 reason=command['reason'], inputs=command.get('inputs', []))
                state['historical'].append(exclusion)
                report['historical_exclusions'].append(exclusion)
                print('EXCLUDED '+port+':'+command['id']+' '+command['reason'], flush=True)
        for command in commands:
            if not checks or command['id'] in checks:
                if not execute(command, workspace, logs, report, port, 'checks'):
                    passed = False
        state['status'] = ('partial' if checks else 'passed') if passed else 'failed'
        failed |= not passed
        save(report)
    if not failed and full:
        for port in selected:
            for command in data[port]['candidates']:
                if not execute(command, workspace, logs, report, port, 'candidates'):
                    failed = True
            if not failed:
                try:
                    report['ports'][port]['artifacts'] = artifacts(workspace, port, data[port], run_root/'candidates')
                except (OSError, ValueError) as error:
                    report['ports'][port].update(status='failed', error=str(error))
                    failed = True
    now = {name.as_posix(): digest(ROOT/name) for name in source_files(ROOT)}
    if now != hashes or approved_images(ROOT, data) != original:
        report['preservation_error'] = 'Original source or approved root images changed during validation'
        failed = True
    report['approved_images_unchanged'] = approved_images(ROOT, data) == original
    report['original_inputs_unchanged'] = all(digest(ROOT/relative(name)) == expected for name, expected in report['input_hashes'].items())
    if not report['original_inputs_unchanged']:
        report['preservation_error'] = 'Original private inputs changed during validation'
        failed = True
    if not failed:
        report['evidence'] = retain_evidence(workspace, run_root/'results', selected)
        if full:
            for port in selected:
                cleanup = dict(id='evidence-cleanup', argv=['powershell', '-File', 'tools/clean-port-update.ps1', '-Port', port])
                if not execute(cleanup, ROOT, logs, report, port, 'cleanup'):
                    failed = True
                    break
        if not failed:
            cleanup = dict(id='workspace-cleanup', argv=['powershell', '-File', 'tools/clean-port-update.ps1', '-Path', str(workspace)])
            if not execute(cleanup, ROOT, logs, report, 'source', 'cleanup'):
                failed = True
    report['status'] = 'failed' if failed else 'passed' if full else 'partial'
    report['workspace_retained'] = workspace.exists()
    if not failed and full:
        for port in selected:
            destination = owned(ROOT/port/'build/review/shared-update', ROOT/port/'build')
            destination.mkdir(parents=True, exist_ok=True)
            for row in report['ports'][port]['artifacts']:
                target = owned(destination/relative(row['name']), destination)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(row['path'], target)
                row['path'] = str(target)
            members = report['ports'][port]['artifacts']
            if len({row['version'] for row in members}) != 1:
                raise ValueError('Candidate members have different assembly versions: '+port)
            identity = dict(schema=1, version=members[0]['version'],
                            files=[{key:row[key] for key in ('name','size','sha256','sum32','built_at')} for row in members])
            (destination/'build-info.json').write_text(json.dumps(identity,indent=2)+'\n')
            report['ports'][port]['completed_candidate'] = finish(ROOT/port,destination)
            report['ports'][port]['status'] = 'validated'
        save(report)
        for port in selected:
            destination = owned(ROOT/port/'build/review/shared-update', ROOT/port/'build')
            own_report = {key:report[key] for key in ('status','full','source_fingerprint','held_ports')}
            own_report.update(ports={port:report['ports'][port]},
                              commands=[row for row in report['commands'] if row['port'] == port],
                              common_report=str(CURRENT))
            (destination/'validation-report.json').write_text(json.dumps(own_report,indent=2)+'\n')
            own_logs = destination/'logs'
            own_logs.mkdir(exist_ok=True)
            for log in logs.glob(port+'--*.log'):
                shutil.copy2(log,own_logs/log.name)
            own_results = run_root/'results'/port/'build'
            if own_results.exists():
                shutil.copytree(own_results,destination/'results',dirs_exist_ok=True)
    save(report)
    print(json.dumps({key: report[key] for key in ('status', 'full', 'source_fingerprint', 'workspace_retained')}), flush=True)
    print('Historical exclusions: '+str(len(report['historical_exclusions'])), flush=True)
    print('Report: '+str(CURRENT), flush=True)
    return int(failed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', action='append', help='Select a port; a subset is a partial run without promotion.')
    parser.add_argument('--check', action='append', help='Select a check ID; partial runs cannot promote candidates.')
    parser.add_argument('--historical', action='store_true', help='Also run declared frozen historical diagnostics with their original inputs.')
    parser.add_argument('--list', action='store_true', help='Validate declarations and list commands without building.')
    args = parser.parse_args()
    owned(OWNED, ROOT/'.agent/test-results').mkdir(parents=True, exist_ok=True)
    if not args.list:
        save(dict(status='running', full=False, commands=[], ports={}))
    try:
        data = declarations()
        if args.list:
            print(json.dumps(data, indent=2))
            return 0
        return run(args, data)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        if not args.list:
            report = json.loads(CURRENT.read_text(encoding='utf-8'))
            report.update(status='failed', error=str(error))
            save(report)
        print(str(error), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
