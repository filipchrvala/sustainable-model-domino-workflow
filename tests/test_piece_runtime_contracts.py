from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pieces.PredictPiece.models import InputModel as PredictInput
from pieces.PredictPiece.piece import PredictPiece
from pieces.TrainModelPiece.models import InputModel as TrainInput
from pieces.TrainModelPiece.piece import TrainModelPiece
from pieces.UserInputPiece.models import InputModel as UserInput
from pieces.UserInputPiece.piece import UserInputPiece
from pieces.DashboardPiece.models import InputModel as DashboardInput
from pieces.DashboardPiece.piece import DashboardPiece


def test_user_input_piece_finds_workflow_json_next_to_inputs(tmp_path: Path) -> None:
    base = tmp_path / "shared"
    base.mkdir()
    load_csv = base / "load.csv"
    prices_csv = base / "prices.csv"
    scenario_yaml = base / "scenario.yaml"
    workflow_json = base / "workflow_user_input.json"

    load_csv.write_text(
        "\n".join(
            [
                "datetime,load_kw",
                "2025-01-01 00:00:00,10",
                "2025-01-01 00:15:00,11",
                "2025-01-01 00:30:00,12",
                "2025-01-01 00:45:00,13",
            ]
        ),
        encoding="utf-8",
    )
    prices_csv.write_text(
        "\n".join(
            [
                "datetime,price_eur_per_kwh",
                "2025-01-01 00:00:00,0.10",
                "2025-01-01 00:15:00,0.11",
                "2025-01-01 00:30:00,0.12",
                "2025-01-01 00:45:00,0.13",
            ]
        ),
        encoding="utf-8",
    )
    scenario_yaml.write_text("timestep_minutes: 15\nproduction:\n  gap_repair_enabled: true\n", encoding="utf-8")
    workflow_json.write_text('{"format":"workflow_user_input_v1"}', encoding="utf-8")

    piece = UserInputPiece.__new__(UserInputPiece)
    piece.results_path = str(tmp_path / "out")
    out = piece.piece_function(
        UserInput(load_csv=str(load_csv), prices_csv=str(prices_csv), scenario_yaml=str(scenario_yaml))
    )

    copied = Path(out.workflow_user_input_json)
    assert copied.is_file()
    assert json.loads(copied.read_text(encoding="utf-8"))["format"] == "workflow_user_input_v1"


def test_train_and_predict_support_multi_department_inputs(tmp_path: Path) -> None:
    datetimes = pd.date_range("2025-01-01 00:00:00", periods=800, freq="15min")
    rows: list[dict[str, float | str]] = []
    for dept, offset in (("A", 20.0), ("B", 55.0)):
        for idx, ts in enumerate(datetimes):
            daily_wave = 8.0 * np.sin(2.0 * np.pi * (idx % 96) / 96.0)
            weekly_wave = 3.0 * np.cos(2.0 * np.pi * (idx % (96 * 7)) / (96 * 7))
            rows.append(
                {
                    "datetime": ts,
                    "department_id": dept,
                    "load_kw": offset + daily_wave + weekly_wave,
                    "price_eur_per_kwh": 0.08 + 0.01 * ((idx % 96) / 96.0),
                }
            )
    train_df = pd.DataFrame(rows)
    train_path = tmp_path / "train_dataset.parquet"
    train_df.to_parquet(train_path, index=False)

    train_piece = TrainModelPiece.__new__(TrainModelPiece)
    train_piece.results_path = str(tmp_path / "train")
    train_out = train_piece.piece_function(TrainInput(data_path=str(train_path)))
    model_path = Path(train_out.model_file_path)
    assert model_path.is_file()

    predict_df = train_df.groupby("department_id", group_keys=False).tail(64).reset_index(drop=True)
    predict_path = tmp_path / "predict.csv"
    predict_df.to_csv(predict_path, index=False)

    predict_piece = PredictPiece.__new__(PredictPiece)
    predict_piece.results_path = str(tmp_path / "predict")
    predict_out = predict_piece.piece_function(
        PredictInput(model_path=str(model_path), data_path=str(predict_path), use_rolling_prediction=True, bridge_rows=4)
    )

    pred_df = pd.read_csv(predict_out.prediction_file_path)
    assert "prediction_load_kw" in pred_df.columns
    assert "department_id" in pred_df.columns
    assert set(pred_df["department_id"]) == {"A", "B"}
    assert pred_df["prediction_load_kw"].notna().all()


def test_predict_piece_generates_missing_planned_csv_from_load(tmp_path: Path) -> None:
    datetimes = pd.date_range("2025-01-01 00:00:00", periods=800, freq="15min")
    train_df = pd.DataFrame(
        {
            "datetime": datetimes,
            "load_kw": 40.0 + 5.0 * np.sin(2.0 * np.pi * np.arange(len(datetimes)) / 96.0),
            "price_eur_per_kwh": 0.08 + 0.01 * ((np.arange(len(datetimes)) % 96) / 96.0),
        }
    )
    train_path = tmp_path / "train_dataset.parquet"
    train_df.to_parquet(train_path, index=False)

    train_piece = TrainModelPiece.__new__(TrainModelPiece)
    train_piece.results_path = str(tmp_path / "train")
    train_out = train_piece.piece_function(TrainInput(data_path=str(train_path)))

    shared_dir = tmp_path / "shared"
    shared_dir.mkdir()
    load_input = shared_dir / "load.csv"
    train_df[["datetime", "load_kw"]].to_csv(load_input, index=False)
    missing_predict_path = shared_dir / "predict_planned_load_halfyear.csv"

    predict_piece = PredictPiece.__new__(PredictPiece)
    predict_piece.results_path = str(tmp_path / "predict")
    predict_out = predict_piece.piece_function(
        PredictInput(model_path=train_out.model_file_path, data_path=str(missing_predict_path), use_rolling_prediction=True)
    )

    assert missing_predict_path.is_file()
    pred_df = pd.read_csv(predict_out.prediction_file_path)
    assert "prediction_load_kw" in pred_df.columns
    assert len(pred_df) > 4


def test_dashboard_piece_accepts_empty_alerts_csv(tmp_path: Path) -> None:
    report_path = tmp_path / "report.json"
    kpi_path = tmp_path / "kpi.csv"
    investment_path = tmp_path / "investment.csv"
    alerts_path = tmp_path / "anomaly_alerts.csv"
    drift_path = tmp_path / "drift.json"

    report_path.write_text(
        json.dumps(
            {
                "meta": {"schema_version": "mrk_report_v2"},
                "executive_summary": {
                    "operating_cost_baseline_eur": 1000.0,
                    "operating_cost_pv_battery_eur": 800.0,
                    "operating_savings_eur_period": 200.0,
                    "operating_savings_eur_per_year_estimate": 2400.0,
                },
                "mrk_and_rv": {},
                "uncertainty_assessment": {},
                "artifacts": {},
            }
        ),
        encoding="utf-8",
    )
    kpi_path.write_text("metric,value\nkpi,1\n", encoding="utf-8")
    investment_path.write_text(
        "annual_savings_eur,total_capex_eur,simple_payback_years,discounted_payback_years,npv_operating_eur\n200,5000,5,6,1000\n",
        encoding="utf-8",
    )
    alerts_path.write_text("", encoding="utf-8")
    drift_path.write_text("{}", encoding="utf-8")

    piece = DashboardPiece.__new__(DashboardPiece)
    piece.results_path = str(tmp_path / "dashboard")
    out = piece.piece_function(
        DashboardInput(
            report_json=str(report_path),
            kpi_results_csv=str(kpi_path),
            investment_evaluation_csv=str(investment_path),
            anomaly_alerts_csv=str(alerts_path),
            drift_report_json=str(drift_path),
        )
    )

    payload = json.loads(Path(out.dashboard_data_json).read_text(encoding="utf-8"))
    assert payload["alerts_and_drift"]["summary"]["total"] == 0
