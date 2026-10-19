import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.tools.rom import verify

parser = argparse.ArgumentParser(description='Verify the size, checksum, reset and identity of a configured ROM.')
parser.add_argument('port', type=Path)
parser.add_argument('--image', type=Path)
arguments = parser.parse_args()
print(json.dumps(verify(arguments.port, arguments.image), indent=2))
