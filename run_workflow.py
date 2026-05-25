"""
Alternate - unified workflow (time-series simulation + investment proposal).

  python run_workflow.py
  python run_workflow.py --phase timeseries
  python run_workflow.py --phase investment

Outputs: tests/ (Piece_*) and merged dashboard: tests/dashboard_data.json
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflow.orchestrator import main

if __name__ == "__main__":
    raise SystemExit(main())
