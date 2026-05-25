"""Spustenie pipeline s callbackom pre Streamlit progress bar."""
from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

from . import paths as P
from . import steps
from .input_modes import DEFAULT_INPUT_MODE
from .live_refresh import run_operational_refresh

ProgressCallback = Callable[[int, int, str], None]


def run_full_pipeline_with_progress(
    root: Path | None = None,
    *,
    input_mode: str = DEFAULT_INPUT_MODE,
    on_progress: ProgressCallback | None = None,
    horizon_hours: int = 24,
) -> None:
    root = root or P.PROJECT_ROOT
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    total = 18
    n = 0

    def tick(label: str) -> None:
        nonlocal n
        n += 1
        if on_progress:
            on_progress(n, total, label)

    tick("1/18 Načítanie dát (Fetch)")
    steps.step_fetch()
    tick("2/18 Predspracovanie dát")
    steps.step_preprocess()
    tick("3/18 Tréning modelov")
    steps.step_train()
    tick("4/18 Predikcia spotreby")
    steps.step_predict()
    tick("5/18 Monitoring modelov")
    steps.step_model_monitoring()

    tick("6/18 Web vstup, technické limity a sizing")
    szo, constraints, economics = steps.run_sizing(root, input_mode=input_mode)
    tick("7/18 Zápis scenára a CAPEX")
    steps.apply_sizing_to_scenario_and_investment_yaml(szo, constraints, economics)

    tick("8/18 Simulácia FVE")
    steps.step_solar()
    tick("9/18 Stratégia batérie")
    steps.step_battery_strategy()
    tick("10/18 Simulácia batérie")
    steps.step_battery()
    tick("11/18 MRK simulácia (SimulatePiece)")
    steps.step_simulate()

    tick("12/18 KPI")
    steps.step_kpi()
    tick("13/18 Investičné hodnotenie")
    steps.step_investment_eval()

    tick("14/18 Feasibility report")
    steps.step_feasibility_report(root, constraints, economics, szo, use_simulation_outputs=True)

    tick("15/18 Sustainable ingest")
    history_csv = steps.step_sustainable_ingest()
    tick("16/18 Inkrementálny tréning")
    models_index_json = steps.step_incremental_train(history_csv)
    tick("17/18 Forecast horizont")
    steps.step_forecast_horizon(history_csv, models_index_json, horizon_hours=horizon_hours)
    tick("18/18 Alerty a dashboard JSON")
    steps.step_anomaly_alerts(history_csv, models_index_json, lookback_rows=672, z_threshold=3.5)
    from .live_refresh import refresh_dashboard_after_alerts

    refresh_dashboard_after_alerts(include_timeseries=True)
