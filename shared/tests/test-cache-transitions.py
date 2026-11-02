"""Common cache lifecycle entry point; controller models remain port-owned."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from shared.tools.cache_proof import main

if __name__ == '__main__':
    main()
