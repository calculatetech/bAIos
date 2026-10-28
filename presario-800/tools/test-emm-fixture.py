"""Exercise real EMM fixture owners; synthetic process exits prove host lifecycle only."""
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import uuid

PORT = Path(__file__).resolve().parents[1]
ROOT = PORT.parent
WRAPPER = 'machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin'
SCENARIOS = ('absent-failure', 'absent-success', 'guarded-cleanup', 'selected-failure', 'selected-success')


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            result.update(chunk)
    return result.hexdigest()


def inventory(folder):
    return {p.relative_to(folder).as_posix(): digest(p) if p.is_file() else 'directory'
            for p in folder.rglob('*')}


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def powershell(body, env=None):
    return subprocess.run([shutil.which('pwsh') or 'powershell', '-NoProfile', '-Command', body],
                          env=env, capture_output=True, text=True, errors='replace',
                          creationflags=subprocess.CREATE_NO_WINDOW)


def ended(pid):
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.restype = ctypes.c_void_p
    kernel.GetExitCodeProcess.argtypes = (ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong))
    kernel.CloseHandle.argtypes = (ctypes.c_void_p,)
    handle = kernel.OpenProcess(0x1000, False, pid)
    if not handle and ctypes.get_last_error() != 87:
        raise ctypes.WinError(ctypes.get_last_error())
    if handle:
        try:
            code = ctypes.c_ulong()
            assert kernel.GetExitCodeProcess(handle, ctypes.byref(code))
            assert code.value != 259, ('owned emulator is still running', pid)
        finally:
            kernel.CloseHandle(handle)


def fake_emulator(control):
    """Only the external process is synthetic; no runner/config/NVR owner is replaced."""
    source = control / 'fake.cs'
    source.write_text(r'''using System;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
class EmmFixtureProcess {
 static string Hash(string path) {
  path = @"\\?\" + path.Replace('/', '\\');
  if (!File.Exists(path)) return "absent";
  using (var hash = SHA256.Create())
  using (var stream = File.OpenRead(path))
   return BitConverter.ToString(hash.ComputeHash(stream)).Replace("-", "").ToLowerInvariant();
 }
 static int Main(string[] args) {
  AppContext.SetSwitch("Switch.System.IO.UseLegacyPathHandling", false);
  AppContext.SetSwitch("Switch.System.IO.BlockLongPaths", false);
  string vm = null, roms = null;
  for (int i = 0; i + 1 < args.Length; i++) {
   if (args[i] == "-P") vm = args[++i];
   else if (args[i] == "-R") roms = args[++i];
  }
  if (vm == null || roms == null) return 127;
  string wrapper = Path.Combine(roms, "machines/d824/fts-biosupdated824noflashbiosepromv320-320334-160.bin");
  File.WriteAllLines(Environment.GetEnvironmentVariable("BAIOS_EMM_PROCESS_LOG"), new[] {
   "pid=" + Process.GetCurrentProcess().Id, "vm=" + vm, "roms=" + roms,
   "wrapper_sha256=" + Hash(wrapper), "config_sha256=" + Hash(Path.Combine(vm, "86box.cfg")),
   "nvr_sha256=" + Hash(Path.Combine(vm, "nvr/d824.nvr"))
  }, new UTF8Encoding(false));
  return int.Parse(Environment.GetEnvironmentVariable("BAIOS_EMM_PROCESS_EXIT"));
 }
}
''')
    compiler = shutil.which('csc.exe') or str(Path(os.environ['WINDIR']) / 'Microsoft.NET/Framework64/v4.0.30319/csc.exe')
    target = control / '86Box.exe'
    target.with_suffix('.exe.config').write_text(
        '<configuration><runtime><AppContextSwitchOverrides value="'
        'Switch.System.IO.UseLegacyPathHandling=false;Switch.System.IO.BlockLongPaths=false'
        '"/></runtime></configuration>')
    subprocess.run([compiler, '/nologo', '/target:winexe', '/out:' + str(target), str(source)],
                   check=True, creationflags=subprocess.CREATE_NO_WINDOW)
    return target


def run_case(workspace, control, image, name, selection, code, numlock, production=False):
    port = workspace / 'presario-800'
    log, environment = control / (name + '.process.txt'), control / (name + '.env.json')
    env = os.environ.copy()
    env['PATH'] = str(control) + os.pathsep + env['PATH']
    env['BAIOS_EMM_PROCESS_LOG'], env['BAIOS_EMM_PROCESS_EXIT'] = str(log), str(code)
    if selection is None:
        env.pop('BAIOS_BUILD_DIRECTORY', None)
    else:
        env['BAIOS_BUILD_DIRECTORY'] = selection
    command = ('& ' + quote(port / 'tools/test-emm-reset.ps1') + ' -ImagePath ' + quote(image) +
               ' -BootNumLock ' + numlock + (' -ProductionRom' if production else ''))
    body = """$ErrorActionPreference='Stop';
$before=Get-Item Env:BAIOS_BUILD_DIRECTORY -ErrorAction SilentlyContinue; $failed=$false;
try { COMMAND } catch { Write-Output $_; $failed=$true } finally {
 $after=Get-Item Env:BAIOS_BUILD_DIRECTORY -ErrorAction SilentlyContinue;
 [ordered]@{before_present=($null -ne $before);before_value=$(if($before){$before.Value}else{$null});
 after_present=($null -ne $after);after_value=$(if($after){$after.Value}else{$null})} |
 ConvertTo-Json | Set-Content -LiteralPath ENVIRONMENT -Encoding utf8
}; if($failed){exit 1}; exit 0
""".replace('COMMAND', command).replace('ENVIRONMENT', quote(environment))
    result = powershell(body, env)
    (control / (name + '.output.txt')).write_text(result.stdout + result.stderr)
    assert (result.returncode == 0) == (code == 0x67), (name, result.stdout, result.stderr)
    state = json.loads(environment.read_text(encoding='utf-8-sig'))
    assert state == dict(before_present=selection is not None, before_value=selection,
                         after_present=selection is not None, after_value=selection), state
    process = dict(line.split('=', 1) for line in log.read_text(encoding='utf-8-sig').splitlines())
    ended(int(process['pid']))
    vm, roms = Path(process['vm']), Path(process['roms'])
    invocation = vm.parents[2]
    source = port / (selection or 'build')
    assert invocation.parent == port / 'build/diagnostics', (invocation, source)
    assert vm == invocation / 'tests/86box/card-vm' and roms == invocation / 'tests/86box/roms'
    if code == 0x67:
        assert not invocation.exists(), 'successful invocation was not consumed'
        if production:
            assert process['wrapper_sha256'] == digest(source / 'baios-presario800.bin')
    else:
        assert invocation.is_dir(), 'failed invocation was removed'
        record = json.loads((invocation / 'invocation.json').read_text(encoding='utf-8-sig'))
        assert record['status'] == 'failed' and record['initial_nvram_present'] is False
        assert Path(record['source_build']) == source
        assert Path(record['source_path']) == port / 'src/bios.asm'
        assert (invocation / 'bios.asm').read_bytes() == (port / 'src/bios.asm').read_bytes()
        selected = (source / 'baios-presario800.bin').read_bytes()
        assert (invocation / 'baios-presario800.bin').read_bytes() == selected
        wrapper = (roms / WRAPPER).read_bytes()
        assert wrapper[:65536] == selected[:65536]
        assert wrapper[65536:] == (invocation / 'system.rom').read_bytes()
        assert sum(wrapper[65536:]) & 255 == 0
        assert process['wrapper_sha256'] == digest(roms / WRAPPER)
        for relative in ('reset.com', 'test.vhd', 'tests/86box/card-vm/86box.cfg', 'tests/86box/card-vm/nvr/d824.nvr'):
            assert (invocation / relative).is_file(), (name, relative)
        assert process['config_sha256'] == digest(vm / '86box.cfg')
        assert process['nvr_sha256'] == digest(vm / 'nvr/d824.nvr')
        nvr = (vm / 'nvr/d824.nvr').read_bytes()
        # Default's final deliberate On policy is enabled only after the native Stage A contrast.
        expected = 0 if numlock == 'Off' else 1
        assert nvr[0x38:0x3B] == b'B8\x02' and nvr[0x3B] == (0x12 | expected)
        assert str(invocation).replace('\\', '/') in (vm / '86box.cfg').read_text(encoding='utf-8-sig')
    return dict(case=name, returncode=result.returncode, environment=state, process=process,
                invocation=str(invocation), evidence=inventory(invocation) if invocation.exists() else 'consumed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('image', nargs='?', type=Path, default=PORT.parent / 'reference/media/dos/test-card.vhd')
    parser.add_argument('--list', action='store_true', help='List lifecycle scenarios without running them.')
    args = parser.parse_args()
    if args.list:
        print('\n'.join(SCENARIOS))
        return
    if os.name != 'nt':
        raise RuntimeError('This existing PowerShell/.NET fixture check requires Windows.')
    image = args.image.resolve()
    images = {clock: (PORT / f'build/baios-presario800-vga{clock}.bin').read_bytes() for clock in (50, 60)}
    assert all(len(value) == 131072 and not sum(value[65536:]) & 255 for value in images.values())
    assert images[50][65536:] == images[60][65536:]
    for value in images.values():
        assert value[:3] == bytes.fromhex('55AA40') and sum(value[:32768]) & 255 == 0
        assert value[65536+0xFFF0:65536+0xFFF5] == bytes.fromhex('EA000000F0')
    assert [i for i in range(131072) if images[50][i] != images[60][i]] == [0x8E7, 32767]
    originals = [image, *(PORT / 'build' / name for name in
                 ('baios-presario800.bin', 'baios-presario800-system.rom',
                  'baios-presario800-vga50.bin', 'baios-presario800-vga60.bin'))]
    originals += [p for p in (PORT / 'build/tests/86box').rglob('*') if p.is_file()]
    originals += [PORT / name for name in ('tools/test-emm-reset.ps1', 'tools/run-card-vhd.ps1',
                  'tools/memory-fixture.py', 'tests/emm-reset-test.asm', 'src/bios.asm')]
    originals.append(ROOT / 'shared/src/pc/keyboard-irq.inc')
    before = {str(p): digest(p) for p in originals}
    run = ROOT / '.agent/test-results/port-update' / ('ef-' + uuid.uuid4().hex[:8])
    workspace = run / 'workspace'
    workspace.mkdir(parents=True)
    report = ROOT / '.agent/test-results/emm-fixture.json'
    outcome = dict(status='running', workspace=str(workspace), proof='host fixture lifecycle; no native reset evidence')
    report.write_text(json.dumps(outcome, indent=2) + '\n')
    try:
        for relative in ('presario-800/src', 'presario-800/tests', 'presario-800/tools', 'shared'):
            shutil.copytree(ROOT / relative, workspace / relative, ignore=shutil.ignore_patterns('__pycache__'))
        port = workspace / 'presario-800'
        source_builds = (port / 'build', port / 'build/tmp/pending-provider')
        for build, clock in zip(source_builds, (50, 60)):
            (build / 'tests/86box').mkdir(parents=True, exist_ok=True)
            shutil.copytree(PORT / 'build/tests/86box/roms', build / 'tests/86box/roms')
            (build / 'baios-presario800.bin').write_bytes(images[clock])
            (build / 'baios-presario800-system.rom').write_bytes(images[clock][65536:])
            (build / 'tests/86box/roms' / WRAPPER).write_bytes(images[clock])
            sentinel = build / 'tests/86box/card-vm/nvr/d824.nvr'
            sentinel.parent.mkdir(parents=True)
            sentinel.write_bytes(b'caller-owned-nvr' + bytes(240))
        decoy = source_builds[1] / 'src/bios.asm'
        decoy.parent.mkdir()
        decoy.write_text('Selected build is data; this invalid assembly must never be compiled.\n')
        protected = {str(p): digest(p) for build in source_builds for p in build.rglob('*') if p.is_file()}
        control = workspace / 'control'
        control.mkdir()
        fake_emulator(control)
        cases = []
        for name, selection, code, numlock, production in (
                ('absent-failure', None, 0x76, 'Default', False),
                ('absent-success', None, 0x67, 'Default', False),
                ('selected-success', 'build/tmp/pending-provider', 0x67, 'Off', True),
                ('selected-failure', 'build/tmp/pending-provider', 0x76, 'On', False)):
            cases.append(run_case(workspace, control, image, name, selection, code, numlock, production))
            for row in cases:
                if row['evidence'] != 'consumed':
                    assert inventory(Path(row['invocation'])) == row['evidence'], 'later invocation changed failed evidence'
            assert all(digest(Path(path)) == value for path, value in protected.items())
        assert cases[0]['process']['wrapper_sha256'] == cases[1]['process']['wrapper_sha256']
        # The failed fixture is an active retention-test input, consumed after this check.
        retention = workspace / 'retention'
        for relative in ('presario-800/tools/clean-build.ps1', 'shared/tools/build-cleanup.ps1'):
            target = retention / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, target)
        failed = Path(cases[0]['invocation'])
        retained = retention / 'presario-800/build/diagnostics' / failed.name
        shutil.copytree(failed, retained)
        retained_before = inventory(retained)
        current = retention / 'presario-800/build/baios-presario800.bin'
        current.write_bytes(images[50])
        obsolete = retention / 'presario-800/build/tmp/consumed.txt'
        obsolete.parent.mkdir()
        obsolete.write_text('Consumed fixture output\n')
        provider = retention / 'presario-800/build/tmp/pending-provider/old.bin'
        provider.parent.mkdir()
        provider.write_bytes(b'consumed provider')
        command = '& ' + quote(retention / 'presario-800/tools/clean-build.ps1')
        prior = inventory(retention)
        result = powershell(command + ' -WhatIf')
        assert result.returncode == 0 and inventory(retention) == prior, result.stderr
        result = powershell(command)
        assert result.returncode == 0 and not obsolete.exists() and not provider.exists(), result.stderr
        assert inventory(retained) == retained_before and current.read_bytes() == images[50]
        for row in cases:
            if row['evidence'] != 'consumed':
                assert inventory(Path(row['invocation'])) == row['evidence'], 'cleanup changed failed diagnosis'
        assert all(digest(Path(path)) == value for path, value in protected.items())
        assert before == {str(p): digest(p) for p in originals}, 'original inputs changed'
        outcome.update(status='passed', cases=cases, original_hashes=before, cleanup='actual WhatIf/apply preserved failed diagnostics')
        result = powershell('& ' + quote(ROOT / 'tools/clean-port-update.ps1') + ' -Path ' + quote(workspace))
        assert result.returncode == 0 and not workspace.exists(), result.stderr
        run.rmdir()
        print('PASS actual EMM wrapper/NASM/media/runner lifecycle, selected source, environment, config/NVR and guarded cleanup; synthetic process only')
    except BaseException as error:
        outcome.update(status='failed', error=str(error))
        raise
    finally:
        report.write_text(json.dumps(outcome, indent=2) + '\n')


if __name__ == '__main__':
    main()
