import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.tools.rom import build

parser = argparse.ArgumentParser(description='Assemble and pack a configured firmware port.')
parser.add_argument('port', type=Path)
parser.add_argument('--output', default='build')
arguments = parser.parse_args()
print(json.dumps(build(arguments.port, arguments.output), indent=2))
