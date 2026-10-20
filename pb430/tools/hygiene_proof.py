"""Run the actual port retention command in a disposable fixture."""
import hashlib
import os
import shutil
import subprocess
from pathlib import Path
PORT=Path(__file__).resolve().parents[1]

def run():
    root=PORT/'build/test-results/build-hygiene/fixture'
    port=root/'pb430';build=port/'build'
    for folder in (port/'tools',root/'shared/tools',build):folder.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(PORT/'tools/clean-build.ps1',port/'tools/clean-build.ps1')
    shutil.copyfile(PORT.parent/'shared/tools/build-cleanup.ps1',root/'shared/tools/build-cleanup.ps1')
    for name in ('task-checkout','deps','diagnostics','final-display','final-cache','obsolete-vm','test-results/complete/vm','test-results/complete/roms','test-results/failed/vm'):
        target=build/name;target.mkdir(parents=True,exist_ok=True);(target/'input.bin').write_bytes(b'fixture')
    current=build/'baios-pb430.bin';current.write_bytes((PORT/'build/baios-pb430.bin').read_bytes())
    saved=hashlib.sha256(current.read_bytes()).hexdigest()
    (build/'test-results/failed/.retain-diagnosis').write_text('current failure')
    (build/'test-results/complete/cells.bin').write_bytes(b'current capture')
    script=port/'tools/clean-build.ps1'
    def command(*extra,expected=0):
        result=subprocess.run(['powershell','-NoProfile','-File',str(script),*extra],capture_output=True,text=True)
        assert result.returncode==expected,(result.returncode,result.stdout,result.stderr)
        return result
    dry=command('-WhatIf');assert 'obsolete-vm' in dry.stdout and 'complete' in dry.stdout
    assert (build/'obsolete-vm').exists() and (build/'test-results/complete/vm').exists()
    command()
    assert not (build/'obsolete-vm').exists() and not (build/'test-results/complete/vm').exists()
    for name in ('task-checkout','deps','diagnostics','final-display','final-cache','test-results/failed/vm','test-results/complete/cells.bin'):
        assert (build/name).exists(),name
    assert (build/'final-cache/input.bin').read_bytes()==b'fixture'
    assert hashlib.sha256(current.read_bytes()).hexdigest()==saved
    # A consumed diagnosis marker reopens disposal; no source/current capture is removed.
    (build/'test-results/failed/.retain-diagnosis').unlink();command();assert not (build/'test-results/failed/vm').exists()
    command();assert hashlib.sha256(current.read_bytes()).hexdigest()==saved
    # The real emulator process must block even dry-run cleanup.
    emulator=PORT/'build/deps/86box-b10408/86Box.exe'
    vm=root/'guard-vm';roms=root/'guard-roms';vm.mkdir(exist_ok=True);roms.mkdir(exist_ok=True)
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=0
    process=subprocess.Popen([str(emulator),'-P',str(vm),'-R',str(roms),'-N'],cwd=vm,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        refused=command('-WhatIf',expected=1)
        assert 'An emulator is running' in refused.stderr and current.exists()
    finally:
        process.kill();process.wait()
    # Reparse descendants must be rejected even for WhatIf.
    junction=build/'obsolete-junction';junction.mkdir(exist_ok=True)
    link=junction/'link'
    owned_target=root/'junction-target';owned_target.mkdir(exist_ok=True)
    sentinel=owned_target/'sentinel.bin';sentinel.write_bytes(b'owned target must survive')
    result=subprocess.run(['powershell','-NoProfile','-Command',f"New-Item -ItemType Junction -Path '{link}' -Target '{owned_target}' | Out-Null"],capture_output=True,text=True)
    assert result.returncode==0,result.stderr
    refused=command('-WhatIf',expected=1);assert 'Reparse child' in refused.stderr
    assert link.resolve()==owned_target.resolve() and link.lstat().st_file_attributes & 0x400
    os.rmdir(link)
    assert sentinel.read_bytes()==b'owned target must survive'
    command()
    return {'dry_run':True,'guarded_deletes':True,'running_emulator_rejected':True,'idempotent':True,'reparse_rejected':True,'owned_reparse_target_preserved':True,'diagnosis_marker_present_and_consumed':True,'protected_sha256':saved,'task_checkout_and_dependency_retained':True}
