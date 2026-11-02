"""Run the common cache scenarios using isolated, independent port fixtures."""
import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import subprocess
import sys
import shutil
import uuid
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
PORTS = ('m919', 'mp386', 'pb430', 'presario-800')
SCENARIOS = tuple(f'S{i}' for i in range(1, 11))


def validate(port, rows):
    required = {'preservation'} if port == 'mp386' else set(SCENARIOS)
    seen = set()
    for row in rows:
        identity = row['id']
        assert identity in required and identity not in seen, (port, identity)
        seen.add(identity)
        assert row['status'] == 'pass', (port, row)
        assert row['evidence'], (port, identity, 'missing evidence')
    assert seen == required, (port, 'missing', sorted(required - seen))


def self_check():
    rows = [dict(id=s, status='pass', evidence=['fixture']) for s in SCENARIOS]
    validate('m919', rows)
    for bad in ([], rows[:-1], rows + [rows[0]],
                rows[:-1] + [dict(rows[-1], status='fail')]):
        try:
            validate('m919', bad)
        except AssertionError:
            continue
        raise AssertionError('Incomplete or failed scenario inventory accepted')
    folder = ROOT/'.agent/test-results'
    folder.mkdir(parents=True, exist_ok=True)
    target = (folder / ('cache-runner-' + uuid.uuid4().hex)).resolve()
    assert target.is_relative_to(folder.resolve())
    target.mkdir()
    try:
        seen = []
        def adapter(command, **unused):
            port = Path(command[2]).parts[-3]
            seen.append(port)
            identities = ('preservation',) if port == 'mp386' else SCENARIOS
            output = Path(command[-1])
            output.write_text(json.dumps(dict(port=port, scenarios=[
                dict(id=s, status='pass', evidence=['external adapter fixture']) for s in identities])))
        with patch(__name__+'.ROOT', target), patch.object(subprocess, 'run', side_effect=adapter), redirect_stdout(StringIO()):
            run(PORTS)
        assert seen == ['m919', 'mp386', 'pb430', 'presario-800'], seen
    finally:
        shutil.rmtree(target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', choices=('all', *PORTS), default='all')
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    self_check()
    if args.self_check:
        print('PASS cache scenario inventory: complete, missing, duplicate and late failure')
        return
    run(PORTS if args.port == 'all' else (args.port,))


def run(ports):
    for port in ports:
        output = ROOT / port / 'build/tests/cache-lifecycle/proof.json'
        output.parent.mkdir(parents=True, exist_ok=True)
        output.unlink(missing_ok=True)
        command = [sys.executable, '-B', str(ROOT / port / 'tools/test-cache-lifecycle.py'),
                   '--output', str(output)]
        subprocess.run(command, cwd=ROOT, check=True)
        report = json.loads(output.read_text())
        assert report['port'] == port, report['port']
        validate(port, report['scenarios'])
        print(f'PASS {port}: {len(report["scenarios"])} cache scenario results; {output}', flush=True)


if __name__ == '__main__':
    main()
