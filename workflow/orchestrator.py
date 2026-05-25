"""
Single linear program:

  1) load prediction (Fetch -> Train -> Predict)
  2) PV + battery sizing + write scenario.yml / solar_config / CAPEX
  3) PV production and battery behavior simulation (Solar -> Battery -> Simulate)
  4) KPI + InvestmentEval (based on simulation)
  5) FeasibilityReport (hardware catalog, CFO JSON) + merged dashboard
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import paths as P
from . import steps
from .input_modes import DEFAULT_INPUT_MODE, INPUT_MODES
from .live_refresh import run_operational_refresh

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


def merge_unified_dashboard(root: Path | None = None, *, include_timeseries: bool = True) -> Path:
    root = root or P.PROJECT_ROOT
    inv_path = P.OUT_INVESTMENT / "dashboard_data.json"
    ts_path = P.OUT_TIMESERIES / "dashboard_data.json"
    unified: dict = {
        "format": "alternate_unified_v1",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    if inv_path.is_file():
        unified["investment"] = json.loads(inv_path.read_text(encoding="utf-8"))
    if include_timeseries and ts_path.is_file():
        unified["timeseries"] = json.loads(ts_path.read_text(encoding="utf-8"))
    P.OUTPUTS.mkdir(parents=True, exist_ok=True)
    P.UNIFIED_DASHBOARD_JSON.write_text(
        json.dumps(unified, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    logger.info("Merged dashboard: %s", P.UNIFIED_DASHBOARD_JSON)
    return P.UNIFIED_DASHBOARD_JSON


def run_full_pipeline(root: Path | None = None, *, input_mode: str = DEFAULT_INPUT_MODE) -> None:
    """Run the complete workflow once."""
    from .progress_runner import run_full_pipeline_with_progress

    run_full_pipeline_with_progress(root, input_mode=input_mode)


def run_investment_phase_only(root: Path | None = None, *, input_mode: str = DEFAULT_INPUT_MODE) -> None:
    """Run sizing + YAML update + feasibility only (no prediction/simulation)."""
    root = root or P.PROJECT_ROOT
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    logger.info("=== PV + battery sizing (without time-series simulation) ===")
    szo, constraints, economics = steps.run_sizing(root, use_predictions=False, input_mode=input_mode)
    steps.apply_sizing_to_scenario_and_investment_yaml(szo, constraints, economics)
    steps.step_feasibility_report(root, constraints, economics, szo, use_simulation_outputs=False)


def main(argv: list[str] | None = None) -> int:
    root = P.PROJECT_ROOT
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    parser = argparse.ArgumentParser(
        description="Alternate: prediction -> PV/BESS sizing -> simulation -> KPI -> investment",
    )
    parser.add_argument(
        "--phase",
        choices=("all", "investment", "sustainable"),
        default="all",
        help="all = complete program; investment = only kWp/kWh sizing + YAML + feasibility; sustainable = ingest/train/forecast/alerts",
    )
    parser.add_argument(
        "--horizon-hours",
        type=int,
        default=24,
        help="Forecast horizon for sustainable phase.",
    )
    parser.add_argument(
        "--input-mode",
        choices=INPUT_MODES,
        default=DEFAULT_INPUT_MODE,
        help="csv = UserInputPiece + CSV files; web = WebUserInputPiece (Streamlit form state)",
    )
    args = parser.parse_args(argv)

    if args.phase == "all":
        run_full_pipeline(root, input_mode=args.input_mode)
        print("\n" + "=" * 60 + "\n  Done. Dashboard: tests/dashboard_data.json\n" + "=" * 60)
        print("  Streamlit: streamlit run scripts/streamlit_dashboard.py")
        print("  Live mode: .\\run_live_dashboard.ps1")
        return 0
    elif args.phase == "sustainable":
        logger.info("=== Sustainable phase only ===")
        run_operational_refresh(
            horizon_hours=args.horizon_hours,
            refresh_dashboard=True,
            include_timeseries=True,
        )
        return 0
    else:
        run_investment_phase_only(root, input_mode=args.input_mode)
        include_timeseries = False

    merge_unified_dashboard(root, include_timeseries=include_timeseries)

    print("\n" + "=" * 60 + "\n  Done. Dashboard: tests/dashboard_data.json\n" + "=" * 60)
    print("  Streamlit: streamlit run scripts/streamlit_dashboard.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
