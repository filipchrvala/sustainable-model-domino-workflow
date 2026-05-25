#!/usr/bin/env python3
"""CLI wrapper for workflow.live_refresh (watch drop folder or one-shot refresh)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.live_refresh import main

if __name__ == "__main__":
    raise SystemExit(main())
