"""
Domino piece calls in sequence - inputs/outputs are defined in workflow.paths
(Piece_Inputs / Piece_Outputs under tests/).
"""
from __future__ import annotations

import logging
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from . import paths as P
from .user_input import load_workflow_user_input, materialize_optional_configs

logger = logging.getLogger(__name__)


def _write_piece_json(out_dir: Path, filename: str, payload: Any) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / filename).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _apply_runtime_constraints_from_predictions(constraints: dict[str, Any]) -> dict[str, Any]:
    """
    Fill runtime values from predictions_15min.csv:
    - annual_load_mwh from prediction_load_kw (if available).
    """
    out = dict(constraints or {})
    pred_path = P.PREDICTIONS_CSV
    if not pred_path.is_file():
        return out

    try:
        pred = pd.read_csv(pred_path)
    except Exception as exc:
        logger.warning("Failed to load predictions (%s): %s", pred_path, exc)
        return out

    if "prediction_load_kw" in pred.columns:
        load_kw = pd.to_numeric(pred["prediction_load_kw"], errors="coerce").dropna()
        if not load_kw.empty:
            annual_load_mwh = float(load_kw.sum() * 0.25 / 1000.0)
            out["annual_load_mwh"] = round(annual_load_mwh, 3)
            logger.info("annual_load_mwh computed from predictions: %.3f MWh", out["annual_load_mwh"])

    return out


def _apply_runtime_economics_from_prices(economics: dict[str, Any]) -> dict[str, Any]:
    """
    Fill electricity.price_eur_per_kwh from internal data:
    1) primary: tests/FetchEnergyDataPiece_Inputs/prices.csv
    2) fallback: tests/PredictPiece_Outputs/predictions_15min.csv (price_* column).
    """
    out = dict(economics or {})
    elec = dict(out.get("electricity") or {})

    avg_price_kwh: float | None = None
    try:
        price_inputs = _find_csv(P.IN_FETCH, "price")
    except FileNotFoundError:
        price_inputs = None
    if price_inputs and price_inputs.is_file():
        try:
            prices = pd.read_csv(price_inputs)
            if "price_eur_kwh" in prices.columns:
                s = pd.to_numeric(prices["price_eur_kwh"], errors="coerce").dropna()
                if not s.empty:
                    avg_price_kwh = float(s.mean())
            elif "price_eur_mwh" in prices.columns:
                s = pd.to_numeric(prices["price_eur_mwh"], errors="coerce").dropna()
                if not s.empty:
                    avg_price_kwh = float(s.mean()) / 1000.0
        except Exception as exc:
            logger.warning("Failed to load prices from inputs (%s): %s", price_inputs, exc)

    if avg_price_kwh is None and P.PREDICTIONS_CSV.is_file():
        try:
            pred = pd.read_csv(P.PREDICTIONS_CSV)
            if "price_eur_kwh" in pred.columns:
                s = pd.to_numeric(pred["price_eur_kwh"], errors="coerce").dropna()
                if not s.empty:
                    avg_price_kwh = float(s.mean())
            elif "price_eur_mwh" in pred.columns:
                s = pd.to_numeric(pred["price_eur_mwh"], errors="coerce").dropna()
                if not s.empty:
                    avg_price_kwh = float(s.mean()) / 1000.0
        except Exception as exc:
            logger.warning("Failed to load prices from predictions (%s): %s", P.PREDICTIONS_CSV, exc)

    if avg_price_kwh is not None:
        elec["price_eur_per_kwh"] = round(avg_price_kwh, 6)
        out["electricity"] = elec
        logger.info("price_eur_per_kwh computed from data: %.6f EUR/kWh", elec["price_eur_per_kwh"])

    return out


def _find_csv(dir_path: Path, name_part: str) -> Path:
    name_part = name_part.lower()
    for p in sorted(dir_path.glob("*.csv")):
        if name_part in p.name.lower():
            return p
    raise FileNotFoundError(f"No CSV containing {name_part!r} in {dir_path}")


def _find_csv_optional(dir_path: Path, name_part: str) -> Path | None:
    try:
        return _find_csv(dir_path, name_part)
    except FileNotFoundError:
        return None


def _predictions_to_load_csv(target_csv: Path) -> Path:
    """Create load_csv expected by MRK pieces from predictions output."""
    if not P.PREDICTIONS_CSV.is_file():
        raise FileNotFoundError(f"Predictions CSV missing: {P.PREDICTIONS_CSV}")
    df = pd.read_csv(P.PREDICTIONS_CSV, parse_dates=["datetime"])
    if "prediction_load_kw" not in df.columns:
        raise ValueError("predictions_15min.csv must contain prediction_load_kw")
    if "price_eur_kwh" in df.columns:
        price = pd.to_numeric(df["price_eur_kwh"], errors="coerce")
    elif "price_eur_per_kwh" in df.columns:
        price = pd.to_numeric(df["price_eur_per_kwh"], errors="coerce")
    elif "price_eur_mwh" in df.columns:
        price = pd.to_numeric(df["price_eur_mwh"], errors="coerce") / 1000.0
    else:
        raise ValueError(
            "predictions_15min.csv must contain one of: price_eur_kwh, price_eur_per_kwh, price_eur_mwh"
        )
    out = pd.DataFrame(
        {
            "datetime": pd.to_datetime(df["datetime"]),
            "load_kw": pd.to_numeric(df["prediction_load_kw"], errors="coerce").fillna(0.0),
            "price_eur_per_kwh": price,
        }
    )
    out["price_eur_per_kwh"] = out["price_eur_per_kwh"].interpolate(limit_direction="both")
    if out["price_eur_per_kwh"].isna().all():
        raise ValueError("All price values in predictions are NaN after normalization")
    target_csv.parent.mkdir(parents=True, exist_ok=True)
    out.to_csv(target_csv, index=False)
    return target_csv


def step_fetch() -> None:
    from pieces.FetchEnergyDataPiece.models import InputModel as FetchInput
    from pieces.FetchEnergyDataPiece.piece import FetchEnergyDataPiece

    P.OUT_FETCH.mkdir(parents=True, exist_ok=True)
    load_csv = P.IN_FETCH
    prices_csv = _find_csv_optional(P.IN_FETCH, "price")

    piece = FetchEnergyDataPiece.__new__(FetchEnergyDataPiece)
    piece.results_path = str(P.OUT_FETCH)
    piece.piece_function(
        FetchInput(
            load_csv=str(load_csv),
            prices_csv=str(prices_csv or ""),
        )
    )


def step_preprocess() -> None:
    from pieces.PreprocessEnergyDataPiece.models import InputModel as PreprocessInput
    from pieces.PreprocessEnergyDataPiece.piece import PreprocessEnergyDataPiece

    P.OUT_PREPROCESS.mkdir(parents=True, exist_ok=True)
    piece = PreprocessEnergyDataPiece.__new__(PreprocessEnergyDataPiece)
    piece.results_path = str(P.OUT_PREPROCESS)
    piece.piece_function(
        PreprocessInput(input_path=str(P.MERGED_PARQUET), generate_predict_dataset=False)
    )


def step_train() -> None:
    from pieces.TrainModelPiece.models import InputModel as TrainInput
    from pieces.TrainModelPiece.piece import TrainModelPiece

    P.OUT_TRAIN.mkdir(parents=True, exist_ok=True)
    df = pd.read_parquet(P.TRAIN_PARQUET)
    if "department_id" not in df.columns:
        piece = TrainModelPiece.__new__(TrainModelPiece)
        piece.results_path = str(P.OUT_TRAIN)
        piece.piece_function(TrainInput(data_path=str(P.TRAIN_PARQUET)))
        return

    model_map: dict[str, str] = {}
    for dept, g in df.groupby("department_id"):
        dept_id = str(dept)
        dept_dir = P.OUT_TRAIN / dept_id
        dept_dir.mkdir(parents=True, exist_ok=True)
        in_path = dept_dir / "train_dataset.parquet"
        g.drop(columns=["department_id"]).to_parquet(in_path, index=False)

        piece = TrainModelPiece.__new__(TrainModelPiece)
        piece.results_path = str(dept_dir)
        piece.piece_function(TrainInput(data_path=str(in_path)))
        model_map[dept_id] = str(dept_dir / "xgboost_model.pkl")

    _write_piece_json(P.OUT_TRAIN, "models_by_department.json", model_map)


def _ensure_planned_csv() -> Path:
    r = subprocess.run([sys.executable, str(P.GEN_SCRIPT)], cwd=str(P.PROJECT_ROOT))
    if r.returncode != 0:
        raise RuntimeError("generate_predict_planned_csv.py zlyhal")
    if not P.PLANNED_CSV.exists():
        raise FileNotFoundError(P.PLANNED_CSV)
    return P.PLANNED_CSV


def step_predict() -> None:
    from pieces.PredictPiece.models import InputModel as PredictInput
    from pieces.PredictPiece.piece import PredictPiece

    planned = _ensure_planned_csv()
    P.OUT_PREDICT.mkdir(parents=True, exist_ok=True)
    plan_df = pd.read_csv(planned, parse_dates=["datetime"])
    if "department_id" not in plan_df.columns:
        piece = PredictPiece.__new__(PredictPiece)
        piece.results_path = str(P.OUT_PREDICT)
        piece.piece_function(
            PredictInput(
                model_path=str(P.MODEL_PKL),
                data_path=str(planned),
                use_rolling_prediction=True,
            )
        )
        return

    pred_parts: list[pd.DataFrame] = []
    for dept, g in plan_df.groupby("department_id"):
        dept_id = str(dept)
        dept_model = P.OUT_TRAIN / dept_id / "xgboost_model.pkl"
        if not dept_model.is_file():
            raise FileNotFoundError(f"Model for department '{dept_id}' not found: {dept_model}")
        dept_dir = P.OUT_PREDICT / dept_id
        dept_dir.mkdir(parents=True, exist_ok=True)
        in_path = dept_dir / "predict_input.csv"
        g.drop(columns=["department_id"]).to_csv(in_path, index=False)

        piece = PredictPiece.__new__(PredictPiece)
        piece.results_path = str(dept_dir)
        piece.piece_function(
            PredictInput(
                model_path=str(dept_model),
                data_path=str(in_path),
                use_rolling_prediction=True,
            )
        )
        out_path = dept_dir / "predictions_15min.csv"
        ddf = pd.read_csv(out_path, parse_dates=["datetime"])
        ddf["department_id"] = dept_id
        pred_parts.append(ddf)

    all_pred = pd.concat(pred_parts, ignore_index=True)
    all_pred.to_csv(P.OUT_PREDICT / "predictions_by_department.csv", index=False)

    agg_map: dict[str, str] = {"prediction_load_kw": "sum"}
    if "price_eur_kwh" in all_pred.columns:
        agg_map["price_eur_kwh"] = "mean"
    if "price_eur_mwh" in all_pred.columns:
        agg_map["price_eur_mwh"] = "mean"
    if "load_kw" in all_pred.columns:
        agg_map["load_kw"] = "sum"
    merged = all_pred.groupby("datetime", as_index=False).agg(agg_map).sort_values("datetime")
    merged.to_csv(P.PREDICTIONS_CSV, index=False)


def step_model_monitoring() -> None:
    from pieces.ModelMonitoringPiece.models import InputModel as MonitoringInput
    from pieces.ModelMonitoringPiece.piece import ModelMonitoringPiece

    P.OUT_MODEL_MONITORING.mkdir(parents=True, exist_ok=True)
    by_dept_path = P.OUT_PREDICT / "predictions_by_department.csv"
    if by_dept_path.is_file():
        df = pd.read_csv(by_dept_path)
        for dept, g in df.groupby("department_id"):
            dept_id = str(dept)
            dept_dir = P.OUT_MODEL_MONITORING / dept_id
            dept_dir.mkdir(parents=True, exist_ok=True)
            src = dept_dir / "predictions_15min.csv"
            g.drop(columns=["department_id"]).to_csv(src, index=False)
            piece = ModelMonitoringPiece.__new__(ModelMonitoringPiece)
            piece.results_path = str(dept_dir)
            piece.piece_function(MonitoringInput(predictions_csv=str(src)))
    piece = ModelMonitoringPiece.__new__(ModelMonitoringPiece)
    piece.results_path = str(P.OUT_MODEL_MONITORING)
    piece.piece_function(MonitoringInput(predictions_csv=str(P.PREDICTIONS_CSV)))


def _find_solar_weather() -> Path:
    csv_files = sorted(P.IN_SOLAR.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV found in {P.IN_SOLAR}")
    for p in csv_files:
        if "solargis" in p.name.lower() and "2025" in p.name:
            return p
    for p in csv_files:
        if "solargis" in p.name.lower():
            return p
    return csv_files[0]


def _find_solar_config() -> Path:
    if P.GENERATED_SOLAR_CONFIG_YML.is_file():
        return P.GENERATED_SOLAR_CONFIG_YML
    for pat in ("*.yml", "*.yaml"):
        ymls = list(P.IN_SOLAR.glob(pat))
        if ymls:
            return ymls[0]
    default_cfg = P.PROJECT_ROOT / "pieces" / "SolarSimPiece" / "solar_config.yml"
    if default_cfg.is_file():
        return default_cfg
    raise FileNotFoundError("solar_config.yml (expected tests/_generated/solar_config.yml after materialize)")


def step_solar() -> None:
    from pieces.SolarSimPiece.models import InputModel as SolarInput
    from pieces.SolarSimPiece.piece import SolarSimPiece

    P.OUT_SOLAR.mkdir(parents=True, exist_ok=True)
    load_csv = _predictions_to_load_csv(P.GENERATED_DIR / "runtime_load_for_sim.csv")
    scenario_path, _ = _ensure_generated_battery_files()
    piece = SolarSimPiece.__new__(SolarSimPiece)
    piece.results_path = str(P.OUT_SOLAR)
    piece.piece_function(SolarInput(load_csv=str(load_csv), scenario_yaml=str(scenario_path)))


def _ensure_generated_battery_files() -> tuple[Path, Path]:
    """
    Ensure generated battery/scenario YAMLs exist (tests/_generated/).
    Returns: (scenario_yml, battery_config_yml)
    """
    P.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    scenario_path = P.GENERATED_SCENARIO_YML
    battery_cfg_path = P.GENERATED_BATTERY_CONFIG_YML

    scenario: dict[str, Any] = {}
    if scenario_path.is_file():
        with open(scenario_path, encoding="utf-8") as f:
            scenario = yaml.safe_load(f) or {}
    if P.USER_SCENARIO_YML.is_file():
        with open(P.USER_SCENARIO_YML, encoding="utf-8") as f:
            user_tpl = yaml.safe_load(f) or {}
        if user_tpl:
            from .user_input import _deep_merge

            scenario = _deep_merge(user_tpl, scenario)
    template_scenario = P.IN_BATTERY / "scenario.yml"
    if not scenario and template_scenario.is_file():
        with open(template_scenario, encoding="utf-8") as f:
            scenario = yaml.safe_load(f) or {}

    # Fill defaults if missing.
    scenario.setdefault("scenario_id", "runtime")
    scenario.setdefault("description", "Auto-generated runtime scenario")
    scenario.setdefault("solar", {})
    scenario.setdefault("battery", {})
    scenario.setdefault("strategy", {})
    scenario.setdefault("time_window", {})
    scenario.setdefault("apply_monthly", True)

    scenario["solar"].setdefault("capacity_kWp", 0.0)
    scenario["battery"].setdefault("capacity_kWh", 0.0)
    scenario["battery"].setdefault("charge_efficiency", 0.95)
    scenario["battery"].setdefault("discharge_efficiency", 0.95)
    scenario["battery"].setdefault("max_c_rate", 0.5)
    scenario["strategy"].setdefault("charge_from", "solar_excess")
    scenario["strategy"].setdefault("discharge_during", "peak_hours")
    tw = scenario["time_window"]
    if not isinstance(tw, dict):
        tw = {}
    tw.setdefault("peak_hours", {"start": "08:00", "end": "18:00"})
    scenario["time_window"] = tw

    battery_cfg: dict[str, Any] = {}
    if battery_cfg_path.is_file():
        with open(battery_cfg_path, encoding="utf-8") as f:
            battery_cfg = yaml.safe_load(f) or {}
    template_cfg = P.IN_BATTERY / "battery_config.yml"
    if not battery_cfg and template_cfg.is_file():
        with open(template_cfg, encoding="utf-8") as f:
            battery_cfg = yaml.safe_load(f) or {}
    battery_cfg.setdefault("capacity_kWh", scenario["battery"].get("capacity_kWh", 0.0))
    battery_cfg.setdefault("charge_efficiency", scenario["battery"].get("charge_efficiency", 0.95))
    battery_cfg.setdefault("discharge_efficiency", scenario["battery"].get("discharge_efficiency", 0.95))
    battery_cfg.setdefault("max_c_rate", scenario["battery"].get("max_c_rate", 0.5))
    battery_cfg.setdefault("initial_soc", 50)

    with open(scenario_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(scenario, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    with open(battery_cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(battery_cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return scenario_path, battery_cfg_path


def step_battery() -> None:
    from pieces.BatterySimPiece.models import InputModel as BatteryInput
    from pieces.BatterySimPiece.piece import BatterySimPiece

    load_csv = _predictions_to_load_csv(P.GENERATED_DIR / "runtime_load_for_sim.csv")
    solar_path = P.VIRTUAL_SOLAR_CSV
    scenario_path, battery_config = _ensure_generated_battery_files()
    _ = battery_config

    P.OUT_BATTERY.mkdir(parents=True, exist_ok=True)
    piece = BatterySimPiece.__new__(BatterySimPiece)
    piece.results_path = str(P.OUT_BATTERY)
    piece.piece_function(
        BatteryInput(
            load_csv=str(load_csv),
            scenario_yaml=str(scenario_path),
            virtual_solar_csv=str(solar_path),
        )
    )


def step_battery_strategy() -> None:
    from pieces.BatteryStrategyOptimizerPiece.models import InputModel as StrategyInput
    from pieces.BatteryStrategyOptimizerPiece.piece import BatteryStrategyOptimizerPiece

    scenario_path, _ = _ensure_generated_battery_files()
    load_csv = _predictions_to_load_csv(P.GENERATED_DIR / "runtime_load_for_sim.csv")
    P.OUT_BATTERY_STRATEGY.mkdir(parents=True, exist_ok=True)
    piece = BatteryStrategyOptimizerPiece.__new__(BatteryStrategyOptimizerPiece)
    piece.results_path = str(P.OUT_BATTERY_STRATEGY)
    piece.piece_function(StrategyInput(load_csv=str(load_csv), scenario_yaml=str(scenario_path)))


def step_simulate() -> None:
    P.STAGING_SIM.mkdir(parents=True, exist_ok=True)
    load_csv = _predictions_to_load_csv(P.STAGING_SIM / "load_for_sim.csv")
    shutil.copy2(P.VIRTUAL_SOLAR_CSV, P.STAGING_SIM / "virtual_solar.csv")
    shutil.copy2(P.VIRTUAL_BATTERY_SOC_CSV, P.STAGING_SIM / "virtual_battery_soc.csv")
    battery_summary_csv = P.OUT_BATTERY / "battery_summary.csv"
    scenario, _ = _ensure_generated_battery_files()
    shutil.copy2(scenario, P.STAGING_SIM / "scenario.yml")

    from pieces.SimulatePiece.models import InputModel as SimulateInput
    from pieces.SimulatePiece.piece import SimulatePiece

    P.OUT_SIMULATE.mkdir(parents=True, exist_ok=True)
    piece = SimulatePiece.__new__(SimulatePiece)
    piece.results_path = str(P.OUT_SIMULATE)
    strategy_json = P.OUT_BATTERY_STRATEGY / "battery_strategy_recommendation.json"
    piece.piece_function(
        SimulateInput(
            load_csv=str(load_csv),
            scenario_yaml=str(P.STAGING_SIM / "scenario.yml"),
            output_dir=str(P.OUT_SIMULATE),
            virtual_battery_soc_csv=str(P.STAGING_SIM / "virtual_battery_soc.csv"),
            battery_summary_csv=str(battery_summary_csv) if battery_summary_csv.is_file() else "",
            battery_strategy_recommendation_json=str(strategy_json) if strategy_json.is_file() else "",
        )
    )


def step_kpi() -> None:
    from pieces.KPIPiece.models import InputModel as KPIInput
    from pieces.KPIPiece.piece import KPIPiece

    P.OUT_KPI.mkdir(parents=True, exist_ok=True)
    piece = KPIPiece.__new__(KPIPiece)
    piece.results_path = str(P.OUT_KPI)
    piece.piece_function(KPIInput(report_json=str(P.OUT_SIMULATE / "mrk_savings_report.json")))


def _find_investment_config() -> Path:
    if P.GENERATED_INVESTMENT_CONFIG_YML.is_file():
        return P.GENERATED_INVESTMENT_CONFIG_YML
    ymls = list(P.IN_INVESTMENT_EVAL.glob("*.yml")) + list(P.IN_INVESTMENT_EVAL.glob("*.yaml"))
    if not ymls:
        raise FileNotFoundError(
            f"investment_config not found: expected {P.GENERATED_INVESTMENT_CONFIG_YML} or YAML under {P.IN_INVESTMENT_EVAL}"
        )
    return ymls[0]


def step_investment_eval() -> None:
    from pieces.InvestmentEvalPiece.models import InputModel as InvestmentInput
    from pieces.InvestmentEvalPiece.piece import InvestmentEvalPiece

    P.OUT_INVESTMENT_EVAL.mkdir(parents=True, exist_ok=True)
    piece = InvestmentEvalPiece.__new__(InvestmentEvalPiece)
    piece.results_path = str(P.OUT_INVESTMENT_EVAL)
    piece.piece_function(
        InvestmentInput(
            report_json=str(P.OUT_SIMULATE / "mrk_savings_report.json"),
            kpi_results_csv=str(P.KPI_RESULTS_CSV),
        )
    )


def step_domino_dashboard() -> None:
    from pieces.DashboardPiece.models import InputModel as DashboardInput
    from pieces.DashboardPiece.piece import DashboardPiece

    P.OUT_TIMESERIES.mkdir(parents=True, exist_ok=True)
    piece = DashboardPiece.__new__(DashboardPiece)
    piece.results_path = str(P.OUT_TIMESERIES)
    if getattr(piece, "logger", None) is None:
        piece.logger = logging.getLogger("DashboardPiece")

    piece.piece_function(
        DashboardInput(
            report_json=str(P.OUT_SIMULATE / "mrk_savings_report.json"),
            kpi_results_csv=str(P.KPI_RESULTS_CSV),
            investment_evaluation_csv=str(P.INVESTMENT_EVAL_CSV),
            anomaly_alerts_csv=str(P.OUT_ANOMALY_ALERT / "anomaly_alerts.csv"),
            drift_report_json=str(P.OUT_ANOMALY_ALERT / "drift_report.json"),
        )
    )


def _resolve_sizing_input_sources(use_predictions: bool) -> tuple[str, str]:
    if use_predictions:
        load_csv = _predictions_to_load_csv(P.GENERATED_DIR / "runtime_load_for_sizing.csv")
        return str(load_csv), ""
    if P.MERGED_PARQUET.is_file():
        df = pd.read_parquet(P.MERGED_PARQUET)
        if "datetime" in df.columns and "load_kw" in df.columns:
            out = pd.DataFrame(
                {
                    "datetime": pd.to_datetime(df["datetime"]),
                    "load_kw": pd.to_numeric(df["load_kw"], errors="coerce").fillna(0.0),
                }
            )
            if "price_eur_kwh" in df.columns:
                out["price_eur_per_kwh"] = pd.to_numeric(df["price_eur_kwh"], errors="coerce")
            elif "price_eur_mwh" in df.columns:
                out["price_eur_per_kwh"] = pd.to_numeric(df["price_eur_mwh"], errors="coerce") / 1000.0
            else:
                out["price_eur_per_kwh"] = pd.NA
            out = out.groupby("datetime", as_index=False).agg({"load_kw": "sum", "price_eur_per_kwh": "mean"})
            out["price_eur_per_kwh"] = pd.to_numeric(out["price_eur_per_kwh"], errors="coerce")
            out["price_eur_per_kwh"] = out["price_eur_per_kwh"].interpolate(limit_direction="both").ffill().bfill()
            if out["price_eur_per_kwh"].isna().all():
                out["price_eur_per_kwh"] = 0.1
            target = P.GENERATED_DIR / "runtime_load_for_sizing_from_merged.csv"
            target.parent.mkdir(parents=True, exist_ok=True)
            out.to_csv(target, index=False)
            return str(target), ""
    load_csv = _find_csv(P.IN_FETCH, "load")
    prices_csv = _find_csv_optional(P.IN_FETCH, "price")
    return str(load_csv), str(prices_csv or "")


def run_user_input_step(
    scenario_path: Path,
    load_csv: str,
    prices_csv: str,
    *,
    input_mode: str,
) -> Any:
    """Classic UserInputPiece (CSV) or WebUserInputPiece (saved web form)."""
    from workflow.input_modes import INPUT_MODE_WEB

    if input_mode == INPUT_MODE_WEB:
        from pieces.WebUserInputPiece.models import InputModel as WebIn
        from pieces.WebUserInputPiece.piece import WebUserInputPiece

        if not P.WEB_FORM_STATE_JSON.is_file():
            raise FileNotFoundError(
                f"Web input mode requires {P.WEB_FORM_STATE_JSON}. "
                "Run: streamlit run scripts/streamlit_web_input.py and save the form."
            )
        piece = WebUserInputPiece.__new__(WebUserInputPiece)
        piece.results_path = str(P.OUT_USER_INPUT)
        return piece.piece_function(
            WebIn(
                web_form_state_json=str(P.WEB_FORM_STATE_JSON),
                scenario_yaml=str(scenario_path),
                use_classic_csv_fallback=True,
            )
        )

    from pieces.UserInputPiece.models import InputModel as UIInput
    from pieces.UserInputPiece.piece import UserInputPiece

    ui = UserInputPiece.__new__(UserInputPiece)
    ui.results_path = str(P.OUT_USER_INPUT)
    return ui.piece_function(
        UIInput(load_csv=str(load_csv), prices_csv=str(prices_csv or ""), scenario_yaml=str(scenario_path))
    )


def run_sizing(
    root: Path | None = None,
    *,
    use_predictions: bool = True,
    input_mode: str | None = None,
):
    """UserInput/WebUserInput -> TechnicalLimits -> SizingOptimization. Returns (szo, constraints, economics)."""
    from workflow.input_modes import DEFAULT_INPUT_MODE

    root = root or P.PROJECT_ROOT
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    mode = input_mode or DEFAULT_INPUT_MODE
    from pieces.SizingOptimizationPiece.models import InputModel as SZInput
    from pieces.SizingOptimizationPiece.piece import SizingOptimizationPiece
    from pieces.TechnicalLimitsPiece.models import InputModel as TLInput
    from pieces.TechnicalLimitsPiece.piece import TechnicalLimitsPiece
    from types import SimpleNamespace

    project_options, constraints, economics, extras = load_workflow_user_input()
    materialize_optional_configs(extras)

    runtime_constraints = _apply_runtime_constraints_from_predictions(constraints)
    runtime_economics = _apply_runtime_economics_from_prices(economics)
    scenario_path, _ = _ensure_generated_battery_files()
    load_csv, prices_csv = _resolve_sizing_input_sources(use_predictions=use_predictions)

    ui_out = run_user_input_step(
        scenario_path,
        str(load_csv),
        str(prices_csv or ""),
        input_mode=mode,
    )
    _write_piece_json(P.OUT_USER_INPUT, "user_input_output.json", ui_out.model_dump())

    tl_input = TLInput(load_csv=str(ui_out.load_csv), scenario_yaml=str(ui_out.scenario_yaml))
    _write_piece_json(P.IN_TECHNICAL_LIMITS, "technical_limits_input.json", tl_input.model_dump())
    tl = TechnicalLimitsPiece.__new__(TechnicalLimitsPiece)
    tl.results_path = str(P.OUT_TECHNICAL_LIMITS)
    tlo = tl.piece_function(tl_input)
    _write_piece_json(P.OUT_TECHNICAL_LIMITS, "technical_limits_output.json", tlo.model_dump())

    sz_input = SZInput(
        load_csv=str(ui_out.load_csv),
        scenario_yaml=str(ui_out.scenario_yaml),
        technical_limits_json=str(tlo.technical_limits_json),
    )
    _write_piece_json(P.IN_SIZING_OPT, "sizing_optimization_input.json", sz_input.model_dump())
    sz = SizingOptimizationPiece.__new__(SizingOptimizationPiece)
    sz.results_path = str(P.OUT_SIZING_OPT)
    szo_raw = sz.piece_function(sz_input)
    _write_piece_json(P.OUT_SIZING_OPT, "sizing_optimization_output.json", szo_raw.model_dump())

    sized_cfg = yaml.safe_load(Path(szo_raw.sized_scenario_yaml).read_text(encoding="utf-8")) or {}
    best_kwp = float(((sized_cfg.get("pv") or {}).get("installed_kwp") or 0.0))
    best_kwh = float(((sized_cfg.get("battery") or {}).get("energy_kwh") or 0.0))
    pv_cfg = runtime_economics.get("solar") or runtime_economics.get("pv") or {}
    bt_cfg = runtime_economics.get("battery") or {}
    eur_kwp = float(pv_cfg.get("eur_per_kwp", pv_cfg.get("specific_capex_eur_per_kwp", 800.0)))
    eur_kwh = float(bt_cfg.get("eur_per_kwh", bt_cfg.get("specific_capex_eur_per_kwh", 400.0)))
    best_capex = best_kwp * eur_kwp + best_kwh * eur_kwh
    auto_log = {}
    try:
        auto_log = json.loads(Path(szo_raw.sizing_optimization_json).read_text(encoding="utf-8")).get("auto_optimization") or {}
    except Exception:
        auto_log = {}
    szo = SimpleNamespace(
        best_kwp=best_kwp,
        best_kwh=best_kwh,
        best_payback_years=float(auto_log.get("best_payback_years", -1.0)) if auto_log else -1.0,
        best_annual_savings_eur=float(auto_log.get("best_annual_savings_eur", 0.0)) if auto_log else 0.0,
        best_capex_eur=best_capex,
        best_npv_eur=float(auto_log.get("best_npv_eur", 0.0)) if auto_log else 0.0,
        grid=list(auto_log.get("grid", [])) if isinstance(auto_log, dict) else [],
    )
    return szo, runtime_constraints, runtime_economics


def apply_sizing_to_scenario_and_investment_yaml(
    szo: Any,
    constraints: dict[str, Any],
    economics: dict[str, Any],
) -> None:
    """
    Write chosen kWp/kWh capacities to tests/_generated/scenario.yml and solar_config.yml,
    and CAPEX values to tests/_generated/investment_config.yml (for InvestmentEvalPiece).
    """
    kwp = float(szo.best_kwp)
    kwh = float(szo.best_kwh)
    solar = economics.get("solar") or {}
    batt = economics.get("battery") or {}
    eur_kwp = float(solar.get("eur_per_kwp", solar.get("specific_capex_eur_per_kwp", 800.0)))
    eur_kwh = float(batt.get("eur_per_kwh", batt.get("specific_capex_eur_per_kwh", 400.0)))
    solar_capex = kwp * eur_kwp
    battery_capex = kwh * eur_kwh

    scenario_path, battery_cfg_path = _ensure_generated_battery_files()
    with open(scenario_path, encoding="utf-8") as f:
        scen = yaml.safe_load(f) or {}
    scen.setdefault("solar", {})["capacity_kWp"] = kwp
    scen.setdefault("pv", {})["installed_kwp"] = kwp
    scen.setdefault("battery", {})["capacity_kWh"] = kwh
    scen.setdefault("battery", {})["energy_kwh"] = kwh
    scen["description"] = (
        f"Workflow proposal: {kwp:.0f} kWp + {kwh:.0f} kWh "
        f"(model payback {szo.best_payback_years:.2f} years)"
    )
    with open(scenario_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(scen, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    with open(battery_cfg_path, encoding="utf-8") as f:
        bcfg = yaml.safe_load(f) or {}
    bcfg["capacity_kWh"] = kwh
    with open(battery_cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(bcfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    solar_cfg_path = P.GENERATED_SOLAR_CONFIG_YML
    scfg: dict[str, Any] = {}
    if solar_cfg_path.is_file():
        with open(solar_cfg_path, encoding="utf-8") as f:
            scfg = yaml.safe_load(f) or {}
    scfg["capacity_kWp"] = kwp
    P.GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    with open(solar_cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(scfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    inv_path = P.GENERATED_INVESTMENT_CONFIG_YML
    inv_cfg: dict[str, Any] = {}
    if inv_path.is_file():
        with open(inv_path, encoding="utf-8") as f:
            inv_cfg = yaml.safe_load(f) or {}
    inv_cfg["solar_capex_eur"] = round(solar_capex, 2)
    inv_cfg["battery_capex_eur"] = round(battery_capex, 2)
    inv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(inv_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(inv_cfg, f, allow_unicode=True, sort_keys=False, default_flow_style=False)

    logger.info(
        "Updated: tests/_generated scenario + solar_config + investment_config "
        "(%.0f kWp, %.0f kWh, PV CAPEX %.0f EUR, BESS CAPEX %.0f EUR)",
        kwp,
        kwh,
        solar_capex,
        battery_capex,
    )


def _load_investment_eval_metrics() -> dict[str, Any] | None:
    """Row from InvestmentEvalPiece (available only after KPI in full pipeline)."""
    p = P.INVESTMENT_EVAL_CSV
    if not p.is_file():
        return None
    df = pd.read_csv(p)
    if df.empty:
        return None
    r = df.iloc[0]

    def _f(key: str, default: float = 0.0) -> float:
        v = r.get(key)
        if v is None or (isinstance(v, float) and pd.isna(v)):
            return default
        try:
            return float(v)
        except (TypeError, ValueError):
            return default

    cyc = r.get("battery_cycles_est")
    cyc_out: float | None
    if cyc is None or (isinstance(cyc, float) and pd.isna(cyc)):
        cyc_out = None
    else:
        try:
            cyc_out = float(cyc)
        except (TypeError, ValueError):
            cyc_out = None

    return {
        "annual_savings_eur": _f("annual_savings_eur"),
        "simple_payback_years": _f("simple_payback_years", 999.0),
        "npv_eur": _f("npv_eur"),
        "total_capex_eur": _f("total_capex_eur"),
        "solar_capex_eur": _f("solar_capex_eur"),
        "battery_capex_eur": _f("battery_capex_eur"),
        "solar_lcoe_eur_per_mwh": _f("solar_lcoe_eur_per_mwh"),
        "annual_co2_saved_ton": _f("annual_co2_saved_ton"),
        "battery_cycles_est": cyc_out,
    }


def step_feasibility_report(
    root: Path,
    constraints: dict[str, Any],
    economics: dict[str, Any],
    szo: Any,
    *,
    use_simulation_outputs: bool = False,
) -> None:
    """FeasibilityReportPiece - panel/battery catalog and dashboard JSON (after KPI/Investment)."""
    del constraints, economics, szo
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    from pieces.FeasibilityReportPiece.models import InputModel as FRInput
    from pieces.FeasibilityReportPiece.piece import FeasibilityReportPiece

    investment_eval_csv = str(P.INVESTMENT_EVAL_CSV) if use_simulation_outputs else ""
    if use_simulation_outputs:
        sim_metrics = _load_investment_eval_metrics()
        if sim_metrics is None:
            logger.warning(
                "use_simulation_outputs=True but %s is missing - feasibility remains parametric.",
                P.INVESTMENT_EVAL_CSV,
            )
            investment_eval_csv = ""

    fr = FeasibilityReportPiece.__new__(FeasibilityReportPiece)
    fr.results_path = str(P.OUT_FEASIBILITY)
    fr_input = FRInput(
        workflow_user_input_json=str(P.OUT_USER_INPUT / "workflow_user_input.json"),
        sized_scenario_yaml=str(P.OUT_SIZING_OPT / "scenario_sized.yaml"),
        sizing_optimization_json=str(P.OUT_SIZING_OPT / "sizing_optimization.json"),
        investment_evaluation_csv=investment_eval_csv,
    )
    _write_piece_json(P.IN_FEASIBILITY, "feasibility_report_input.json", fr_input.model_dump())
    fr.piece_function(fr_input)


def step_sustainable_ingest() -> str:
    from pieces.SustainableIngestPiece.models import InputModel as IngestInput
    from pieces.SustainableIngestPiece.piece import SustainableIngestPiece

    P.OUT_SUSTAINABLE_INGEST.mkdir(parents=True, exist_ok=True)
    piece = SustainableIngestPiece.__new__(SustainableIngestPiece)
    piece.results_path = str(P.OUT_SUSTAINABLE_INGEST)
    out = piece.piece_function(
        IngestInput(
            history_csv=str(P.SUSTAINABLE_HISTORY_CSV),
            updates_dir=str(P.SUSTAINABLE_UPDATES_DIR),
            archive_dir=str(P.SUSTAINABLE_ARCHIVE_DIR),
            bootstrap_parquet=str(P.SUSTAINABLE_BOOTSTRAP_PARQUET),
        )
    )
    return out.history_csv_out


def step_incremental_train(history_csv: str) -> str:
    from pieces.IncrementalTrainPiece.models import InputModel as TrainInput
    from pieces.IncrementalTrainPiece.piece import IncrementalTrainPiece

    P.OUT_INCREMENTAL_TRAIN.mkdir(parents=True, exist_ok=True)
    piece = IncrementalTrainPiece.__new__(IncrementalTrainPiece)
    piece.results_path = str(P.OUT_INCREMENTAL_TRAIN)
    out = piece.piece_function(
        TrainInput(
            history_csv=history_csv,
            model_registry_dir=str(P.SUSTAINABLE_MODEL_REGISTRY_DIR),
            incremental_window_days=30,
            full_retrain_every_n_updates=20,
            incremental_trees=50,
        )
    )
    return out.models_index_json


def step_forecast_horizon(history_csv: str, models_index_json: str, horizon_hours: int = 24) -> str:
    from pieces.ForecastHorizonPiece.models import InputModel as ForecastInput
    from pieces.ForecastHorizonPiece.piece import ForecastHorizonPiece

    P.OUT_FORECAST_HORIZON.mkdir(parents=True, exist_ok=True)
    piece = ForecastHorizonPiece.__new__(ForecastHorizonPiece)
    piece.results_path = str(P.OUT_FORECAST_HORIZON)
    out = piece.piece_function(
        ForecastInput(
            history_csv=history_csv,
            models_index_json=models_index_json,
            model_registry_dir=str(P.SUSTAINABLE_MODEL_REGISTRY_DIR),
            horizon_hours=int(horizon_hours),
        )
    )
    return out.forecast_csv


def step_anomaly_alerts(history_csv: str, models_index_json: str, lookback_rows: int = 672, z_threshold: float = 3.5) -> str:
    from pieces.AnomalyAlertPiece.models import InputModel as AlertInput
    from pieces.AnomalyAlertPiece.piece import AnomalyAlertPiece

    P.OUT_ANOMALY_ALERT.mkdir(parents=True, exist_ok=True)
    piece = AnomalyAlertPiece.__new__(AnomalyAlertPiece)
    piece.results_path = str(P.OUT_ANOMALY_ALERT)
    out = piece.piece_function(
        AlertInput(
            history_csv=history_csv,
            models_index_json=models_index_json,
            model_registry_dir=str(P.SUSTAINABLE_MODEL_REGISTRY_DIR),
            lookback_rows=int(lookback_rows),
            z_threshold=float(z_threshold),
            min_abs_delta_kw=2.0,
            cooldown_minutes=60,
            warn_kw_threshold=10.0,
            critical_kw_threshold=25.0,
        )
    )
    try:
        alerts_df = pd.read_csv(out.alerts_csv)
        sev_counts = alerts_df.get("severity", pd.Series([], dtype=str)).value_counts().to_dict()
        logger.warning("Anomaly alerts generated: %s", sev_counts)
    except Exception:
        logger.warning("Anomaly alerts generated: unable to summarize severities")
    return out.alerts_csv
