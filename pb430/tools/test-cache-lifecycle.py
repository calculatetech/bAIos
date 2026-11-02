"""Shared lifecycle adapter retaining independent stock and SRAM fixtures."""
import argparse
import importlib
import json
from pathlib import Path
import subprocess
import sys

PORT = Path(__file__).resolve().parents[1]
ROOT = PORT.parent


def budget():
    proof = importlib.import_module('test-cache-check')
    rows = [proof.post(PORT/'build/baios-pb430.bin', kib=128, ram_mib=ram, transitions=False)
            for ram in (8, 16)]
    assert rows[0]['cold_sram_accesses'] == rows[1]['cold_sram_accesses']
    return dict(id='S7', status='pass', evidence=rows)


def run():
    commands = (
        ('transitions', ['pb430/tools/test-cache-transitions.py']),
        ('sram', ['pb430/tools/test-cache-check.py', 'pb430/build/baios-pb430.bin']),
        ('reference', ['pb430/tools/test-port.py', '--case', 'cache']),
        ('ram-order', ['pb430/tools/test-ram-order.py']),
        ('recovery', ['pb430/tools/test-timing-recovery.py', 'pb430/build/baios-pb430.bin']))
    evidence = []
    for name, argv in commands:
        subprocess.run([sys.executable, '-B', *argv], cwd=ROOT, check=True)
        evidence.append(dict(check=name, command=argv, status='pass'))
    rows = json.loads((PORT/'build/tests/results/cache-transitions.json').read_text())
    assert sum(r.get('operation') == 'cold' for r in rows) == 4
    for required in ('defaults-discard', 'defaults-save', 'rejected-save-followed-CAD'):
        assert any(r.get('operation') == required for r in rows), required
    mapping = {'S1': ('transitions', 'reference'), 'S2': ('transitions',),
               'S3': ('transitions', 'sram'), 'S4': ('transitions',),
               'S5': ('transitions',), 'S6': ('sram', 'reference'),
               'S7': ('sram',), 'S8': ('ram-order',), 'S9': ('sram', 'recovery'),
               'S10': ('reference', 'transitions')}
    result = [dict(id=k, status='pass', evidence=[r for r in evidence if r['check'] in names])
              for k, names in mapping.items()]
    result[6]['evidence'].extend(budget()['evidence'])
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget-only', action='store_true')
    args = parser.parse_args()
    result = [budget()] if args.budget_only else run()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(port='pb430', scenarios=result), indent=2)+'\n')
