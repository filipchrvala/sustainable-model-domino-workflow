"""
Inputs/outputs are stored directly in ``Alternate/tests/`` using the same
structure as industry_sg_vre (Piece_Inputs / Piece_Outputs).
Module and battery catalogs are in ``Alternate/catalog/*.json``.
"""
from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TESTS_DIR = PROJECT_ROOT / "tests"
CATALOG_DIR = PROJECT_ROOT / "catalog"

# User-edited only (never overwritten by the orchestrator).
USER_INPUT_DIR = TESTS_DIR / "user_input"
WORKFLOW_USER_INPUT_JSON = USER_INPUT_DIR / "workflow_user_input.json"
USER_SCENARIO_YML = USER_INPUT_DIR / "scenario.yaml"

# Web form (Streamlit) – parallel to classic CSV / JSON editing.
IN_WEB_USER_INPUT = TESTS_DIR / "WebUserInputPiece_Input"
OUT_WEB_USER_INPUT = TESTS_DIR / "WebUserInputPiece_Output"
WEB_FORM_STATE_JSON = IN_WEB_USER_INPUT / "web_form_state.json"
WEB_UPLOAD_LOAD_CSV = IN_WEB_USER_INPUT / "uploaded_load.csv"
WEB_UPLOAD_PRICES_CSV = IN_WEB_USER_INPUT / "uploaded_prices.csv"
WEB_APPEND_DROP_CSV = IN_WEB_USER_INPUT / "pending_append_to_drop.csv"

# Orchestrator-generated YAML (merged from workflow_user_input.json + sizing); not user-edited.
GENERATED_DIR = TESTS_DIR / "_generated"
GENERATED_SOLAR_CONFIG_YML = GENERATED_DIR / "solar_config.yml"
GENERATED_INVESTMENT_CONFIG_YML = GENERATED_DIR / "investment_config.yml"
GENERATED_SCENARIO_YML = GENERATED_DIR / "scenario.yml"
GENERATED_BATTERY_CONFIG_YML = GENERATED_DIR / "battery_config.yml"

# --- Inputs (directly under tests/) ---
IN_FETCH = TESTS_DIR / "FetchEnergyDataPiece_Inputs"
IN_PREDICT = TESTS_DIR / "PredictPiece_Inputs"
IN_SOLAR = TESTS_DIR / "SolarSimPiece_Inputs"
IN_BATTERY = TESTS_DIR / "BatterySimPiece_Inputs"
IN_INVESTMENT_EVAL = TESTS_DIR / "InvestmentEvalPiece_Inputs"
IN_USER_INPUT = TESTS_DIR / "UserInputPiece_Input"
IN_TECHNICAL_LIMITS = TESTS_DIR / "TechnicalLimitsPiece_Input"
IN_SIZING_OPT = TESTS_DIR / "SizingOptimizationPiece_Input"
IN_FEASIBILITY = TESTS_DIR / "FeasibilityReportPiece_Input"

# --- Outputs (directly under tests/) ---
OUT_FETCH = TESTS_DIR / "FetchEnergyDataPiece_Outputs"
OUT_PREPROCESS = TESTS_DIR / "PreprocessEnergyDataPiece_Outputs"
OUT_TRAIN = TESTS_DIR / "TrainModelPiece_Outputs"
OUT_PREDICT = TESTS_DIR / "PredictPiece_Outputs"
OUT_SOLAR = TESTS_DIR / "SolarSimPiece_Outputs"
OUT_BATTERY = TESTS_DIR / "BatterySimPiece_Outputs"
OUT_SIMULATE = TESTS_DIR / "SimulatePiece_Outputs"
OUT_KPI = TESTS_DIR / "KPIPiece_Outputs"
OUT_INVESTMENT_EVAL = TESTS_DIR / "InvestmentEvalPiece_Outputs"
OUT_FEASIBILITY = TESTS_DIR / "FeasibilityReportPiece_Outputs"
OUT_DASHBOARD = TESTS_DIR / "DashboardPiece_Outputs"
OUT_USER_INPUT = TESTS_DIR / "UserInputPiece_Output"
OUT_TECHNICAL_LIMITS = TESTS_DIR / "TechnicalLimitsPiece_Output"
OUT_SIZING_OPT = TESTS_DIR / "SizingOptimizationPiece_Output"
OUT_MODEL_MONITORING = TESTS_DIR / "ModelMonitoringPiece_Outputs"
OUT_BATTERY_STRATEGY = TESTS_DIR / "BatteryStrategyOptimizerPiece_Outputs"
OUT_SUSTAINABLE_INGEST = TESTS_DIR / "SustainableIngestPiece_Outputs"
OUT_INCREMENTAL_TRAIN = TESTS_DIR / "IncrementalTrainPiece_Outputs"
OUT_FORECAST_HORIZON = TESTS_DIR / "ForecastHorizonPiece_Outputs"
OUT_ANOMALY_ALERT = TESTS_DIR / "AnomalyAlertPiece_Outputs"

STAGING = TESTS_DIR / "_staging"
STAGING_SIM = STAGING / "simulate"
STAGING_KPI = STAGING / "kpi"

MERGED_PARQUET = OUT_FETCH / "merged_energy_data.parquet"
TRAIN_PARQUET = OUT_PREPROCESS / "train_dataset.parquet"
MODEL_PKL = OUT_TRAIN / "xgboost_model.pkl"
PREDICTIONS_CSV = OUT_PREDICT / "predictions_15min.csv"
VIRTUAL_SOLAR_CSV = OUT_SOLAR / "virtual_solar.csv"
VIRTUAL_BATTERY_SOC_CSV = OUT_BATTERY / "virtual_battery_soc.csv"
BATTERY_SUMMARY_CSV = OUT_BATTERY / "battery_summary.csv"
SIMULATED_RESULTS_CSV = OUT_SIMULATE / "simulated_results.csv"
SUMMARY_CSV = OUT_SIMULATE / "summary.csv"
KPI_RESULTS_CSV = OUT_KPI / "kpi_results.csv"
INVESTMENT_EVAL_CSV = OUT_INVESTMENT_EVAL / "investment_evaluation.csv"

PLANNED_CSV = IN_PREDICT / "predict_planned_load_halfyear.csv"
GEN_SCRIPT = PROJECT_ROOT / "scripts" / "generate_predict_planned_csv.py"

UNIFIED_DASHBOARD_JSON = TESTS_DIR / "dashboard_data.json"

OUT_INVESTMENT = OUT_FEASIBILITY
OUT_TIMESERIES = OUT_DASHBOARD

# Backward compatibility (legacy names)
DATA_DIR = TESTS_DIR
INPUTS = TESTS_DIR
OUTPUTS = TESTS_DIR

SUSTAINABLE_DIR = TESTS_DIR / "sustainable"
SUSTAINABLE_HISTORY_CSV = SUSTAINABLE_DIR / "history" / "energy_history.csv"
SUSTAINABLE_UPDATES_DIR = SUSTAINABLE_DIR / "company_drop"
SUSTAINABLE_ARCHIVE_DIR = SUSTAINABLE_DIR / "company_archive"
SUSTAINABLE_MODEL_REGISTRY_DIR = SUSTAINABLE_DIR / "model_registry"
SUSTAINABLE_BOOTSTRAP_PARQUET = OUT_FETCH / "merged_energy_data.parquet"
