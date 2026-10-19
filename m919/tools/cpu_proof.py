"""Compose the shared CPU proof with this port's actual rendering owners."""
import json
from pathlib import Path
import sys
PORT=Path(__file__).resolve().parents[1]
REPOSITORY=PORT.parent
sys.path.insert(0,str(REPOSITORY))
from shared.tools.rom import build,configuration
from shared.tools.ram_proof import constants
from shared.tools.cpu_proof import check


def run():
    result=build(PORT,'build/hardware-tests/cpu')
    _,cfg=configuration(PORT)
    state=constants(REPOSITORY/'shared/src/pc/state.inc')
    state.update(constants(REPOSITORY/'shared/src/setup/layout.inc'))
    rows=check(Path(result['path']),cfg['rom'],state)
    path=PORT/'build/hardware-research/cpu-proof.json';path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps({'image':result,'cases':rows},indent=2)+'\n')
    print(f'CPU primary identities, guards, full state and actual render: {len(rows)} PASS',flush=True)
    return path
