"""Check the documented profile build without prior diagnostic outputs."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

PORT = Path(__file__).resolve().parents[1]


def main():
    (PORT/'build').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='profile-build-', dir=PORT/'build') as folder:
        port = Path(folder)
        shutil.copytree(PORT/'tools', port/'tools',
                        ignore=shutil.ignore_patterns('__pycache__'))
        command = [sys.executable, '-B', str(port/'tools/build-acc-profile.py')]
        subprocess.run(command, cwd=port, check=True)
        out = port/'build/diagnostics'
        result = json.loads((out/'acc-profile-checks.json').read_text())
        assert result['unchanged_diagnostics'] == []
        assert (out/'ACCPROF.COM').stat().st_size == result['size'] > 0
        assert len(result['checks']) == 30
        assert not (out/'ACCPROBE.COM').exists()
        assert not (out/'ACCORDER.COM').exists()
        print('PASS profile build without prior outputs')


if __name__ == '__main__':
    main()
