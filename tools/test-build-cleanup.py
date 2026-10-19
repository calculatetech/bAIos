"""Exercise actual cleanup commands on owned disposable repository fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
RESULTS = ROOT / '.agent/test-results'
SCRIPTS = ('tools/clean-build.ps1', 'shared/tools/build-cleanup.ps1',
           'presario-800/tools/clean-build.ps1', 'm919/tools/clean-build.ps1')
CASES = []


def inventory(folder):
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            if p.is_file() else 'directory' for p in folder.rglob('*')}


def quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def ps(name, body, *, error=None, running=False):
    # Replace only opaque process discovery. Actual safety, ShouldProcess and filesystem run.
    seam = 'function global:Get-Process { ' + ('[pscustomobject]@{Id=1}' if running else '$null') + ' }; '
    result = subprocess.run(['pwsh', '-NoProfile', '-Command', seam + "$ErrorActionPreference='Stop'; " + body],
                            capture_output=True, text=True, errors='replace',
                            creationflags=subprocess.CREATE_NO_WINDOW)
    output = result.stdout + result.stderr
    assert (result.returncode != 0 and error in output) if error else result.returncode == 0, output
    CASES.append({'case': name, 'command': body, 'exit': result.returncode,
                  'expected_error': error, 'output': output})


def put(folder, path):
    target = folder / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(('retained or disposable fixture: ' + path).encode())
    return target


def direct_port_checks(fixture, outside):
    for port, current_name in (('presario-800', 'baios-presario800-vga50.bin'),
                               ('m919', 'baios-m919.bin')):
        repository = fixture / ('direct-' + port)
        for source in ('shared/tools/build-cleanup.ps1', port + '/tools/clean-build.ps1'):
            target = repository / source
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, target)
        current = put(repository, port + '/build/' + current_name)
        obsolete = put(repository, port + '/build/obsolete/generated.bin')
        if port == 'm919':
            put(repository, port + '/build/post-tests/core-cd-secondary/cd.iso')
            put(repository, port + '/build/post-tests/core-cd-secondary/screen.png')
        if port == 'presario-800':
            put(repository, port + '/build/tmp/first.bin')
            put(repository, port + '/build/tmp/nested/last.bin')
        command = '& ' + quote(repository / port / 'tools/clean-build.ps1')
        before = inventory(repository)
        ps(port + ' direct running guard', command, error='An emulator is running', running=True)
        after = inventory(repository)
        assert before == after
        CASES[-1].update({'inventory_before': before, 'inventory_after': after})
        ps(port + ' direct stopped apply', command)
        after = inventory(repository)
        assert not obsolete.exists() and current.exists()
        expected = {p: value for p, value in before.items()
                    if p != port + '/build/obsolete' and not p.startswith(port + '/build/obsolete/')
                    and not (port == 'presario-800' and p.startswith(port + '/build/tmp/'))
                    and p != 'm919/build/post-tests/core-cd-secondary/cd.iso'}
        assert after == expected
        CASES[-1].update({'inventory_before': before, 'inventory_after': after})
        build = repository / port / 'build'
        if port == 'presario-800':
            scratch = build / 'tmp'
            assert scratch.is_dir() and not list(scratch.iterdir())
            with tempfile.TemporaryDirectory(prefix='native-reader-', dir=scratch) as temporary:
                native = Path(temporary)
                assert native.is_dir() and native.parent == scratch
            assert not native.exists() and scratch.is_dir() and not list(scratch.iterdir())
            CASES.append({'case': 'Presario direct cleanup retains native tempfile parent',
                          'command': 'native tempfile.TemporaryDirectory(prefix="native-reader-", dir=retained_tmp)',
                          'exit': 0, 'parent_retained_empty': True, 'native_context_disposed': True})
            saved_tmp = repository / port / 'saved-tmp-control'
            assert scratch.resolve().is_relative_to(repository.resolve()) and saved_tmp.resolve().is_relative_to(repository.resolve())
            ps('Presario move owned tmp control', 'Move-Item -LiteralPath ' + quote(scratch) + ' -Destination ' + quote(saved_tmp))
            empty_outside = fixture / 'empty-outside'
            empty_outside.mkdir()
            ps('Presario create empty-target tmp junction', 'New-Item -ItemType Junction -Path ' + quote(scratch) + ' -Target ' + quote(empty_outside) + ' | Out-Null')
            before = inventory(repository)
            sentinel_before = inventory(outside)
            ps('Presario direct empty tmp junction refuses', command, error='Reparse')
            after = inventory(repository)
            assert before == after and inventory(outside) == sentinel_before and not list(empty_outside.iterdir())
            CASES[-1].update({'inventory_before': before, 'inventory_after': after,
                             'outside_before': sentinel_before, 'outside_after': inventory(outside),
                             'empty_outside_preserved': True})
            ps('Presario remove owned tmp junction', 'Remove-Item -LiteralPath ' + quote(scratch) + ' -Force')
            assert saved_tmp.resolve().is_relative_to(repository.resolve()) and scratch.resolve().is_relative_to(repository.resolve())
            ps('Presario restore owned tmp control', 'Move-Item -LiteralPath ' + quote(saved_tmp) + ' -Destination ' + quote(scratch))
        for label, junction in (('child', build / 'obsolete-junction'),
                                ('nested descendant', build / 'obsolete/nested/child')):
            junction.parent.mkdir(parents=True, exist_ok=True)
            ps(port + ' create ' + label + ' junction', 'New-Item -ItemType Junction -Path ' +
               quote(junction) + ' -Target ' + quote(outside) + ' | Out-Null')
            before = inventory(repository)
            sentinel_before = inventory(outside)
            ps(port + ' direct ' + label + ' junction refuses', command, error='Reparse')
            after = inventory(repository)
            assert after == before and inventory(outside) == sentinel_before
            CASES[-1].update({'inventory_before': before, 'inventory_after': after,
                             'outside_before': sentinel_before, 'outside_after': inventory(outside)})
            ps(port + ' remove owned ' + label + ' junction', 'Remove-Item -LiteralPath ' + quote(junction) + ' -Force')
        ps(port + ' direct ordinary directory refresh', command)
        # The wrapper must reject its own build ancestor, without the root dispatcher.
        saved = repository / port / 'saved-build'
        assert build.resolve().is_relative_to(repository.resolve()) and saved.resolve().is_relative_to(repository.resolve())
        ps(port + ' move owned build control', 'Move-Item -LiteralPath ' + quote(build) + ' -Destination ' + quote(saved))
        ps(port + ' create build ancestor junction', 'New-Item -ItemType Junction -Path ' + quote(build) +
           ' -Target ' + quote(outside) + ' | Out-Null')
        before = inventory(repository)
        sentinel_before = inventory(outside)
        ps(port + ' direct build ancestor junction refuses', command, error='Reparse')
        after = inventory(repository)
        assert before == after and inventory(outside) == sentinel_before
        CASES[-1].update({'inventory_before': before, 'inventory_after': after,
                         'outside_before': sentinel_before, 'outside_after': inventory(outside)})
        ps(port + ' remove owned build ancestor junction', 'Remove-Item -LiteralPath ' + quote(build) + ' -Force')
        ps(port + ' restore owned build control', 'Move-Item -LiteralPath ' + quote(saved) + ' -Destination ' + quote(build))


def main():
    RESULTS.mkdir(parents=True, exist_ok=True)
    fixture = Path(tempfile.mkdtemp(prefix='cleanup-', dir=RESULTS)).resolve()
    assert fixture.is_relative_to(RESULTS.resolve())
    outside = fixture / 'outside'
    outside.mkdir()
    put(outside, 'sentinel.txt')
    repository = fixture / 'repository'
    for source in SCRIPTS:
        target = repository / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)
    retained = ('presario-800/build/baios-presario800-vga50.bin',
                'presario-800/build/baios-presario800-vga60.bin',
                'presario-800/build/baios-presario800-system.rom',
                'presario-800/build/presario800-card.vhd',
                'presario-800/build/review/baios-presario800-vga50.bin',
                'presario-800/build/review/baios-presario800-vga60.bin',
                'presario-800/build/review/baios-presario800-system.rom',
                'presario-800/build/chipset-review/current/screen.png',
                'presario-800/docs/jumpers.pdf', 'presario-800/src/user.asm',
                'reference/software/speedsys/4.78/SPEEDSYS-code.bin',
                'm919/build/baios-m919.bin', 'm919/build/baios-m919.lst',
                'm919/build/configuration.inc', 'm919/build/rom-checksums.json',
                'm919/build/diagnostics/current-failed/vm/86box.cfg',
                'm919/build/diagnostics/current-failed/disk.img',
                'm919/build/hardware-research/current.json',
                'm919/build/post-tests/current/screen.png',
                'm919/build/post-tests/current/output.txt',
                'm919/build/post-tests/current/86box.cfg',
                'm919/build/post-tests/current/screen.nvr',
                'm919/build/post-tests/current/observer.bin',
                'm919/build/final-display/current.png', '.vscode/user.json')
    obsolete = ('presario-800/build/post-ui/obsolete.bin',
                'presario-800/build/post-ui-50/obsolete.bin',
                'presario-800/build/later-obsolete/obsolete.bin',
                'presario-800/build/tmp/old.bin',
                'presario-800/build/research/old.bin',
                'presario-800/build/cd-review/preview.pid',
                'presario-800/build/chipset-review/completed-vm/86box.cfg',
                'presario-800/build/chipset-review/completed-vm/disk.img',
                'm919/build/physical-core/old.bin', 'm919/build/cache-correction/old.bin',
                'm919/build/later-obsolete/old.bin', 'm919/build/build-tests/current/old.bin',
                'm919/build/post-tests/current/vm/86box.cfg',
                'm919/build/post-tests/current/disk.img', 'm919/build/post-tests/current/cd.iso',
                'build/shared-tools-validation/old.bin')
    for path in retained + obsolete:
        put(repository, path)
    before = inventory(repository)
    command = '& ' + quote(repository / SCRIPTS[0])
    ps('all-port preview', command + ' -WhatIf')
    assert before == inventory(repository), 'Preview changed files or directories'
    ps('running emulator refuses before deletion', command, error='An emulator is running', running=True)
    assert before == inventory(repository)
    ps('invalid port refuses', command + " -Port '../outside'", error='Unknown maintained port')
    assert before == inventory(repository)
    ps('single port apply', command + " -Port 'm919'")
    assert (repository / obsolete[0]).is_file() and (repository / obsolete[-1]).is_file()
    assert not (repository / 'm919/build/later-obsolete').exists()
    ps('all ports and root scratch apply', command)
    assert all((repository / p).is_file() for p in retained)
    assert all(not (repository / p).exists() for p in obsolete)
    scratch = repository / 'presario-800/build/tmp'
    assert scratch.is_dir() and not list(scratch.iterdir())
    with tempfile.TemporaryDirectory(prefix='native-reader-', dir=scratch) as temporary:
        native = Path(temporary)
        assert native.is_dir() and native.parent == scratch
    assert not native.exists() and scratch.is_dir() and not list(scratch.iterdir())
    CASES.append({'case': 'root cleanup retains Presario native tempfile parent',
                  'command': 'native tempfile.TemporaryDirectory(prefix="native-reader-", dir=retained_tmp)',
                  'exit': 0, 'parent_retained_empty': True, 'native_context_disposed': True})
    after = inventory(repository)
    assert all(after[p] == before[p] for p in retained)
    ps('repeated apply', command)
    assert after == inventory(repository)
    # The real deletion owner rejects an outside target and a root target.
    helper = '. ' + quote(repository / SCRIPTS[1]) + '; Initialize-BuildCleanup ' + quote(repository / 'build') + ' $null; '
    ps('outside target rejects', helper + 'Remove-Generated ' + quote(outside), error='outside build')
    ps('build root rejects', helper + 'Remove-Generated ' + quote(repository / 'build'), error='outside build')
    linked = repository / 'm919/build/obsolete-junction'
    ps('create child junction', 'New-Item -ItemType Junction -Path ' + quote(linked) + ' -Target ' + quote(outside) + ' | Out-Null')
    ps('child junction rejects', command + " -Port 'm919'", error='Reparse')
    assert (outside / 'sentinel.txt').is_file()
    # Delete only the junction itself, with native PowerShell; never traverse its target.
    ps('remove owned junction', 'Remove-Item -LiteralPath ' + quote(linked) + ' -Force')
    nested = repository / 'm919/build/obsolete/child'
    nested.parent.mkdir()
    ps('create nested junction', 'New-Item -ItemType Junction -Path ' + quote(nested) + ' -Target ' + quote(outside) + ' | Out-Null')
    ps('nested junction rejects', command + " -Port 'm919'", error='Reparse child')
    ps('remove nested junction', 'Remove-Item -LiteralPath ' + quote(nested) + ' -Force')
    ps('post-rejection apply', command)
    # Empty and one maintained port are valid; root mechanics contain no model names.
    empty = fixture / 'empty'
    for source in SCRIPTS[:2]:
        target = empty / source
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / source, target)
    put(empty, 'build/scratch.txt')
    ps('zero ports and root scratch', '& ' + quote(empty / SCRIPTS[0]))
    assert not (empty / 'build/scratch.txt').exists()
    source = SCRIPTS[3]
    target = empty / source
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(ROOT / source, target)
    put(empty, 'm919/build/baios-m919.bin')
    put(empty, 'm919/build/obsolete.txt')
    ps('one maintained port', '& ' + quote(empty / SCRIPTS[0]))
    assert (empty / 'm919/build/baios-m919.bin').exists() and not (empty / 'm919/build/obsolete.txt').exists()
    ps('remove empty owned build root', 'Remove-Item -LiteralPath ' + quote(empty / 'build'))
    ps('create build ancestor junction', 'New-Item -ItemType Junction -Path ' + quote(empty / 'build') + ' -Target ' + quote(outside) + ' | Out-Null')
    ps('build ancestor junction rejects before port deletion', '& ' + quote(empty / SCRIPTS[0]), error='Reparse')
    assert (outside / 'sentinel.txt').is_file() and (empty / 'm919/build/baios-m919.bin').is_file()
    ps('remove owned ancestor junction', 'Remove-Item -LiteralPath ' + quote(empty / 'build') + ' -Force')
    direct_port_checks(fixture, outside)
    (RESULTS / 'build-cleanup-checks.json').write_text(json.dumps({'cases': CASES,
        'source_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in SCRIPTS},
        'retained': list(retained), 'obsolete': list(obsolete)}, indent=2))
    # Dispose only this verified owned fixture, after every terminal oracle.
    ps('dispose owned fixture', '. ' + quote(ROOT / SCRIPTS[1]) + '; $target=Assert-OwnedPath ' + quote(fixture) + ' ' + quote(RESULTS.resolve()) + '; Remove-Item -LiteralPath $target -Recurse -Force')
    print(f'PASS {len(CASES)} actual cleanup contrasts; retained bytes unchanged; owned fixture removed')


if __name__ == '__main__':
    main()
