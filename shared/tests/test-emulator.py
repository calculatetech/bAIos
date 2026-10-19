"""Check that test launches cannot reuse an obsolete saved flash image."""
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.tools.emulator import run_86box

with tempfile.TemporaryDirectory(dir=sys.argv[1]) as folder:
    vm = Path(folder)
    (vm / 'nvr').mkdir()
    (vm / '86box.cfg').write_text('[Machine]\nmachine = testboard\n')
    flash = vm / 'nvr/testboard.bin'
    cmos = vm / 'nvr/testboard.nvr'
    other = vm / 'nvr/other.bin'
    flash.write_bytes(b'obsolete firmware')
    cmos.write_bytes(b'accepted settings')
    other.write_bytes(b'unrelated device')
    with patch('shared.tools.emulator.subprocess.Popen') as process:
        process.return_value.wait.return_value = 103
        assert run_86box(vm, vm, executable='test-emulator') == 103
        assert not flash.exists()
        assert cmos.read_bytes() == b'accepted settings'
        assert other.read_bytes() == b'unrelated device'
        assert run_86box(vm, vm, executable='test-emulator') == 103
        (vm / '86box.cfg').write_text('[Machine]\nmachine = ../../escape\n')
        before = process.call_count
        try:
            run_86box(vm, vm, executable='test-emulator')
        except ValueError:
            pass
        else:
            raise AssertionError('Outside-VM flash path was accepted')
        assert process.call_count == before
print('PASS: stale flash removed, CMOS and other devices retained, repeated launch and path boundary')
