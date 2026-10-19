from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.tools.inspect_vhd import Vhd, chs, main

if __name__ == "__main__":
    main()
