#!/usr/bin/env python3
"""Root convenience entry point for the DWSIM HAZOP Bridge pipeline."""
import sys
from pathlib import Path

# Ensure src/ directory is on sys.path
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from hazop_bridge.run_full_pipeline import main

if __name__ == "__main__":
    sys.exit(main())
