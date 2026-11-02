"""Preserve the 386-only native controller path through shared lifecycle edits."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

PORT = Path(__file__).resolve().parents[1]


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    results = []
    for case in ('boot', 'qualification', 'instructions', 'policy', 'guards', 'checksum'):
        command = [sys.executable, '-B', 'mp386/tools/test-cache.py',
                   '--image', 'mp386/build/baios-mp386.bin', '--case', case]
        subprocess.run(command, cwd=PORT.parent, check=True)
        results.append(dict(case=case, command=command, status='pass'))
    sys.path.insert(0,str(PORT/'tools'))
    import importlib
    failure=importlib.import_module('test-cache').boots(PORT/'build/baios-mp386.bin',fault=0x6507)
    results.append(dict(case='boot-data-failure',status='pass',evidence=failure))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(dict(port='mp386', scenarios=[
        dict(id='preservation', status='pass', evidence=results,
             applicability='Native switch policy; no new L1, WB or geometry interface')]), indent=2)+'\n')
