"""Boot an AT A20 consumer that must turn the physical gate off and on."""
import argparse
import json
import os
from pathlib import Path
import subprocess
from unicorn import x86_const as x

from build import PORT
from fixture import Tiger


def check(image, expect_failure=False):
    guest = image.parent/'a20-boot.bin'
    nasm = Path(os.environ['LOCALAPPDATA'])/'bin/NASM/nasm.exe'
    subprocess.run([str(nasm), '-w+error', '-f', 'bin', '-o', str(guest),
                    str(PORT/'tests/a20-handoff.asm')], check=True)
    rows = []
    for cache in (False, True):
        m = Tiger(image, cache=cache)
        m.disk = guest.read_bytes()+bytes(512)
        gates = []
        def observe(mm, address):
            if address == 0xF0000+mm.symbol('chipset_visible_ram_test'):
                mm.pending.append(1)
            if address == 0x7C00:
                gates.append((mm.controls[0xE1], mm.kbc_output))
        m.code_observer = observe
        for warm in (False, True):
            try:
                m.boot(warm=warm, count=10000000)
            except AssertionError as error:
                assert expect_failure and error.args[0] == ('boot observer failed', '0xee'), error
                assert m.cpu.reg_read(x.UC_X86_REG_DX) >> 8 == 0
                assert m.cpu.reg_read(x.UC_X86_REG_CX) & 255 == 1
            else:
                assert not expect_failure and m.booted
            e1, kbc = gates[-1]
            assert bool(e1 & 0x20) == expect_failure
            assert m.controls[0xE1] == e1 and m.kbc_output == kbc
            assert not m.port92_accesses
            rows.append(dict(cache=cache, warm=warm, E1=e1, KBC=kbc,
                             gate_off_on=m.booted, gate_state_restored=True))
            print('PASS', rows[-1], flush=True)
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--expect-failure', action='store_true')
    args = parser.parse_args()
    result = check(args.image.resolve(), args.expect_failure)
    (args.image.parent/'a20-handoff.json').write_text(json.dumps(result, indent=2)+'\n')
