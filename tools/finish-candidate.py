"""Finish a recorded build without rebuilding or changing its firmware bytes."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared.tools.candidates import finish, record

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('port')
    parser.add_argument('--directory', type=Path)
    parser.add_argument('--record', nargs='+', type=Path, help='Builder-only: record the verified assembly outputs.')
    parser.add_argument('--version', help='Builder-only: version used by the assembly.')
    args = parser.parse_args()
    if args.record and not args.version:
        parser.error('--record requires the version used by the assembly')
    port = (ROOT/args.port).resolve()
    if port.parent != ROOT or not (port/'src/bios.asm').is_file():
        parser.error('Select one port directory')
    data = record(port,args.record,args.version) if args.record else finish(port,args.directory)
    print(json.dumps(data,indent=2))
