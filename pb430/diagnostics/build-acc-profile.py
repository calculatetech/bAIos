"""Build the combined ACC2168 timing experiment using the existing probe engine."""
import importlib
import json
import os
from pathlib import Path
import shutil
import subprocess

PORT = Path(__file__).resolve().parents[1]


def main():
    out = PORT / 'build/diagnostics'
    out.mkdir(parents=True, exist_ok=True)
    nasm = shutil.which('nasm') or str(Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe')
    source = PORT/'diagnostics/acc-timing.asm'
    image = out/'ACCPROF.COM'
    subprocess.run([nasm, '-w+error', '-f', 'bin', '-DACC_PROFILE',
                    '-I'+str(PORT/'diagnostics')+'/', '-o', str(image), str(source)], check=True)
    raw = image.read_bytes()
    cases = ['trial05', 'trial-128', 'bad-ram', 'bad-a20', 'bad-ticks',
             'bad-argument', 'v86', 'xms', 'little-memory', 'wrong-cache',
             'wrong-timer', 'short-output', 'output-error']
    for prefix, indices in (('readback', (1,0x0B,0x16,0x19)),
                            ('restore', (1,0x0B,0x16,0x19)),
                            ('wrong', (1,4,5,0x0B,0x12,0x14,0x16,0x18,0x19))):
        cases.extend(f'profile-{prefix}-{index:02x}' for index in indices)
    checks = importlib.import_module('build-acc-timing').check(raw, cases, profile=True)
    # Conditional assembly must leave both already-delivered diagnostics intact.
    unchanged = []
    for name, defines in (('ACCPROBE', []), ('ACCORDER', ['-DACC_ORDER'])):
        retained = out/(name+'.COM')
        if not retained.exists():
            continue
        temporary = out/(name+'-unchanged.COM')
        subprocess.run([nasm, '-w+error', '-f', 'bin', *defines,
                        '-I'+str(PORT/'diagnostics')+'/', '-o', str(temporary), str(source)], check=True)
        assert temporary.read_bytes() == retained.read_bytes(), name
        temporary.unlink()
        unchanged.append(name)
    result = {'path':str(image), 'size':len(raw), 'sum32':f'{sum(raw):08X}',
              'checks':checks, 'unchanged_diagnostics':unchanged,
              'scope':'Assembled-code checks with synthetic devices. Physical timing and stability remain untested.'}
    (out/'acc-profile-checks.json').write_text(json.dumps(result,indent=2)+'\n')
    print(f'{image}: {len(raw)} bytes, SUM32 {sum(raw):08X}; {len(checks)} checks passed')


if __name__ == '__main__':
    main()
