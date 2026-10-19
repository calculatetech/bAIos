import configparser
import os
from pathlib import Path
import shutil
import subprocess


def run_86box(vm, roms, timeout=90, executable=None):
    vm, roms = Path(vm).resolve(), Path(roms).resolve()
    # Saved emulated flash overrides the ROM staged by a test fixture.
    config = configparser.ConfigParser()
    config.read(vm / '86box.cfg')
    machine = config.get('Machine', 'machine', fallback='')
    if machine:
        flash = (vm / 'nvr' / (machine + '.bin')).resolve()
        if not flash.is_relative_to(vm):
            raise ValueError('Saved flash must stay inside the test VM')
        flash.unlink(missing_ok=True)
    executable = executable or shutil.which('86Box.exe')
    if not executable:
        executable = Path(os.environ['LOCALAPPDATA']) / 'Microsoft/WinGet/Packages/86Box.86Box_Microsoft.Winget.Source_8wekyb3d8bbwe/86Box.exe'
    command = [str(executable), '-P', str(vm), '-R', str(roms), '-L', str(vm / '86box.log'), '-N']
    options = {}
    if os.name == 'nt':
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = 0
        options['startupinfo'] = startup
        options['creationflags'] = subprocess.CREATE_NO_WINDOW
    with (vm / 'emulator-output.txt').open('wb') as output:
        process = subprocess.Popen(command, cwd=vm, stdout=output, stderr=output, **options)
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            raise TimeoutError(f'86Box did not reach a terminal result within {timeout} seconds; fixture: {vm}') from None
    return code
