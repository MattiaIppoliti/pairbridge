#!/usr/bin/env python3
"""Run PairBridge from a source checkout, without installing a Python package."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from pairbridge.cli import main
if __name__ == "__main__":
    raise SystemExit(main())
