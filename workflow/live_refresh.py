"""
Operational refresh: ingest new CSVs → train → forecast → alerts → rebuild dashboard JSON.

Used by:
  - run_workflow.py --phase sustainable (and end of full pipeline)
  - scripts/dashboard_live.py (watch drop folder while Streamlit runs)
"""
from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

from . import paths as P
from . import steps

logger = logging.getLogger(__name__)


def run_operational_refresh(
    *,
    horizon_hours: int = 24,
    lookback_rows: int = 672,
    z_threshold: float = 3.5,
    refresh_dashboard: bool = True,
    include_timeseries: bool = True,
) -> dict[str, str]:
    """
    Ingest updates, retrain incrementally, forecast, anomaly alerts.
    Optionally rebuild timeseries dashboard + tests/dashboard_data.json.
    """
    history_csv = steps.step_sustainable_ingest()
    models_index_json = steps.step_incremental_train(history_csv)
    forecast_csv = steps.step_forecast_horizon(
        history_csv, models_index_json, horizon_hours=int(horizon_hours)
    )
    alerts_csv = steps.step_anomaly_alerts(
        history_csv,
        models_index_json,
        lookback_rows=int(lookback_rows),
        z_threshold=float(z_threshold),
    )
    if refresh_dashboard:
        refresh_dashboard_after_alerts(include_timeseries=include_timeseries)
    return {
        "history_csv": history_csv,
        "models_index_json": models_index_json,
        "forecast_csv": forecast_csv,
        "alerts_csv": alerts_csv,
    }


def refresh_dashboard_after_alerts(*, include_timeseries: bool = True) -> None:
    """Rebuild DashboardPiece JSON (with latest alerts) and merge unified dashboard."""
    report = P.OUT_SIMULATE / "mrk_savings_report.json"
    if include_timeseries and report.is_file() and P.KPI_RESULTS_CSV.is_file():
        steps.step_domino_dashboard()
    else:
        logger.info(
            "Skipping timeseries dashboard rebuild (simulation outputs missing); "
            "merging investment + any existing timeseries JSON."
        )
    from .orchestrator import merge_unified_dashboard

    merge_unified_dashboard(include_timeseries=include_timeseries)


def _drop_folder_signature() -> float:
    """Latest mtime among files in company_drop (0 if empty)."""
    drop = P.SUSTAINABLE_UPDATES_DIR
    if not drop.is_dir():
        return 0.0
    mtimes = [p.stat().st_mtime for p in drop.iterdir() if p.is_file()]
    return max(mtimes) if mtimes else 0.0


def watch_and_refresh(
    *,
    poll_seconds: int = 60,
    horizon_hours: int = 24,
    lookback_rows: int = 672,
    z_threshold: float = 3.5,
    run_once: bool = False,
) -> None:
    """
    Poll company_drop for new CSV files; on change run operational refresh.
    """
    P.SUSTAINABLE_UPDATES_DIR.mkdir(parents=True, exist_ok=True)
    last_sig = _drop_folder_signature()
    logger.info("Watching %s (poll every %ss)", P.SUSTAINABLE_UPDATES_DIR, poll_seconds)

    while True:
        sig = _drop_folder_signature()
        if sig > last_sig or (run_once and last_sig == 0 and sig == 0):
            if sig > last_sig:
                logger.info("New file(s) detected in company_drop — refreshing data and alerts")
            elif run_once:
                logger.info("Running one operational refresh cycle")
            run_operational_refresh(
                horizon_hours=horizon_hours,
                lookback_rows=lookback_rows,
                z_threshold=z_threshold,
            )
            last_sig = max(sig, _drop_folder_signature())
        if run_once:
            break
        time.sleep(max(5, int(poll_seconds)))


def main(argv: list[str] | None = None) -> int:
    import argparse

    root = P.PROJECT_ROOT
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(description="Refresh forecasts, alerts, and dashboard JSON")
    parser.add_argument("--once", action="store_true", help="Single refresh cycle (no watch loop)")
    parser.add_argument("--watch", action="store_true", help="Poll company_drop until interrupted")
    parser.add_argument("--poll-seconds", type=int, default=60)
    parser.add_argument("--horizon-hours", type=int, default=24)
    parser.add_argument("--lookback-rows", type=int, default=672)
    parser.add_argument("--z-threshold", type=float, default=3.5)
    parser.add_argument(
        "--dashboard-only",
        action="store_true",
        help="Rebuild dashboard from existing outputs (no ingest/train)",
    )
    args = parser.parse_args(argv)

    if args.dashboard_only:
        refresh_dashboard_after_alerts(include_timeseries=True)
        return 0

    if args.watch:
        watch_and_refresh(
            poll_seconds=args.poll_seconds,
            horizon_hours=args.horizon_hours,
            lookback_rows=args.lookback_rows,
            z_threshold=args.z_threshold,
            run_once=False,
        )
        return 0

    if args.once:
        logger.info("Single operational refresh")
        run_operational_refresh(
            horizon_hours=args.horizon_hours,
            lookback_rows=args.lookback_rows,
            z_threshold=args.z_threshold,
        )
        return 0

    run_operational_refresh(
        horizon_hours=args.horizon_hours,
        lookback_rows=args.lookback_rows,
        z_threshold=args.z_threshold,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
