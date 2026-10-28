import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.tools.rom import build
from shared.tools.candidates import record

parser = argparse.ArgumentParser(description='Assemble and pack a configured firmware port.')
parser.add_argument('port', type=Path)
parser.add_argument('--output', default='build')
arguments = parser.parse_args()
result = build(arguments.port, arguments.output)
record(arguments.port, [Path(result['path'])], result['identity']['version'])
print(json.dumps(result, indent=2))
